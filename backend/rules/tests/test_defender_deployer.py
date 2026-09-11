"""Tests for Defender deployer query metadata extraction."""

from unittest.mock import patch

from django.test import SimpleTestCase

from rules.deployers.defender import (
    DefenderDeployer,
    _extract_query_metadata,
    _normalize_graph_period,
    _to_graph_rule_id,
)

class TestExtractQueryMetadata(SimpleTestCase):
    def test_extracts_rule_name_and_tags_from_kql_comments(self):
        query = """
// ============================================
// Rule Metadata
// ============================================
// Rule name: [Prod][JPH][Atomic] ShadowPad RoboForm DLL Sideload
// tags: kql, t1059.003, detect::sideload, detect::command, roboform, shadowpad

DeviceProcessEvents
| where FileName =~ \"powershell.exe\"
        """.strip()

        rule_name, tags = _extract_query_metadata(query)

        self.assertEqual(rule_name, '[Prod][JPH][Atomic] ShadowPad RoboForm DLL Sideload')
        self.assertEqual(
            tags,
            ['kql', 't1059.003', 'detect::sideload', 'detect::command', 'roboform', 'shadowpad'],
        )

    def test_returns_empty_metadata_when_comments_are_missing(self):
        rule_name, tags = _extract_query_metadata('DeviceProcessEvents | take 10')

        self.assertIsNone(rule_name)
        self.assertEqual(tags, [])


class _MockResponse:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.content = text.encode('utf-8') if text else b'{}'
        self.ok = 200 <= status_code < 400

    def json(self):
        return self._json_data


def _patch_requests(responses):
    """Patch all HTTP verbs used by the deployer so a single ordered list of
    ``_MockResponse`` instances can drive the test regardless of whether the
    deployer reaches for ``requests.post``/``patch``/``get``/``request``.

    Returns a context manager yielding a single ``MagicMock`` whose
    ``call_args_list`` contains every (method, url, **kwargs) call made.
    """
    from unittest.mock import MagicMock, patch

    counter = {'i': 0}
    seq = list(responses)

    def _next(*args, **kwargs):
        idx = counter['i']
        counter['i'] += 1
        return seq[idx]

    tracker = MagicMock()

    def _record(method, url, **kwargs):
        tracker(method, url, **kwargs)
        return _next()

    def _post(url, **kwargs):
        return _record('POST', url, **kwargs)

    def _patch_verb(url, **kwargs):
        return _record('PATCH', url, **kwargs)

    def _get(url, **kwargs):
        return _record('GET', url, **kwargs)

    def _request(method, url, **kwargs):
        return _record(method, url, **kwargs)

    patches = [
        patch('rules.deployers.defender.requests.post', side_effect=_post),
        patch('rules.deployers.defender.requests.patch', side_effect=_patch_verb),
        patch('rules.deployers.defender.requests.get', side_effect=_get),
        patch('rules.deployers.defender.requests.request', side_effect=_request),
    ]
    for p in patches:
        p.start()
    return tracker, patches


