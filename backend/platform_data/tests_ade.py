import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from graphql import GraphQLError

from platform_data.ade_sync import (
    KIND_DLE,
    KIND_ITW,
    KIND_LIKELIHOOD_CHECK,
    KIND_SUBCATEGORY,
    build_entries,
    parse_likelihood_test,
    parse_record_yaml,
    parse_taxonomy_markdown,
    select_ade_paths,
)
from platform_data.models import AdeEntry, AdeImportJob, AdeSnapshot, PlatformDataVersion
from platform_data.schema import (
    PromoteAdeSnapshot,
    RollbackAdeSnapshot,
    RunAdeImport,
    _activate_ade_snapshot,
    compute_ade_diff,
)
from platform_data.tasks import fail_stale_ade_jobs

# ---------------------------------------------------------------------------
# Fixtures that mimic the upstream layout (see docs/taxonomy/*.md in the ADE repo)
# ---------------------------------------------------------------------------

TAXONOMY_ADE2 = """# ADE2 - Omit Alternatives

Omit Alternatives bugs occur when a rule covers one way of doing something.

## Subcategories

### ADE2-01: Omit Alternatives - Method/Binary

**Definition:** Detection logic covers one tool while equivalent
tools are in scope.

**Common Scenarios:**
- Something

---

### ADE2-02: Omit Alternatives - Versioning

**Definition:** Logic encodes version-specific assumptions.

## Examples

### ADE2-01: Looks like a subcategory but sits outside the section

**Definition:** must be ignored.

## Detection Rule Patterns Vulnerable to ADE2

### ADE2-01 Patterns (no colon, must be ignored)
"""

LIKELIHOOD = """# Bug Likelihood Test

## Bug Likelihood Test

- [ ] Is there another method or tool in scope?

      - ADE2\u201101 \u2013 Omit Alternatives
      - Also ADE2\u201104.

- [ ] Is there another version of the OS?

      - ADE2-02 \u2013 Versioning
"""

DLE_YAML = """
id: DLE-2026-00001
bypass_description: Static substring match.
related_ade:
  - ADE2-01
schema_version: 1.0
affected_detection_logic:
  name: Use Something
  platform: Sigma
rule_version: 2023-10-27
logsource:
  product: windows
mitre_attack:
  - T1049
"""

ITW_YAML = """
id: ITW-2026-00001
title: Switch written with Unicode modifier letters
related_ade:
  - ADE2-02
schema_version: 1.0
technique_description: Attackers vary the spelling.
mitre_attack: [T1218]
"""


def _files():
    return [
        ("docs/taxonomy/ade2-omit-alternatives.md", TAXONOMY_ADE2),
        ("docs/guides/bug-likelihood-test.md", LIKELIHOOD),
        ("dle/2026/DLE-2026-00001.yaml", DLE_YAML),
        ("in-the-wild/ITW-2026-00001.yaml", ITW_YAML),
    ]


