"""
Unit tests for rules.metadata_injector.inject_metadata().
"""

import re
import uuid
from django.test import SimpleTestCase

from rules.metadata_injector import inject_metadata


SAMPLE_YAML = "title: Test\nstatus: experimental\n"
SAMPLE_KQL = "DeviceProcessEvents\n| where ProcessCommandLine contains 'malicious'\n"
SAMPLE_SPL = "index=main sourcetype=syslog\n"
SAMPLE_WAZUH = "<rule id=\"100001\" level=\"7\"><description>test</description></rule>\n"
SAMPLE_OTHER = "some rule content\n"

TEST_RULE_ID = "550e8400-e29b-41d4-a716-446655440000"

FULL_META = dict(
    author="john_analyst",
    rule_name="Suspicious PowerShell Execution",
    description="Detect suspicious PowerShell execution",
    tags=["execution", "powershell"],
    severity="HIGH",
    status="DRAFT",
    mitre_technique="T1059.001",
    rule_id=TEST_RULE_ID,
)


class TestInjectMetadataYaml(SimpleTestCase):
    def _injected(self, **kwargs):
        meta = {**FULL_META, **kwargs}
        return inject_metadata(rule_content=SAMPLE_YAML, rule_format="OTHER", **meta)

    def test_contains_original_content(self):
        result = self._injected()
        self.assertIn(SAMPLE_YAML, result)

    def test_uses_hash_comments(self):
        result = self._injected()
        self.assertIn("# Rule Metadata", result)
        self.assertIn("# Author: john_analyst", result)

    def test_contains_all_fields(self):
        result = self._injected()
        self.assertIn("# Rule name: Suspicious PowerShell Execution", result)
        self.assertIn("# Description: Detect suspicious PowerShell execution", result)
        self.assertIn("# Tags: execution, powershell", result)
        self.assertIn("# Severity: HIGH", result)
        self.assertIn("# Status: DRAFT", result)
        self.assertIn("# MITRE technique: T1059.001", result)

    def test_uses_provided_rule_id(self):
        result = self._injected()
        self.assertIn(f"# ID: {TEST_RULE_ID}", result)

    def test_same_id_on_repeated_calls(self):
        r1 = self._injected()
        r2 = self._injected()
        id1 = re.search(r"# ID: ([0-9a-f-]+)", r1).group(1)
        id2 = re.search(r"# ID: ([0-9a-f-]+)", r2).group(1)
        self.assertEqual(id1, id2)

    def test_metadata_before_content(self):
        result = self._injected()
        meta_pos = result.index("# Rule Metadata")
        content_pos = result.index(SAMPLE_YAML)
        self.assertLess(meta_pos, content_pos)

    def test_blank_line_between_metadata_and_content(self):
        result = self._injected()
        # The separator line ends with '======\n' and is followed by '\n' then rule content
        self.assertRegex(result, r"={3,}\n\n" + re.escape(SAMPLE_YAML))


class TestInjectMetadataKql(SimpleTestCase):
    def _injected(self, **kwargs):
        meta = {**FULL_META, **kwargs}
        return inject_metadata(rule_content=SAMPLE_KQL, rule_format="KQL", **meta)

    def test_uses_double_slash_comments(self):
        result = self._injected()
        self.assertIn("// Rule Metadata", result)
        self.assertIn("// Author: john_analyst", result)

    def test_contains_original_content(self):
        result = self._injected()
        self.assertIn(SAMPLE_KQL, result)

    def test_uses_provided_rule_id(self):
        result = self._injected()
        self.assertIn(f"// ID: {TEST_RULE_ID}", result)


class TestInjectMetadataSpl(SimpleTestCase):
    def _injected(self, **kwargs):
        meta = {**FULL_META, **kwargs}
        return inject_metadata(rule_content=SAMPLE_SPL, rule_format="SPL", **meta)

    def test_uses_hash_comments(self):
        result = self._injected()
        self.assertIn("# Rule Metadata", result)

    def test_contains_original_content(self):
        result = self._injected()
        self.assertIn(SAMPLE_SPL, result)


class TestInjectMetadataWazuh(SimpleTestCase):
    def _injected(self, **kwargs):
        meta = {**FULL_META, **kwargs}
        return inject_metadata(rule_content=SAMPLE_WAZUH, rule_format="WAZUH", **meta)

    def test_uses_xml_comment(self):
        result = self._injected()
        self.assertTrue(result.startswith("<!--\n"))
        self.assertIn("-->", result)

    def test_contains_all_fields(self):
        result = self._injected()
        self.assertIn("Author: john_analyst", result)
        self.assertIn("Rule name: Suspicious PowerShell Execution", result)
        self.assertIn("Severity: HIGH", result)
        self.assertIn("Status: DRAFT", result)
        self.assertIn("MITRE technique: T1059.001", result)

    def test_contains_original_content(self):
        result = self._injected()
        self.assertIn(SAMPLE_WAZUH, result)

    def test_uses_provided_rule_id(self):
        result = self._injected()
        self.assertIn(f"ID: {TEST_RULE_ID}", result)


class TestInjectMetadataOther(SimpleTestCase):
    def _injected(self, **kwargs):
        meta = {**FULL_META, **kwargs}
        return inject_metadata(rule_content=SAMPLE_OTHER, rule_format="OTHER", **meta)

    def test_uses_hash_comments(self):
        result = self._injected()
        self.assertIn("# Rule Metadata", result)

    def test_contains_original_content(self):
        result = self._injected()
        self.assertIn(SAMPLE_OTHER, result)


class TestInjectMetadataAql(SimpleTestCase):
    def test_uses_double_dash_comments(self):
        result = inject_metadata(
            rule_content="SELECT * FROM events",
            rule_format="AQL",
            author="alice",
            rule_name="AQL rule",
            severity="MEDIUM",
            status="DRAFT",
            mitre_technique="T0000",
        )
        self.assertIn("-- Rule Metadata", result)
        self.assertIn("-- Author: alice", result)


class TestInjectMetadataMissingFields(SimpleTestCase):
    """Test fallback to 'NA' for missing/blank optional fields."""

    def test_severity_na(self):
        result = inject_metadata(
            rule_content=SAMPLE_YAML, rule_format="OTHER",
            author="alice", rule_name="Test Rule",
            severity="NA", status="NA", mitre_technique="NA",
        )
        self.assertIn("# Severity: NA", result)
        self.assertIn("# Status: NA", result)
        self.assertIn("# MITRE technique: NA", result)

    def test_unknown_format_falls_back_to_hash(self):
        result = inject_metadata(
            rule_content=SAMPLE_OTHER, rule_format="UNKNOWN_FORMAT",
            author="bob", rule_name="Rule", severity="LOW",
            status="DEPLOYED", mitre_technique="T1234",
        )
        self.assertIn("# Rule Metadata", result)
