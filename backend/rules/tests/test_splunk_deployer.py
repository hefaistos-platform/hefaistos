from unittest.mock import patch

from django.test import SimpleTestCase

from rules.deployers.splunk import SplunkDeployer


class _MockResponse:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class TestSplunkDeployer(SimpleTestCase):
    def setUp(self):
        self.deployer = SplunkDeployer({'url': 'https://splunk.local', 'api_token': 't'})
        self.deployer._token = 't'
        self.rule = {
            'metadata': {'title': 'Rule 1'},
            'platforms': {'spl': {'query': 'search index=main | head 1'}},
        }

    @patch('rules.deployers.splunk.requests.post')
    def test_error_body_from_splunk_json(self, mock_post):
        mock_post.return_value = _MockResponse(
            status_code=400,
            json_data={'messages': [{'type': 'ERROR', 'text': 'Parser failed'}]},
            text='{"messages":[...]}',
        )
        result = self.deployer.deploy_rule(self.rule)
        self.assertFalse(result.success)
        self.assertIn('Splunk rejected the rule', result.message)
        self.assertIn('ERROR: Parser failed', result.errors)

    @patch('rules.deployers.splunk.requests.post')
    def test_error_body_from_html_response(self, mock_post):
        mock_post.return_value = _MockResponse(
            status_code=500,
            text='<html>boom</html>',
        )
        with patch.object(_MockResponse, 'json', side_effect=ValueError('nope')):
            result = self.deployer.deploy_rule(self.rule)
        self.assertFalse(result.success)
        self.assertIn('HTTP 500', result.message)
        self.assertIn('<html>boom</html>', result.errors[0])

    def test_preflight_unbalanced_quotes(self):
        valid, errors = self.deployer.validate_query('search index=main "oops')
        self.assertFalse(valid)
        self.assertTrue(any('unbalanced " quotes' in e for e in errors))

    def test_preflight_missing_search_prefix(self):
        valid, errors = self.deployer.validate_query('index=main | head 1')
        self.assertFalse(valid)
        self.assertTrue(any('start with "search" or "|"' in e for e in errors))

    @patch('rules.deployers.splunk.requests.post')
    def test_happy_path_201(self, mock_post):
        mock_post.return_value = _MockResponse(
            status_code=201,
            json_data={'entry': [{'name': 'Rule 1'}]},
        )
        result = self.deployer.deploy_rule(self.rule)
        self.assertTrue(result.success)
        self.assertEqual(result.rule_id, 'Rule 1')
