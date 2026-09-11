from unittest.mock import patch

from django.test import SimpleTestCase

from rules.deployers.qradar import QRadarDeployer


class _MockResponse:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class TestQRadarDeployer(SimpleTestCase):
    def setUp(self):
        self.deployer = QRadarDeployer({'url': 'https://qradar.local', 'api_token': 'sec'})
        self.deployer._token = 'sec'
        self.rule = {
            'metadata': {'title': 'Rule'},
            'platforms': {'qradar': {'query': 'SELECT * FROM EVENTS'}},
        }

    @patch('rules.deployers.qradar.requests.post')
    def test_parses_qradar_error_details(self, mock_post):
        mock_post.return_value = _MockResponse(
            status_code=400,
            json_data={
                'code': 1005,
                'description': 'AQL parser error',
                'details': {'line': 1, 'column': 12},
            },
        )
        result = self.deployer.deploy_rule(self.rule)
        self.assertFalse(result.success)
        self.assertIn('IBM QRadar rejected the rule', result.message)
        self.assertTrue(any('line 1, column 12' in item for item in result.errors))

    def test_preflight_requires_select(self):
        valid, errors = self.deployer.validate_query('FROM EVENTS')
        self.assertFalse(valid)
        self.assertIn('QRadar AQL query must start with SELECT.', errors)

    def test_preflight_requires_from(self):
        valid, errors = self.deployer.validate_query('SELECT *')
        self.assertFalse(valid)
        self.assertIn('QRadar AQL query must contain a FROM clause.', errors)

    def test_preflight_rejects_semicolon(self):
        valid, errors = self.deployer.validate_query('SELECT * FROM EVENTS;')
        self.assertFalse(valid)
        self.assertIn('QRadar AQL query must not end with a semicolon.', errors)