class AdeParserTests(SimpleTestCase):
    def test_taxonomy_reads_only_colon_headings_inside_subcategories_section(self):
        parsed = parse_taxonomy_markdown(TAXONOMY_ADE2, "docs/taxonomy/ade2-omit-alternatives.md")
        ids = [s["ade_id"] for s in parsed["subcategories"]]
        self.assertEqual(ids, ["ADE2-01", "ADE2-02"])
        self.assertEqual(parsed["category"]["ade_id"], "ADE2")
        self.assertEqual(parsed["category"]["title"], "Omit Alternatives")
        # Multi-line definition is joined, and stops at the next bold block.
        self.assertEqual(
            parsed["subcategories"][0]["definition"],
            "Detection logic covers one tool while equivalent tools are in scope.",
        )
        self.assertEqual(parsed["warnings"], [])

    def test_taxonomy_without_expected_layout_warns_instead_of_raising(self):
        parsed = parse_taxonomy_markdown("Just prose.\n", "docs/taxonomy/ade9.md")
        self.assertEqual(parsed["subcategories"], [])
        self.assertTrue(any("Subcategories" in w for w in parsed["warnings"]))

    def test_likelihood_normalizes_non_breaking_hyphens(self):
        parsed = parse_likelihood_test(LIKELIHOOD)
        self.assertEqual(len(parsed["checks"]), 2)
        self.assertEqual(parsed["checks"][0]["related_ade"], ["ADE2-01", "ADE2-04"])
        self.assertEqual(parsed["checks"][1]["related_ade"], ["ADE2-02"])
        self.assertEqual([c["position"] for c in parsed["checks"]], [1, 2])

    def test_record_yaml_dle_and_itw(self):
        dle = parse_record_yaml(DLE_YAML, "dle/2026/DLE-2026-00001.yaml")["record"]
        self.assertEqual(dle["kind"], KIND_DLE)
        self.assertEqual(dle["title"], "Use Something")
        self.assertEqual(dle["related_ade"], ["ADE2-01"])
        self.assertEqual(dle["mitre_attack"], ["T1049"])
        # YAML dates must survive JSONField storage.
        self.assertEqual(dle["content"]["rule_version"], "2023-10-27")
        itw = parse_record_yaml(ITW_YAML, "in-the-wild/ITW-2026-00001.yaml")["record"]
        self.assertEqual(itw["kind"], KIND_ITW)
        self.assertEqual(itw["title"], "Switch written with Unicode modifier letters")

    def test_record_yaml_bad_input_returns_warning(self):
        self.assertIsNone(parse_record_yaml("id: [unclosed", "x.yaml")["record"])
        self.assertIsNone(parse_record_yaml("- just\n- a list\n", "x.yaml")["record"])
        self.assertIsNone(parse_record_yaml("title: no id\n", "x.yaml")["record"])
        self.assertIsNone(parse_record_yaml("id: FOO-1\n", "x.yaml")["record"])

    def test_select_ade_paths(self):
        selected = select_ade_paths([
            "README.md", "docs/taxonomy/overview.md", "docs/taxonomy/ade1-x.md",
            "docs/guides/bug-likelihood-test.md", "dle/README.md", "dle/2026/DLE-1.yaml",
            "in-the-wild/ITW-1.yml", "examples/foo.yaml",
        ])
        self.assertEqual(selected, [
            "dle/2026/DLE-1.yaml", "docs/guides/bug-likelihood-test.md",
            "docs/taxonomy/ade1-x.md", "in-the-wild/ITW-1.yml",
        ])

    def test_build_entries_counts_and_cross_reference_warnings(self):
        built = build_entries(_files())
        self.assertEqual(built["counts"], {
            "CATEGORY": 1, "SUBCATEGORY": 2, "LIKELIHOOD_CHECK": 2, "DLE": 1, "ITW": 1,
        })
        # ADE2-04 is referenced by the likelihood test but not defined in the fixture.
        self.assertTrue(any("unknown ADE2-04" in w for w in built["warnings"]))
        keys = {e["entry_key"] for e in built["entries"]}
        self.assertIn("SUBCATEGORY:ADE2-01", keys)
        self.assertIn("LIKELIHOOD_CHECK:01", keys)
        self.assertTrue(all(e["source_hash"] for e in built["entries"]))

    def test_build_entries_flags_unknown_schema_version(self):
        files = _files()
        files[2] = ("dle/2026/DLE-2026-00001.yaml", DLE_YAML.replace("schema_version: 1.0", "schema_version: 2.0"))
        built = build_entries(files)
        self.assertTrue(any("unrecognized schema_version '2.0'" in w for w in built["warnings"]))

    def test_hash_changes_when_definition_changes(self):
        base = {e["entry_key"]: e["source_hash"] for e in build_entries(_files())["entries"]}
        files = _files()
        files[0] = (files[0][0], TAXONOMY_ADE2.replace("version-specific", "release-specific"))
        changed = {e["entry_key"]: e["source_hash"] for e in build_entries(files)["entries"]}
        self.assertNotEqual(base["SUBCATEGORY:ADE2-02"], changed["SUBCATEGORY:ADE2-02"])
        self.assertEqual(base["SUBCATEGORY:ADE2-01"], changed["SUBCATEGORY:ADE2-01"])


