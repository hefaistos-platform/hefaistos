"""Regression tests for HEF MDR-to-deployment payload adaptation."""

from unittest.mock import patch

from django.test import SimpleTestCase

from rules.opentide_publish import (
    mdr_to_deployer_payload,
    _ensure_mdr_uuid4,
    _is_uuid4,
    _classify_deployment_failure,
    build_deployment_failure_summary,
    deploy_opentide_rule_to_platforms,
)
from rules.deployers.base import DeploymentResult


class TestMdrToDeployerPayload(SimpleTestCase):
    def test_maps_supported_configurations_to_platforms(self):
        mdr = {
            'name': 'mdr_de_t1059_001',
            'description': 'Detect suspicious powershell execution',
            'metadata': {
                'uuid': '550e8400-e29b-41d4-a716-446655440000',
                'author': 'analyst',
                'schema': 'mdr::2.1',
                'version': 1,
            },
            'response': {
                'alert_severity': 'High',
            },
            'configurations': {
                'defender_for_endpoint': {
                    'query': 'DeviceProcessEvents | where ProcessCommandLine contains "powershell"',
                    'alert': {
                        'title': 'Suspicious PowerShell Execution',
                        'description': 'PowerShell abuse detection',
                        'techniques': ['T1059.001'],
                    },
                },
                'splunk': {
                    'query': 'index=main sourcetype=syslog powershell',
                },
                'wazuh': {
                    'rule': '<rule id="100001"><description>test</description></rule>',
                },
            },
        }

        payload = mdr_to_deployer_payload(mdr)

        self.assertIn('metadata', payload)
        self.assertIn('platforms', payload)
        self.assertEqual(payload['metadata']['title'], 'Suspicious PowerShell Execution')
        self.assertEqual(payload['metadata']['severity'], 'HIGH')
        self.assertEqual(payload['metadata']['mitre_technique'], 'T1059.001')

        self.assertIn('kql', payload['platforms'])
        self.assertIn('spl', payload['platforms'])
        self.assertIn('wazuh', payload['platforms'])
        self.assertIn('query', payload['platforms']['kql'])
        self.assertIn('configurations', payload)
        self.assertIn('defender_for_endpoint', payload['configurations'])
        self.assertEqual(
            payload['configurations']['defender_for_endpoint']['alert']['title'],
            'Suspicious PowerShell Execution',
        )

    def test_defaults_when_alert_metadata_is_missing(self):
        mdr = {
            'name': 'mdr_de_t0001',
            'metadata': {
                'uuid': '550e8400-e29b-41d4-a716-446655440000',
                'schema': 'mdr::2.1',
                'version': 1,
            },
            'response': {
                'alert_severity': 'Medium',
            },
            'configurations': {
                'splunk': {
                    'query': 'index=main test',
                },
            },
        }

        payload = mdr_to_deployer_payload(mdr)

        self.assertEqual(payload['metadata']['title'], 'mdr_de_t0001')
        self.assertEqual(payload['metadata']['severity'], 'MEDIUM')
        self.assertEqual(payload['metadata']['mitre_technique'], 'T0000')
        self.assertEqual(payload['platforms']['spl']['query'], 'index=main test')

    def test_maps_sentinel_configuration_to_kql_platform(self):
        mdr = {
            'name': 'mdr_de_t0002',
            'metadata': {
                'uuid': '550e8400-e29b-41d4-a716-446655440000',
                'schema': 'mdr::2.1',
                'version': 1,
            },
            'configurations': {
                'microsoft_sentinel': {
                    'query': 'SecurityEvent | where EventID == 4688',
                },
            },
        }
        payload = mdr_to_deployer_payload(mdr)
        self.assertIn('kql', payload['platforms'])
        self.assertEqual(
            payload['platforms']['kql']['query'],
            'SecurityEvent | where EventID == 4688',
        )
        self.assertIn('configurations', payload)
        self.assertIn('microsoft_sentinel', payload['configurations'])
        self.assertEqual(
            payload['configurations']['microsoft_sentinel']['query'],
            'SecurityEvent | where EventID == 4688',
        )

    def test_ensure_mdr_uuid4_normalizes_legacy_v5_uuid(self):
        mdr = {
            'name': 'mdr_de_t1059_001',
            'metadata': {
                'uuid': '2b2ea935-c16a-5b61-8ed6-83621ecb1c54',
                'schema': 'mdr::2.1',
                'version': 1,
            },
            'configurations': {
                'defender_for_endpoint': {
                    'query': 'DeviceProcessEvents | take 1',
                },
            },
        }

        _ensure_mdr_uuid4(mdr, fallback_seed='playbook-123')

        normalized_uuid = mdr['metadata']['uuid']
        self.assertTrue(_is_uuid4(normalized_uuid))
        self.assertNotEqual(normalized_uuid, '2b2ea935-c16a-5b61-8ed6-83621ecb1c54')

    def test_ensure_mdr_uuid4_preserves_valid_uuid4(self):
        original_uuid = '550e8400-e29b-41d4-a716-446655440000'
        mdr = {
            'name': 'mdr_de_t1059_001',
            'metadata': {
                'uuid': original_uuid,
                'schema': 'mdr::2.1',
                'version': 1,
            },
        }

        _ensure_mdr_uuid4(mdr, fallback_seed='playbook-123')

        self.assertEqual(mdr['metadata']['uuid'], original_uuid)


