from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from graphql import GraphQLError

from identity.decorators import Roles
from organizations.schema import Query, RunOrgAiTaskNow, SetOrgAiTaskConfig


class TestOrgAiTasksPermissions(SimpleTestCase):
    def _make_info(self, role=Roles.ADMIN):
        user = SimpleNamespace(
            is_anonymous=False,
            role=role,
            is_superuser=False,
            is_staff=False,
            organization=SimpleNamespace(id='org-1'),
            id='user-1',
            username='tester',
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    def test_non_admin_cannot_query_org_ai_task_configs(self):
        with self.assertRaises(GraphQLError):
            Query().resolve_org_ai_task_configs(self._make_info(role=Roles.ANALYST))

    def test_non_admin_cannot_set_ai_task_config(self):
        with self.assertRaises(PermissionDenied):
            SetOrgAiTaskConfig.mutate(
                None,
                self._make_info(role=Roles.ANALYST),
                task_key='coverage_gap_digest',
                enabled=True,
            )

    def test_non_admin_cannot_run_ai_task_now(self):
        with self.assertRaises(PermissionDenied):
            RunOrgAiTaskNow.mutate(
                None,
                self._make_info(role=Roles.ANALYST),
                task_key='coverage_gap_digest',
            )

    @patch('organizations.schema.ensure_org_task_configs')
    def test_admin_can_query_org_ai_task_configs(self, mock_ensure):
        expected = [SimpleNamespace(task_key='coverage_gap_digest')]
        mock_ensure.return_value = expected

        result = Query().resolve_org_ai_task_configs(self._make_info(role=Roles.ADMIN))
        self.assertEqual(result, expected)

    @patch('organizations.schema.update_task_config')
    @patch('organizations.schema.get_or_create_task_config')
    @patch('organizations.schema.get_ai_task_definition')
    def test_admin_can_set_ai_task_config(
        self,
        mock_get_definition,
        mock_get_or_create,
        mock_update,
    ):
        mock_get_definition.return_value = SimpleNamespace(key='coverage_gap_digest')
        config = SimpleNamespace(task_key='coverage_gap_digest')
        mock_get_or_create.return_value = config
        mock_update.return_value = config

        result = SetOrgAiTaskConfig.mutate(
            None,
            self._make_info(role=Roles.ADMIN),
            task_key='coverage_gap_digest',
            enabled=True,
            schedule='WEEKLY',
            day_of_week=2,
            run_hour=8,
            run_minute=0,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.config, config)

