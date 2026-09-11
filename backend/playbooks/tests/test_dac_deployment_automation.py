from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from identity.decorators import Roles
from playbooks.models import DetectionPlaybook
from playbooks.schema import (
    AdminApproveDeployment,
    UpdatePlaybookGraphStatus,
    _queue_dac_deployment_automation,
)


class TestAdminApproveDeploymentDacAutomation(SimpleTestCase):
    def _make_info(self):
        user = SimpleNamespace(
            id='user-1',
            username='admin',
            is_anonymous=False,
            role=Roles.ADMIN,
            is_superuser=False,
            is_staff=False,
            organization=SimpleNamespace(id='org-1'),
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    def _make_graph(self):
        graph = MagicMock()
        graph.id = 'graph-1'
        graph.title = 'Workbench'
        graph.status = str(DetectionPlaybook.PlaybookStatus.APPROVED)
        graph.version = 5
        graph.minor_version = 2
        graph.organization = SimpleNamespace(id='org-1')
        graph.author = SimpleNamespace(id='author-1')
        return graph

    @patch('playbooks.schema.publish_event', return_value=True)
    @patch('playbooks.schema.get_publisher')
    @patch('organizations.models.OpenTideHefPublishJob.objects')
    @patch('organizations.models.DacDeploymentConfig.objects')
    @patch('playbooks.schema.PlaybookGraph.objects')
    def test_mode_none_no_publish_job_created(
        self,
        mock_graph_objects,
        mock_dac_config_objects,
        mock_job_objects,
        mock_get_publisher,
        mock_publish_event,
    ):
        graph = self._make_graph()
        mock_graph_objects.get.return_value = graph
        mock_get_publisher.return_value = SimpleNamespace(publish_message=lambda *args, **kwargs: None)
        mock_dac_config_objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(
            mode='NONE',
        )

        result = AdminApproveDeployment.mutate(None, self._make_info(), id='graph-1')

        self.assertEqual(result.playbook_graph, graph)
        graph.auto_update_opentide_yaml.assert_called_once_with()
        graph.save.assert_called_once_with(
            update_fields=["status", "opentide_yaml", "configured_platforms", "updated_at"]
        )
        mock_job_objects.create.assert_not_called()
        self.assertEqual(mock_publish_event.call_count, 0)

    @patch('playbooks.schema.publish_event', return_value=True)
    @patch('playbooks.schema.get_publisher')
    @patch('organizations.models.OpenTideHefPublishJob.objects')
    @patch('organizations.models.DacDeploymentConfig.objects')
    @patch('playbooks.schema.PlaybookGraph.objects')
    def test_mode_git_push_creates_publish_job(
        self,
        mock_graph_objects,
        mock_dac_config_objects,
        mock_job_objects,
        mock_get_publisher,
        mock_publish_event,
    ):
        graph = self._make_graph()
        mock_graph_objects.get.return_value = graph
        mock_get_publisher.return_value = SimpleNamespace(publish_message=lambda *args, **kwargs: None)
        mock_job_objects.filter.return_value.exists.return_value = False
        mock_job_objects.create.return_value = SimpleNamespace(id='job-1')
        mock_dac_config_objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(
            mode='GIT_PUSH',
            target_repository=SimpleNamespace(git_url='https://github.com/acme/rules', token='token'),
            target_branch='main',
            target_folder='rules/kql',
            target_platforms=[],
            publish_profile=None,
        )

        AdminApproveDeployment.mutate(None, self._make_info(), id='graph-1')

        self.assertEqual(mock_publish_event.call_count, 1)
        kwargs = mock_job_objects.create.call_args.kwargs
        self.assertEqual(kwargs['requested_platforms'], [])
        self.assertTrue(kwargs['push_opentide_bundle'])
        self.assertTrue(kwargs['push_platform_rules'])
        self.assertEqual(kwargs['source'], 'DAC_AUTOMATION')

    @patch('playbooks.schema.publish_event', return_value=True)
    @patch('playbooks.schema.get_publisher')
    @patch('organizations.models.PlatformCredential.objects')
    @patch('organizations.models.OpenTideHefPublishJob.objects')
    @patch('organizations.models.DacDeploymentConfig.objects')
    @patch('playbooks.schema.PlaybookGraph.objects')
    def test_mode_git_push_and_deploy_creates_publish_job_with_platforms(
        self,
        mock_graph_objects,
        mock_dac_config_objects,
        mock_job_objects,
        mock_platform_credential_objects,
        mock_get_publisher,
        _mock_publish_event,
    ):
        graph = self._make_graph()
        mock_graph_objects.get.return_value = graph
        mock_get_publisher.return_value = SimpleNamespace(publish_message=lambda *args, **kwargs: None)
        mock_job_objects.filter.return_value.exists.return_value = False
        mock_job_objects.create.return_value = SimpleNamespace(id='job-2')
        mock_dac_config_objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(
            mode='GIT_PUSH_AND_DEPLOY',
            target_repository=SimpleNamespace(git_url='https://github.com/acme/rules', token='token'),
            target_branch='release',
            target_folder='detections',
            target_platforms=['splunk', 'qradar'],
            publish_profile=None,
        )
        mock_platform_credential_objects.filter.return_value.values_list.return_value = [
            'splunk',
            'qradar',
        ]

        AdminApproveDeployment.mutate(None, self._make_info(), id='graph-1')

        kwargs = mock_job_objects.create.call_args.kwargs
        self.assertEqual(kwargs['requested_platforms'], ['splunk', 'qradar'])


class TestQueueDacDeploymentAutomation(SimpleTestCase):
    def _make_graph(self):
        graph = MagicMock()
        graph.id = 'graph-1'
        graph.title = 'Workbench'
        graph.version = 5
        graph.minor_version = 2
        graph.organization = SimpleNamespace(id='org-1')
        graph.author = SimpleNamespace(id='author-1', username='author', organization=graph.organization)
        return graph

    def _make_actor(self):
        return SimpleNamespace(id='user-1', username='admin', organization=SimpleNamespace(id='org-1'))

    @patch('rules.opentide_publish.deploy_opentide_rule_to_platforms', return_value=([{'platform': 'Splunk', 'success': True}], True, 'ok'))
    @patch('rules.opentide_publish.upsert_opentide_rule_for_graph')
    @patch('playbooks.utils.opentide_compiler.dump_opentide_yaml', return_value='raw-yaml')
    @patch('playbooks.utils.opentide_compiler.compile_mdr_yaml', return_value={'name': 'rule'})
    @patch('playbooks.utils.opentide_compiler._normalize_mdr_impacted_entities')
    @patch('playbooks.schema.ActivityLog.objects')
    @patch('organizations.models.PlatformCredential.objects')
    @patch('organizations.models.OpenTideHefPublishJob.objects')
    @patch('organizations.models.DacDeploymentConfig.objects')
    def test_deploy_only_skips_publish_job_and_deploys_directly(
        self,
        mock_dac_config_objects,
        mock_job_objects,
        mock_platform_credential_objects,
        mock_activity_objects,
        _mock_normalize_entities,
        _mock_compile_mdr_yaml,
        _mock_dump_yaml,
        mock_upsert_rule,
        mock_deploy_rule,
    ):
        graph = self._make_graph()
        actor = self._make_actor()
        rule = SimpleNamespace(id='rule-1')
        mock_upsert_rule.return_value = rule
        mock_dac_config_objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(
            mode='DEPLOY_ONLY',
            target_repository=None,
            target_branch='main',
            target_folder='',
            target_platforms=['splunk'],
            publish_profile=None,
        )
        mock_platform_credential_objects.filter.return_value.values_list.return_value = ['splunk']
        mock_activity_objects.filter.return_value.exists.return_value = False

        result = _queue_dac_deployment_automation(graph, actor)

        self.assertTrue(result)
        mock_job_objects.create.assert_not_called()
        mock_activity_objects.create.assert_called_once()
        mock_upsert_rule.assert_called_once_with(graph, actor, 'raw-yaml', repository=None)
        mock_deploy_rule.assert_called_once_with(rule, graph.organization, ['splunk'])


class TestUpdatePlaybookGraphStatusGuard(SimpleTestCase):
    def _make_info(self):
        user = SimpleNamespace(
            id='reviewer-1',
            username='reviewer',
            is_anonymous=False,
            role=Roles.REVIEWER,
            is_superuser=False,
            is_staff=False,
            organization=SimpleNamespace(id='org-1'),
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    @patch('playbooks.schema.PlaybookGraph.objects')
    def test_rejects_setting_deployed_outside_admin_approval(self, mock_graph_objects):
        graph = MagicMock()
        graph.id = 'graph-1'
        graph.organization = SimpleNamespace(id='org-1')
        graph.author = SimpleNamespace(id='author-1')
        mock_graph_objects.get.return_value = graph

        with self.assertRaises(Exception) as exc:
            UpdatePlaybookGraphStatus.mutate(
                None,
                self._make_info(),
                id='graph-1',
                status='DEPLOYED',
            )

        self.assertIn('DEPLOYED status can only be set via admin approval workflow', str(exc.exception))
        graph.save.assert_not_called()
