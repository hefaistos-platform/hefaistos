from unittest.mock import patch

from django.test import SimpleTestCase

from rules.deployers.wazuh import WazuhDeployer


class _MockResponse:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class TestWazuhDeployer(SimpleTestCase):
    def setUp(self):
        self.deployer = WazuhDeployer({'url': 'https://wazuh.local', 'username': 'u', 'password': 'p'})
        self.deployer._token = 'tok'
        self.rule = {
            'metadata': {'title': 'Rule'},
            'platforms': {'wazuh': {'rule': '<group name="x"><rule id="1" level="5"/></group>'}},
        }

    @patch('rules.deployers.wazuh.requests.put')
    def test_parses_wazuh_error_failed_items(self, mock_put):
        mock_put.return_value = _MockResponse(
            status_code=400,
            json_data={
                'error': 1,
                'message': 'Invalid XML',
                'data': {'failed_items': [{'error': {'code': 1720, 'message': 'Malformed rule'}}]},
            },
        )
        result = self.deployer.deploy_rule(self.rule)
        self.assertFalse(result.success)
        self.assertIn('Wazuh rejected the rule', result.message)
        self.assertIn('1720: Malformed rule', result.errors)

    def test_preflight_malformed_xml(self):
        valid, errors = self.deployer.validate_query('<group><rule></group>')
        self.assertFalse(valid)
        self.assertTrue(any('not well-formed' in item for item in errors))

    def test_preflight_level_out_of_range(self):
        valid, errors = self.deployer.validate_query('<group><rule id="10" level="99"/></group>')
        self.assertFalse(valid)
        self.assertIn('Wazuh <rule> #1 level must be between 0 and 16.', errors)
