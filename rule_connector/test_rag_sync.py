#!/usr/bin/env python3
"""
Regression tests for RAG template collection.
Can be run in Docker: docker compose exec rule_connector python test_rag_sync.py
"""

import logging
import os
import sys
import tempfile
import uuid

try:
    import requests as _requests
except ModuleNotFoundError:
    class _RequestsStub:
        @staticmethod
        def request(*args, **kwargs):
            raise RuntimeError('requests library is required for Qdrant network calls')

    sys.modules['requests'] = _RequestsStub()

from rag_sync import collect_templates_from_repo

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _collect_single_file(content: str, *, relative_path: str = 'data-kql/sample.jsonl', dataset_path: str | None = None):
    with tempfile.TemporaryDirectory() as repo_root:
        normalized_relative_path = relative_path.replace('\\', '/')
        file_path = os.path.join(repo_root, normalized_relative_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as handle:
            handle.write(content)

        inferred_dataset_path = dataset_path
        if inferred_dataset_path is None:
            inferred_dataset_path = os.path.dirname(normalized_relative_path) or '.'

        templates, file_statuses = collect_templates_from_repo(
            repo_root=repo_root,
            repo_id='1',
            repo_name='test-repo',
            organization_id='1',
            source_branch='main',
            dataset_path=inferred_dataset_path,
        )

        return templates, file_statuses


def test_jsonl_line_delimited_ingests():
    templates, file_statuses = _collect_single_file(
        '{"title":"Line JSONL","query":"DeviceProcessEvents | take 1"}\n'
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    status = file_statuses[0]
    assert status['ingestion_status'] == 'INGESTED', f"Expected INGESTED, got {status['ingestion_status']}"
    assert status['templates_count'] == 1, f"Expected templates_count=1, got {status['templates_count']}"


def test_json_document_fallback_ingests_multiline_object():
    templates, file_statuses = _collect_single_file(
        """{
  "title": "Multiline JSON",
  "query": "DeviceNetworkEvents | take 1",
  "description": "Structured JSON object, not strict JSONL"
}
"""
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    status = file_statuses[0]
    assert status['ingestion_status'] == 'INGESTED', f"Expected INGESTED, got {status['ingestion_status']}"
    assert status['templates_count'] == 1, f"Expected templates_count=1, got {status['templates_count']}"


def test_json_document_fallback_ingests_bom_prefixed_json():
    templates, file_statuses = _collect_single_file(
        '\ufeff{"title":"BOM JSON","query":"SigninLogs | take 1"}\n'
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    status = file_statuses[0]
    assert status['ingestion_status'] == 'INGESTED', f"Expected INGESTED, got {status['ingestion_status']}"
    assert status['templates_count'] == 1, f"Expected templates_count=1, got {status['templates_count']}"


def test_chat_messages_jsonl_ingests_assistant_content():
    templates, file_statuses = _collect_single_file(
        '{"messages":[{"role":"system","content":"Schema: DeviceProcessEvents"},'
        '{"role":"user","content":"Title: ChatML Rule"},'
        '{"role":"assistant","content":"DeviceProcessEvents | take 1"}]}'
        '\n'
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"

    status = file_statuses[0]
    assert status['ingestion_status'] == 'INGESTED', f"Expected INGESTED, got {status['ingestion_status']}"
    assert status['templates_count'] == 1, f"Expected templates_count=1, got {status['templates_count']}"

    payload = templates[0]['payload']
    assert payload['title'] == 'ChatML Rule', f"Expected title='ChatML Rule', got {payload['title']}"
    assert 'DeviceProcessEvents | take 1' in payload['content'], 'Expected assistant query content in payload'

    point_id = templates[0]['id']
    try:
        uuid.UUID(point_id)
    except Exception as exc:
        raise AssertionError(f"Expected UUID point id, got '{point_id}'") from exc


def test_eql_jsonl_detects_language_from_data_folder():
    templates, file_statuses = _collect_single_file(
        '{"messages":[{"role":"system","content":"Schema: Elastic EQL corpus"},'
        '{"role":"user","content":"Title: EQL Rule"},'
        '{"role":"assistant","content":"process where process.name == \\\"cmd.exe\\\""}]}'
        '\n',
        relative_path='data-eql/hefaistos_eql_dataset.jsonl',
        dataset_path='data-eql',
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert templates[0]['payload']['language'] == 'EQL', f"Expected EQL payload language, got {templates[0]['payload']['language']}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    assert file_statuses[0]['language'] == 'EQL', f"Expected EQL file status language, got {file_statuses[0]['language']}"


def test_spl_jsonl_detects_language_from_data_folder():
    templates, file_statuses = _collect_single_file(
        '{"messages":[{"role":"system","content":"Schema: Splunk SPL corpus"},'
        '{"role":"user","content":"Title: SPL Rule"},'
        '{"role":"assistant","content":"index=wineventlog | stats count by host"}]}'
        '\n',
        relative_path='data-spl/hefaistos_spl_dataset.jsonl',
        dataset_path='data-spl',
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert templates[0]['payload']['language'] == 'SPL', f"Expected SPL payload language, got {templates[0]['payload']['language']}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    assert file_statuses[0]['language'] == 'SPL', f"Expected SPL file status language, got {file_statuses[0]['language']}"


def test_wazuh_jsonl_detects_language_from_data_folder():
    templates, file_statuses = _collect_single_file(
        '{"messages":[{"role":"system","content":"Schema: WazuhRule (rule_id, source_path)."},'
        '{"role":"user","content":"Title: sample.xml#rule-100001"},'
        '{"role":"assistant","content":"// Platform: Wazuh\\n// Record Type: wazuh_rule\\n<rule id=\\\"100001\\\" level=\\\"3\\\"><description>Test</description></rule>"}]}'
        '\n',
        relative_path='data-wazuh/hefaistos_wazuh_dataset.jsonl',
        dataset_path='data-wazuh',
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert templates[0]['payload']['language'] == 'WAZUH', f"Expected WAZUH payload language, got {templates[0]['payload']['language']}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    assert file_statuses[0]['language'] == 'WAZUH', f"Expected WAZUH file status language, got {file_statuses[0]['language']}"


def test_eql_file_extension_ingests_eql_language():
    templates, file_statuses = _collect_single_file(
        "// Title: EQL Extension Test\n"
        "process where process.name == \"powershell.exe\"\n",
        relative_path='queries/suspicious_process.eql',
        dataset_path='queries',
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert templates[0]['payload']['language'] == 'EQL', f"Expected EQL payload language, got {templates[0]['payload']['language']}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    assert file_statuses[0]['language'] == 'EQL', f"Expected EQL file status language, got {file_statuses[0]['language']}"


def test_spl_file_extension_ingests_spl_language():
    templates, file_statuses = _collect_single_file(
        "# Title: SPL Extension Test\n"
        "index=wineventlog sourcetype=XmlWinEventLog:Security | stats count by EventCode\n",
        relative_path='queries/suspicious_login.spl',
        dataset_path='queries',
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert templates[0]['payload']['language'] == 'SPL', f"Expected SPL payload language, got {templates[0]['payload']['language']}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    assert file_statuses[0]['language'] == 'SPL', f"Expected SPL file status language, got {file_statuses[0]['language']}"


def test_jsonl_without_language_hint_fails_in_strict_mode():
    templates, file_statuses = _collect_single_file(
        '{"title":"Ambiguous JSONL","query":"DeviceProcessEvents | take 1"}\n',
        relative_path='rules/templates/ambiguous.jsonl',
        dataset_path='rules/templates',
    )

    assert len(templates) == 0, f"Expected 0 templates, got {len(templates)}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    status = file_statuses[0]
    assert status['ingestion_status'] == 'FAILED', f"Expected FAILED, got {status['ingestion_status']}"
    assert status['language'] == 'UNKNOWN', f"Expected UNKNOWN language, got {status['language']}"
    assert 'Strict language validation failed' in status['error_message'], (
        f"Expected strict-language error, got: {status['error_message']}"
    )


def test_jsonl_explicit_language_succeeds_without_path_hint():
    templates, file_statuses = _collect_single_file(
        '{"language":"EQL","title":"Explicit EQL","query":"process where process.name == \\\"cmd.exe\\\""}\n',
        relative_path='rules/templates/explicit.jsonl',
        dataset_path='rules/templates',
    )

    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
    assert templates[0]['payload']['language'] == 'EQL', f"Expected EQL payload language, got {templates[0]['payload']['language']}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    assert file_statuses[0]['language'] == 'EQL', f"Expected EQL file status language, got {file_statuses[0]['language']}"
    assert file_statuses[0]['ingestion_status'] == 'INGESTED', (
        f"Expected INGESTED, got {file_statuses[0]['ingestion_status']}"
    )


def test_jsonl_mismatched_explicit_language_fails_in_strict_mode():
    templates, file_statuses = _collect_single_file(
        '{"language":"SPL","title":"Mismatch","query":"index=wineventlog | stats count"}\n',
        relative_path='data-kql/mismatch.jsonl',
        dataset_path='data-kql',
    )

    assert len(templates) == 0, f"Expected 0 templates, got {len(templates)}"
    assert len(file_statuses) == 1, f"Expected 1 file status, got {len(file_statuses)}"
    status = file_statuses[0]
    assert status['ingestion_status'] == 'FAILED', f"Expected FAILED, got {status['ingestion_status']}"
    assert status['language'] == 'KQL', f"Expected KQL language from dataset path, got {status['language']}"
    assert "mismatches dataset language 'KQL'" in status['error_message'], (
        f"Expected mismatch error, got: {status['error_message']}"
    )


def run_tests():
    tests = [
        test_jsonl_line_delimited_ingests,
        test_json_document_fallback_ingests_multiline_object,
        test_json_document_fallback_ingests_bom_prefixed_json,
        test_chat_messages_jsonl_ingests_assistant_content,
        test_eql_jsonl_detects_language_from_data_folder,
        test_spl_jsonl_detects_language_from_data_folder,
        test_wazuh_jsonl_detects_language_from_data_folder,
        test_eql_file_extension_ingests_eql_language,
        test_spl_file_extension_ingests_spl_language,
        test_jsonl_without_language_hint_fails_in_strict_mode,
        test_jsonl_explicit_language_succeeds_without_path_hint,
        test_jsonl_mismatched_explicit_language_fails_in_strict_mode,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            logger.info("✅ PASS: %s", test.__name__)
            passed += 1
        except Exception as exc:
            logger.error("❌ FAIL: %s -> %s", test.__name__, exc)
            failed += 1

    logger.info("RAG sync tests finished: %s passed, %s failed", passed, failed)
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_tests())
