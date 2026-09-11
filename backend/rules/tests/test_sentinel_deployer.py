from unittest.mock import patch

from django.test import SimpleTestCase

from rules.deployers.sentinel import SentinelDeployer


class _MockResponse:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class TestSentinelDeployer(SimpleTestCase):
    def setUp(self):
        self.deployer = SentinelDeployer({
            'tenant_id': 't',
            'client_id': 'c',
            'client_secret': 's',
            'subscription_id': 'sub',
            'resource_group': 'rg',
            'workspace_name': 'ws',
        })
        self.deployer._token = 'tok'
        self.rule = {
            'metadata': {'title': 'Rule', 'uuid': '11111111-1111-1111-1111-111111111111'},
            'platforms': {'kql': {'query': 'SecurityEvent | take 10'}},
        }

    @patch('rules.deployers.sentinel.requests.put')
    def test_parses_graph_style_error(self, mock_put):
        mock_put.return_value = _MockResponse(
            status_code=400,
            json_data={'error': {'code': 'BadRequest', 'message': 'Invalid query'}},
        )
        result = self.deployer.deploy_rule(self.rule)
        self.assertFalse(result.success)
        self.assertIn('Azure Sentinel rejected the rule', result.message)
        self.assertIn('Invalid query', result.errors)

    @patch('rules.deployers.sentinel.requests.put')
    def test_uses_microsoft_sentinel_configuration_fields(self, mock_put):
        mock_put.return_value = _MockResponse(status_code=200, json_data={})
        rule = {
            'metadata': {'title': 'Rule', 'uuid': '11111111-1111-1111-1111-111111111111'},
            'platforms': {'kql': {'query': 'SecurityEvent | take 10'}},
            'configurations': {
                'microsoft_sentinel': {
                    'queryFrequency': 'PT10M',
                    'queryPeriod': 'PT30M',
                    'triggerOperator': 'GreaterThan',
                    'triggerThreshold': 2,
                    'suppressionDuration': 'PT2H',
                    'suppressionEnabled': True,
                    'customDetails': {'source': 'hefaistos'},
                    'entityMappings': [],
                },
            },
        }
        result = self.deployer.deploy_rule(rule)
        self.assertTrue(result.success)
        kwargs = mock_put.call_args.kwargs
        props = kwargs['json']['properties']
        self.assertEqual(props['queryFrequency'], 'PT10M')
        self.assertEqual(props['queryPeriod'], 'PT30M')
        self.assertEqual(props['triggerThreshold'], 2)
        self.assertEqual(props['suppressionDuration'], 'PT2H')
        self.assertTrue(props['suppressionEnabled'])
        self.assertEqual(props['customDetails'], {'source': 'hefaistos'})
        self.assertEqual(props['entityMappings'], [])

    def test_preflight_validates_sentinel_specific_fields(self):
        valid, errors = self.deployer.validate_query(
            'SecurityEvent | take 10',
            {
                'configurations': {
                    'microsoft_sentinel': {
                        'queryFrequency': 'not-duration',
                        'triggerOperator': 'BadOperator',
                        'triggerThreshold': 'nan',
                        'suppressionEnabled': 'not-bool',
                    }
                }
            },
        )
        self.assertFalse(valid)
        self.assertTrue(any('queryFrequency must be a valid ISO 8601 duration' in item for item in errors))
        self.assertTrue(any('triggerOperator must be one of' in item for item in errors))
        self.assertTrue(any('triggerThreshold must be an integer' in item for item in errors))
        self.assertTrue(any('suppressionEnabled must be a boolean value' in item for item in errors))

    def test_preflight_query_length_limit(self):
        valid, errors = self.deployer.validate_query('A' * 10001)
        self.assertFalse(valid)
        self.assertTrue(any('exceeds 10000 characters' in item for item in errors))

    def test_preflight_validates_advanced_sentinel_block_shapes(self):
        valid, errors = self.deployer.validate_query(
            'SecurityEvent | take 10',
            {
                'configurations': {
                    'microsoft_sentinel': {
                        'tactics': ['Execution', ''],
                        'techniques': 'T1059',
                        'customDetails': {'source': 1},
                        'entityMappings': {},
                        'eventGroupingSettings': {'enabled': 'yes'},
                        'incidentConfiguration': 'invalid',
                        'alertDetailsOverride': 'invalid',
                    },
                },
            },
        )
        self.assertFalse(valid)
        self.assertTrue(any('tactics must be a non-empty list of strings' in item for item in errors))
        self.assertTrue(any('techniques must be a non-empty list of strings' in item for item in errors))
        self.assertTrue(any('customDetails keys and values must be strings' in item for item in errors))
        self.assertTrue(any('entityMappings must be a list' in item for item in errors))
        self.assertTrue(any('eventGroupingSettings.enabled must be a boolean value' in item for item in errors))
        self.assertTrue(any('incidentConfiguration must be an object/dictionary' in item for item in errors))
        self.assertTrue(any('alertDetailsOverride must be an object/dictionary' in item for item in errors))
