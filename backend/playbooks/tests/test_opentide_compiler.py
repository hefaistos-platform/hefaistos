"""Tests for the OpenTide metadata compiler utilities."""

import re
import uuid
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

from django.test import TestCase

from playbooks.utils.opentide_compiler import (
    compile_dom_yaml,
    compile_full_opentide_yaml,
    compile_mdr_yaml,
    compile_opentide_metadata,
    compile_tvm_yaml,
    diff_metadata,
    merge_metadata_with_platforms,
    validate_opentide_metadata,
    _deterministic_uuid4,
    _extract_threat_surface,
    _infer_impacted_entities,
    _normalize_mdr_impacted_entities,
)


def _make_playbook(**kwargs):
    """Return a mock PlaybookGraph-like object with sensible defaults."""
    playbook = MagicMock()
    playbook.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    playbook.title = kwargs.get("title", "Test Detection")
    playbook.goal = kwargs.get("goal", "Detect suspicious activity")
    playbook.technical_context = kwargs.get("technical_context", "")
    playbook.blind_spots = kwargs.get("blind_spots", "")
    playbook.false_positives = kwargs.get("false_positives", "")
    playbook.response_playbook = kwargs.get("response_playbook", "")
    playbook.default_severity = kwargs.get("default_severity", "MEDIUM")
    playbook.alert_trigger = kwargs.get("alert_trigger", "")
    playbook.robustness_level = kwargs.get("robustness_level", 0)
    playbook.data_source_maturity = kwargs.get("data_source_maturity", "")
    playbook.data_source_robustness = kwargs.get("data_source_robustness", "")
    playbook.opentide_yaml = kwargs.get("opentide_yaml", None)
    playbook.custom_id = kwargs.get("custom_id", None)
    playbook.status = kwargs.get("status", "DEPLOYED")
    playbook.triage_guidance = kwargs.get("triage_guidance", "")

    # Testing metadata fields
    playbook.test_validation_status = kwargs.get("test_validation_status", "NOT_TESTED")
    playbook.test_results = kwargs.get("test_results", None)
    playbook.last_tested_at = kwargs.get("last_tested_at", None)
    playbook.test_scenario = kwargs.get("test_scenario", "")
    playbook.test_expected_output = kwargs.get("test_expected_output", "")

    # Tuning parameter fields
    playbook.time_window = kwargs.get("time_window", "")
    playbook.alert_threshold = kwargs.get("alert_threshold", None)
    playbook.threshold_operator = kwargs.get("threshold_operator", "greater_than")
    playbook.aggregation_field = kwargs.get("aggregation_field", "")
    playbook.aggregation_function = kwargs.get("aggregation_function", "count")
    playbook.suppression_window = kwargs.get("suppression_window", "")

    # SOAR procedure fields
    playbook.enrichment_steps = kwargs.get("enrichment_steps", [])
    playbook.containment_steps = kwargs.get("containment_steps", [])
    playbook.notification_steps = kwargs.get("notification_steps", [])

    # OpenTide v2.1 fields
    playbook.tlp_classification = kwargs.get("tlp_classification", "AMBER")
    playbook.public_references = kwargs.get("public_references", [])
    playbook.internal_references = kwargs.get("internal_references", [])
    playbook.threat_actors = kwargs.get("threat_actors", [])
    playbook.threat_surface = kwargs.get("threat_surface", [])

    # Author mock
    author = MagicMock()
    author.username = kwargs.get("author_username", "analyst1")
    playbook.author = kwargs.get("author", author)

    # Organization mock
    organization = MagicMock()
    organization.name = kwargs.get("org_name", "Test Org")
    playbook.organization = kwargs.get("organization", organization)

    # Timestamps
    playbook.created_at = kwargs.get("created_at", datetime(2024, 1, 1, 0, 0, 0))
    playbook.updated_at = kwargs.get("updated_at", datetime(2024, 6, 1, 0, 0, 0))

    # MITRE technique mock — use "mitre_technique" in kwargs to allow explicit None
    if "mitre_technique" in kwargs:
        playbook.mitre_technique = kwargs["mitre_technique"]
    else:
        technique = MagicMock()
        technique.technique_id = kwargs.get("technique_id", "T1059")
        technique.name = kwargs.get("technique_name", "Command and Scripting Interpreter")
        # MitreAttackTechnique doesn't have tactic by default
        del technique.tactic
        playbook.mitre_technique = technique

    # Tags manager mock
    tags_manager = MagicMock()
    tags_manager.exists.return_value = False
    playbook.tags = tags_manager

    # linked_rules queryset mock (empty by default)
    linked_rules_qs = _make_linked_rules_qs(kwargs.get("linked_rules", []))
    playbook.linked_rules = linked_rules_qs

    return playbook


def _make_rule(fmt: str, content: str):
    """Return a mock DetectionRule-like object."""
    rule = MagicMock()
    rule.format = fmt
    rule.raw_content = content
    rule.updated_at = datetime(2024, 6, 1, 0, 0, 0)
    return rule


def _make_linked_rules_qs(rules: list):
    """Return a mock queryset that iterates over the given list of mock rules."""
    qs = MagicMock()
    qs.__iter__ = MagicMock(return_value=iter(rules))
    qs.order_by.return_value = iter(rules)
    return qs


class TestCompileOpentideMetadata(TestCase):
    """Tests for compile_opentide_metadata()."""

    def test_basic_fields_populated(self):
        playbook = _make_playbook(title="My Rule", author_username="jane")
        result = compile_opentide_metadata(playbook)

        self.assertEqual(result["title"], "My Rule")
        self.assertEqual(result["author"], "jane")
        self.assertIn("created", result)
        self.assertIn("modified", result)

    def test_title_fallback(self):
        playbook = _make_playbook(title="")
        playbook.title = ""
        result = compile_opentide_metadata(playbook)
        self.assertEqual(result["title"], "Untitled Detection")

    def test_author_fallback_when_none(self):
        playbook = _make_playbook()
        playbook.author = None
        result = compile_opentide_metadata(playbook)
        self.assertEqual(result["author"], "unknown")

    def test_mitre_section_populated(self):
        technique = MagicMock()
        technique.technique_id = "T1059.001"
        technique.name = "PowerShell"
        del technique.tactic  # MitreAttackTechnique has no tactic field
        playbook = _make_playbook(mitre_technique=technique)
        result = compile_opentide_metadata(playbook)

        self.assertIn("mitre", result)
        self.assertEqual(result["mitre"]["technique_id"], "T1059.001")
        self.assertEqual(result["mitre"]["technique_name"], "PowerShell")
        self.assertNotIn("tactic", result["mitre"])

    def test_mitre_tactic_included_when_present(self):
        technique = MagicMock()
        technique.technique_id = "T1059"
        technique.name = "Command Interpreter"
        technique.tactic = "Execution"
        playbook = _make_playbook(mitre_technique=technique)
        result = compile_opentide_metadata(playbook)

        self.assertEqual(result["mitre"]["tactic"], "Execution")

    def test_no_mitre_section_when_no_technique(self):
        playbook = _make_playbook(mitre_technique=None)
        playbook.mitre_technique = None
        result = compile_opentide_metadata(playbook)
        self.assertNotIn("mitre", result)

    def test_capability_section_populated(self):
        playbook = _make_playbook(
            goal="Detect lateral movement",
            technical_context="Uses WMI",
            blind_spots="Encrypted traffic",
            false_positives="Admin tools",
        )
        result = compile_opentide_metadata(playbook)
        self.assertIn("capability", result)
        cap = result["capability"]
        self.assertEqual(cap["goal"], "Detect lateral movement")
        self.assertEqual(cap["technical_context"], "Uses WMI")
        self.assertEqual(cap["blind_spots"], "Encrypted traffic")
        self.assertEqual(cap["false_positives"], "Admin tools")

    def test_no_capability_section_when_all_empty(self):
        playbook = _make_playbook(goal="")
        playbook.goal = ""
        playbook.technical_context = ""
        playbook.blind_spots = ""
        playbook.false_positives = ""
        result = compile_opentide_metadata(playbook)
        self.assertNotIn("capability", result)

    def test_response_section_populated(self):
        playbook = _make_playbook(
            response_playbook="Isolate host",
            default_severity="HIGH",
            alert_trigger="When process created",
        )
        result = compile_opentide_metadata(playbook)
        self.assertIn("response", result)
        self.assertEqual(result["response"]["playbook"], "Isolate host")
        self.assertEqual(result["response"]["severity"], "HIGH")
        self.assertEqual(result["response"]["alert_trigger"], "When process created")

    def test_validation_section_populated(self):
        playbook = _make_playbook(robustness_level=4, data_source_maturity="KERNEL_MODE")
        result = compile_opentide_metadata(playbook)
        self.assertIn("validation", result)
        self.assertEqual(result["validation"]["robustness_level"], 4)
        self.assertEqual(result["validation"]["data_source_maturity"], "KERNEL_MODE")

    def test_no_validation_when_zero_robustness(self):
        playbook = _make_playbook(robustness_level=0, data_source_maturity="")
        result = compile_opentide_metadata(playbook)
        self.assertNotIn("validation", result)

    def test_tags_included_when_present(self):
        playbook = _make_playbook()
        playbook.tags.exists.return_value = True
        playbook.tags.values_list.return_value = ["lateral-movement", "windows"]
        result = compile_opentide_metadata(playbook)
        self.assertIn("tags", result)
        self.assertIn("lateral-movement", result["tags"])

    def test_timestamps_are_isoformat(self):
        playbook = _make_playbook(
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            updated_at=datetime(2024, 6, 30, 8, 30, 0),
        )
        result = compile_opentide_metadata(playbook)
        self.assertIn("T", result["created"])
        self.assertIn("T", result["modified"])