class TestDefenderEndpointFallback(SimpleTestCase):
    def setUp(self):
        # Operator must explicitly opt into the retired legacy endpoints.
        self.deployer = DefenderDeployer({
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
            'allow_legacy_fallback': True,
        })
        # Legacy-only deployer (Graph token unavailable) — tests legacy fallback path.
        self.deployer._token = 'token'
        self.deployer._graph_token = None

    @patch('rules.deployers.defender.requests.request')
    def test_falls_back_when_first_endpoint_returns_405(self, mock_request):
        mock_request.side_effect = [
            _MockResponse(status_code=405, text='Method Not Allowed'),
            _MockResponse(status_code=200, json_data={'id': 'rule-123'}, text='ok'),
        ]

        result = self.deployer.deploy_rule({
            'metadata': {'title': 'Rule', 'severity': 'MEDIUM'},
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
        })

        self.assertTrue(result.success)
        self.assertEqual(result.rule_id, 'rule-123')
        self.assertEqual(mock_request.call_count, 2)

    @patch('rules.deployers.defender.requests.request')
    def test_reports_aggregated_errors_when_all_endpoints_fail(self, mock_request):
        mock_request.side_effect = [
            _MockResponse(status_code=404, text='Not Found'),
            _MockResponse(status_code=405, text='Method Not Allowed'),
            _MockResponse(status_code=401, text='Unauthorized'),
            _MockResponse(status_code=500, text='Server Error'),
        ]

        result = self.deployer.deploy_rule({
            'metadata': {'title': 'Rule', 'severity': 'MEDIUM'},
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
        })

        self.assertFalse(result.success)
        self.assertIn('See errors for details', result.message)
        self.assertTrue(result.errors)
        self.assertEqual(mock_request.call_count, 4)

    @patch('rules.deployers.defender.requests.request')
    def test_tries_put_with_uuid_after_post_attempts(self, mock_request):
        mock_request.side_effect = [
            _MockResponse(status_code=405, text='Method Not Allowed'),
            _MockResponse(status_code=405, text='Method Not Allowed'),
            _MockResponse(status_code=405, text='Method Not Allowed'),
            _MockResponse(status_code=405, text='Method Not Allowed'),
            _MockResponse(status_code=200, json_data={'id': 'rule-put-123'}, text='ok'),
        ]

        result = self.deployer.deploy_rule({
            'metadata': {
                'title': 'Rule',
                'severity': 'MEDIUM',
                'uuid': '550e8400-e29b-41d4-a716-446655440000',
            },
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
        })

        self.assertTrue(result.success)
        self.assertEqual(result.rule_id, 'rule-put-123')
        # 4 POST attempts (one per endpoint) + 1st PUT attempt succeeds
        self.assertEqual(mock_request.call_count, 5)

    def test_returns_structured_error_for_invalid_platforms_shape(self):
        result = self.deployer.deploy_rule({
            'metadata': {'title': 'Rule', 'severity': 'MEDIUM'},
            'platforms': ['Windows'],
        })

        self.assertFalse(result.success)
        self.assertIn('platforms must be an object', result.message)


class TestDefenderGraphApiPath(SimpleTestCase):
    """Microsoft Graph Security API is the modern replacement for the
    retired WindowsDefenderATP custom detection rules surface."""

    def setUp(self):
        self.deployer = DefenderDeployer({
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
            # Required for the legacy fallback test below; safe for the rest.
            'allow_legacy_fallback': True,
        })
        self.deployer._token = 'legacy-token'
        self.deployer._graph_token = 'graph-token'
        self.deployer._graph_token_error = None

    def test_graph_endpoint_is_tried_first(self):
        tracker, patches = _patch_requests([
            _MockResponse(status_code=201, json_data={'id': 'graph-rule-1'}, text='ok'),
        ])
        try:
            result = self.deployer.deploy_rule({
                'metadata': {'title': 'Rule', 'severity': 'HIGH'},
                'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
            })
        finally:
            for p in patches:
                p.stop()

        self.assertTrue(result.success)
        self.assertEqual(result.rule_id, 'graph-rule-1')
        first_call = tracker.call_args_list[0]
        method, url = first_call.args[0], first_call.args[1]
        self.assertEqual(method, 'POST')
        self.assertIn('graph.microsoft.com', url)
        # Graph payload uses lowercase severity & alertTemplate structure.
        body = first_call.kwargs['json']
        self.assertEqual(body['detectionAction']['alertTemplate']['severity'], 'high')
        self.assertIn('schedule', body)
        # Period must be the Graph enum, not ISO 8601.
        self.assertEqual(body['schedule']['period'], '1H')
        # Graph token is used in the Authorization header.
        self.assertEqual(first_call.kwargs['headers']['Authorization'], 'Bearer graph-token')

    def test_graph_payload_honors_defender_configuration_alert_and_impacted_entities(self):
        tracker, patches = _patch_requests([
            _MockResponse(status_code=201, json_data={'id': 'graph-rule-2'}, text='ok'),
        ])
        try:
            result = self.deployer.deploy_rule({
                'metadata': {'title': 'Fallback title', 'severity': 'LOW'},
                'platforms': {'kql': {'query': 'DeviceProcessEvents | project DeviceName, AccountName'}},
                'configurations': {
                    'defender_for_endpoint': {
                        'alert': {
                            'title': 'Configured title',
                            'description': 'Configured description',
                            'severity': 'HIGH',
                            'enabled': False,
                        },
                        'impacted_entities': {'device': 'DeviceName'},
                    }
                },
            })
        finally:
            for p in patches:
                p.stop()

        self.assertTrue(result.success)
        first_call = tracker.call_args_list[0]
        body = first_call.kwargs['json']
        self.assertEqual(body['displayName'], 'Configured title')
        self.assertFalse(body['isEnabled'])
        self.assertEqual(body['detectionAction']['alertTemplate']['description'], 'Configured description')
        self.assertEqual(body['detectionAction']['alertTemplate']['severity'], 'high')
        impacted_asset = body['detectionAction']['alertTemplate']['impactedAssets'][0]
        self.assertEqual(
            impacted_asset['@odata.type'],
            '#microsoft.graph.security.impactedDeviceAsset',
        )
        self.assertEqual(impacted_asset['identifier'], 'deviceName')

    def test_falls_back_to_legacy_when_graph_endpoints_fail(self):
        # Graph POST fails (400), 1st legacy POST succeeds.
        tracker, patches = _patch_requests([
            _MockResponse(status_code=400, text='Bad Request'),
            _MockResponse(status_code=200, json_data={'id': 'legacy-rule'}, text='ok'),
        ])
        try:
            result = self.deployer.deploy_rule({
                'metadata': {'title': 'Rule', 'severity': 'MEDIUM'},
                'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
            })
        finally:
            for p in patches:
                p.stop()

        self.assertTrue(result.success)
        self.assertEqual(result.rule_id, 'legacy-rule')
        second_call = tracker.call_args_list[1]
        self.assertIn('securitycenter.microsoft.com', second_call.args[1])
        self.assertEqual(second_call.kwargs['headers']['Authorization'], 'Bearer legacy-token')

    def test_no_tokens_fails_fast(self):
        deployer = DefenderDeployer({
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
            'allow_legacy_fallback': True,
        })
        deployer._token = None
        deployer._graph_token = None
        deployer._graph_token_error = None

        result = deployer.deploy_rule({
            'metadata': {'title': 'Rule', 'severity': 'MEDIUM'},
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
        })

        self.assertFalse(result.success)
        self.assertIn('No Defender access tokens', result.message)


