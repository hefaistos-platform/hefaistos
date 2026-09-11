from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from graphql import GraphQLError

from identity.decorators import Roles
from organizations.schema import Query, UpdateDacDeploymentConfig


class TestDacDeploymentConfigPermissions(SimpleTestCase):
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

    def test_non_admin_cannot_query_dac_config(self):
        with self.assertRaises(GraphQLError):
            Query().resolve_dac_deployment_config(self._make_info(role=Roles.ANALYST))

    def test_non_admin_cannot_update_dac_config(self):
        with self.assertRaises(PermissionDenied):
            UpdateDacDeploymentConfig.mutate(
                None,
                self._make_info(role=Roles.ANALYST),
                mode='NONE',
            )

    @patch('organizations.schema.DacDeploymentConfig.objects')
    def test_admin_query_returns_config(self, mock_config_objects):
        expected = SimpleNamespace(mode='NONE')
        mock_config_objects.select_related.return_value.get_or_create.return_value = (expected, False)

        result = Query().resolve_dac_deployment_config(self._make_info(role=Roles.ADMIN))

        self.assertIs(result, expected)


class TestUpdateDacDeploymentConfig(SimpleTestCase):
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

    def _make_config(self):
        config = SimpleNamespace(
            mode='NONE',
            target_repository=SimpleNamespace(id='repo-1'),
            target_branch='release',
            target_folder='detections',
            target_platforms=[],
            publish_profile=SimpleNamespace(id='profile-1'),
            updated_by=None,
        )
        config.save = MagicMock()
        return config

    @patch('organizations.schema.DacDeploymentConfig.objects')
    def test_accepts_deploy_only_with_platforms(self, mock_config_objects):
        config = self._make_config()
        mock_config_objects.get_or_create.return_value = (config, False)

        result = UpdateDacDeploymentConfig.mutate(
            None,
            self._make_info(),
            mode='DEPLOY_ONLY',
            target_platforms=['splunk', 'splunk'],
        )

        self.assertTrue(result.success)
        self.assertEqual(config.mode, 'DEPLOY_ONLY')
        self.assertEqual(config.target_platforms, ['splunk'])

    @patch('organizations.schema.DacDeploymentConfig.objects')
    def test_rejects_deploy_only_without_platforms(self, mock_config_objects):
        config = self._make_config()
        mock_config_objects.get_or_create.return_value = (config, False)

        with self.assertRaises(GraphQLError):
            UpdateDacDeploymentConfig.mutate(
                None,
                self._make_info(),
                mode='DEPLOY_ONLY',
                target_platforms=[],
            )

    @patch('organizations.schema.OpenTidePublishProfile.objects.get')
    @patch('rules.models.RuleRepository.objects.get')
    @patch('organizations.schema.DacDeploymentConfig.objects')
    def test_deploy_only_does_not_require_repository(
        self,
        mock_config_objects,
        mock_rule_repository_get,
        mock_publish_profile_get,
    ):
        config = self._make_config()
        mock_config_objects.get_or_create.return_value = (config, False)

        result = UpdateDacDeploymentConfig.mutate(
            None,
            self._make_info(),
            mode='DEPLOY_ONLY',
            target_repository_id='repo-2',
            publish_profile_id='profile-2',
            target_platforms=['splunk'],
        )

        self.assertTrue(result.success)
        self.assertIsNone(config.target_repository)
        self.assertEqual(config.target_branch, 'main')
        self.assertEqual(config.target_folder, '')
        self.assertIsNone(config.publish_profile)
        mock_rule_repository_get.assert_not_called()
        mock_publish_profile_get.assert_not_called()