def _write_local_repo(root: Path, taxonomy: str = TAXONOMY_ADE2):
    (root / "docs/taxonomy").mkdir(parents=True)
    (root / "docs/guides").mkdir(parents=True)
    (root / "dle/2026").mkdir(parents=True)
    (root / "in-the-wild").mkdir(parents=True)
    (root / "docs/taxonomy/ade2-omit-alternatives.md").write_text(taxonomy, encoding="utf-8")
    (root / "docs/guides/bug-likelihood-test.md").write_text(LIKELIHOOD, encoding="utf-8")
    (root / "dle/2026/DLE-2026-00001.yaml").write_text(DLE_YAML, encoding="utf-8")
    (root / "in-the-wild/ITW-2026-00001.yaml").write_text(ITW_YAML, encoding="utf-8")
    (root / "README.md").write_text("ignored", encoding="utf-8")


class AdeImportCommandTests(TestCase):
    def test_local_import_stages_snapshot_and_never_activates(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_local_repo(Path(tmp))
            call_command("import_ade_framework", mode="local", dir=tmp)
        snapshot = AdeSnapshot.objects.get()
        self.assertEqual(snapshot.status, AdeSnapshot.Status.STAGED)
        self.assertEqual(snapshot.entry_count, 7)
        self.assertEqual(snapshot.summary["counts"][KIND_SUBCATEGORY], 2)
        self.assertEqual(snapshot.summary["counts"][KIND_LIKELIHOOD_CHECK], 2)
        self.assertIn("unknown ADE2-04", snapshot.validation_errors)
        self.assertFalse(PlatformDataVersion.objects.filter(framework="ade-framework").exists())

    def test_reimport_into_same_snapshot_replaces_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_local_repo(Path(tmp))
            call_command("import_ade_framework", mode="local", dir=tmp)
            snapshot = AdeSnapshot.objects.get()
            call_command("import_ade_framework", mode="local", dir=tmp, snapshot_id=str(snapshot.id))
        self.assertEqual(AdeSnapshot.objects.count(), 1)
        self.assertEqual(AdeEntry.objects.filter(snapshot=snapshot).count(), 7)

    def test_layout_change_without_subcategories_fails_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_local_repo(Path(tmp), taxonomy="# ADE2 - Omit Alternatives\n\nNo subsections any more.\n")
            with self.assertRaises(CommandError):
                call_command("import_ade_framework", mode="local", dir=tmp)
        snapshot = AdeSnapshot.objects.get()
        self.assertEqual(snapshot.status, AdeSnapshot.Status.FAILED)
        self.assertIn("layout may have changed", snapshot.validation_errors)

    def test_local_mode_requires_dir_and_existing_path(self):
        with self.assertRaises(CommandError):
            call_command("import_ade_framework", mode="local")
        with self.assertRaises(CommandError):
            call_command("import_ade_framework", mode="local", dir="/nonexistent/ade")


def _snapshot_with(entries, status=AdeSnapshot.Status.STAGED, sha="a" * 40):
    snapshot = AdeSnapshot.objects.create(status=status, source_sha=sha)
    for key, kind, ade_id, title, definition in entries:
        AdeEntry.objects.create(
            snapshot=snapshot, entry_key=key, kind=kind, ade_id=ade_id, title=title,
            definition=definition, source_hash=f"{title}|{definition}",
        )
    return snapshot


class AdeLifecycleTests(TestCase):
    def test_promote_archives_previous_and_records_version(self):
        first = _snapshot_with([], sha="1" * 40)
        second = _snapshot_with([], sha="2" * 40)
        _activate_ade_snapshot(first)
        _activate_ade_snapshot(second)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, AdeSnapshot.Status.ARCHIVED)
        self.assertEqual(second.status, AdeSnapshot.Status.ACTIVE)
        self.assertEqual(PlatformDataVersion.objects.get(framework="ade-framework").version, "2" * 12)
        # Rollback re-activates the archived one and archives the current one.
        _activate_ade_snapshot(first)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, AdeSnapshot.Status.ACTIVE)
        self.assertEqual(second.status, AdeSnapshot.Status.ARCHIVED)
        self.assertEqual(AdeSnapshot.objects.filter(status=AdeSnapshot.Status.ACTIVE).count(), 1)

    def test_diff_reports_added_changed_renamed_removed(self):
        active = _snapshot_with([
            ("SUBCATEGORY:ADE2-01", "SUBCATEGORY", "ADE2-01", "API/Function", "Covers one API."),
            ("SUBCATEGORY:ADE2-02", "SUBCATEGORY", "ADE2-02", "Versioning", "Old text."),
            ("SUBCATEGORY:ADE2-03", "SUBCATEGORY", "ADE2-03", "Locations", "Paths."),
            ("SUBCATEGORY:ADE9-09", "SUBCATEGORY", "ADE9-09", "Gone", "Removed upstream."),
        ], status=AdeSnapshot.Status.ACTIVE)
        staged = _snapshot_with([
            ("SUBCATEGORY:ADE2-01", "SUBCATEGORY", "ADE2-01", "Method/Binary", "Covers one API."),
            ("SUBCATEGORY:ADE2-02", "SUBCATEGORY", "ADE2-02", "Versioning", "New text."),
            ("SUBCATEGORY:ADE2-03", "SUBCATEGORY", "ADE2-03", "Locations", "Paths."),
            ("SUBCATEGORY:ADE3-06", "SUBCATEGORY", "ADE3-06", "Limit Saturation", "New."),
        ])
        diff = compute_ade_diff(staged, active)
        by_key = {c["entry_key"]: c["change"] for c in diff["changes"]}
        self.assertEqual(by_key, {
            "SUBCATEGORY:ADE2-01": "RENAMED",
            "SUBCATEGORY:ADE2-02": "CHANGED",
            "SUBCATEGORY:ADE3-06": "ADDED",
            "SUBCATEGORY:ADE9-09": "REMOVED",
        })
        self.assertEqual((diff["added"], diff["changed"], diff["removed"], diff["unchanged"]), (1, 2, 1, 1))

    def test_diff_without_active_snapshot_marks_everything_added(self):
        staged = _snapshot_with([("SUBCATEGORY:ADE1-01", "SUBCATEGORY", "ADE1-01", "A", "x")])
        diff = compute_ade_diff(staged, None)
        self.assertEqual((diff["added"], diff["active_count"]), (1, 0))