class TestDefenderGraphErrorSurfacing(SimpleTestCase):
    """Without ``allow_legacy_fallback`` the deployer must surface the real
    Microsoft Graph error and must NOT silently fall back to the retired
    ``api.securitycenter.microsoft.com`` endpoints (which always return 405)."""

    def setUp(self):
        self.deployer = DefenderDeployer({
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
        })
        self.deployer._token = 'legacy-token'
        self.deployer._graph_token = 'graph-token'
        self.deployer._graph_token_error = None

    def test_graph_4xx_is_returned_without_legacy_fallback(self):
        tracker, patches = _patch_requests([
            _MockResponse(status_code=403, text='Forbidden: insufficient permissions'),
        ])
        try:
            result = self.deployer.deploy_rule({
                'metadata': {'title': 'Rule', 'severity': 'MEDIUM'},
                'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
            })
        finally:
            for p in patches:
                p.stop()

        self.assertFalse(result.success)
        self.assertIn('Microsoft Graph rejected the rule', result.message)
        self.assertTrue(result.errors)
        # Legacy retired endpoint is NOT contacted.
        self.assertEqual(tracker.call_count, 1)
        for call in tracker.call_args_list:
            self.assertNotIn('securitycenter.microsoft.com', call.args[1])

    def test_missing_graph_token_returns_actionable_hint(self):
        # Simulate a tenant where the app registration lacks the Graph permission.
        self.deployer._graph_token = None
        self.deployer._graph_token_error = 'HTTP 401 from Microsoft Graph token endpoint: invalid_scope'

        result = self.deployer.deploy_rule({
            'metadata': {'title': 'Rule', 'severity': 'MEDIUM'},
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
        })

        self.assertFalse(result.success)
        self.assertIn('CustomDetections.ReadWrite.All', result.message)
        self.assertIn('allow_legacy_fallback', result.message)
        self.assertIn('invalid_scope', result.message)

    def test_authenticate_fails_when_graph_token_missing_and_no_legacy_fallback(self):
        deployer = DefenderDeployer({
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
        })
        with patch('rules.deployers.defender.requests.post') as mock_post:
            mock_post.side_effect = [
                _MockResponse(status_code=200, json_data={'access_token': 'legacy'}, text='ok'),
                _MockResponse(status_code=401, text='invalid_scope'),
            ]
            self.assertFalse(deployer.authenticate())

    def test_authenticate_succeeds_when_graph_token_missing_with_legacy_fallback(self):
        deployer = DefenderDeployer({
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
            'allow_legacy_fallback': True,
        })
        with patch('rules.deployers.defender.requests.post') as mock_post:
            mock_post.side_effect = [
                _MockResponse(status_code=200, json_data={'access_token': 'legacy'}, text='ok'),
                _MockResponse(status_code=401, text='invalid_scope'),
            ]
            self.assertTrue(deployer.authenticate())