class TestValidateOpentideMetadata(TestCase):
    """Tests for validate_opentide_metadata()."""

    def _valid_metadata(self, **overrides):
        base = {"title": "My Rule", "author": "analyst", "created": "2024-01-01T00:00:00"}
        base.update(overrides)
        return base

    def test_valid_metadata_passes(self):
        is_valid, errors = validate_opentide_metadata(self._valid_metadata())
        self.assertTrue(is_valid)
        self.assertEqual(errors, [])

    def test_missing_required_field(self):
        meta = {"title": "Test", "author": "analyst"}  # missing 'created'
        is_valid, errors = validate_opentide_metadata(meta)
        self.assertFalse(is_valid)
        self.assertTrue(any("created" in e for e in errors))

    def test_invalid_mitre_technique_id(self):
        meta = self._valid_metadata(mitre={"technique_id": "BAD_ID"})
        is_valid, errors = validate_opentide_metadata(meta)
        self.assertFalse(is_valid)
        self.assertTrue(any("MITRE" in e for e in errors))

    def test_valid_mitre_technique_id(self):
        meta = self._valid_metadata(mitre={"technique_id": "T1059"})
        is_valid, errors = validate_opentide_metadata(meta)
        self.assertTrue(is_valid)

    def test_valid_mitre_subtechnique_id(self):
        meta = self._valid_metadata(mitre={"technique_id": "T1059.001"})
        is_valid, errors = validate_opentide_metadata(meta)
        self.assertTrue(is_valid)

    def test_invalid_severity(self):
        meta = self._valid_metadata(response={"severity": "EXTREME"})
        is_valid, errors = validate_opentide_metadata(meta)
        self.assertFalse(is_valid)
        self.assertTrue(any("severity" in e.lower() for e in errors))

    def test_valid_severity_values(self):
        for sev in ("Critical", "High", "Medium", "Low", "Informational"):
            meta = self._valid_metadata(response={"severity": sev})
            is_valid, errors = validate_opentide_metadata(meta)
            self.assertTrue(is_valid, f"Expected valid for severity={sev}, errors={errors}")

    def test_invalid_robustness_level(self):
        meta = self._valid_metadata(validation={"robustness_level": 6})
        is_valid, errors = validate_opentide_metadata(meta)
        self.assertFalse(is_valid)
        self.assertTrue(any("robustness" in e.lower() for e in errors))

    def test_valid_robustness_levels(self):
        for level in range(1, 6):
            meta = self._valid_metadata(validation={"robustness_level": level})
            is_valid, errors = validate_opentide_metadata(meta)
            self.assertTrue(is_valid, f"Expected valid for robustness_level={level}, errors={errors}")


class TestDiffMetadata(TestCase):
    """Tests for diff_metadata()."""

    def test_no_diff_when_identical(self):
        meta = {"title": "Test", "author": "analyst"}
        result = diff_metadata(meta, meta)
        self.assertEqual(result, {})

    def test_top_level_change_detected(self):
        old = {"title": "Old Title", "author": "analyst"}
        new = {"title": "New Title", "author": "analyst"}
        result = diff_metadata(old, new)
        self.assertIn("title", result)
        self.assertEqual(result["title"]["old"], "Old Title")
        self.assertEqual(result["title"]["new"], "New Title")

    def test_nested_change_detected(self):
        old = {"mitre": {"technique_id": "T1059"}}
        new = {"mitre": {"technique_id": "T1078"}}
        result = diff_metadata(old, new)
        self.assertIn("mitre.technique_id", result)

    def test_added_field_detected(self):
        old = {"title": "Test"}
        new = {"title": "Test", "author": "analyst"}
        result = diff_metadata(old, new)
        self.assertIn("author", result)
        self.assertIsNone(result["author"]["old"])

    def test_removed_field_detected(self):
        old = {"title": "Test", "author": "analyst"}
        new = {"title": "Test"}
        result = diff_metadata(old, new)
        self.assertIn("author", result)
        self.assertIsNone(result["author"]["new"])


class TestMergeMetadataWithPlatforms(TestCase):
    """Tests for merge_metadata_with_platforms()."""

    def test_platforms_preserved(self):
        playbook = _make_playbook(title="Test")
        platforms = {"kql": {"query": "DeviceProcessEvents | limit 10"}}
        result = merge_metadata_with_platforms(playbook, platforms)

        self.assertEqual(result["platforms"], platforms)
        self.assertIn("metadata", result)

    def test_empty_platforms_allowed(self):
        playbook = _make_playbook()
        result = merge_metadata_with_platforms(playbook, {})
        self.assertEqual(result["platforms"], {})

    def test_metadata_refreshed(self):
        playbook = _make_playbook(title="Updated Title")
        result = merge_metadata_with_platforms(playbook, {})
        self.assertEqual(result["metadata"]["title"], "Updated Title")


class TestCompileFullOpentideYaml(TestCase):
    """Tests for compile_full_opentide_yaml()."""

    def test_structure_has_metadata_and_platforms(self):
        playbook = _make_playbook()
        playbook.opentide_yaml = None
        result = compile_full_opentide_yaml(playbook)

        self.assertIn("metadata", result)
        self.assertIn("platforms", result)
        self.assertEqual(result["platforms"], {})

    def test_existing_platforms_preserved(self):
        existing = {"kql": {"query": "SomeQuery"}, "sigma": {"detection": "stuff", "logsource": {}}}
        playbook = _make_playbook(opentide_yaml={"metadata": {}, "platforms": existing})
        result = compile_full_opentide_yaml(playbook)

        self.assertEqual(result["platforms"], existing)


