"""Unit tests for the AI-powered OpenTIDE enrichment engine."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from ai_assistant.opentide_enrichment import (
    _normalize_entity,
    _normalize_logsource,
    _normalize_methodology,
    _parse_json_response,
    ai_classify_detection_type,
    ai_enrich_mdr_response,
    ai_generate_bdr_schema,
    ai_generate_detection_objective,
    ai_map_platforms_and_targets,
    call_ai_provider,
)


def _make_ai_settings(has_key: bool = True):
    """Return a minimal mock UserAISettings-like object."""
    settings = MagicMock()
    settings.get_openai_key.return_value = 'sk-test' if has_key else ''
    settings.get_gemini_key.return_value = ''
    settings.get_claude_key.return_value = ''
    settings.get_ollama_url.return_value = ''
    settings.get_ollama_model.return_value = ''
    settings.preferred_model = 'GPT-5.4'
    settings.enable_auto_enrichment = True
    settings.auto_generate_bdr = True
    settings.auto_enrich_response = True
    settings.auto_map_platforms = True
    return settings


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestParseJsonResponse(TestCase):
    def test_valid_json(self):
        result = _parse_json_response('{"key": "value"}', {})
        self.assertEqual(result, {'key': 'value'})

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(raw, {})
        self.assertEqual(result, {'key': 'value'})

    def test_invalid_json_returns_fallback(self):
        result = _parse_json_response('not json', {'default': True})
        self.assertEqual(result, {'default': True})

    def test_empty_string_returns_fallback(self):
        result = _parse_json_response('', [])
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# call_ai_provider tests
# ---------------------------------------------------------------------------

class TestCallAiProvider(TestCase):
    def test_returns_empty_string_when_no_keys(self):
        settings = _make_ai_settings(has_key=False)
        result = call_ai_provider('test prompt', settings)
        self.assertEqual(result, '')

    @patch('ai_assistant.opentide_enrichment.call_ai_provider', return_value='{"classification": "THREAT", "confidence": 0.9}')
    def test_provider_called_with_prompt(self, mock_call):
        settings = _make_ai_settings()
        result = call_ai_provider('my prompt', settings)
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# ai_classify_detection_type tests
# ---------------------------------------------------------------------------

class TestAIClassifyDetectionType(TestCase):
    def _make_playbook_data(self, title='', goal='', technical_context='', compliance=''):
        return {
            'title': title,
            'goal': goal,
            'technical_context': technical_context,
            'compliance': compliance,
        }

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_threat_detection_classification(self, mock_call):
        mock_call.return_value = '{"classification": "THREAT", "confidence": 0.95}'
        settings = _make_ai_settings()
        data = self._make_playbook_data(
            title='Kerberoasting Detection',
            goal='Detect Kerberos service ticket requests',
            technical_context='Monitor Event ID 4769 for suspicious TGS requests',
        )
        result = ai_classify_detection_type(data, settings)
        self.assertEqual(result, 'THREAT')

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_business_detection_classification(self, mock_call):
        mock_call.return_value = '{"classification": "BUSINESS", "confidence": 0.88}'
        settings = _make_ai_settings()
        data = self._make_playbook_data(
            title='GDPR Privileged Access Monitoring',
            goal='Detect unauthorized use of high-privileged accounts to comply with GDPR Article 32',
            compliance='GDPR Article 32',
        )
        result = ai_classify_detection_type(data, settings)
        self.assertEqual(result, 'BUSINESS')

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_invalid_classification_defaults_to_threat(self, mock_call):
        mock_call.return_value = '{"classification": "UNKNOWN", "confidence": 0.3}'
        settings = _make_ai_settings()
        result = ai_classify_detection_type({}, settings)
        self.assertEqual(result, 'THREAT')

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_ai_failure_defaults_to_threat(self, mock_call):
        mock_call.return_value = ''
        settings = _make_ai_settings()
        result = ai_classify_detection_type({}, settings)
        self.assertEqual(result, 'THREAT')


# ---------------------------------------------------------------------------
# ai_generate_bdr_schema tests
# ---------------------------------------------------------------------------

class TestAIGenerateBDRSchema(TestCase):
    VALID_BDR_RESPONSE = '''{
        "criticality": "High",
        "domains": ["Enterprise"],
        "targets": ["Identity Services", "Directory"],
        "platforms": ["Windows", "Active Directory"],
        "violation": "Unauthorized use of high-privileged account",
        "justification": "GDPR Article 32 - privileged access monitoring",
        "description": "Monitor privileged account usage for compliance"
    }'''

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_bdr_generation_for_business_detection(self, mock_call):
        mock_call.return_value = self.VALID_BDR_RESPONSE
        settings = _make_ai_settings()
        data = {'title': 'Test', 'goal': 'Monitor privileged accounts', 'technical_context': ''}
        result = ai_generate_bdr_schema(data, settings, force_generate=True)
        self.assertIsNotNone(result)
        self.assertEqual(result['criticality'], 'High')
        self.assertIn('Enterprise', result['domains'])
        self.assertIn('Identity Services', result['targets'])
        self.assertIn('Windows', result['platforms'])
        self.assertEqual(result['violation'], 'Unauthorized use of high-privileged account')

    @patch('ai_assistant.opentide_enrichment.ai_classify_detection_type')
    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_no_bdr_for_threat_detection(self, mock_call, mock_classify):
        mock_classify.return_value = 'THREAT'
        mock_call.return_value = self.VALID_BDR_RESPONSE
        settings = _make_ai_settings()
        data = {'title': 'Kerberoasting', 'goal': 'Detect TGS requests', 'technical_context': ''}
        result = ai_generate_bdr_schema(data, settings, force_generate=False)
        self.assertIsNone(result)

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_force_generate_overrides_classification(self, mock_call):
        mock_call.return_value = self.VALID_BDR_RESPONSE
        settings = _make_ai_settings()
        data = {'title': 'Forced BDR', 'goal': 'Any detection', 'technical_context': ''}
        result = ai_generate_bdr_schema(data, settings, force_generate=True)
        self.assertIsNotNone(result)

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_missing_fields_get_defaults(self, mock_call):
        mock_call.return_value = '{}'
        settings = _make_ai_settings()
        result = ai_generate_bdr_schema({}, settings, force_generate=True)
        self.assertIsNotNone(result)
        self.assertEqual(result['criticality'], 'Medium')
        self.assertEqual(result['domains'], [])
        self.assertEqual(result['platforms'], [])
        self.assertEqual(result['targets'], [])


# ---------------------------------------------------------------------------
# ai_enrich_mdr_response tests
# ---------------------------------------------------------------------------

class TestAIEnrichMDRResponse(TestCase):
    VALID_RESPONSE = '''{
        "alert_severity": "High",
        "responders": "CSIRC",
        "procedure": {
            "analysis": "1. Review the alert. 2. Triage.",
            "searches": [
                {"purpose": "Auth history", "system": "Sentinel", "query": "SecurityEvent | ..."}
            ],
            "containment": "Disable the account immediately."
        }
    }'''

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_response_procedure_generation(self, mock_call):
        mock_call.return_value = self.VALID_RESPONSE
        settings = _make_ai_settings()
        data = {
            'title': 'Kerberoasting',
            'goal': 'Detect TGS requests',
            'technical_context': 'Windows AD',
            'default_severity': 'HIGH',
            'false_positives': 'Legitimate service accounts',
            'response_playbook': '',
        }
        result = ai_enrich_mdr_response(data, settings)
        self.assertEqual(result['alert_severity'], 'High')
        self.assertEqual(result['responders'], 'CSIRC')
        self.assertIn('analysis', result['procedure'])
        self.assertIn('searches', result['procedure'])
        self.assertIsInstance(result['procedure']['searches'], list)
        self.assertIn('containment', result['procedure'])

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_fallback_on_ai_failure(self, mock_call):
        mock_call.return_value = ''
        settings = _make_ai_settings()
        result = ai_enrich_mdr_response({'default_severity': 'HIGH'}, settings)
        self.assertIn(result['alert_severity'], ['High', 'Medium'])
        self.assertIn(result['responders'], ['CSIRC', 'CATCH', 'MARTI', 'S1-SA'])
        self.assertIn('analysis', result['procedure'])

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_invalid_severity_defaults_to_medium(self, mock_call):
        mock_call.return_value = '{"alert_severity": "INVALID", "responders": "CSIRC", "procedure": {}}'
        settings = _make_ai_settings()
        result = ai_enrich_mdr_response({}, settings)
        self.assertEqual(result['alert_severity'], 'Medium')

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_invalid_responder_defaults_to_csirc(self, mock_call):
        mock_call.return_value = '{"alert_severity": "High", "responders": "UNKNOWN_TEAM", "procedure": {}}'
        settings = _make_ai_settings()
        result = ai_enrich_mdr_response({}, settings)
        self.assertEqual(result['responders'], 'CSIRC')


# ---------------------------------------------------------------------------
# ai_map_platforms_and_targets tests
# ---------------------------------------------------------------------------

class TestAIMapPlatformsTargets(TestCase):
    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_windows_active_directory_detection(self, mock_call):
        mock_call.return_value = '''{
            "platforms": ["Windows", "Active Directory"],
            "targets": ["Identity Services", "Directory"],
            "domains": ["Enterprise"]
        }'''
        settings = _make_ai_settings()
        result = ai_map_platforms_and_targets(
            'Monitor Event ID 4769 in Active Directory for suspicious TGS ticket requests',
            settings,
        )
        self.assertIn('Windows', result['platforms'])
        self.assertIn('Active Directory', result['platforms'])
        self.assertIn('Identity Services', result['targets'])
        self.assertIn('Enterprise', result['domains'])

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_cloud_detection_mapping(self, mock_call):
        mock_call.return_value = '''{
            "platforms": ["AWS", "Azure"],
            "targets": ["Cloud Resources", "Identity Services"],
            "domains": ["Public Cloud"]
        }'''
        settings = _make_ai_settings()
        result = ai_map_platforms_and_targets(
            'Detect suspicious AWS IAM role assumption and Azure AD sign-in anomalies',
            settings,
        )
        self.assertIn('AWS', result['platforms'])
        self.assertIn('Public Cloud', result['domains'])

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_empty_context_returns_empty_lists(self, mock_call):
        mock_call.return_value = ''
        settings = _make_ai_settings()
        result = ai_map_platforms_and_targets('', settings)
        self.assertEqual(result['platforms'], [])
        self.assertEqual(result['targets'], [])
        self.assertEqual(result['domains'], [])


# ---------------------------------------------------------------------------
# ai_generate_detection_objective tests
# ---------------------------------------------------------------------------

class TestAIGenerateDetectionObjective(TestCase):
    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_signals_do_not_contain_logic_field(self, mock_call):
        """AI must never generate detection rule logic — signals are descriptive only."""
        mock_call.return_value = '''{
            "priority": "High",
            "type": "Threat",
            "description": "Detect Kerberoasting activity",
            "composition": "atomic",
            "signals": [
                {
                    "id": "sig-001",
                    "name": "TGS Request",
                    "description": "Monitors for TGS ticket requests",
                    "data": {
                        "logsources": ["siem::Windows Security Events"]
                    },
                    "logic": "This should be stripped"
                }
            ]
        }'''
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({'title': 'Test'}, settings)
        self.assertIsInstance(result['signals'], list)
        self.assertEqual(len(result['signals']), 1)
        # logic field must be stripped — detection rules are always user-provided
        self.assertNotIn('logic', result['signals'][0])
        # logsources must be present in data
        self.assertIn('logsources', result['signals'][0]['data'])

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_signals_contain_logsources(self, mock_call):
        """AI-generated signals must use data.logsources array, not top-level data_source."""
        mock_call.return_value = '''{
            "priority": "High",
            "type": "Threat",
            "description": "Detect lateral movement",
            "composition": "atomic",
            "signals": [
                {
                    "id": "sig-001",
                    "name": "Pass-the-Hash",
                    "description": "Detects NTLM authentication anomalies",
                    "data": {
                        "logsources": ["siem::Authentication Events"]
                    }
                }
            ]
        }'''
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({'title': 'Test'}, settings)
        self.assertNotIn('data_source', result['signals'][0])
        self.assertNotIn('data_sources', result['signals'][0])
        self.assertIn('logsources', result['signals'][0]['data'])
        self.assertIn('siem::Authentication Events', result['signals'][0]['data']['logsources'])

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_signals_legacy_data_sources_list_handled(self, mock_call):
        """If AI returns legacy data_sources list, first element is normalised and added to logsources."""
        mock_call.return_value = '''{
            "priority": "High",
            "type": "Threat",
            "description": "Detect lateral movement",
            "composition": "atomic",
            "signals": [
                {
                    "id": "sig-001",
                    "name": "Pass-the-Hash",
                    "description": "Detects NTLM authentication anomalies",
                    "data_sources": ["Windows Event Log 4624", "Sysmon Event ID 10"]
                }
            ]
        }'''
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({'title': 'Test'}, settings)
        self.assertEqual(len(result['signals']), 1)
        self.assertNotIn('data_source', result['signals'][0])
        self.assertNotIn('data_sources', result['signals'][0])
        self.assertIn('logsources', result['signals'][0]['data'])
        self.assertIn('siem::Windows Security Events', result['signals'][0]['data']['logsources'])

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_signals_do_not_have_invalid_fields(self, mock_call):
        """AI-generated signals must not contain fields rejected by the Signal class."""
        mock_call.return_value = '''{
            "priority": "High",
            "type": "Threat",
            "description": "Detect lateral movement",
            "composition": "atomic",
            "signals": [
                {
                    "id": "sig-001",
                    "name": "Pass-the-Hash",
                    "description": "Detects NTLM authentication anomalies",
                    "data_source": "Windows Event Log 4624"
                }
            ]
        }'''
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({'title': 'Test'}, settings)
        self.assertEqual(len(result['signals']), 1)
        self.assertNotIn('id', result['signals'][0], "Signal must not have 'id' field rejected by CoreTide Signal class")
        self.assertNotIn('data_source', result['signals'][0], "Signal must not have top-level 'data_source'")
        self.assertNotIn('data_sources', result['signals'][0], "Signal must not have 'data_sources' (plural)")
        self.assertIn('data', result['signals'][0], "Signal missing required 'data' field")
        self.assertIn('severity', result['signals'][0], "Signal missing required 'severity' field")
        self.assertIn('methodology', result['signals'][0], "Signal missing required 'methodology' field")
        self.assertIn('entities', result['signals'][0], "Signal missing required 'entities' field")

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_invalid_priority_defaults_to_medium(self, mock_call):
        mock_call.return_value = '{"priority": "SUPER_CRITICAL", "signals": []}'
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({}, settings)
        self.assertEqual(result['priority'], 'Medium')

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_fallback_on_empty_response(self, mock_call):
        mock_call.return_value = ''
        settings = _make_ai_settings()
        data = {'title': 'Test', 'goal': 'My goal'}
        result = ai_generate_detection_objective(data, settings)
        self.assertEqual(result['priority'], 'Medium')
        self.assertEqual(result['description'], 'My goal')
        self.assertEqual(result['signals'], [])


# ---------------------------------------------------------------------------
# Normalisation helper tests
# ---------------------------------------------------------------------------

class TestNormalizeLogsource(TestCase):
    """_normalize_logsource maps old-style names to schema-compliant tool::name values."""

    def test_valid_value_returned_unchanged(self):
        self.assertEqual(_normalize_logsource('siem::Windows Security Events'),
                         'siem::Windows Security Events')
        self.assertEqual(_normalize_logsource('mde::Microsoft Defender XDR'),
                         'mde::Microsoft Defender XDR')

    def test_legacy_windows_event_log(self):
        self.assertEqual(_normalize_logsource('Windows Security Event Log'),
                         'siem::Windows Security Events')
        self.assertEqual(_normalize_logsource('Windows Event Log 4769'),
                         'siem::Windows Security Events')

    def test_legacy_sysmon(self):
        self.assertEqual(_normalize_logsource('Sysmon'), 'siem::Sysmon')
        self.assertEqual(_normalize_logsource('Sysmon Event ID 10'), 'siem::Sysmon')

    def test_legacy_mde(self):
        self.assertEqual(_normalize_logsource('Microsoft Defender for Endpoint'),
                         'mde::Microsoft Defender XDR')
        self.assertEqual(_normalize_logsource('EDR File and Process Telemetry'),
                         'mde::Microsoft Defender XDR')
        self.assertEqual(_normalize_logsource('EDR Module Load Telemetry'),
                         'mde::Microsoft Defender XDR')

    def test_legacy_file_auditing(self):
        self.assertEqual(_normalize_logsource('Windows File System Auditing'),
                         'siem::File Events')
        self.assertEqual(_normalize_logsource('Domain Controller File Share Auditing'),
                         'siem::File Events')

    def test_unmappable_returns_none(self):
        self.assertIsNone(_normalize_logsource('Some Completely Unknown Source'))


class TestNormalizeEntity(TestCase):
    """_normalize_entity maps plain names and namespaced values to schema-compliant domain::Entity values."""

    def test_valid_domain_entity_value_returned_unchanged(self):
        """Values already in domain::Entity format must be returned unchanged."""
        for ent in ('host::Account', 'cloud::Account', 'host::User', 'cloud::User',
                    'host::Hostname', 'network::IP Address', 'host::Process', 'host::Command Line'):
            self.assertEqual(_normalize_entity(ent), ent)

    def test_plain_process_maps_to_host_process(self):
        self.assertEqual(_normalize_entity('process'), 'host::Process')

    def test_plain_user_maps_to_host_user(self):
        self.assertEqual(_normalize_entity('user'), 'host::User')

    def test_namespaced_process_returned_unchanged(self):
        """'host::Process' is already valid and must be returned as-is."""
        self.assertEqual(_normalize_entity('host::Process'), 'host::Process')

    def test_unmapped_suffix_returns_closest(self):
        self.assertEqual(_normalize_entity('host::CommandLine'), 'host::Command Line')
        self.assertEqual(_normalize_entity('host::Module'), 'host::Process')
        self.assertEqual(_normalize_entity('host::DigitalSignature'), 'host::Process')
        self.assertEqual(_normalize_entity('host::TempStorage'), 'host::Hostname')

    def test_unmappable_returns_none(self):
        self.assertIsNone(_normalize_entity('domain::GroupPolicyObject'))


class TestNormalizeMethodology(TestCase):
    """_normalize_methodology maps methodology strings to valid DOM schema values."""

    def test_valid_values_returned_unchanged(self):
        for method in ('Behavioural', 'Anomaly', 'Artifacts', 'Pattern Matching',
                       'Event Search', 'Statistical', 'Machine Learning',
                       'Heuristic', 'Threat Intelligence'):
            self.assertEqual(_normalize_methodology(method), method)

    def test_american_spelling_normalized(self):
        self.assertEqual(_normalize_methodology('Behavioral'), 'Behavioural')

    def test_correlation_maps_to_pattern_matching(self):
        self.assertEqual(_normalize_methodology('Correlation'), 'Pattern Matching')

    def test_threshold_maps_to_statistical(self):
        self.assertEqual(_normalize_methodology('Threshold'), 'Statistical')

    def test_invalid_value_defaults_to_behavioural(self):
        self.assertEqual(_normalize_methodology('Signature-based'), 'Behavioural')
        self.assertEqual(_normalize_methodology(''), 'Behavioural')


class TestAIGenerateDetectionObjectiveNormalization(TestCase):
    """ai_generate_detection_objective normalises AI output to schema-compliant values."""

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_old_logsource_names_are_normalised(self, mock_call):
        """Legacy logsource names from AI must be mapped to tool::name format."""
        mock_call.return_value = '''{
            "priority": "High",
            "type": "Threat",
            "description": "Detect GPO abuse",
            "composition": "atomic",
            "signals": [
                {
                    "name": "GPO Modification",
                    "description": "Detects changes to Group Policy Objects",
                    "severity": "High",
                    "methodology": "Behavioral",
                    "entities": ["host::File", "host::Process", "host::User", "domain::GroupPolicyObject"],
                    "data": {
                        "availability": "Partial",
                        "requirements": "Requires Windows Security Event Log",
                        "logsources": [
                            "Windows Security Event Log",
                            "Windows File System Auditing",
                            "Domain Controller File Share Auditing",
                            "Microsoft Defender for Endpoint"
                        ]
                    }
                }
            ]
        }'''
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({'title': 'GPO Abuse'}, settings)
        self.assertEqual(len(result['signals']), 1)
        signal = result['signals'][0]
        logsources = signal['data']['logsources']
        for ls in logsources:
            self.assertIn('::', ls, f"Logsource '{ls}' is not in tool::name format")
        self.assertIn('siem::Windows Security Events', logsources)
        self.assertIn('siem::File Events', logsources)
        self.assertIn('mde::Microsoft Defender XDR', logsources)

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_namespaced_entities_are_normalised(self, mock_call):
        """Entity values in domain::Entity format must be preserved or mapped."""
        mock_call.return_value = '''{
            "priority": "Medium",
            "type": "Threat",
            "description": "Detect credential access",
            "composition": "atomic",
            "signals": [
                {
                    "name": "LSASS Access",
                    "description": "Detects LSASS memory access",
                    "severity": "High",
                    "methodology": "Behavioural",
                    "entities": ["host::Process", "host::User", "host::Account"],
                    "data": {
                        "logsources": ["siem::Process Events"]
                    }
                }
            ]
        }'''
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({'title': 'Credential Access'}, settings)
        entities = result['signals'][0]['entities']
        self.assertIn('host::Process', entities)
        self.assertIn('host::User', entities)
        self.assertIn('host::Account', entities)
        for ent in entities:
            self.assertIn('::', ent, f"Entity '{ent}' must be in domain::Entity format")

    @patch('ai_assistant.opentide_enrichment.call_ai_provider')
    def test_behavioral_methodology_is_normalised(self, mock_call):
        """American-English 'Behavioral' must be corrected to 'Behavioural'."""
        mock_call.return_value = '''{
            "priority": "High",
            "type": "Threat",
            "description": "Detect DLL hijacking",
            "composition": "atomic",
            "signals": [
                {
                    "name": "DLL Load",
                    "description": "Monitors DLL loads",
                    "severity": "Medium",
                    "methodology": "Behavioral",
                    "entities": ["Process"],
                    "data": {"logsources": ["siem::Process Events"]}
                }
            ]
        }'''
        settings = _make_ai_settings()
        result = ai_generate_detection_objective({'title': 'DLL Hijacking'}, settings)
        self.assertEqual(result['signals'][0]['methodology'], 'Behavioural')


# ---------------------------------------------------------------------------
# generate_opentide_threat_fields TVM vocabulary filtering
# ---------------------------------------------------------------------------

class TestGenerateOpentideThreatFieldsVocabFilter(TestCase):
    """generate_opentide_threat_fields must drop AI values outside the OpenTIDE vocab.

    Strict OpenTIDE/CoreTide schema validation rejects ``tvm_leverage`` /
    ``tvm_impact`` / ``tvm_viability`` values that are not in the published
    vocabulary, so the engine filters AI responses post-hoc.
    """

    @patch('ai_assistant.engine.openai')
    def test_invalid_values_are_dropped(self, mock_openai_module):
        from ai_assistant.engine import generate_opentide_threat_fields

        # AI emits a mixture of valid OpenTIDE values and invalid free-form /
        # MITRE ATT&CK tactic strings that previously slipped through.
        ai_payload = (
            '{'
            '"terrain": "Windows host",'
            '"leverage": ["Persistence", "Defense Evasion", "Tampering"],'
            '"impact": ["Service Disruption", "Data Loss", "Impairement"],'
            '"viability": "Highly viable",'
            '"description": "An attacker disables defences."'
            '}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=ai_payload))]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_module.OpenAI.return_value = mock_client

        settings = _make_ai_settings()
        result, _provider = generate_opentide_threat_fields(
            settings,
            {
                'title': 'T1562.008 — Disable Cloud Logs',
                'goal': 'Detect tampering with logging',
                'technical_context': 'Cloud audit log disabled',
                'mitre_technique_id': 'T1562.008',
                'mitre_technique_name': 'Disable or Modify Cloud Logs',
                'default_severity': 'HIGH',
            },
        )

        # Only the canonical STRIDE / OpenTIDE entries survive.
        self.assertEqual(result['leverage'], ['Tampering'])
        self.assertEqual(result['impact'], ['Impairement'])
        # Invalid viability is dropped entirely (caller falls back to default).
        self.assertNotIn('viability', result)
        self.assertEqual(result['terrain'], 'Windows host')
        self.assertEqual(result['description'], 'An attacker disables defences.')

    @patch('ai_assistant.engine.openai')
    def test_valid_values_pass_through_case_insensitive(self, mock_openai_module):
        from ai_assistant.engine import generate_opentide_threat_fields

        ai_payload = (
            '{'
            '"terrain": "Endpoint",'
            '"leverage": ["tampering", "ELEVATION OF PRIVILEGE"],'
            '"impact": ["data breach"],'
            '"viability": "very likely",'
            '"description": "x"'
            '}'
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=ai_payload))]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_module.OpenAI.return_value = mock_client

        settings = _make_ai_settings()
        result, _ = generate_opentide_threat_fields(
            settings,
            {'title': 'x', 'mitre_technique_id': 'T1', 'default_severity': 'LOW'},
        )

        self.assertEqual(result['leverage'], ['Tampering', 'Elevation of Privilege'])
        self.assertEqual(result['impact'], ['Data Breach'])
        self.assertEqual(result['viability'], 'Very Likely')
