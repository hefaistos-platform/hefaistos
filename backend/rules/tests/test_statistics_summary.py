import importlib.util
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import unittest

# The aggregation is intentionally independent of Django and database setup.
spec = importlib.util.spec_from_file_location('rule_statistics', Path(__file__).parents[1] / 'statistics.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReadinessSummaryTests(unittest.TestCase):
    def test_shared_workbench_is_counted_once_and_formats_keep_rule_counts(self):
        now = datetime.now(timezone.utc)
        wb = SimpleNamespace(pk=1, status='DEPLOYED', test_validation_status='PASSED',
                             last_tested_at=now, updated_at=now - timedelta(hours=1))
        rules = [SimpleNamespace(status=' Active ', format=fmt, playbook=wb) for fmt in ('KQL', 'SPL')]
        rules.append(SimpleNamespace(status=None, format='KQL', playbook=None))
        result = module.summarize_readiness(rules)
        self.assertEqual(result['linked_workbench_count'], 1)
        self.assertEqual(dict((d['name'], d['count']) for d in result['validation'])['PASSED'], 1)
        self.assertEqual(sum(d['deployed'] for d in result['deployment_by_format']), 2)
        self.assertEqual(sum(d['unlinked'] for d in result['deployment_by_format']), 1)
        self.assertEqual(result['by_status'], [{'name': 'active', 'count': 2}, {'name': 'unknown', 'count': 1}])

    def test_missing_timestamp_and_changes_after_test_are_outdated(self):
        now = datetime.now(timezone.utc)
        workbenches = [
            SimpleNamespace(pk=1, status='TESTING', test_validation_status='PASSED', last_tested_at=None, updated_at=now),
            SimpleNamespace(pk=2, status='REVIEW', test_validation_status='FAILED', last_tested_at=now - timedelta(days=1), updated_at=now),
            SimpleNamespace(pk=3, status='DEVELOPMENT', test_validation_status='NOT_TESTED', last_tested_at=None, updated_at=now),
            SimpleNamespace(pk=4, status='TESTING', test_validation_status='FAILED', last_tested_at=now, updated_at=now),
        ]
        rules = [SimpleNamespace(status='', format='KQL', playbook=wb) for wb in workbenches]
        result = module.summarize_readiness(rules)
        validation = dict((d['name'], d['count']) for d in result['validation'])
        self.assertEqual(validation, {'PASSED': 0, 'FAILED': 1, 'NOT_TESTED': 1, 'OUTDATED': 2})
        self.assertEqual(result['deployment_by_format'][0]['testing'], 2)
        self.assertEqual(result['deployment_by_format'][0]['development'], 2)

    def test_empty_inventory_has_no_claimed_passes(self):
        result = module.summarize_readiness([])
        self.assertEqual(result['linked_workbench_count'], 0)
        self.assertEqual(sum(d['count'] for d in result['validation']), 0)
        self.assertEqual(result['deployment_by_format'], [])
