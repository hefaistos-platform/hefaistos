from django.test import SimpleTestCase

from rules.deployers.base import parse_http_error


class _MockResponse:
    def __init__(self, status_code=400, json_data=None, text='', json_raises=False):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError('bad json')
        return self._json_data


class TestParseHttpError(SimpleTestCase):
    def test_parses_graph_envelope(self):
        resp = _MockResponse(
            status_code=400,
            json_data={
                'error': {
                    'code': 'BadRequest',
                    'message': 'Top-level error',
                    'innerError': {'details': [{'target': 'query', 'message': 'Invalid table'}]},
                }
            },
        )
        summary, details = parse_http_error(resp, platform='Microsoft Graph')
        self.assertIn('HTTP 400 - BadRequest', summary)
        self.assertIn('Top-level error', details)
        self.assertIn('query: Invalid table', details)

    def test_parses_arm_error_details_list(self):
        resp = _MockResponse(
            status_code=400,
            json_data={
                'error': {
                    'code': 'BadRequest',
                    'message': 'Validation failed',
                    'details': [
                        {'code': 'InvalidTemplate', 'message': 'Template is invalid'},
                        {'target': 'query', 'message': 'Parser error near line 1'},
                    ],
                }
            },
        )
        summary, details = parse_http_error(resp, platform='Azure Sentinel')
        self.assertIn('HTTP 400 - BadRequest', summary)
        self.assertIn('Validation failed', details)
        self.assertIn('InvalidTemplate: Template is invalid', details)
        self.assertIn('query: Parser error near line 1', details)

    def test_parses_splunk_envelope(self):
        resp = _MockResponse(
            status_code=422,
            json_data={'messages': [{'type': 'ERROR', 'text': 'Syntax error'}]},
        )
        summary, details = parse_http_error(resp, platform='Splunk')
        self.assertIn('Splunk rejected the rule', summary)
        self.assertIn('ERROR: Syntax error', details)

    def test_parses_qradar_envelope(self):
        resp = _MockResponse(
            status_code=400,
            json_data={'code': 1005, 'description': 'AQL parser error', 'details': {'line': 1, 'column': 12}},
        )
        summary, details = parse_http_error(resp, platform='IBM QRadar')
        self.assertIn('code 1005', summary)
        self.assertTrue(any('line 1, column 12' in item for item in details))

    def test_parses_wazuh_envelope(self):
        resp = _MockResponse(
            status_code=400,
            json_data={
                'error': 1000,
                'message': 'General error',
                'data': {'failed_items': [{'error': {'code': 2001, 'message': 'Rule parse failed'}}]},
            },
        )
        summary, details = parse_http_error(resp, platform='Wazuh')
        self.assertIn('Wazuh rejected the rule', summary)
        self.assertIn('General error', details)
        self.assertIn('2001: Rule parse failed', details)

    def test_fallback_for_malformed_json(self):
        resp = _MockResponse(status_code=500, text='server exploded', json_raises=True)
        summary, details = parse_http_error(resp, platform='X')
        self.assertEqual(summary, 'HTTP 500')
        self.assertEqual(details, ['server exploded'])

    def test_fallback_for_empty_body(self):
        resp = _MockResponse(status_code=409, text='', json_raises=True)
        summary, details = parse_http_error(resp, platform='X')
        self.assertEqual(summary, 'HTTP 409')
        self.assertEqual(details, ['<empty response body>'])