class TestDefenderQueryPreflight(SimpleTestCase):
    def setUp(self):
        self.deployer = DefenderDeployer({
            'tenant_id': 't',
            'client_id': 'c',
            'client_secret': 's',
        })
        self.deployer._graph_token = 'graph-token'

    @patch('rules.deployers.defender.requests.post')
    @patch('rules.deployers.defender.requests.patch')
    @patch('rules.deployers.defender.requests.request')
    def test_non_defender_table_blocks_without_network(self, mock_request, mock_patch, mock_post):
        result = self.deployer.deploy_rule({
            'metadata': {'title': 'Rule'},
            'platforms': {'kql': {'query': 'Syslog | take 10'}},
        })
        self.assertFalse(result.success)
        self.assertIn('Syslog', '\n'.join(result.errors))
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_patch.call_count, 0)
        self.assertEqual(mock_request.call_count, 0)

    @patch('rules.deployers.defender.requests.post')
    @patch('rules.deployers.defender.requests.patch')
    @patch('rules.deployers.defender.requests.request')
    def test_impacted_entities_column_missing_blocks_without_network(self, mock_request, mock_patch, mock_post):
        result = self.deployer.deploy_rule({
            'metadata': {'title': 'Rule'},
            'configurations': {
                'defender_for_endpoint': {
                    'impacted_entities': {'device': 'DeviceId'},
                }
            },
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 10'}},
        })
        self.assertFalse(result.success)
        self.assertIn('impacted entity `device = DeviceId`', '\n'.join(result.errors))
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_patch.call_count, 0)
        self.assertEqual(mock_request.call_count, 0)


class TestGraphPeriodNormalization(SimpleTestCase):
    def test_iso_8601_pt1h_becomes_1h(self):
        self.assertEqual(_normalize_graph_period('PT1H'), '1H')

    def test_bare_enum_passthrough(self):
        for v in ('0', '1H', '3H', '12H', '24H'):
            self.assertEqual(_normalize_graph_period(v), v)

    def test_lowercase_iso_normalized(self):
        self.assertEqual(_normalize_graph_period('pt3h'), '3H')

    def test_p1d_maps_to_24h(self):
        self.assertEqual(_normalize_graph_period('P1D'), '24H')

    def test_unknown_falls_back_to_default(self):
        self.assertEqual(_normalize_graph_period('weekly'), '1H')
        self.assertEqual(_normalize_graph_period(None), '1H')
        self.assertEqual(_normalize_graph_period(''), '1H')


class TestToGraphRuleId(SimpleTestCase):
    def test_uuid_starting_with_digit_gets_r_prefix(self):
        # UUID like 3b4d99a1-... must not start with a digit for Graph.
        result = _to_graph_rule_id('3b4d99a1-1537-46b8-9e22-d92929b65900')
        self.assertEqual(result, 'r3b4d99a1-1537-46b8-9e22-d92929b65900')
        self.assertTrue(result[0].isalpha())

    def test_uuid_starting_with_letter_unchanged(self):
        result = _to_graph_rule_id('a1b2c3d4-0000-4000-8000-000000000000')
        self.assertEqual(result, 'a1b2c3d4-0000-4000-8000-000000000000')

    def test_truncated_to_100_chars(self):
        long_id = 'r' + 'a' * 200
        result = _to_graph_rule_id(long_id)
        self.assertEqual(len(result), 100)

    def test_empty_string_returns_empty(self):
        self.assertEqual(_to_graph_rule_id(''), '')