class TestDeployOpenTideRuleToPlatforms(SimpleTestCase):
    @patch('rules.opentide_publish.PlatformCredential.objects.filter', return_value=[])
    @patch('rules.opentide_publish.mdr_to_deployer_payload')
    @patch('rules.opentide_publish.validate_mdr_structure', return_value=(True, []))
    @patch('rules.opentide_publish.pyyaml.safe_load')
    def test_converts_mdr_even_when_platforms_is_list(
        self,
        mock_safe_load,
        _mock_validate,
        mock_to_payload,
        _mock_creds,
    ):
        mock_safe_load.return_value = {
            'name': 'mdr_de_t1059_001',
            'metadata': {
                'uuid': '2b2ea935-c16a-5b61-8ed6-83621ecb1c54',
                'schema': 'mdr::2.1',
                'version': 1,
            },
            'platforms': ['Windows'],
            'configurations': {
                'defender_for_endpoint': {
                    'query': 'DeviceProcessEvents | take 1',
                },
            },
        }
        mock_to_payload.return_value = {
            'metadata': {'title': 'Rule'},
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 1'}},
        }

        class _Rule:
            format = 'OPENTIDE'
            raw_content = 'yaml-content'
            playbook_id = 'playbook-123'

        results, success, message = deploy_opentide_rule_to_platforms(
            _Rule(),
            organization=object(),
            platforms=[],
        )

        self.assertEqual(results, [])
        self.assertTrue(success)
        self.assertIn('0/0 platform', message)
        mock_to_payload.assert_called_once()

    @patch('rules.opentide_publish.PlatformCredential.preferred_credentials_map')
    @patch('rules.opentide_publish.PLATFORM_DEPLOYER_MAP')
    @patch('rules.opentide_publish.pyyaml.safe_load')
    def test_enriches_failed_results_with_failure_taxonomy(
        self,
        mock_safe_load,
        mock_deployer_map,
        mock_preferred_creds,
    ):
        mock_safe_load.return_value = {
            'metadata': {'title': 'Rule'},
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 1'}},
        }
        mock_preferred_creds.return_value = {'defender': {'tenant_id': 'x'}}

        class _FakeDeployer:
            PLATFORM_NAME = 'Microsoft Defender'

            def __init__(self, _credentials):
                pass

            def run(self, _payload):
                return DeploymentResult(
                    platform='Microsoft Defender',
                    success=False,
                    message='Authentication error: HTTP 401 from Microsoft Graph token endpoint: invalid_scope',
                    errors=['invalid_scope'],
                )

        mock_deployer_map.keys.return_value = ['defender']
        mock_deployer_map.__contains__.side_effect = lambda x: x == 'defender'
        mock_deployer_map.__getitem__.side_effect = lambda x: _FakeDeployer if x == 'defender' else None

        class _Rule:
            format = 'OPENTIDE'
            raw_content = 'yaml-content'

        results, success, _message = deploy_opentide_rule_to_platforms(
            _Rule(),
            organization=object(),
            platforms=['defender'],
        )

        self.assertFalse(success)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['failure_type'], 'AUTH_SCOPE')
        self.assertIn('CustomDetections.ReadWrite.All', results[0]['operator_hint'])


class TestDeploymentFailureClassification(SimpleTestCase):
    def test_classifies_query_validation(self):
        enriched = _classify_deployment_failure(
            platform='Azure Sentinel',
            message='KQL query validation failed.',
            errors=['queryFrequency must be a valid ISO 8601 duration'],
        )
        self.assertEqual(enriched['failure_type'], 'QUERY_VALIDATION')

    def test_classifies_authz(self):
        enriched = _classify_deployment_failure(
            platform='Microsoft Defender',
            message='Microsoft Graph rejected the rule (HTTP 403 - Forbidden). See errors for details.',
            errors=['Insufficient privileges to complete the operation.'],
        )
        self.assertEqual(enriched['failure_type'], 'AUTHZ')

    def test_builds_failure_summary(self):
        summary = build_deployment_failure_summary([
            {
                'platform': 'Microsoft Defender',
                'success': False,
                'failure_type': 'AUTH_SCOPE',
                'operator_hint': 'Grant CustomDetections.ReadWrite.All.',
            },
            {
                'platform': 'Azure Sentinel',
                'success': False,
                'failure_type': 'QUERY_VALIDATION',
                'operator_hint': 'Validate KQL syntax.',
            },
            {
                'platform': 'Splunk',
                'success': True,
            },
        ])
        self.assertEqual(summary['failed_count'], 2)
        self.assertEqual(summary['failed_platforms'], ['Microsoft Defender', 'Azure Sentinel'])
        self.assertEqual(summary['failure_type_counts']['AUTH_SCOPE'], 1)
        self.assertEqual(summary['failure_type_counts']['QUERY_VALIDATION'], 1)
        self.assertIn('Validate KQL syntax.', summary['operator_hints'])


