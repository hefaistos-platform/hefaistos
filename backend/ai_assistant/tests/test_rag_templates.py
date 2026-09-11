import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
import requests

from ai_assistant.rag_templates import (
    QdrantTemplateRetriever,
    build_hash_embedding,
    build_rag_query_text,
    build_reference_context_prompt,
    retrieve_reference_context,
    summarize_reference_context,
)


class _MockResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class RAGTemplateRetrieverTests(SimpleTestCase):
    def test_hash_embedding_is_deterministic_and_normalized(self):
        one = build_hash_embedding('DeviceProcessEvents | where FileName == "cmd.exe"', size=64)
        two = build_hash_embedding('DeviceProcessEvents | where FileName == "cmd.exe"', size=64)

        self.assertEqual(one, two)
        self.assertEqual(len(one), 64)
        self.assertAlmostEqual(sum(v * v for v in one), 1.0, places=5)

    def test_build_reference_context_prompt(self):
        prompt = build_reference_context_prompt([
            {
                'title': 'Suspicious Process Chain',
                'source_ref': 'rules/templates/windows.jsonl:12',
                'repository_name': 'Detection Repo',
                'language': 'KQL',
                'description': 'Detects Office spawning script interpreters.',
                'content': 'DeviceProcessEvents | where InitiatingProcessFileName in~ ("winword.exe")',
                'schema_context': {
                    'data_source': 'MDE',
                    'tactic': 'Execution',
                },
            }
        ])

        self.assertIn('STRICT RETRIEVED KQL GROUNDING CONTEXT', prompt)
        self.assertIn('TABLE NAME HINTS', prompt)
        self.assertIn('SCHEMA / FIELD HINTS', prompt)
        self.assertIn('Suspicious Process Chain', prompt)
        self.assertIn('rules/templates/windows.jsonl:12', prompt)
        self.assertIn('DeviceProcessEvents', prompt)
        self.assertIn('SCHEMA_CONTEXT', prompt)

    def test_build_reference_context_prompt_spl_uses_language_header(self):
        prompt = build_reference_context_prompt([
            {
                'title': 'SPL Suspicious Login',
                'source_ref': 'data-spl/hefaistos_spl_dataset.jsonl:1',
                'repository_name': 'Splunk Repo',
                'language': 'SPL',
                'description': 'Detect unusual login surge from one host.',
                'content': 'index=wineventlog sourcetype=XmlWinEventLog:Security | stats count by host',
                'schema_context': {
                    'data_source': 'Windows Security',
                },
            }
        ])

        self.assertIn('STRICT RETRIEVED SPL GROUNDING CONTEXT', prompt)
        self.assertIn('index=wineventlog', prompt)
        self.assertIn('TABLE_HINTS', prompt)

    def test_summarize_reference_context_extracts_table_and_schema_hints(self):
        summary = summarize_reference_context([
            {
                'source_ref': 'templates/base.kql',
                'repository_name': 'Repo One',
                'content': 'DeviceNetworkEvents | where RemoteIP != ""',
                'schema_context': {
                    'data_source': 'Network',
                    'severity': 'high',
                },
            }
        ])

        self.assertIn('DeviceNetworkEvents', summary['table_hints'])
        self.assertIn('data_source=Network', summary['schema_hints'])
        self.assertIn('severity=high', summary['schema_hints'])
        self.assertIn('templates/base.kql', summary['source_refs'])
        self.assertIn('Repo One', summary['repository_names'])

    def test_build_rag_query_text_includes_key_context_fields(self):
        query_text = build_rag_query_text(
            {
                'title': 'Suspicious PowerShell',
                'strategy_name': 'Behavioral',
                'goal': 'Detect encoded PowerShell',
                'technique_id': 'T1059.001',
                'technical_context': 'PowerShell encoded command execution',
                'detection_focus_layer': 'Execution',
            },
            rule_content='DeviceProcessEvents | where ProcessCommandLine has "-enc"',
            additional_text='Prefer robust anti-evasion filters',
        )

        self.assertIn('Suspicious PowerShell', query_text)
        self.assertIn('Behavioral', query_text)
        self.assertIn('T1059.001', query_text)
        self.assertIn('DeviceProcessEvents', query_text)
        self.assertIn('Prefer robust anti-evasion filters', query_text)

    @patch('ai_assistant.rag_templates.requests.request')
    def test_search_templates_applies_language_and_org_filters(self, request_mock):
        recorded = []

        def _fake_request(method, url, json=None, headers=None, timeout=None):
            recorded.append((method, url, json))
            if method == 'PUT' and '/collections/' in url:
                return _MockResponse({'status': 'ok'})
            if method == 'POST' and url.endswith('/points/search'):
                return _MockResponse({
                    'result': [
                        {
                            'id': 'abc123',
                            'score': 0.91,
                            'payload': {
                                'title': 'KQL Template',
                                'description': 'Template description',
                                'content': 'SecurityEvent | take 1',
                                'language': 'KQL',
                                'repository_name': 'Repo One',
                                'source_path': 'templates/base.kql',
                                'source_ref': 'templates/base.kql',
                                'source_branch': 'main',
                                'schema_context': {'data_source': 'Windows'},
                            },
                        }
                    ]
                })
            raise AssertionError(f'Unexpected request: {method} {url}')

        request_mock.side_effect = _fake_request

        retriever = QdrantTemplateRetriever(base_url='http://qdrant:6333', collection_name='hefaistos_rule_templates', vector_size=64)
        results = retriever.search_templates(
            'detect suspicious process execution',
            language='KQL',
            organization_id='org-123',
            limit=3,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['language'], 'KQL')
        self.assertEqual(results[0]['title'], 'KQL Template')

        search_call = next(item for item in recorded if item[0] == 'POST' and item[1].endswith('/points/search'))
        search_payload = search_call[2]
        must_filters = search_payload['filter']['must']
        self.assertIn({'key': 'language', 'match': {'value': 'KQL'}}, must_filters)
        self.assertIn({'key': 'organization_id', 'match': {'value': 'org-123'}}, must_filters)

    def test_retrieve_reference_context_supports_spl(self):
        with patch.object(QdrantTemplateRetriever, 'search_templates', return_value=[{'id': 'one'}]) as search_mock:
            results = retrieve_reference_context(
                playbook_context={'title': 'Suspicious Auth'},
                language='SPL',
                organization_id='org-1',
                limit=3,
            )

        self.assertEqual(results, [{'id': 'one'}])
        search_mock.assert_called_once()
        _, kwargs = search_mock.call_args
        self.assertEqual(kwargs['language'], 'SPL')
        self.assertEqual(kwargs['organization_id'], 'org-1')
        self.assertEqual(kwargs['limit'], 3)

    def test_retrieve_reference_context_rejects_unsupported_language(self):
        with patch.object(QdrantTemplateRetriever, 'search_templates') as search_mock:
            results = retrieve_reference_context(
                playbook_context={'title': 'Suspicious Auth'},
                language='WAZUH',
                organization_id='org-1',
                limit=3,
            )

        self.assertEqual(results, [])
        search_mock.assert_not_called()

    def test_ensure_collection_handles_conflict_and_aligns_vector_size(self):
        retriever = QdrantTemplateRetriever(
            base_url='http://qdrant:6333',
            collection_name='hefaistos_rule_templates',
            vector_size=256,
        )

        def _fake_request(method, path, payload=None):
            if method == 'PUT' and path.endswith('/collections/hefaistos_rule_templates'):
                response = SimpleNamespace(status_code=409, text='Collection already exists')
                raise requests.HTTPError('Conflict', response=response)
            if method == 'GET' and path.endswith('/collections/hefaistos_rule_templates'):
                return {
                    'result': {
                        'config': {
                            'params': {
                                'vectors': {
                                    'size': 384,
                                    'distance': 'Cosine',
                                }
                            }
                        }
                    }
                }
            raise AssertionError(f'Unexpected request: {method} {path}')

        with patch.object(retriever, '_request', side_effect=_fake_request):
            retriever.ensure_collection()

        self.assertEqual(retriever.vector_size, 384)
