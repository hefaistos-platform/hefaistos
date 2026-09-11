from unittest.mock import patch

from django.test import SimpleTestCase

from rules.deployers.defender import DefenderDeployer
from rules.deployers.qradar import QRadarDeployer
from rules.deployers.sentinel import SentinelDeployer
from rules.deployers.splunk import SplunkDeployer
from rules.deployers.wazuh import WazuhDeployer


class _MockResponse:
    def __init__(self, status_code=400, json_data=None, text='', json_raises=False):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.content = text.encode('utf-8') if text else b'{}'
        self.ok = 200 <= status_code < 400
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError('invalid json')
        return self._json_data


class TestDeployerErrorSurface(SimpleTestCase):
    def test_defender_error_surface(self):
        deployer = DefenderDeployer({'tenant_id': 't', 'client_id': 'c', 'client_secret': 's'})
        deployer._graph_token = 'graph'
        deployer._token = None
        with patch.object(DefenderDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.defender.requests.post'
        ) as mock_post:
            mock_post.return_value = _MockResponse(
                status_code=400,
                json_data={'error': {'code': 'BadRequest', 'message': 'Bad KQL'}},
            )
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
            })
        self.assertFalse(result.success)
        self.assertLess(len(result.message), 200)
        self.assertNotIn('Sent payload:', result.message)
        self.assertIn('Bad KQL', '\n'.join(result.errors))

    def test_splunk_error_surface(self):
        deployer = SplunkDeployer({'url': 'https://splunk.local', 'api_token': 't'})
        with patch.object(SplunkDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.splunk.requests.post',
            return_value=_MockResponse(
                status_code=400,
                json_data={'messages': [{'type': 'ERROR', 'text': 'Search parsing failed'}]},
            ),
        ):
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'spl': {'query': 'search index=main | stats count'}},
            })
        self.assertFalse(result.success)
        self.assertLess(len(result.message), 200)
        self.assertNotIn('Sent payload:', result.message)
        self.assertIn('Search parsing failed', '\n'.join(result.errors))

    def test_qradar_error_surface(self):
        deployer = QRadarDeployer({'url': 'https://qradar.local', 'api_token': 'sec'})
        deployer._token = 'sec'
        with patch.object(QRadarDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.qradar.requests.post',
            return_value=_MockResponse(
                status_code=400,
                json_data={'code': 1005, 'description': 'AQL parser error', 'details': {'line': 1, 'column': 7}},
            ),
        ):
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'qradar': {'query': 'SELECT * FROM EVENTS'}},
            })
        self.assertFalse(result.success)
        self.assertLess(len(result.message), 200)
        self.assertNotIn('Sent payload:', result.message)
        self.assertIn('AQL parser error', '\n'.join(result.errors))

    def test_wazuh_error_surface(self):
        deployer = WazuhDeployer({'url': 'https://wazuh.local', 'username': 'u', 'password': 'p'})
        deployer._token = 'token'
        with patch.object(WazuhDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.wazuh.requests.put',
            return_value=_MockResponse(
                status_code=400,
                json_data={
                    'error': 1,
                    'message': 'Validation failed',
                    'data': {'failed_items': [{'error': {'code': 1720, 'message': 'Malformed XML'}}]},
                },
            ),
        ):
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'wazuh': {'rule': '<group><rule id="1" level="5"/></group>'}},
            })
        self.assertFalse(result.success)
        self.assertLess(len(result.message), 200)
        self.assertNotIn('Sent payload:', result.message)
        self.assertIn('Malformed XML', '\n'.join(result.errors))

    def test_sentinel_error_surface(self):
        deployer = SentinelDeployer({
            'tenant_id': 't',
            'client_id': 'c',
            'client_secret': 's',
            'subscription_id': 'sub',
            'resource_group': 'rg',
            'workspace_name': 'ws',
        })
        deployer._token = 'token'
        with patch.object(SentinelDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.sentinel.requests.put',
            return_value=_MockResponse(
                status_code=400,
                json_data={'error': {'code': 'BadRequest', 'message': 'Query is invalid'}},
            ),
        ):
            result = deployer.run({
                'metadata': {'title': 'Rule', 'uuid': '11111111-1111-1111-1111-111111111111'},
                'platforms': {'kql': {'query': 'SecurityEvent | take 10'}},
            })
        self.assertFalse(result.success)
        self.assertLess(len(result.message), 200)
        self.assertNotIn('Sent payload:', result.message)
        self.assertIn('Query is invalid', '\n'.join(result.errors))

    def test_sentinel_error_surface_arm_details(self):
        deployer = SentinelDeployer({
            'tenant_id': 't',
            'client_id': 'c',
            'client_secret': 's',
            'subscription_id': 'sub',
            'resource_group': 'rg',
            'workspace_name': 'ws',
        })
        deployer._token = 'token'
        with patch.object(SentinelDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.sentinel.requests.put',
            return_value=_MockResponse(
                status_code=400,
                json_data={
                    'error': {
                        'code': 'BadRequest',
                        'message': 'Validation failed',
                        'details': [
                            {'code': 'InvalidTemplate', 'message': 'Template malformed'},
                            {'target': 'query', 'message': 'Unknown table SecurityEventX'},
                        ],
                    }
                },
            ),
        ):
            result = deployer.run({
                'metadata': {'title': 'Rule', 'uuid': '11111111-1111-1111-1111-111111111111'},
                'platforms': {'kql': {'query': 'SecurityEvent | take 10'}},
            })
        self.assertFalse(result.success)
        self.assertIn('Validation failed', '\n'.join(result.errors))
        self.assertIn('InvalidTemplate: Template malformed', '\n'.join(result.errors))
        self.assertIn('query: Unknown table SecurityEventX', '\n'.join(result.errors))

    def test_defender_preflight_blocks_without_network(self):
        deployer = DefenderDeployer({'tenant_id': 't', 'client_id': 'c', 'client_secret': 's'})
        with patch.object(DefenderDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.defender.requests.post'
        ) as mock_post:
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'kql': {'query': 'Syslog | take 1'}},
            })
        self.assertFalse(result.success)
        self.assertEqual(mock_post.call_count, 0)

    def test_splunk_preflight_blocks_without_network(self):
        deployer = SplunkDeployer({'url': 'https://splunk.local', 'api_token': 't'})
        with patch.object(SplunkDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.splunk.requests.post'
        ) as mock_post:
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'spl': {'query': 'index=main'}},
            })
        self.assertFalse(result.success)
        self.assertEqual(mock_post.call_count, 0)

    def test_qradar_preflight_blocks_without_network(self):
        deployer = QRadarDeployer({'url': 'https://qradar.local', 'api_token': 'sec'})
        with patch.object(QRadarDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.qradar.requests.post'
        ) as mock_post:
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'qradar': {'query': 'FROM EVENTS'}},
            })
        self.assertFalse(result.success)
        self.assertEqual(mock_post.call_count, 0)

    def test_wazuh_preflight_blocks_without_network(self):
        deployer = WazuhDeployer({'url': 'https://wazuh.local', 'username': 'u', 'password': 'p'})
        with patch.object(WazuhDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.wazuh.requests.put'
        ) as mock_put:
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'wazuh': {'rule': '<group><rule id="1" level="x"/></group>'}},
            })
        self.assertFalse(result.success)
        self.assertEqual(mock_put.call_count, 0)

    def test_sentinel_preflight_blocks_without_network(self):
        deployer = SentinelDeployer({
            'tenant_id': 't',
            'client_id': 'c',
            'client_secret': 's',
            'subscription_id': 'sub',
            'resource_group': 'rg',
            'workspace_name': 'ws',
        })
        with patch.object(SentinelDeployer, 'authenticate', return_value=True), patch(
            'rules.deployers.sentinel.requests.put'
        ) as mock_put:
            result = deployer.run({
                'metadata': {'title': 'Rule'},
                'platforms': {'kql': {'query': 'X' * 10001}},
            })
        self.assertFalse(result.success)
        self.assertEqual(mock_put.call_count, 0)