class TestMitreTechniqueFallbacks(SimpleTestCase):
    def test_falls_back_to_metadata_mitre_technique_id(self):
        """When Defender configuration is absent, fall back to metadata.mitre."""
        from rules.opentide_publish import _extract_mitre_technique_from_mdr

        mdr = {
            'metadata': {
                'mitre': {'technique_id': 'T1055'},
            },
            'configurations': {
                'splunk': {'query': 'index=main'},
            },
        }
        self.assertEqual(_extract_mitre_technique_from_mdr(mdr), 'T1055')

    def test_falls_back_to_other_platform_alert_techniques(self):
        from rules.opentide_publish import _extract_mitre_technique_from_mdr

        mdr = {
            'configurations': {
                'splunk': {
                    'query': 'index=main',
                    'alert': {'techniques': ['T1078']},
                },
            },
        }
        self.assertEqual(_extract_mitre_technique_from_mdr(mdr), 'T1078')

    def test_returns_t0000_when_no_signal(self):
        from rules.opentide_publish import _extract_mitre_technique_from_mdr

        self.assertEqual(_extract_mitre_technique_from_mdr({}), 'T0000')
        self.assertEqual(_extract_mitre_technique_from_mdr({'metadata': {}}), 'T0000')


class TestElasticPayloadMapping(SimpleTestCase):
    """``configurations.elastic`` should round-trip into ``platforms.elastic``.

    No deployer exists for elastic yet (see ``rules.deployers.PLATFORM_DEPLOYER_MAP``)
    so the mapping is informational, but it must remain stable so a future
    ElasticDeployer can rely on the existing payload contract.
    """

    def test_elastic_query_maps_to_platforms_elastic(self):
        mdr = {
            'name': 'mdr_de_elastic',
            'metadata': {
                'uuid': '550e8400-e29b-41d4-a716-446655440000',
                'schema': 'mdr::2.1',
                'version': 1,
            },
            'configurations': {
                'elastic': {'query': 'process where process.name == "powershell.exe"'},
            },
        }
        payload = mdr_to_deployer_payload(mdr)
        self.assertIn('elastic', payload['platforms'])
        self.assertEqual(
            payload['platforms']['elastic']['query'],
            'process where process.name == "powershell.exe"',
        )

    def test_blank_elastic_query_is_dropped(self):
        mdr = {
            'name': 'mdr_de_elastic',
            'metadata': {'uuid': '550e8400-e29b-41d4-a716-446655440000'},
            'configurations': {
                'elastic': {'query': '   '},
                'splunk': {'query': 'index=main test'},
            },
        }
        payload = mdr_to_deployer_payload(mdr)
        self.assertNotIn('elastic', payload['platforms'])
        self.assertIn('spl', payload['platforms'])


class TestQRadarPayloadMapping(SimpleTestCase):
    """``configurations.qradar`` should round-trip into ``platforms.qradar``.

    The QRadar AQL query predicate must be preserved in the deployer payload
    so the QRadar deployer can include it in the API call.
    """

    def test_qradar_query_maps_to_platforms_qradar(self):
        mdr = {
            'name': 'mdr_de_qradar',
            'metadata': {
                'uuid': '550e8400-e29b-41d4-a716-446655440000',
                'schema': 'mdr::2.1',
                'version': 1,
            },
            'configurations': {
                'qradar': {'query': "sourceip = '10.0.0.1' AND eventtype = 'login'"},
            },
        }
        payload = mdr_to_deployer_payload(mdr)
        self.assertIn('qradar', payload['platforms'])
        self.assertEqual(
            payload['platforms']['qradar']['query'],
            "sourceip = '10.0.0.1' AND eventtype = 'login'",
        )

    def test_blank_qradar_query_is_dropped(self):
        mdr = {
            'name': 'mdr_de_qradar',
            'metadata': {'uuid': '550e8400-e29b-41d4-a716-446655440000'},
            'configurations': {
                'qradar': {'query': '   '},
                'splunk': {'query': 'index=main test'},
            },
        }
        payload = mdr_to_deployer_payload(mdr)
        self.assertNotIn('qradar', payload['platforms'])
        self.assertIn('spl', payload['platforms'])