class AdeMutationGuardTests(TestCase):
    def _info(self, *, superuser):
        user = SimpleNamespace(is_anonymous=False, is_superuser=superuser, username="t", id=None)
        return SimpleNamespace(context=SimpleNamespace(user=user))

    def test_mutations_require_superuser(self):
        snapshot = _snapshot_with([])
        info = self._info(superuser=False)
        for call in (
            lambda: RunAdeImport.mutate(None, info),
            lambda: PromoteAdeSnapshot.mutate(None, info, snapshot.id),
            lambda: RollbackAdeSnapshot.mutate(None, info, snapshot.id),
        ):
            with self.assertRaises(GraphQLError):
                call()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.status, AdeSnapshot.Status.STAGED)

    def test_failed_snapshot_cannot_be_promoted_or_rolled_back(self):
        failed = _snapshot_with([], status=AdeSnapshot.Status.FAILED)
        info = self._info(superuser=True)
        with self.assertRaises(GraphQLError):
            PromoteAdeSnapshot.mutate(None, info, failed.id)
        with self.assertRaises(GraphQLError):
            RollbackAdeSnapshot.mutate(None, info, failed.id)

    def test_import_refused_while_another_is_running(self):
        AdeImportJob.objects.create(status=AdeImportJob.Status.RUNNING)
        with self.assertRaises(GraphQLError):
            RunAdeImport.mutate(None, self._info(superuser=True))

    def test_stale_jobs_are_failed_so_the_button_self_heals(self):
        job = AdeImportJob.objects.create(status=AdeImportJob.Status.RUNNING)
        AdeImportJob.objects.filter(id=job.id).update(updated_at=timezone.now() - timedelta(hours=1))
        fresh = AdeImportJob.objects.create(status=AdeImportJob.Status.PENDING)
        self.assertEqual(fail_stale_ade_jobs(), 1)
        job.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(job.status, AdeImportJob.Status.FAILED)
        self.assertEqual(fresh.status, AdeImportJob.Status.PENDING)
