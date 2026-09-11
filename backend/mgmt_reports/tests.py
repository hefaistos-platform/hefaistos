from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase

from identity.decorators import Roles

from .schema import Query


def make_info(user):
    return SimpleNamespace(context=SimpleNamespace(user=user))


def make_user(role, username='tester', is_superuser=False, is_staff=False):
    return SimpleNamespace(
        role=role,
        username=username,
        is_anonymous=False,
        is_superuser=is_superuser,
        is_staff=is_staff,
        organization=SimpleNamespace(id=1),
    )


class MgmtReportsQueryTests(SimpleTestCase):
    def test_viewer_is_denied(self):
        info = make_info(make_user(Roles.VIEWER, username='viewer'))

        with self.assertRaises(PermissionDenied):
            Query().resolve_ai_prompts(info)

    def test_reviewer_only_sees_reviewer_prompts(self):
        info = make_info(make_user(Roles.REVIEWER, username='reviewer'))
        base_queryset = MagicMock()
        reviewer_queryset = MagicMock()

        with patch('mgmt_reports.schema.AIPrompt.objects.filter', return_value=base_queryset) as filter_mock:
            base_queryset.filter.return_value = reviewer_queryset

            result = Query().resolve_ai_prompts(info)

        filter_mock.assert_called_once_with(is_active=True)
        base_queryset.filter.assert_called_once_with(required_role='REVIEWER')
        self.assertIs(result, reviewer_queryset)

    def test_admin_sees_all_active_prompts(self):
        info = make_info(make_user(Roles.ADMIN, username='admin'))
        base_queryset = MagicMock()

        with patch('mgmt_reports.schema.AIPrompt.objects.filter', return_value=base_queryset) as filter_mock:
            result = Query().resolve_ai_prompts(info)

        filter_mock.assert_called_once_with(is_active=True)
        base_queryset.filter.assert_not_called()
        self.assertIs(result, base_queryset)

    def test_mgmt_stats_uses_monthly_cache_when_available(self):
        user = make_user(Roles.ADMIN, username='admin')
        user.organization = SimpleNamespace(id=99)
        info = make_info(user)
        cached_payload = {
            'ach': {'total': 1, 'created_last_30d': 1, 'by_status': [{'status': 'RESEARCH', 'count': 1}]},
            'advops': {'total': 2, 'created_last_30d': 1, 'by_status': [], 'by_priority': []},
            'workbench': {'total': 3, 'created_last_30d': 1, 'by_status': [], 'by_robustness': []},
            'rules': {
                'total': 4,
                'created_last_30d': 1,
                'active_count': 2,
                'deprecated_count': 1,
                'with_playbooks_count': 1,
                'standalone_count': 3,
            },
        }

        with patch('mgmt_reports.schema.cache.get', return_value=cached_payload) as cache_get_mock, \
                patch('mgmt_reports.schema._compute_mgmt_cave_stats_payload') as compute_mock:
            result = Query().resolve_mgmt_cave_stats(info)

        cache_get_mock.assert_called_once()
        compute_mock.assert_not_called()
        self.assertEqual(result.ach.total, 1)
        self.assertEqual(result.rules.total, 4)

    def test_mgmt_stats_computes_and_caches_on_cache_miss(self):
        user = make_user(Roles.ADMIN, username='admin')
        user.organization = SimpleNamespace(id=77)
        info = make_info(user)
        computed_payload = {
            'ach': {'total': 8, 'created_last_30d': 2, 'by_status': [{'status': 'RESEARCH', 'count': 8}]},
            'advops': {'total': 5, 'created_last_30d': 1, 'by_status': [], 'by_priority': []},
            'workbench': {'total': 7, 'created_last_30d': 3, 'by_status': [], 'by_robustness': []},
            'rules': {
                'total': 11,
                'created_last_30d': 2,
                'active_count': 9,
                'deprecated_count': 1,
                'with_playbooks_count': 6,
                'standalone_count': 5,
            },
        }

        with patch('mgmt_reports.schema.cache.get', return_value=None), \
                patch('mgmt_reports.schema.cache.set') as cache_set_mock, \
                patch('mgmt_reports.schema._compute_mgmt_cave_stats_payload', return_value=computed_payload) as compute_mock:
            result = Query().resolve_mgmt_cave_stats(info)

        compute_mock.assert_called_once()
        cache_set_mock.assert_called_once()
        self.assertEqual(result.ach.total, 8)
        self.assertEqual(result.workbench.total, 7)
