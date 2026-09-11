from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase

from platform_data.models import (
    ChokepointEntry,
    ChokepointSnapshot,
    PlatformDataVersion,
)
from platform_data.schema import _activate_chokepoint_snapshot


class ChokepointImportCommandTests(TestCase):
    def test_remote_import_stages_snapshot_entries(self):
        snapshot = ChokepointSnapshot.objects.create(
            source_repo="https://github.com/iimp0ster/detection-chokepoints",
            source_ref="main",
            status=ChokepointSnapshot.Status.STAGED,
        )

        sample_yaml = """
chokepoints:
  - id: cp-01
    title: Script interpreter execution chokepoint
    technique: T1059.001
    tactic: Execution
    telemetry_prerequisites:
      - process_create
      - command_line
    native_rule_hints:
      kql:
        - DeviceProcessEvents | where ProcessCommandLine has "powershell"
      spl:
        - index=edr sourcetype=process
      wazuh_xml:
        - '<rule id="100001" level="10"></rule>'
"""

        with patch(
            "platform_data.management.commands.import_detection_chokepoints.list_remote_chokepoint_paths",
            return_value=["chokepoints/windows/script_exec.yml"],
        ), patch(
            "platform_data.management.commands.import_detection_chokepoints.fetch_remote_chokepoint_text",
            return_value=sample_yaml,
        ), patch(
            "platform_data.management.commands.import_detection_chokepoints.fetch_latest_ref_sha",
            return_value="0123456789abcdef0123456789abcdef01234567",
        ):
            call_command(
                "import_detection_chokepoints",
                snapshot_id=str(snapshot.id),
                mode="remote",
                source_repo="https://github.com/iimp0ster/detection-chokepoints",
                ref="main",
            )

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.status, ChokepointSnapshot.Status.STAGED)
        self.assertEqual(snapshot.entry_count, 1)
        self.assertEqual(snapshot.source_sha, "0123456789abcdef0123456789abcdef01234567")

        entry = ChokepointEntry.objects.get(snapshot=snapshot)
        self.assertEqual(entry.primary_technique_id, "T1059")
        self.assertEqual(entry.sub_technique_id, "T1059.001")
        self.assertIn("kql", entry.native_rule_hints)
        self.assertTrue(entry.native_rule_hints["kql"])

    def test_remote_import_parses_upstream_file_level_schema(self):
        snapshot = ChokepointSnapshot.objects.create(
            source_repo="https://github.com/iimp0ster/detection-chokepoints",
            source_ref="main",
            status=ChokepointSnapshot.Status.STAGED,
        )

        sample_yaml = """
Name: AiTM WebSocket Kit Relay
Id: 42a49200-e524-492e-8352-3ce4a2c78864
MitreIds:
  - T1539
  - T1078.004
Tactics:
  - Credential Access
Techniques:
  - Steal Web Session Cookie
  - Valid Accounts: Cloud Accounts
Description: >
  Adversary-in-the-Middle kit relays authentication and captures session tokens.
Prerequisites:
  - Victim must visit phishing page
Chokepoints:
  - Stage: Kit Relay Sign-In (Node.js UA)
    Observable: Entra ID SigninLogs with node/axios user agent
    LogSources:
      - Entra ID Sign-in Logs
KnownBypasses:
  - Bypass: Operator rotates residential proxies quickly
    Mitigation: Correlate session IDs and ASN transitions
    Detection: Pair cloud-VPS + residential transitions for same UPN
Intel:
  - Name: Elastic research
    URL: https://www.elastic.co/security-labs/tycoon-2fa-aitm-detection-engineering
"""

        with patch(
            "platform_data.management.commands.import_detection_chokepoints.list_remote_chokepoint_paths",
            return_value=["chokepoints/credential-access/aitm-websocket-relay.yml"],
        ), patch(
            "platform_data.management.commands.import_detection_chokepoints.fetch_remote_chokepoint_text",
            return_value=sample_yaml,
        ), patch(
            "platform_data.management.commands.import_detection_chokepoints.fetch_latest_ref_sha",
            return_value="3853e3c04131432e5c00ecaf3bfa62582f478c4",
        ):
            call_command(
                "import_detection_chokepoints",
                snapshot_id=str(snapshot.id),
                mode="remote",
                source_repo="https://github.com/iimp0ster/detection-chokepoints",
                ref="main",
            )

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.status, ChokepointSnapshot.Status.STAGED)
        self.assertEqual(snapshot.entry_count, 1)

        entry = ChokepointEntry.objects.get(snapshot=snapshot)
        self.assertEqual(entry.title, "AiTM WebSocket Kit Relay")
        self.assertEqual(entry.primary_technique_id, "T1539")
        self.assertEqual(entry.sub_technique_id, "T1078.004")
        self.assertIn("Steal Web Session Cookie", entry.technique_name)
        self.assertIn("Credential Access", entry.tactic)
        self.assertIn("Victim must visit phishing page", entry.telemetry_prerequisites)
        self.assertIn("Known bypasses:", entry.detection_context)
        self.assertIn("https://www.elastic.co/security-labs/tycoon-2fa-aitm-detection-engineering", entry.references)

        metadata = entry.metadata or {}
        self.assertIn("T1539", metadata.get("technique_codes", []))
        self.assertIn("T1078.004", metadata.get("technique_codes", []))
        self.assertTrue(metadata.get("known_bypasses"))
        intel = metadata.get("intel", [])
        self.assertTrue(intel)
        self.assertIn("Elastic", str(intel[0]))

    def test_remote_import_marks_snapshot_failed_on_empty_input(self):
        snapshot = ChokepointSnapshot.objects.create(
            source_repo="https://github.com/iimp0ster/detection-chokepoints",
            source_ref="main",
            status=ChokepointSnapshot.Status.STAGED,
        )

        with patch(
            "platform_data.management.commands.import_detection_chokepoints.list_remote_chokepoint_paths",
            return_value=[],
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "import_detection_chokepoints",
                    snapshot_id=str(snapshot.id),
                    mode="remote",
                    source_repo="https://github.com/iimp0ster/detection-chokepoints",
                    ref="main",
                )

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.status, ChokepointSnapshot.Status.FAILED)

    def test_remote_import_accepts_yaml_date_scalars_in_metadata(self):
        snapshot = ChokepointSnapshot.objects.create(
            source_repo="https://github.com/iimp0ster/detection-chokepoints",
            source_ref="main",
            status=ChokepointSnapshot.Status.STAGED,
        )

        sample_yaml = """
chokepoints:
  - id: cp-date-01
    title: Date scalar regression test
    technique: T1059
    tactic: Execution
    detections:
      - tested_on: 2026-08-21
        source: unit-test
    intel:
      - Date: 2026-08-20
        Source: https://example.com/research
"""

        with patch(
            "platform_data.management.commands.import_detection_chokepoints.list_remote_chokepoint_paths",
            return_value=["chokepoints/regression/date-scalar.yml"],
        ), patch(
            "platform_data.management.commands.import_detection_chokepoints.fetch_remote_chokepoint_text",
            return_value=sample_yaml,
        ), patch(
            "platform_data.management.commands.import_detection_chokepoints.fetch_latest_ref_sha",
            return_value="fedcba9876543210fedcba9876543210fedcba98",
        ):
            call_command(
                "import_detection_chokepoints",
                snapshot_id=str(snapshot.id),
                mode="remote",
                source_repo="https://github.com/iimp0ster/detection-chokepoints",
                ref="main",
            )

        entry = ChokepointEntry.objects.get(snapshot=snapshot)
        metadata = entry.metadata or {}
        detections = metadata.get("detections") or []
        intel = metadata.get("intel") or []

        self.assertTrue(detections)
        self.assertEqual(detections[0].get("tested_on"), "2026-08-21")
        self.assertTrue(intel)
        self.assertEqual(intel[0].get("Date"), "2026-08-20")


class ChokepointActivationTests(TestCase):
    def test_activate_snapshot_archives_previous_and_updates_version(self):
        old_active = ChokepointSnapshot.objects.create(
            source_repo="https://github.com/iimp0ster/detection-chokepoints",
            source_ref="main",
            source_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            status=ChokepointSnapshot.Status.ACTIVE,
            entry_count=10,
        )
        staged = ChokepointSnapshot.objects.create(
            source_repo="https://github.com/iimp0ster/detection-chokepoints",
            source_ref="main",
            source_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            status=ChokepointSnapshot.Status.STAGED,
            entry_count=15,
        )

        _activate_chokepoint_snapshot(staged)

        old_active.refresh_from_db()
        staged.refresh_from_db()
        self.assertEqual(old_active.status, ChokepointSnapshot.Status.ARCHIVED)
        self.assertEqual(staged.status, ChokepointSnapshot.Status.ACTIVE)
        self.assertIsNotNone(staged.activated_at)

        version_row = PlatformDataVersion.objects.get(framework="detection-chokepoints")
        self.assertEqual(version_row.version, "bbbbbbbbbbbb")
