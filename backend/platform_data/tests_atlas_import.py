import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

import yaml
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from platform_data import atlas_sync
from platform_data.models import (
    AtlasCaseStudy,
    AtlasMitigation,
    AtlasRelationship,
    AtlasTactic,
    AtlasTechnique,
)

MANIFEST = [
    {"release": "2026.10", "release-date": "2026-10-28", "versions": [{"format-version": "6.1.0", "path": "v6/ATLAS-2026.10.yaml"}]},
    {"release": "2026.09", "release-date": "2026-09-15", "versions": [{"format-version": "6.0.0", "path": "v6/ATLAS-2026.09.yaml"}]},
]

# Shaped like upstream dist/v6/ATLAS-<release>.yaml: dicts keyed by ID, hyphenated keys,
# relationships without ids under relationships.<source>.<type>[].
CURRENT = {
    "tactics": {
        "AML.TA0001": {"id": "AML.TA0001", "name": "AI Attack Adaptation", "description": "d",
                        "created-date": "2021-05-13", "modified-date": "2026-08-31",
                        "uuid": "06017740-23bb-5d05-b6d5-366ce7f0c0a1"},
    },
    "techniques": {
        "AML.T0051": {"id": "AML.T0051", "name": "LLM Prompt Injection", "description": "d",
                       "created-date": "2023-10-25", "modified-date": "2026-07-31", "maturity": "Realized"},
    },
    "mitigations": {
        "AML.M0004": {"id": "AML.M0004", "name": "Limit Query Rate", "description": "d",
                       "created-date": "2023-04-12", "lifecycle-phases": ["Deployment"], "categories": ["Policy"]},
    },
    "case-studies": {
        "AML.CS0001": {"id": "AML.CS0001", "name": "DGA", "description": "d", "type": "Exercise",
                        "created-date": "2020-12-15", "start-date": "2020-01-01",
                        "start-date-granularity": "Year", "end-date": "2020-01-01", "end-date-granularity": "Year"},
    },
    "relationships": {
        "AML.CS0001": {
            "employs": [{"source": "AML.CS0001", "target": "AML.T0051", "relationship-type": "employs",
                          "description": "step", "tactic": "AML.TA0001", "step-id": "S00", "leads-to": ["S01"]}],
        },
        "AML.T0051": {
            "achieves": [{"source": "AML.T0051", "target": "AML.TA0001", "relationship-type": "achieves"}],
        },
        "ATLAS-matrix": {  # non-AML source: skipped
            "sequences": [{"source": "ATLAS-matrix", "target": "AML.TA0001", "relationship-type": "sequences"}],
        },
    },
}

# Older release that still carries a technique retired in the current release.
OLD = {
    "techniques": {
        "AML.T0056": {"id": "AML.T0056", "name": "Extract LLM System Prompt", "description": "retired"},
    },
}


class AtlasManifestTests(SimpleTestCase):
    def test_latest_path_from_manifest_picks_newest(self):
        self.assertEqual(
            atlas_sync.latest_path_from_manifest(yaml.safe_dump(MANIFEST)),
            ("dist/v6/ATLAS-2026.10.yaml", "2026.10"),
        )

    def test_latest_path_from_manifest_rejects_garbage(self):
        self.assertIsNone(atlas_sync.latest_path_from_manifest("not: [a list"))
        self.assertIsNone(atlas_sync.latest_path_from_manifest("{}"))

    def test_remote_listing_returns_only_latest_release(self):
        with mock.patch.object(atlas_sync, "fetch_remote_atlas_text", return_value=yaml.safe_dump(MANIFEST)):
            self.assertEqual(atlas_sync.list_remote_atlas_paths(), ["dist/v6/ATLAS-2026.10.yaml"])

    def test_remote_listing_falls_back_to_tree_when_manifest_missing(self):
        tree = {"tree": [
            {"type": "blob", "path": ".github/workflows/ci.yml"},
            {"type": "blob", "path": "dist/ATLAS.yaml"},
            {"type": "blob", "path": "dist/legacy/ATLAS-4.0.0.yaml"},
            {"type": "blob", "path": "dist/v6/ATLAS-2026.09.yaml"},
            {"type": "blob", "path": "dist/v6/ATLAS-2026.10.yaml"},
        ]}
        import requests
        with mock.patch.object(atlas_sync, "fetch_remote_atlas_text", side_effect=requests.RequestException("boom")), \
                mock.patch.object(atlas_sync, "_github_json", return_value=tree):
            self.assertEqual(atlas_sync.list_remote_atlas_paths(), ["dist/v6/ATLAS-2026.10.yaml"])


class AtlasImportCommandTests(TestCase):
    def _checkout(self, root: Path) -> None:
        dist = root / "dist"
        (dist / "v6").mkdir(parents=True)
        (dist / "manifest.yaml").write_text(yaml.safe_dump(MANIFEST))
        (dist / "v6" / "ATLAS-2026.10.yaml").write_text(yaml.safe_dump(CURRENT))
        (dist / "v6" / "ATLAS-2026.09.yaml").write_text(yaml.safe_dump(OLD))
        (root / ".github").mkdir()
        (root / ".github" / "ci.yml").write_text("name: [unclosed")  # must never be read

    def _import(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._checkout(Path(tmp))
            call_command("import_atlas_framework", mode="local", dir=tmp)

    def test_retired_objects_are_not_imported(self):
        self._import()
        self.assertFalse(AtlasTechnique.objects.filter(atlas_id="AML.T0056").exists())
        self.assertEqual(AtlasTechnique.objects.count(), 1)
        self.assertEqual(AtlasTactic.objects.count(), 1)

    def test_relationships_are_imported_with_hyphenated_keys(self):
        self._import()
        self.assertEqual(AtlasRelationship.objects.count(), 2)  # ATLAS-matrix source skipped
        rel = AtlasRelationship.objects.get(source_atlas_id="AML.CS0001")
        self.assertEqual(rel.target_atlas_id, "AML.T0051")
        self.assertEqual(rel.relationship_type, "employs")
        self.assertEqual(rel.tactic_atlas_id, "AML.TA0001")
        self.assertEqual(rel.step_id, "S00")
        self.assertEqual(rel.leads_to, ["S01"])
        self.assertTrue(AtlasRelationship.objects.filter(relationship_type="achieves").exists())

    def test_hyphenated_dates_and_uuid_are_read(self):
        self._import()
        tactic = AtlasTactic.objects.get(atlas_id="AML.TA0001")
        self.assertEqual(tactic.created_date, date(2021, 5, 13))
        self.assertEqual(tactic.modified_date, date(2026, 8, 31))
        self.assertIsNotNone(tactic.atlas_uuid)
        self.assertEqual(AtlasTechnique.objects.get().created_date, date(2023, 10, 25))
        self.assertEqual(AtlasMitigation.objects.get().created_date, date(2023, 4, 12))
        self.assertEqual(AtlasMitigation.objects.get().lifecycle_phases, ["Deployment"])
        case_study = AtlasCaseStudy.objects.get()
        self.assertEqual(case_study.start_date, date(2020, 1, 1))
        self.assertEqual(case_study.start_date_granularity, "Year")
        self.assertEqual(case_study.case_study_type, "Exercise")
