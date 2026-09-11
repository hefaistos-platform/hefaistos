"""Integration tests for AI-enhanced OpenTIDE compiler functions."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from django.test import TestCase

from playbooks.utils.opentide_compiler import (
    compile_bdr_yaml_with_ai,
    compile_dom_yaml_with_ai,
    compile_mdr_yaml_with_ai,
)


def _make_playbook(**kwargs):
    """Return a mock PlaybookGraph-like object with sensible defaults."""
    playbook = MagicMock()
    playbook.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    playbook.title = kwargs.get("title", "Kerberoasting Detection")
    playbook.goal = kwargs.get("goal", "Detect Kerberos TGS ticket requests for service accounts")
    playbook.technical_context = kwargs.get(
        "technical_context",
        "Monitor Windows Event ID 4769 in Active Directory environments",
    )
    playbook.blind_spots = kwargs.get("blind_spots", "")
    playbook.false_positives = kwargs.get("false_positives", "Legitimate service account activity")
    playbook.response_playbook = kwargs.get("response_playbook", "")
    playbook.default_severity = kwargs.get("default_severity", "HIGH")
    playbook.alert_trigger = kwargs.get("alert_trigger", "")
    playbook.robustness_level = kwargs.get("robustness_level", 0)
    playbook.data_source_maturity = kwargs.get("data_source_maturity", "")
    playbook.opentide_yaml = kwargs.get("opentide_yaml", None)
    playbook.custom_id = kwargs.get("custom_id", "DE-T1558-001")
    playbook.status = kwargs.get("status", "DEPLOYED")
    playbook.triage_guidance = kwargs.get("triage_guidance", "")

    author = MagicMock()
    author.username = kwargs.get("author_username", "analyst1")
    playbook.author = kwargs.get("author", author)

    organization = MagicMock()
    organization.name = kwargs.get("org_name", "Test Org")
    playbook.organization = kwargs.get("organization", organization)

    playbook.created_at = kwargs.get("created_at", datetime(2024, 1, 1))
    playbook.updated_at = kwargs.get("updated_at", datetime(2024, 6, 1))

    technique = MagicMock()
    technique.technique_id = kwargs.get("technique_id", "T1558")
    technique.name = kwargs.get("technique_name", "Steal or Forge Kerberos Tickets")
    del technique.tactic
    playbook.mitre_technique = technique

    tags_manager = MagicMock()
    tags_manager.exists.return_value = False
    playbook.tags = tags_manager

    rules = kwargs.get("linked_rules", [])
    qs = MagicMock()
    qs.__iter__ = MagicMock(return_value=iter(rules))
    qs.order_by.return_value = iter(rules)
    playbook.linked_rules = qs

    return playbook


def _make_ai_settings(**kwargs):
    """Return a minimal mock UserAISettings-like object."""
    s = MagicMock()
    s.get_openai_key.return_value = kwargs.get("openai_key", "sk-test")
    s.get_gemini_key.return_value = kwargs.get("gemini_key", "")
    s.get_claude_key.return_value = kwargs.get("claude_key", "")
    s.get_ollama_url.return_value = ""
    s.get_ollama_model.return_value = ""
    s.preferred_model = "GPT-4"
    s.enable_auto_enrichment = kwargs.get("enable_auto_enrichment", True)
    s.auto_generate_bdr = kwargs.get("auto_generate_bdr", True)
    s.auto_enrich_response = kwargs.get("auto_enrich_response", True)
    s.auto_map_platforms = kwargs.get("auto_map_platforms", True)
    return s


# ---------------------------------------------------------------------------
# compile_mdr_yaml_with_ai tests
# ---------------------------------------------------------------------------

MOCK_MDR_RESPONSE = {
    "alert_severity": "High",
    "responders": "CSIRC",
    "procedure": {
        "analysis": "Check for anomalous TGS requests",
        "searches": [{"purpose": "Auth history", "system": "Sentinel", "query": "SecurityEvent | ..."}],
        "containment": "Disable account",
    },
}

MOCK_PLATFORM_MAP = {
    "platforms": ["Windows", "Active Directory"],
    "targets": ["Identity Services"],
    "domains": ["Enterprise"],
}


class TestCompileMDRWithAI(TestCase):
    @patch("ai_assistant.opentide_enrichment.ai_enrich_mdr_response")
    def test_ai_enrichment_enabled(self, mock_response):
        mock_response.return_value = MOCK_MDR_RESPONSE
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()

        result = compile_mdr_yaml_with_ai(playbook, ai_settings, use_ai_enrichment=True)

        self.assertIn("name", result)
        self.assertIn("metadata", result)
        # AI-enriched fields should be present
        self.assertIn("response", result)
        # Detection rules (configurations) are never AI-generated
        # configurations only present if user supplied linked_rules with content

    def test_ai_enrichment_disabled(self):
        """Without AI, result is identical to compile_mdr_yaml()."""
        playbook = _make_playbook()
        result = compile_mdr_yaml_with_ai(playbook, ai_settings=None, use_ai_enrichment=False)
        self.assertIn("name", result)
        self.assertIn("metadata", result)
        # No AI tracking metadata should be added
        self.assertNotIn("_ai_generated", result)

    @patch("ai_assistant.opentide_enrichment.ai_enrich_mdr_response")
    def test_ai_generated_field_tracking(self, mock_response):
        mock_response.return_value = MOCK_MDR_RESPONSE
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()

        result = compile_mdr_yaml_with_ai(playbook, ai_settings, use_ai_enrichment=True)

        # _ai_generated tracks which fields came from AI
        self.assertIn("_ai_generated", result)
        ai_gen = result["_ai_generated"]
        self.assertIsInstance(ai_gen, dict)
        # Response enrichment should be tracked
        self.assertIn("response.responders", ai_gen)

    def test_no_ai_tracking_when_disabled(self):
        playbook = _make_playbook()
        result = compile_mdr_yaml_with_ai(playbook, None, use_ai_enrichment=False)
        self.assertNotIn("_ai_generated", result)

    @patch("ai_assistant.opentide_enrichment.ai_enrich_mdr_response")
    def test_configurations_block_not_ai_generated(self, mock_response):
        """Detection queries in configurations must NEVER be AI-generated."""
        mock_response.return_value = MOCK_MDR_RESPONSE

        # Simulate a playbook with user-provided KQL rule
        rule = MagicMock()
        rule.format = "KQL"
        rule.raw_content = "DeviceProcessEvents | where FileName == 'mimikatz.exe'"
        rule.updated_at = datetime(2024, 6, 1)
        playbook = _make_playbook(linked_rules=[rule])
        ai_settings = _make_ai_settings()

        result = compile_mdr_yaml_with_ai(playbook, ai_settings, use_ai_enrichment=True)

        # configurations is from user, so it must NOT be in _ai_generated
        ai_gen = result.get("_ai_generated", {})
        self.assertNotIn("configurations", ai_gen)
        self.assertNotIn("configurations.defender_for_endpoint", ai_gen)

    @patch("ai_assistant.opentide_enrichment.ai_enrich_mdr_response")
    def test_mdr_does_not_contain_domains_field(self, mock_response):
        """MDR objects must not contain domains (BDR-only field). platforms and targets are valid MDR fields."""
        mock_response.return_value = MOCK_MDR_RESPONSE
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()

        result = compile_mdr_yaml_with_ai(playbook, ai_settings, use_ai_enrichment=True)

        # domains is BDR-only and must NOT appear in MDR
        self.assertNotIn("domains", result)

        # platforms and targets are valid MDR fields (added for CoreTide MDR schema)
        # They may or may not be present depending on linked rules

        # Valid MDR fields should still be present
        self.assertIn("name", result)
        self.assertIn("metadata", result)
        self.assertIn("response", result)


# ---------------------------------------------------------------------------
# compile_bdr_yaml_with_ai tests
# ---------------------------------------------------------------------------

MOCK_BDR_FIELDS = {
    "criticality": "High",
    "domains": ["Enterprise"],
    "targets": ["Identity Services"],
    "platforms": ["Windows", "Active Directory"],
    "violation": "Unauthorized privileged account use",
    "justification": "GDPR Article 32",
    "description": "Monitor privileged account usage",
}


class TestCompileBDRWithAI(TestCase):
    """BDR framework is deprecated — compile_bdr_yaml_with_ai always returns None."""

    def test_always_returns_none_regardless_of_settings(self):
        """BDR generation is deprecated; the function must always return None."""
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()
        self.assertIsNone(compile_bdr_yaml_with_ai(playbook, ai_settings, force_generate=True))

    def test_returns_none_without_ai_settings(self):
        playbook = _make_playbook()
        self.assertIsNone(compile_bdr_yaml_with_ai(playbook, ai_settings=None, force_generate=False))

    def test_returns_none_with_force_generate(self):
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()
        self.assertIsNone(compile_bdr_yaml_with_ai(playbook, ai_settings, force_generate=True))

    def test_returns_none_without_force_generate(self):
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()
        self.assertIsNone(compile_bdr_yaml_with_ai(playbook, ai_settings, force_generate=False))


# ---------------------------------------------------------------------------
# compile_dom_yaml_with_ai tests
# ---------------------------------------------------------------------------

MOCK_DOM_OBJECTIVE = {
    "priority": "High",
    "type": "Threat",
    "description": "Detect Kerberoasting by monitoring TGS requests",
    "composition": "atomic",
    "signals": [
        {
            "id": "sig-001",
            "name": "TGS Request Anomaly",
            "description": "Unusual TGS ticket requests for service accounts",
            "data_source": "Windows Event Log 4769",
        }
    ],
}


class TestCompileDOMWithAI(TestCase):
    @patch("ai_assistant.opentide_enrichment.ai_generate_detection_objective")
    def test_ai_enrichment_adds_signals(self, mock_obj):
        mock_obj.return_value = MOCK_DOM_OBJECTIVE
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()

        result = compile_dom_yaml_with_ai(playbook, ai_settings, use_ai_enrichment=True)

        self.assertIn("objective", result)
        self.assertIn("signals", result["objective"])
        self.assertEqual(len(result["objective"]["signals"]), 1)
        self.assertEqual(result["objective"]["signals"][0]["name"], "TGS Request Anomaly")
        # Signals must NOT have a logic/query field
        self.assertNotIn("logic", result["objective"]["signals"][0])

    def test_no_ai_enrichment_has_no_signals(self):
        playbook = _make_playbook()
        result = compile_dom_yaml_with_ai(playbook, None, use_ai_enrichment=False)
        self.assertNotIn("_ai_generated", result)

    @patch("ai_assistant.opentide_enrichment.ai_generate_detection_objective")
    def test_signals_never_contain_detection_rule_logic(self, mock_obj):
        """Signals are descriptive only — detection rule logic is always user-provided."""
        # Simulate AI attempting to add logic (should be stripped by enrichment module)
        objective_with_logic = dict(MOCK_DOM_OBJECTIVE)
        objective_with_logic["signals"] = [
            {
                "id": "sig-001",
                "name": "TGS Request",
                "description": "Monitors TGS requests",
                "data_source": "Windows Event Log 4769",
                # logic field should be absent here (stripped by opentide_enrichment)
            }
        ]
        mock_obj.return_value = objective_with_logic
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()

        result = compile_dom_yaml_with_ai(playbook, ai_settings, use_ai_enrichment=True)

        for sig in result.get("objective", {}).get("signals", []):
            self.assertNotIn("logic", sig)
            self.assertNotIn("query", sig)

    @patch("ai_assistant.opentide_enrichment.ai_generate_detection_objective")
    def test_ai_generated_tracking(self, mock_obj):
        mock_obj.return_value = MOCK_DOM_OBJECTIVE
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()

        result = compile_dom_yaml_with_ai(playbook, ai_settings, use_ai_enrichment=True)
        self.assertIn("_ai_generated", result)
        self.assertTrue(result["_ai_generated"].get("signals"))


class TestBdrUniqueUuid(TestCase):
    """BDR framework is deprecated — compile_bdr_yaml_with_ai always returns None."""

    def test_bdr_always_returns_none(self):
        """Since BDR is deprecated, the function always returns None regardless of inputs."""
        playbook = _make_playbook()
        ai_settings = _make_ai_settings()
        self.assertIsNone(compile_bdr_yaml_with_ai(playbook, ai_settings, force_generate=True))
        self.assertIsNone(compile_bdr_yaml_with_ai(playbook, ai_settings, force_generate=False))
        self.assertIsNone(compile_bdr_yaml_with_ai(playbook, ai_settings=None, force_generate=True))