class TestCompileMdrYaml(TestCase):
    """Tests for compile_mdr_yaml() — CoreTide MDR schema format."""

    def test_top_level_structure(self):
        playbook = _make_playbook(linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertIn('name', result)
        self.assertIn('metadata', result)
        # Old fields should NOT be present
        self.assertNotIn('id', result)
        self.assertNotIn('status', result)
        self.assertNotIn('detection', result)

    def test_name_is_snake_case(self):
        playbook = _make_playbook(custom_id='DE-T1070-001', linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertEqual(result['name'], 'mdr_de_t1070_001')

    def test_metadata_required_fields(self):
        playbook = _make_playbook(linked_rules=[])
        meta = compile_mdr_yaml(playbook)['metadata']
        for field in ('uuid', 'schema', 'version', 'tlp', 'created', 'modified'):
            self.assertIn(field, meta, f"Missing metadata field: {field}")
        self.assertEqual(meta['schema'], 'mdr::2.1')
        self.assertEqual(meta['version'], 1)
        self.assertEqual(meta['tlp'], 'amber')

    def test_metadata_author_is_string(self):
        playbook = _make_playbook(author_username='analyst1')
        meta = compile_mdr_yaml(playbook)['metadata']
        self.assertIsInstance(meta['author'], str, "metadata.author must be a plain string")
        self.assertIn('analyst1', meta['author'])

    def test_description_from_goal(self):
        playbook = _make_playbook(goal='Detect suspicious activity', linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertIn('description', result)
        self.assertEqual(result['description'], 'Detect suspicious activity')

    def test_description_fallback_to_title(self):
        playbook = _make_playbook(goal='', linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertIn('description', result)
        self.assertEqual(result['description'], 'Test Detection')

    def test_response_alert_severity(self):
        playbook = _make_playbook(default_severity='HIGH', linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertIn('response', result)
        self.assertEqual(result['response']['alert_severity'], 'High')

    @patch('playbooks.utils.opentide_compiler.build_l1_portal_share_url')
    @patch('playbooks.utils.opentide_compiler.upsert_l1_portal_snapshot')
    def test_response_includes_l1_portal_fields_for_deployed(
        self,
        mock_upsert_l1_portal_snapshot,
        mock_build_l1_portal_share_url,
    ):
        playbook = _make_playbook(status='DEPLOYED', linked_rules=[])
        entry = MagicMock()
        entry.url_token = uuid.UUID("00000000-0000-0000-0000-000000000099")
        mock_upsert_l1_portal_snapshot.return_value = entry
        mock_build_l1_portal_share_url.return_value = (
            "https://detect.example.org/l1-portal/00000000-0000-0000-0000-000000000099"
        )

        result = compile_mdr_yaml(playbook)

        self.assertEqual(
            result['response']['l1_portal_url'],
            "https://detect.example.org/l1-portal/00000000-0000-0000-0000-000000000099",
        )
        self.assertEqual(
            result['response']['l1_portal_token'],
            "00000000-0000-0000-0000-000000000099",
        )
        mock_upsert_l1_portal_snapshot.assert_called_once_with(playbook)
        mock_build_l1_portal_share_url.assert_called_once_with(entry.url_token)

    @patch('playbooks.utils.opentide_compiler.upsert_l1_portal_snapshot')
    def test_response_omits_l1_portal_fields_for_non_deployed(self, mock_upsert_l1_portal_snapshot):
        playbook = _make_playbook(status='APPROVED', linked_rules=[])

        result = compile_mdr_yaml(playbook)

        self.assertNotIn('l1_portal_url', result['response'])
        self.assertNotIn('l1_portal_token', result['response'])
        mock_upsert_l1_portal_snapshot.assert_not_called()

    def test_response_always_present_without_severity(self):
        playbook = _make_playbook(linked_rules=[])
        playbook.default_severity = None
        result = compile_mdr_yaml(playbook)
        self.assertIn('response', result, "MDR 'response' block must always be present")
        self.assertIn('alert_severity', result['response'], "MDR 'response.alert_severity' must always be present")
        self.assertEqual(result['response']['alert_severity'], 'Medium')

    def test_no_configurations_when_no_linked_rules(self):
        playbook = _make_playbook(linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('configurations', result)

    def test_kql_rule_maps_to_defender_for_endpoint(self):
        rule = _make_rule('KQL', 'DeviceProcessEvents | where FileName == "powershell.exe"')
        playbook = _make_playbook(
            linked_rules=[rule],
            title='Suspicious PowerShell',
            goal='Detect PowerShell abuse',
            default_severity='HIGH',
            technique_id='T1059.001',
        )
        result = compile_mdr_yaml(playbook)
        self.assertIn('configurations', result)
        dfe = result['configurations']['defender_for_endpoint']
        self.assertEqual(
            dfe['query'],
            'DeviceProcessEvents | where FileName == "powershell.exe"',
        )
        # Required top-level fields
        self.assertEqual(dfe['schema'], 'defender_for_endpoint::2.0')
        self.assertEqual(dfe['status'], 'PRODUCTION')
        self.assertEqual(dfe['scheduling'], '1H')
        self.assertIn('impacted_entities', dfe)
        # The test KQL is "DeviceProcessEvents | where FileName == "powershell.exe"" — no
        # entity columns match, so the safe default applies
        self.assertEqual(dfe['impacted_entities'], {'device': 'DeviceName'})
        self.assertIn('scope', dfe)
        self.assertEqual(dfe['scope']['selection'], 'All')
        # Alert block must conform to CoreTide DefenderForEndpoint.Alert schema
        alert = dfe['alert']
        self.assertEqual(alert['category'], 'Suspicious Activity')
        self.assertEqual(alert['title'], 'Suspicious PowerShell')
        self.assertEqual(alert['description'], 'Detect PowerShell abuse')
        self.assertEqual(alert['severity'], 'High')
        self.assertNotIn('enabled', alert)
        self.assertEqual(alert['techniques'], ['T1059.001'])
        # Old-style detection key must NOT appear
        self.assertNotIn('detection', result)

    def test_spl_rule_maps_to_splunk(self):
        rule = _make_rule('SPL', 'index=windows EventCode=4624 | stats count by user')
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertIn('splunk', result['configurations'])
        self.assertEqual(
            result['configurations']['splunk']['query'],
            'index=windows EventCode=4624 | stats count by user',
        )

    def test_sigma_rule_maps_to_sigma(self):
        sigma_content = 'title: Test\ndetection:\n  selection:\n    EventID: 4624\n  condition: selection'
        rule = _make_rule('SIGMA', sigma_content)
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertIn('sigma', result['configurations'])
        self.assertEqual(result['configurations']['sigma']['rule'], sigma_content)

    def test_wazuh_rule_maps_to_wazuh(self):
        wazuh_content = '<rule id="100001" level="10"><description>Test</description></rule>'
        rule = _make_rule('WAZUH', wazuh_content)
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertIn('wazuh', result['configurations'])
        self.assertEqual(result['configurations']['wazuh']['rule'], wazuh_content)

    def test_multiple_formats_all_included(self):
        rules = [
            _make_rule('KQL', 'KQL query here'),
            _make_rule('SPL', 'SPL query here'),
            _make_rule('SIGMA', 'sigma: yaml'),
            _make_rule('WAZUH', '<rule/>'),
        ]
        playbook = _make_playbook(linked_rules=rules)
        result = compile_mdr_yaml(playbook)
        configurations = result['configurations']
        self.assertIn('defender_for_endpoint', configurations)
        self.assertIn('microsoft_sentinel', configurations)
        self.assertIn('splunk', configurations)
        self.assertIn('sigma', configurations)
        self.assertIn('wazuh', configurations)

    def test_empty_raw_content_excluded(self):
        rule = _make_rule('KQL', '   ')
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('configurations', result)

    def test_other_format_excluded(self):
        rule = _make_rule('OTHER', 'some other content')
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('configurations', result)

    def test_elastic_rule_maps_to_elastic(self):
        rule = _make_rule('ELASTIC', 'process where process.name == "powershell.exe"')
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertIn('configurations', result)
        self.assertIn('elastic', result['configurations'])
        self.assertEqual(
            result['configurations']['elastic']['query'],
            'process where process.name == "powershell.exe"',
        )

    def test_eql_rule_maps_to_elastic(self):
        rule = _make_rule('EQL', 'sequence [process where process.name == "cmd.exe"]')
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertIn('configurations', result)
        self.assertIn('elastic', result['configurations'])
        self.assertEqual(
            result['configurations']['elastic']['query'],
            'sequence [process where process.name == "cmd.exe"]',
        )

    def test_all_formats_including_elastic(self):
        rules = [
            _make_rule('KQL', 'KQL query here'),
            _make_rule('SPL', 'SPL query here'),
            _make_rule('SIGMA', 'sigma: yaml'),
            _make_rule('WAZUH', '<rule/>'),
            _make_rule('ELASTIC', 'process where true'),
        ]
        playbook = _make_playbook(linked_rules=rules)
        result = compile_mdr_yaml(playbook)
        configurations = result['configurations']
        self.assertIn('defender_for_endpoint', configurations)
        self.assertIn('microsoft_sentinel', configurations)
        self.assertIn('splunk', configurations)
        self.assertIn('sigma', configurations)
        self.assertIn('wazuh', configurations)
        self.assertIn('elastic', configurations)

    def test_no_configurations_adds_validation_warning(self):
        playbook = _make_playbook(linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('configurations', result)
        self.assertIn('_validation_warning', result)
        self.assertEqual(result['_validation_warning'], 'No detection configurations present')

    def test_configurations_present_no_validation_warning(self):
        rule = _make_rule('KQL', 'DeviceProcessEvents | limit 10')
        playbook = _make_playbook(linked_rules=[rule])
        result = compile_mdr_yaml(playbook)
        self.assertIn('configurations', result)
        self.assertNotIn('_validation_warning', result)

    def test_mdr_response_procedure_from_enrichment_steps(self):
        steps = [{'action': 'Get-User', 'input': 'event.user', 'output': 'user.dept'}]
        playbook = _make_playbook(linked_rules=[], enrichment_steps=steps)
        result = compile_mdr_yaml(playbook)
        self.assertIn('procedure', result['response'])
        self.assertEqual(result['response']['procedure']['analysis'], steps)

    def test_mdr_response_procedure_from_containment_steps(self):
        steps = [{'description': 'Isolate host', 'critical': True}]
        playbook = _make_playbook(linked_rules=[], containment_steps=steps)
        result = compile_mdr_yaml(playbook)
        self.assertIn('procedure', result['response'])
        self.assertEqual(result['response']['procedure']['containment'], steps)

    def test_mdr_response_procedure_omitted_when_no_steps(self):
        playbook = _make_playbook(linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('procedure', result['response'])

    # ------------------------------------------------------------------
    # Workbench → MDR field-mapping tests
    # User-entered Deep Dive / SOAR / Testing fields must round-trip into
    # the MDR YAML so they survive an OpenTIDE commit.
    # ------------------------------------------------------------------

    def test_mdr_response_includes_response_playbook(self):
        playbook = _make_playbook(linked_rules=[], response_playbook='Isolate host\nReset creds')
        result = compile_mdr_yaml(playbook)
        self.assertEqual(result['response']['playbook'], 'Isolate host\nReset creds')

    def test_mdr_response_includes_alert_trigger(self):
        playbook = _make_playbook(linked_rules=[])
        playbook.alert_trigger = 'Triggered when LSASS is read'
        result = compile_mdr_yaml(playbook)
        self.assertEqual(result['response']['alert_trigger'], 'Triggered when LSASS is read')

    def test_mdr_response_includes_false_positives(self):
        """false_positives lives on MDR.response (not DOM root) per upstream schema."""
        playbook = _make_playbook(linked_rules=[], false_positives='Admin tooling, EDR scans')
        result = compile_mdr_yaml(playbook)
        self.assertEqual(result['response']['false_positives'], 'Admin tooling, EDR scans')

    def test_mdr_response_includes_triage_guidance(self):
        playbook = _make_playbook(linked_rules=[], triage_guidance='1. Check signer\n2. Review parent')
        result = compile_mdr_yaml(playbook)
        self.assertEqual(result['response']['triage_guidance'], '1. Check signer\n2. Review parent')

    def test_mdr_response_procedure_from_notification_steps(self):
        steps = [{'channel': 'email', 'recipient': 'soc@example.com', 'template': 'high-sev'}]
        playbook = _make_playbook(linked_rules=[], notification_steps=steps)
        result = compile_mdr_yaml(playbook)
        self.assertIn('procedure', result['response'])
        self.assertEqual(result['response']['procedure']['notification'], steps)

    def test_mdr_response_includes_testing_fields(self):
        playbook = _make_playbook(linked_rules=[])
        playbook.test_scenario = 'Run mimikatz on a sandboxed host'
        playbook.test_expected_output = 'Process event for lsass.exe handle open'
        result = compile_mdr_yaml(playbook)
        testing = result['response'].get('testing', {})
        self.assertEqual(testing.get('scenario'), 'Run mimikatz on a sandboxed host')
        self.assertEqual(testing.get('expected_output'), 'Process event for lsass.exe handle open')

    def test_mdr_response_omits_testing_when_no_inputs(self):
        playbook = _make_playbook(linked_rules=[])
        playbook.test_scenario = ''
        playbook.test_expected_output = ''
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('testing', result['response'])

    # ------------------------------------------------------------------
    # schema compliance tests — invalid top-level fields must not appear
    # ------------------------------------------------------------------

    def test_mdr_no_invalid_top_level_fields(self):
        """MDR must not contain fields rejected by the CoreTide mdr::2.1 schema."""
        playbook = _make_playbook(linked_rules=[], robustness_level=4)
        playbook.test_validation_status = 'PASSED'
        playbook.test_results = {'test_cases_passed': 12}
        playbook.last_tested_at = datetime(2024, 1, 15, 14, 0, 0)
        playbook.time_window = '5m'
        playbook.alert_threshold = 1
        playbook.aggregation_field = 'DeviceName'
        playbook.suppression_window = '1h'
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('testing', result, "MDR must not contain 'testing' field")
        self.assertNotIn('tuning', result, "MDR must not contain 'tuning' field")
        self.assertNotIn('tags', result, "MDR must not contain 'tags' field (belongs in DOM)")

    def test_mdr_has_no_targets(self):
        """MDR must not contain a top-level 'targets' field (TideModels.MDR rejects it)."""
        playbook = _make_playbook(linked_rules=[])
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('targets', result, "MDR must not contain 'targets' field (TideModels.MDR rejects it)")

    def test_mdr_has_no_platforms(self):
        """MDR must not contain a top-level 'platforms' field (TideModels.MDR rejects it)."""
        rules = [_make_rule('KQL', 'DeviceProcessEvents | limit 10')]
        playbook = _make_playbook(linked_rules=rules)
        result = compile_mdr_yaml(playbook)
        self.assertNotIn('platforms', result, "MDR must not contain 'platforms' field (TideModels.MDR rejects it)")

    def test_mdr_defender_for_endpoint_has_impacted_entities(self):
        """defender_for_endpoint block must contain impacted_entities (required by CoreTide tide.py)."""
        rules = [_make_rule('KQL', 'DeviceProcessEvents | limit 10')]
        playbook = _make_playbook(linked_rules=rules)
        result = compile_mdr_yaml(playbook)
        dfe = result.get('configurations', {}).get('defender_for_endpoint', {})
        self.assertIn('impacted_entities', dfe,
                      "defender_for_endpoint must contain 'impacted_entities' field (CoreTide requires it)")
        self.assertIsInstance(dfe['impacted_entities'], dict,
                              "'impacted_entities' must be a dict")


class TestImpactedEntitiesInference(TestCase):
    """Tests for _infer_impacted_entities() — KQL-to-entity mapping."""

    def test_device_name_detected(self):
        kql = 'DeviceProcessEvents | project DeviceName, FileName'
        result = _infer_impacted_entities(kql)
        self.assertEqual(result.get('device'), 'DeviceName')
        self.assertNotIn('user', result)
        self.assertNotIn('mailbox', result)

    def test_device_id_only(self):
        kql = 'DeviceNetworkEvents | project DeviceId, RemoteIP'
        result = _infer_impacted_entities(kql)
        self.assertEqual(result.get('device'), 'DeviceId')

    def test_user_column_detected(self):
        kql = 'DeviceEvents | project AccountUpn, FileName'
        result = _infer_impacted_entities(kql)
        self.assertIn('user', result)
        self.assertEqual(result['user'], 'AccountUpn')

    def test_device_and_user_both_detected(self):
        # With word-boundary matching, AccountUpn does NOT match inside
        # InitiatingProcessAccountUpn, so the latter is matched by its own entry.
        kql = 'DeviceProcessEvents | project DeviceName, InitiatingProcessAccountUpn'
        result = _infer_impacted_entities(kql)
        self.assertEqual(result.get('device'), 'DeviceName')
        self.assertEqual(result.get('user'), 'InitiatingProcessAccountUpn')

    def test_mailbox_column_detected(self):
        kql = 'EmailEvents | project RecipientEmailAddress, Subject'
        result = _infer_impacted_entities(kql)
        self.assertIn('mailbox', result)
        self.assertEqual(result['mailbox'], 'RecipientEmailAddress')

    def test_empty_kql_defaults_to_device_name(self):
        self.assertEqual(_infer_impacted_entities(''), {'device': 'DeviceName'})

    def test_no_match_kql_defaults_to_device_name(self):
        kql = 'SomeTable | where SomeColumn == "value"'
        self.assertEqual(_infer_impacted_entities(kql), {'device': 'DeviceName'})

    def test_none_kql_defaults_to_device_name(self):
        self.assertEqual(_infer_impacted_entities(None), {'device': 'DeviceName'})

    def test_at_least_one_entity_key_always_present(self):
        """Generated impacted_entities must always contain at least one of device/mailbox/user."""
        test_cases = [
            '',
            'DeviceProcessEvents | project DeviceName',
            'EmailEvents | project SenderFromAddress',
            'DeviceEvents | project AccountUpn',
            'SomeRandomTable | where col == 1',
        ]
        for kql in test_cases:
            result = _infer_impacted_entities(kql)
            self.assertTrue(
                any(k in result for k in ('device', 'mailbox', 'user')),
                f"impacted_entities must have at least one key for KQL: {kql!r}, got {result}",
            )

    def test_compile_mdr_impacted_entities_conforms_to_schema(self):
        """MDR compiled from KQL must have a valid impacted_entities block (at least one key)."""
        kqls = [
            'DeviceProcessEvents | project DeviceName',
            'EmailEvents | project SenderFromAddress',
            'DeviceEvents | project AccountUpn',
            'SomeTable | limit 10',
        ]
        for kql in kqls:
            rule = _make_rule('KQL', kql)
            playbook = _make_playbook(linked_rules=[rule])
            result = compile_mdr_yaml(playbook)
            ie = result['configurations']['defender_for_endpoint']['impacted_entities']
            self.assertTrue(
                any(k in ie for k in ('device', 'mailbox', 'user')),
                f"impacted_entities must have at least one valid key for KQL: {kql!r}, got {ie}",
            )


class TestNormalizeMdrImpactedEntities(TestCase):
    """Tests for _normalize_mdr_impacted_entities() — backfill helper for commit worker."""

    def test_backfills_missing_impacted_entities(self):
        """When defender_for_endpoint exists but impacted_entities is absent it must be added."""
        mdr = {
            'configurations': {
                'defender_for_endpoint': {
                    'schema': 'defender_for_endpoint::2.0',
                    'query': 'DeviceProcessEvents | project DeviceName',
                }
            }
        }
        _normalize_mdr_impacted_entities(mdr)
        dfe = mdr['configurations']['defender_for_endpoint']
        self.assertIn('impacted_entities', dfe)
        self.assertIsInstance(dfe['impacted_entities'], dict)
        self.assertTrue(
            any(k in dfe['impacted_entities'] for k in ('device', 'mailbox', 'user'))
        )

    def test_infers_from_kql_query(self):
        """impacted_entities is inferred from the KQL query column names."""
        mdr = {
            'configurations': {
                'defender_for_endpoint': {
                    'query': 'EmailEvents | project RecipientEmailAddress',
                }
            }
        }
        _normalize_mdr_impacted_entities(mdr)
        ie = mdr['configurations']['defender_for_endpoint']['impacted_entities']
        self.assertIn('mailbox', ie)

    def test_defaults_when_no_query(self):
        """Falls back to device: DeviceName when no query column matches."""
        mdr = {
            'configurations': {
                'defender_for_endpoint': {
                    'query': '',
                }
            }
        }
        _normalize_mdr_impacted_entities(mdr)
        ie = mdr['configurations']['defender_for_endpoint']['impacted_entities']
        self.assertEqual(ie, {'device': 'DeviceName'})

    def test_does_not_overwrite_existing_impacted_entities(self):
        """If impacted_entities is already present it must not be changed."""
        original = {'device': 'CustomDeviceCol'}
        mdr = {
            'configurations': {
                'defender_for_endpoint': {
                    'query': 'DeviceEvents | project DeviceName',
                    'impacted_entities': original,
                }
            }
        }
        _normalize_mdr_impacted_entities(mdr)
        self.assertIs(
            mdr['configurations']['defender_for_endpoint']['impacted_entities'], original
        )

    def test_no_configurations_is_a_noop(self):
        """MDR dicts without configurations must not be modified."""
        mdr = {'name': 'mdr_t1059', 'metadata': {}}
        _normalize_mdr_impacted_entities(mdr)
        self.assertNotIn('configurations', mdr)

    def test_no_defender_for_endpoint_is_a_noop(self):
        """MDR dicts whose configurations don't include defender_for_endpoint are unchanged."""
        mdr = {'configurations': {'splunk': {'query': 'index=main'}}}
        _normalize_mdr_impacted_entities(mdr)
        self.assertNotIn('defender_for_endpoint', mdr['configurations'])


class TestCompileTvmYaml(TestCase):
    """Tests for compile_tvm_yaml() — CoreTide TVM schema format."""

    def test_top_level_structure(self):
        playbook = _make_playbook()
        result = compile_tvm_yaml(playbook)
        self.assertIn('name', result)
        self.assertIn('metadata', result)
        # Legacy fields must NOT be present at the top level
        self.assertNotIn('id', result)
        self.assertNotIn('title', result)
        # Fields removed per tvm::2.1 schema compliance
        self.assertNotIn('description', result)
        self.assertNotIn('mitre', result)
        self.assertNotIn('technical_context', result)
        self.assertNotIn('blind_spots', result)
        self.assertNotIn('false_positives', result)

    def test_name_is_snake_case_from_mitre(self):
        playbook = _make_playbook(technique_id='T1070')
        result = compile_tvm_yaml(playbook)
        self.assertEqual(result['name'], 'tvm_t1070')

    def test_name_is_snake_case_from_custom_id(self):
        playbook = _make_playbook(mitre_technique=None, custom_id='MY-THREAT-01')
        result = compile_tvm_yaml(playbook)
        self.assertEqual(result['name'], 'tvm_my_threat_01')

    def test_metadata_required_fields(self):
        playbook = _make_playbook()
        meta = compile_tvm_yaml(playbook)['metadata']
        for field in ('uuid', 'schema', 'version', 'tlp', 'created', 'modified'):
            self.assertIn(field, meta, f"Missing metadata field: {field}")
        self.assertEqual(meta['schema'], 'tvm::2.1')
        self.assertEqual(meta['version'], 1)
        self.assertEqual(meta['tlp'], 'amber')

    def test_metadata_author_is_string(self):
        playbook = _make_playbook(author_username='analyst1')
        meta = compile_tvm_yaml(playbook)['metadata']
        self.assertIsInstance(meta['author'], str, "metadata.author must be a plain string")
        self.assertIn('analyst1', meta['author'])

    def test_tvm_has_required_threat_fields(self):
        playbook = _make_playbook(technical_context='Windows domain controller compromise')
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})

        self.assertIn('att&ck', threat, "TVM threat missing required 'att&ck' field")
        self.assertIn('terrain', threat, "TVM threat missing required 'terrain' field")
        self.assertIn('severity', threat, "TVM threat missing required 'severity' field")
        self.assertIn('leverage', threat, "TVM threat missing required 'leverage' field")
        self.assertIn('impact', threat, "TVM threat missing required 'impact' field")
        self.assertIn('viability', threat, "TVM threat missing required 'viability' field")
        self.assertIn('description', threat, "TVM threat missing required 'description' field")

        self.assertIsInstance(threat['att&ck'], list)
        self.assertIsInstance(threat['leverage'], list)
        self.assertIsInstance(threat['impact'], list)
        self.assertIsInstance(threat['severity'], str)
        self.assertIsInstance(threat['viability'], str)

    def test_tvm_threat_always_present_without_technique(self):
        playbook = _make_playbook(mitre_technique=None, custom_id='TVM-001')
        result = compile_tvm_yaml(playbook)
        self.assertIn('threat', result, "TVM 'threat' block must always be present")
        threat = result['threat']
        self.assertEqual(threat['att&ck'], [])
        self.assertIn('severity', threat)
        self.assertIn('leverage', threat)
        self.assertIn('impact', threat)
        self.assertIn('viability', threat)

    def test_tvm_threat_severity_mapped_from_playbook(self):
        for severity, expected in [
            ('CRITICAL', 'Highly significant incident'),
            ('HIGH', 'Significant incident'),
            ('MEDIUM', 'Substantial incident'),
            ('LOW', 'Moderate incident'),
            ('INFORMATIONAL', 'Localised incident'),
        ]:
            with self.subTest(severity=severity):
                playbook = _make_playbook(default_severity=severity)
                result = compile_tvm_yaml(playbook)
                self.assertEqual(result['threat']['severity'], expected)

    def test_tvm_threat_severity_defaults_to_substantial_when_no_severity(self):
        playbook = _make_playbook()
        playbook.default_severity = None
        result = compile_tvm_yaml(playbook)
        self.assertEqual(result['threat']['severity'], 'Substantial incident')

    def test_tvm_threat_viability_defaults_to_roughly_even_chance(self):
        playbook = _make_playbook()
        result = compile_tvm_yaml(playbook)
        self.assertEqual(result['threat']['viability'], 'Roughly even chance')

    def test_tvm_threat_terrain_from_ai_enrichment(self):
        playbook = _make_playbook(technical_context='Windows host')
        result = compile_tvm_yaml(playbook, ai_enrichment={'terrain': 'AI-generated terrain'})
        self.assertEqual(result['threat']['terrain'], 'AI-generated terrain')

    def test_tvm_threat_terrain_fallback_to_technical_context(self):
        playbook = _make_playbook(technical_context='Windows host with AD')
        result = compile_tvm_yaml(playbook)
        self.assertEqual(result['threat']['terrain'], 'Windows host with AD')

    def test_tvm_threat_terrain_default_when_empty(self):
        playbook = _make_playbook(technical_context='')
        result = compile_tvm_yaml(playbook)
        self.assertEqual(result['threat']['terrain'], 'Not specified')

    def test_tvm_false_positives_omitted(self):
        """false_positives must not appear at TVM root level per tvm::2.1 schema."""
        playbook = _make_playbook(false_positives='Admin scripts')
        result = compile_tvm_yaml(playbook)
        self.assertNotIn('false_positives', result)

    def test_tvm_uuid_is_deterministic_v4(self):
        """TVM UUID must be deterministic, differ from the raw playbook UUID, and be v4 format."""
        playbook = _make_playbook()
        result = compile_tvm_yaml(playbook)
        tvm_uuid = result['metadata']['uuid']
        # Must not equal the raw playbook UUID
        self.assertNotEqual(tvm_uuid, str(playbook.id))
        # Must be valid UUID v4 format (version nibble == '4', variant nibble in [8,9,a,b])
        parsed = uuid.UUID(tvm_uuid)
        self.assertEqual(parsed.version, 4, "TVM UUID must be UUID v4")

    def test_tvm_uuid_is_deterministic(self):
        """TVM UUID must be the same across multiple calls for the same playbook."""
        playbook = _make_playbook()
        tvm1 = compile_tvm_yaml(playbook)
        tvm2 = compile_tvm_yaml(playbook)
        self.assertEqual(tvm1['metadata']['uuid'], tvm2['metadata']['uuid'])


class TestCompileDomYaml(TestCase):
    """Tests for compile_dom_yaml() — CoreTide DOM schema format."""

    def test_top_level_structure(self):
        playbook = _make_playbook()
        result = compile_dom_yaml(playbook)
        self.assertIn('name', result)
        self.assertIn('metadata', result)
        self.assertIn('objective', result)
        # tvm_ref must NOT be present — relationships are handled via objective.threats
        self.assertNotIn('tvm_ref', result)
        # Legacy fields must NOT be present at the top level
        self.assertNotIn('id', result)
        self.assertNotIn('title', result)
        # Fields that belong inside objective must NOT be at root level
        self.assertNotIn('type', result)
        self.assertNotIn('signals', result)
        self.assertNotIn('composition', result)
        self.assertNotIn('priority', result)

    def test_name_is_snake_case(self):
        playbook = _make_playbook(custom_id='DE-T1070-001')
        result = compile_dom_yaml(playbook)
        self.assertEqual(result['name'], 'dom_de_t1070_001')

    def test_metadata_required_fields(self):
        playbook = _make_playbook()
        meta = compile_dom_yaml(playbook)['metadata']
        for field in ('uuid', 'schema', 'version', 'tlp', 'created', 'modified'):
            self.assertIn(field, meta, f"Missing metadata field: {field}")
        self.assertEqual(meta['schema'], 'dom::2.1')
        self.assertEqual(meta['version'], 1)
        self.assertEqual(meta['tlp'], 'amber')

    def test_metadata_author_is_string(self):
        playbook = _make_playbook(author_username='analyst1')
        meta = compile_dom_yaml(playbook)['metadata']
        self.assertIsInstance(meta['author'], str, "metadata.author must be a plain string")
        self.assertIn('analyst1', meta['author'])

    def test_description_from_goal(self):
        playbook = _make_playbook(goal='Detect lateral movement')
        result = compile_dom_yaml(playbook)
        self.assertIn('objective', result)
        self.assertEqual(result['objective']['description'], 'Detect lateral movement')

    def test_description_fallback_to_title(self):
        playbook = _make_playbook(goal='')
        result = compile_dom_yaml(playbook)
        self.assertIn('objective', result)
        self.assertEqual(result['objective']['description'], 'Test Detection')

    def test_triage_guidance_included(self):
        playbook = _make_playbook(triage_guidance='Check process tree')
        result = compile_dom_yaml(playbook)
        self.assertEqual(result['triage_guidance'], 'Check process tree')

    def test_false_positives_omitted_from_dom_root(self):
        """false_positives must NOT appear at DOM root.

        The upstream OpenTIDE/CoreTide Detection Objective schema rejects it
        with ``Additional properties are not allowed ('false_positives' was
        unexpected)``, so emitting it would break strict schema validation.
        """
        playbook = _make_playbook(false_positives='Admin tooling false trigger')
        result = compile_dom_yaml(playbook)
        self.assertNotIn('false_positives', result)
        self.assertNotIn('false_positives', result.get('objective', {}))

    def test_dom_validation_block_from_workbench(self):
        """robustness_level + data_source_maturity from Workbench → DOM ``validation``."""
        playbook = _make_playbook()
        playbook.robustness_level = 4
        playbook.data_source_maturity = 'KERNEL_MODE'
        result = compile_dom_yaml(playbook)
        self.assertIn('validation', result)
        self.assertEqual(result['validation']['robustness_level'], 4)
        # Stored enum value KERNEL_MODE is mapped to OpenTIDE-friendly label.
        self.assertEqual(result['validation']['data_source_maturity'], 'Kernel-Mode')

    def test_dom_validation_omitted_when_empty(self):
        playbook = _make_playbook()
        playbook.robustness_level = 0
        playbook.data_source_maturity = ''
        result = compile_dom_yaml(playbook)
        self.assertNotIn('validation', result)

    def test_signals_do_not_have_data_source_field(self):
        playbook = _make_playbook(technical_context='process creation via sysmon telemetry')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertTrue(len(signals) > 0, "Expected at least one signal to be generated")
        for sig in signals:
            self.assertNotIn('data_source', sig, f"Signal {sig.get('name')} must not have invalid 'data_source' field")

    def test_signals_have_id_and_name(self):
        playbook = _make_playbook(technical_context='process creation via sysmon telemetry')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertTrue(len(signals) > 0, "Expected at least one signal to be generated")
        for sig in signals:
            self.assertIn('id', sig, f"Signal is missing required 'id' field")
            self.assertIn('name', sig, f"Signal is missing required 'name' field")

    def test_signals_do_not_have_invalid_fields(self):
        playbook = _make_playbook(technical_context='process creation via sysmon telemetry')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertTrue(len(signals) > 0, "Expected at least one signal to be generated")
        for sig in signals:
            self.assertNotIn('data_sources', sig, "Signal must not have 'data_sources' (plural) field")
            self.assertIn('data', sig, "Signal missing required 'data' field")
            self.assertIn('severity', sig, "Signal missing required 'severity' field")
            self.assertIn('methodology', sig, "Signal missing required 'methodology' field")
            self.assertIn('entities', sig, "Signal missing required 'entities' field")
            self.assertIsInstance(sig['data'], dict)
            self.assertIn('availability', sig['data'])
            self.assertIn('requirements', sig['data'])

    def test_signal_logsources_use_tool_prefix(self):
        """Log sources must use tool::name format required by OpenTIDE DOM schema."""
        playbook = _make_playbook(technical_context='process creation via sysmon telemetry')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertTrue(len(signals) > 0, "Expected at least one signal to be generated")
        for sig in signals:
            for logsource in sig.get('data', {}).get('logsources', []):
                self.assertIn('::', logsource, f"Log source '{logsource}' must use tool::name format")

    def test_signal_entities_populated(self):
        """DOM signals must have non-empty entities list derived from their data source."""
        playbook = _make_playbook(technical_context='process creation via sysmon telemetry')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertTrue(len(signals) > 0, "Expected at least one signal to be generated")
        for sig in signals:
            entities = sig.get('entities', [])
            self.assertIsInstance(entities, list, "entities must be a list")
            self.assertGreater(len(entities), 0,
                               f"Signal '{sig.get('name')}' must have at least one entity type")

    def test_signal_methodology_is_behavioural(self):
        """DOM signals must use 'Behavioural' (British spelling) methodology."""
        playbook = _make_playbook(technical_context='process creation via sysmon telemetry')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertTrue(len(signals) > 0, "Expected at least one signal to be generated")
        for sig in signals:
            self.assertEqual(sig.get('methodology'), 'Behavioural',
                             "methodology must use British spelling 'Behavioural'")

    def test_composition_is_always_present(self):
        playbook = _make_playbook()
        result = compile_dom_yaml(playbook)
        self.assertIn('composition', result['objective'])

    def test_composition_is_a_mapping(self):
        playbook = _make_playbook()
        result = compile_dom_yaml(playbook)
        composition = result['objective']['composition']
        self.assertIsInstance(composition, dict, "composition must be a dict, not a string")

    def test_composition_has_required_fields(self):
        playbook = _make_playbook()
        result = compile_dom_yaml(playbook)
        composition = result['objective']['composition']
        self.assertIn('strategy', composition)
        self.assertIn('description', composition)

    def test_composition_independent_when_no_signals(self):
        playbook = _make_playbook()  # no technical_context → no signals
        result = compile_dom_yaml(playbook)
        composition = result['objective']['composition']
        self.assertEqual(composition['strategy'], 'Independent')

    def test_composition_independent_when_single_signal(self):
        # 'registry regedit' only matches Registry Telemetry (no other keywords)
        playbook = _make_playbook(technical_context='registry regedit')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertEqual(len(signals), 1, "Expected exactly one signal for single-keyword context")
        composition = result['objective']['composition']
        self.assertEqual(composition['strategy'], 'Independent')

    def test_composition_combined_when_multiple_signals(self):
        # 'sysmon windows event log network traffic' matches Sysmon + Windows Event Log + Network
        playbook = _make_playbook(technical_context='sysmon windows event log network traffic')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertGreater(len(signals), 1, "Expected multiple signals for multi-keyword context")
        composition = result['objective']['composition']
        self.assertEqual(composition['strategy'], 'Combined')

    def test_signal_uuids_are_deterministic(self):
        """Signal UUIDs must be the same across multiple calls for the same playbook."""
        playbook = _make_playbook(technical_context='sysmon windows event log process creation')
        result1 = compile_dom_yaml(playbook)
        result2 = compile_dom_yaml(playbook)
        sigs1 = result1.get('objective', {}).get('signals', [])
        sigs2 = result2.get('objective', {}).get('signals', [])
        self.assertEqual(len(sigs1), len(sigs2))
        for s1, s2 in zip(sigs1, sigs2):
            self.assertEqual(
                s1['uuid'], s2['uuid'],
                f"Signal UUID for '{s1.get('name')}' must be deterministic across calls"
            )

    def test_signal_uuids_are_valid_v4(self):
        """Each signal UUID must be a valid UUID v4 string."""
        playbook = _make_playbook(technical_context='process creation via sysmon telemetry')
        result = compile_dom_yaml(playbook)
        signals = result.get('objective', {}).get('signals', [])
        self.assertTrue(len(signals) > 0)
        for sig in signals:
            parsed = uuid.UUID(sig['uuid'])
            self.assertEqual(parsed.version, 4, f"Signal UUID {sig['uuid']} must be UUID v4")


class TestTvmCriticality(TestCase):
    """Tests for the `criticality` field in compile_tvm_yaml()."""

    def test_criticality_present(self):
        playbook = _make_playbook(default_severity='HIGH')
        result = compile_tvm_yaml(playbook)
        self.assertIn('criticality', result)

    def test_criticality_critical(self):
        playbook = _make_playbook(default_severity='CRITICAL')
        self.assertEqual(compile_tvm_yaml(playbook)['criticality'], 'Critical')

    def test_criticality_high(self):
        playbook = _make_playbook(default_severity='HIGH')
        self.assertEqual(compile_tvm_yaml(playbook)['criticality'], 'High')

    def test_criticality_medium(self):
        playbook = _make_playbook(default_severity='MEDIUM')
        self.assertEqual(compile_tvm_yaml(playbook)['criticality'], 'Medium')

    def test_criticality_low(self):
        playbook = _make_playbook(default_severity='LOW')
        self.assertEqual(compile_tvm_yaml(playbook)['criticality'], 'Low')

    def test_criticality_informational_maps_to_low(self):
        playbook = _make_playbook(default_severity='INFORMATIONAL')
        self.assertEqual(compile_tvm_yaml(playbook)['criticality'], 'Low')

    def test_criticality_case_insensitive(self):
        playbook = _make_playbook(default_severity='high')
        self.assertEqual(compile_tvm_yaml(playbook)['criticality'], 'High')


class TestDomObjectiveThreats(TestCase):
    """Tests for the `objective.threats` field in compile_dom_yaml()."""

    def test_threats_contains_tvm_uuid(self):
        """objective.threats must contain the TVM UUID, not the TVM snake_case name."""
        playbook = _make_playbook(technique_id='T1059')
        result = compile_dom_yaml(playbook)
        threats = result.get('objective', {}).get('threats', [])
        expected_tvm_uuid = _deterministic_uuid4(playbook.id, 'tvm')
        self.assertEqual(threats, [expected_tvm_uuid])

    def test_threats_not_empty(self):
        playbook = _make_playbook()
        result = compile_dom_yaml(playbook)
        threats = result.get('objective', {}).get('threats', [])
        self.assertIsInstance(threats, list)
        self.assertGreater(len(threats), 0, "objective.threats must not be empty")

    def test_threats_uuid_is_deterministic(self):
        """DOM threats UUID must match the TVM UUID for the same playbook."""
        playbook = _make_playbook(mitre_technique=None, custom_id='MY-001')
        result = compile_dom_yaml(playbook)
        threats = result.get('objective', {}).get('threats', [])
        expected_tvm_uuid = _deterministic_uuid4(playbook.id, 'tvm')
        self.assertEqual(threats, [expected_tvm_uuid])

    def test_threats_does_not_contain_snake_case_name(self):
        """objective.threats must not use legacy snake_case TVM names."""
        playbook = _make_playbook(technique_id='T1059')
        result = compile_dom_yaml(playbook)
        threats = result.get('objective', {}).get('threats', [])
        for threat_ref in threats:
            self.assertNotEqual(threat_ref, 'tvm_t1059', "threats must use UUID, not snake_case name")


class TestDomTvmRef(TestCase):
    """Tests that the DOM links back to the TVM via objective.threats (not tvm_ref)."""

    def test_tvm_ref_not_present(self):
        """DOM must NOT have a top-level tvm_ref — relationships are via objective.threats."""
        playbook = _make_playbook(technique_id='T1059')
        result = compile_dom_yaml(playbook)
        self.assertNotIn('tvm_ref', result, "DOM must not contain deprecated top-level 'tvm_ref'")

    def test_tvm_uuid_in_objective_threats(self):
        """DOM objective.threats must contain the TVM UUID linking back to the parent TVM."""
        playbook = _make_playbook(technique_id='T1059')
        result = compile_dom_yaml(playbook)
        tvm = compile_tvm_yaml(playbook)
        threats = result.get('objective', {}).get('threats', [])
        self.assertIn(tvm['metadata']['uuid'], threats,
                      "DOM objective.threats must include the TVM UUID")

    def test_threats_list_not_empty(self):
        """DOM objective.threats must not be empty."""
        playbook = _make_playbook(custom_id='DE-T1003-001')
        result = compile_dom_yaml(playbook)
        threats = result.get('objective', {}).get('threats', [])
        self.assertTrue(len(threats) >= 1, "DOM objective.threats must contain at least one entry")

    def test_threats_contains_valid_uuid(self):
        """DOM objective.threats entries must be valid UUID v4 strings."""
        playbook = _make_playbook(technique_id='T1070')
        result = compile_dom_yaml(playbook)
        threats = result.get('objective', {}).get('threats', [])
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        )
        for entry in threats:
            self.assertRegex(entry, uuid_pattern, f"Threat entry '{entry}' must be a UUID v4")


class TestMetadataAuthorObject(TestCase):
    """Tests that metadata.author is a plain string across all object types."""

    def test_tvm_author_is_object_with_name(self):
        playbook = _make_playbook(author_username='analyst1')
        meta = compile_tvm_yaml(playbook)['metadata']
        self.assertIsInstance(meta['author'], str)
        self.assertIn('analyst1', meta['author'])

    def test_tvm_author_includes_organisation(self):
        playbook = _make_playbook(author_username='analyst1', org_name='SecOps Team')
        meta = compile_tvm_yaml(playbook)['metadata']
        self.assertIsInstance(meta['author'], str)
        self.assertIn('SecOps Team', meta['author'])

    def test_dom_author_is_object_with_name(self):
        playbook = _make_playbook(author_username='analyst1')
        meta = compile_dom_yaml(playbook)['metadata']
        self.assertIsInstance(meta['author'], str)
        self.assertIn('analyst1', meta['author'])

    def test_mdr_author_is_object_with_name(self):
        playbook = _make_playbook(author_username='analyst1', linked_rules=[])
        meta = compile_mdr_yaml(playbook)['metadata']
        self.assertIsInstance(meta['author'], str)
        self.assertIn('analyst1', meta['author'])


class TestMdrAlertSeverityTitleCase(TestCase):
    """Tests that MDR response.alert_severity uses Title Case (CoreTide spec)."""

    def test_critical_maps_to_title_case(self):
        playbook = _make_playbook(default_severity='CRITICAL', linked_rules=[])
        self.assertEqual(compile_mdr_yaml(playbook)['response']['alert_severity'], 'Critical')

    def test_high_maps_to_title_case(self):
        playbook = _make_playbook(default_severity='HIGH', linked_rules=[])
        self.assertEqual(compile_mdr_yaml(playbook)['response']['alert_severity'], 'High')

    def test_medium_maps_to_title_case(self):
        playbook = _make_playbook(default_severity='MEDIUM', linked_rules=[])
        self.assertEqual(compile_mdr_yaml(playbook)['response']['alert_severity'], 'Medium')

    def test_low_maps_to_title_case(self):
        playbook = _make_playbook(default_severity='LOW', linked_rules=[])
        self.assertEqual(compile_mdr_yaml(playbook)['response']['alert_severity'], 'Low')

    def test_informational_maps_to_title_case(self):
        playbook = _make_playbook(default_severity='INFORMATIONAL', linked_rules=[])
        self.assertEqual(compile_mdr_yaml(playbook)['response']['alert_severity'], 'Informational')




    def test_default_tlp_is_amber(self):
        playbook = _make_playbook()
        tvm = compile_tvm_yaml(playbook)
        self.assertEqual(tvm['metadata']['tlp'], 'amber')

    def test_tlp_clear(self):
        playbook = _make_playbook(tlp_classification='CLEAR')
        tvm = compile_tvm_yaml(playbook)
        self.assertEqual(tvm['metadata']['tlp'], 'clear')

    def test_tlp_green(self):
        playbook = _make_playbook(tlp_classification='GREEN')
        tvm = compile_tvm_yaml(playbook)
        self.assertEqual(tvm['metadata']['tlp'], 'green')

    def test_tlp_amber_strict(self):
        playbook = _make_playbook(tlp_classification='AMBER+STRICT')
        tvm = compile_tvm_yaml(playbook)
        self.assertEqual(tvm['metadata']['tlp'], 'amber+strict')

    def test_tlp_red(self):
        playbook = _make_playbook(tlp_classification='RED')
        tvm = compile_tvm_yaml(playbook)
        self.assertEqual(tvm['metadata']['tlp'], 'red')

    def test_tlp_applied_to_dom(self):
        playbook = _make_playbook(tlp_classification='GREEN')
        dom = compile_dom_yaml(playbook)
        self.assertEqual(dom['metadata']['tlp'], 'green')

    def test_tlp_applied_to_mdr(self):
        playbook = _make_playbook(tlp_classification='RED', linked_rules=[])
        mdr = compile_mdr_yaml(playbook)
        self.assertEqual(mdr['metadata']['tlp'], 'red')

    def test_empty_tlp_defaults_to_amber(self):
        playbook = _make_playbook(tlp_classification='')
        tvm = compile_tvm_yaml(playbook)
        self.assertEqual(tvm['metadata']['tlp'], 'amber')


class TestExtractThreatSurface(TestCase):
    """Tests for _extract_threat_surface() helper."""

    def test_empty_context_returns_empty(self):
        self.assertEqual(_extract_threat_surface(''), [])

    def test_none_returns_empty(self):
        self.assertEqual(_extract_threat_surface(None), [])

    def test_windows_detected(self):
        surfaces = _extract_threat_surface('Targets Windows endpoints via WMI')
        self.assertIn('host::Hostname', surfaces)

    def test_linux_detected(self):
        surfaces = _extract_threat_surface('Linux kernel privilege escalation via SUID')
        self.assertIn('host::Hostname', surfaces)

    def test_macos_detected(self):
        surfaces = _extract_threat_surface('macOS persistence via LaunchAgent')
        self.assertIn('host::Hostname', surfaces)

    def test_all_surfaces_use_domain_entity_format(self):
        """All auto-detected surfaces must use the domain::Entity format."""
        surfaces = _extract_threat_surface(
            'Windows endpoint linux server macos workstation android ios'
        )
        for surface in surfaces:
            self.assertIn('::', surface, f"Surface '{surface}' must use domain::Entity format")

    def test_no_duplicates(self):
        surfaces = _extract_threat_surface('Windows Windows Windows')
        # Windows maps to host::Hostname, should appear only once
        self.assertEqual(len(surfaces), surfaces.count(surfaces[0]) if surfaces else 0)

    def test_surface_added_to_tvm_threat_block(self):
        playbook = _make_playbook(
            technical_context='Windows endpoint process creation via Sysmon'
        )
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        self.assertIn('surface', threat)
        # Should detect host::Process (from "process creation") and host::Hostname (from "windows")
        surfaces = threat['surface']
        self.assertTrue(any('::' in s for s in surfaces), "Surface entries must use domain::Entity format")


class TestTvmReferences(TestCase):
    """Tests for references block in compile_tvm_yaml()."""

    def test_no_references_when_empty(self):
        playbook = _make_playbook(public_references=[], internal_references=[])
        result = compile_tvm_yaml(playbook)
        self.assertNotIn('references', result)

    def test_public_references_numbered(self):
        playbook = _make_playbook(public_references=['https://example.com', 'https://other.com'])
        result = compile_tvm_yaml(playbook)
        refs = result.get('references', {})
        self.assertIn('public', refs)
        self.assertEqual(refs['public']['1'], 'https://example.com')
        self.assertEqual(refs['public']['2'], 'https://other.com')

    def test_internal_references_lettered(self):
        playbook = _make_playbook(internal_references=['JIRA-1234', 'CASE-5678'])
        result = compile_tvm_yaml(playbook)
        refs = result.get('references', {})
        self.assertIn('internal', refs)
        self.assertEqual(refs['internal']['a'], 'JIRA-1234')
        self.assertEqual(refs['internal']['b'], 'CASE-5678')

    def test_both_references_present(self):
        playbook = _make_playbook(
            public_references=['https://example.com'],
            internal_references=['JIRA-1234'],
        )
        result = compile_tvm_yaml(playbook)
        refs = result.get('references', {})
        self.assertIn('public', refs)
        self.assertIn('internal', refs)


class TestTvmThreatActors(TestCase):
    """Tests for threat actor attribution in compile_tvm_yaml()."""

    def test_no_actors_when_empty(self):
        playbook = _make_playbook(threat_actors=[])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        self.assertNotIn('actors', threat)

    def test_actors_included_with_group_id(self):
        """Actors with ATT&CK group_id are included as att&ck:: strings."""
        playbook = _make_playbook(threat_actors=[
            {'name': 'APT29', 'group_id': 'G0016', 'aliases': ['Cozy Bear']},
        ])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        self.assertIn('actors', threat)
        self.assertEqual(len(threat['actors']), 1)
        self.assertEqual(threat['actors'][0], 'att&ck::G0016')

    def test_actors_without_group_id_use_custom_fallback(self):
        """Actors without an ATT&CK group_id fall back to custom:: namespace."""
        playbook = _make_playbook(threat_actors=[
            {'name': 'APT29', 'aliases': ['Cozy Bear']},  # no group_id → custom fallback
        ])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        self.assertIn('actors', threat)
        self.assertEqual(threat['actors'], ['custom::APT29'])

    def test_actors_mixed_valid_and_invalid(self):
        """Actors with group_id use att&ck:: prefix; actors without use custom:: prefix."""
        playbook = _make_playbook(threat_actors=[
            {'name': 'APT28', 'group_id': 'G0007'},
            {'name': 'Unknown Actor'},  # no group_id → custom fallback
        ])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        actors = threat.get('actors', [])
        self.assertEqual(len(actors), 2)
        self.assertEqual(actors[0], 'att&ck::G0007')
        self.assertEqual(actors[1], 'custom::Unknown Actor')

    def test_invalid_actor_entries_skipped(self):
        """Non-dict entries (strings, None) are always skipped."""
        playbook = _make_playbook(threat_actors=['invalid', None, {'name': 'APT28', 'group_id': 'G0007'}])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        actors = threat.get('actors', [])
        self.assertEqual(len(actors), 1)
        self.assertEqual(actors[0], 'att&ck::G0007')

    def test_empty_actor_dict_skipped(self):
        playbook = _make_playbook(threat_actors=[{}])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        self.assertNotIn('actors', threat)

    def test_custom_actor_without_attck_group(self):
        """Actor dicts without group_id but with a name produce custom:: entries."""
        playbook = _make_playbook(threat_actors=[
            {'name': 'FIN7'},
            {'name': 'Lazarus Group'},
        ])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        actors = threat.get('actors', [])
        self.assertEqual(actors, ['custom::FIN7', 'custom::Lazarus Group'])

    def test_custom_actor_name_whitespace_stripped(self):
        """Custom actor names have leading/trailing whitespace stripped."""
        playbook = _make_playbook(threat_actors=[
            {'name': '  Scattered Spider  '},
        ])
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        actors = threat.get('actors', [])
        self.assertEqual(actors, ['custom::Scattered Spider'])


class TestTvmThreatSurfaceManualOverride(TestCase):
    """Tests for manual threat_surface override field in compile_tvm_yaml()."""

    def test_manual_surface_used_when_set(self):
        """Manual surfaces take precedence and appear first."""
        playbook = _make_playbook(
            technical_context='',
            threat_surface=['host::Hostname', 'host::Process'],
        )
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        self.assertIn('surface', threat)
        self.assertEqual(threat['surface'][:2], ['host::Hostname', 'host::Process'])

    def test_manual_surface_merged_with_auto(self):
        """Auto-detected surfaces are appended to manual ones (no duplicates)."""
        playbook = _make_playbook(
            technical_context='process execution on endpoint',
            threat_surface=['cloud::Account'],
        )
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        surfaces = threat.get('surface', [])
        # Manual surface appears first
        self.assertEqual(surfaces[0], 'cloud::Account')
        # Auto-detected surfaces are merged in
        self.assertTrue(len(surfaces) >= 1)

    def test_no_duplicates_when_manual_and_auto_overlap(self):
        """If manual and auto surface overlap, no duplicates in output."""
        playbook = _make_playbook(
            technical_context='Windows endpoint',
            threat_surface=['host::Hostname'],
        )
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        surfaces = threat.get('surface', [])
        self.assertEqual(surfaces.count('host::Hostname'), 1)

    def test_empty_manual_surface_falls_back_to_auto(self):
        """When threat_surface is empty, auto-detection still works."""
        playbook = _make_playbook(
            technical_context='Windows endpoint',
            threat_surface=[],
        )
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        surfaces = threat.get('surface', [])
        # host::Hostname should be detected from 'windows' and 'endpoint' keywords
        self.assertIn('host::Hostname', surfaces)

    def test_no_surface_when_both_empty(self):
        """No surface key emitted when there are no surfaces at all."""
        playbook = _make_playbook(
            technical_context='Some generic context without surface keywords',
            threat_surface=[],
        )
        result = compile_tvm_yaml(playbook)
        threat = result.get('threat', {})
        # If there are no surface keywords in context and no manual, key absent
        self.assertNotIn('surface', threat)


class TestUniqueUuidsAcrossObjects(TestCase):
    """Verify that TVM, DOM, and MDR each get a distinct UUID."""

    def test_tvm_dom_mdr_have_different_uuids(self):
        """TVM, DOM, and MDR must not share the same metadata.uuid."""
        playbook = _make_playbook(linked_rules=[])
        tvm = compile_tvm_yaml(playbook)
        dom = compile_dom_yaml(playbook)
        mdr = compile_mdr_yaml(playbook)

        tvm_uuid = tvm['metadata']['uuid']
        dom_uuid = dom['metadata']['uuid']
        mdr_uuid = mdr['metadata']['uuid']

        self.assertNotEqual(tvm_uuid, dom_uuid, "TVM and DOM must not share the same UUID")
        self.assertNotEqual(tvm_uuid, mdr_uuid, "TVM and MDR must not share the same UUID")
        self.assertNotEqual(dom_uuid, mdr_uuid, "DOM and MDR must not share the same UUID")

    def test_dom_uuid_is_deterministic(self):
        """DOM UUID must be the same across multiple calls for the same playbook."""
        playbook = _make_playbook(linked_rules=[])
        dom1 = compile_dom_yaml(playbook)
        dom2 = compile_dom_yaml(playbook)
        self.assertEqual(dom1['metadata']['uuid'], dom2['metadata']['uuid'])

    def test_mdr_uuid_is_deterministic(self):
        """MDR UUID must be the same across multiple calls for the same playbook."""
        playbook = _make_playbook(linked_rules=[])
        mdr1 = compile_mdr_yaml(playbook)
        mdr2 = compile_mdr_yaml(playbook)
        self.assertEqual(mdr1['metadata']['uuid'], mdr2['metadata']['uuid'])
