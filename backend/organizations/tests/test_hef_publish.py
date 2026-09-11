from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from identity.decorators import Roles
from organizations.schema import PublishWorkbenchOpenTide


class TestPublishWorkbenchOpenTide(SimpleTestCase):
    def _make_info(self):
        user = SimpleNamespace(
            id='user-1',
            is_anonymous=False,
            role=Roles.ADMIN,
            is_superuser=False,
            is_staff=False,
            organization=SimpleNamespace(id='org-1'),
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    def _make_graph(self):
        linked_rules = MagicMock()
        linked_rules.filter.return_value.exclude.return_value.exclude.return_value.exists.return_value = True
        return SimpleNamespace(
            id='graph-1',
            title='Workbench',
            status='APPROVED',
            configured_platforms=['defender'],
            linked_rules=linked_rules,
        )

    @patch('core.rabbitmq.publish_event', return_value=True)
    @patch('organizations.schema.OpenTideHefPublishJob.objects.create')
    @patch('organizations.schema.PlatformCredential.objects.filter')
    @patch('organizations.schema.OpenTidePublishProfile.objects')
    @patch('playbooks.models.PlaybookGraph.objects')
    def test_explicit_empty_platform_selection_skips_profile_defaults(
        self,
        mock_graph_objects,
        mock_profile_objects,
        mock_platform_filter,
        mock_job_create,
        _mock_publish_event,
    ):
        graph = self._make_graph()
        repository = SimpleNamespace(id='repo-1', git_url='https://github.com/acme/repo', token='token')
        profile = SimpleNamespace(
            repository=repository,
            enabled_platforms=['splunk'],
            use_graph_configured_platforms=True,
            branch='main',
            target_folder='content/hef',
            push_platform_rules=True,
        )
        mock_graph_objects.prefetch_related.return_value.get.return_value = graph
        mock_profile_objects.select_related.return_value.get.return_value = profile
        mock_job_create.return_value = SimpleNamespace(id='job-1')

        result = PublishWorkbenchOpenTide.mutate(
            None,
            self._make_info(),
            graph_id='graph-1',
            profile_id='profile-1',
            platforms=[],
        )

        self.assertTrue(result.success)
        self.assertIn('No deployment targets selected', result.message)
        self.assertEqual(mock_job_create.call_args.kwargs['requested_platforms'], [])
        self.assertTrue(mock_job_create.call_args.kwargs['push_opentide_bundle'])
        self.assertTrue(mock_job_create.call_args.kwargs['push_platform_rules'])
        mock_platform_filter.assert_not_called()

    @patch('core.rabbitmq.publish_event', return_value=True)
    @patch('organizations.schema.OpenTideHefPublishJob.objects.create')
    @patch('organizations.schema.PlatformCredential.objects.filter')
    @patch('organizations.schema.OpenTidePublishProfile.objects')
    @patch('playbooks.models.PlaybookGraph.objects')
    def test_omitted_platform_selection_uses_profile_defaults(
        self,
        mock_graph_objects,
        mock_profile_objects,
        mock_platform_filter,
        mock_job_create,
        _mock_publish_event,
    ):
        graph = self._make_graph()
        repository = SimpleNamespace(id='repo-1', git_url='https://github.com/acme/repo', token='token')
        profile = SimpleNamespace(
            repository=repository,
            enabled_platforms=['splunk'],
            use_graph_configured_platforms=True,
            branch='main',
            target_folder='content/hef',
            push_platform_rules=False,
        )
        mock_graph_objects.prefetch_related.return_value.get.return_value = graph
        mock_profile_objects.select_related.return_value.get.return_value = profile
        mock_platform_filter.return_value.values_list.return_value = ['splunk']
        mock_job_create.return_value = SimpleNamespace(id='job-2')

        result = PublishWorkbenchOpenTide.mutate(
            None,
            self._make_info(),
            graph_id='graph-1',
            profile_id='profile-1',
            platforms=None,
        )

        self.assertTrue(result.success)
        self.assertIn('Deployment targets: splunk', result.message)
        self.assertEqual(mock_job_create.call_args.kwargs['requested_platforms'], ['splunk'])

    @patch('core.rabbitmq.publish_event', return_value=True)
    @patch('organizations.schema.OpenTideHefPublishJob.objects.create')
    @patch('organizations.schema.PlatformCredential.objects.filter')
    @patch('organizations.schema.OpenTidePublishProfile.objects')
    @patch('playbooks.models.PlaybookGraph.objects')
    def test_profile_kql_policy_is_used_when_request_omits_override(
        self,
        mock_graph_objects,
        mock_profile_objects,
        mock_platform_filter,
        mock_job_create,
        _mock_publish_event,
    ):
        graph = self._make_graph()
        graph.configured_platforms = ['kql']
        repository = SimpleNamespace(id='repo-1', git_url='https://github.com/acme/repo', token='token')
        profile = SimpleNamespace(
            repository=repository,
            enabled_platforms=[],
            use_graph_configured_platforms=True,
            branch='main',
            target_folder='content/hef',
            push_platform_rules=False,
            kql_target_policy='sentinel',
        )
        mock_graph_objects.prefetch_related.return_value.get.return_value = graph
        mock_profile_objects.select_related.return_value.get.return_value = profile
        mock_platform_filter.return_value.values_list.return_value = ['sentinel']
        mock_job_create.return_value = SimpleNamespace(id='job-3')

        result = PublishWorkbenchOpenTide.mutate(
            None,
            self._make_info(),
            graph_id='graph-1',
            profile_id='profile-1',
            platforms=None,
            kql_target_policy=None,
        )

        self.assertTrue(result.success)
        self.assertEqual(mock_job_create.call_args.kwargs['requested_platforms'], ['sentinel'])

    @patch('core.rabbitmq.publish_event', return_value=True)
    @patch('organizations.schema.OpenTideHefPublishJob.objects.create')
    @patch('organizations.schema.PlatformCredential.objects.filter')
    @patch('organizations.schema.OpenTidePublishProfile.objects')
    @patch('playbooks.models.PlaybookGraph.objects')
    def test_request_kql_policy_overrides_profile_default(
        self,
        mock_graph_objects,
        mock_profile_objects,
        mock_platform_filter,
        mock_job_create,
        _mock_publish_event,
    ):
        graph = self._make_graph()
        graph.configured_platforms = ['kql']
        repository = SimpleNamespace(id='repo-1', git_url='https://github.com/acme/repo', token='token')
        profile = SimpleNamespace(
            repository=repository,
            enabled_platforms=[],
            use_graph_configured_platforms=True,
            branch='main',
            target_folder='content/hef',
            push_platform_rules=False,
            kql_target_policy='sentinel',
        )
        mock_graph_objects.prefetch_related.return_value.get.return_value = graph
        mock_profile_objects.select_related.return_value.get.return_value = profile
        mock_platform_filter.return_value.values_list.return_value = ['defender', 'sentinel']
        mock_job_create.return_value = SimpleNamespace(id='job-4')

        result = PublishWorkbenchOpenTide.mutate(
            None,
            self._make_info(),
            graph_id='graph-1',
            profile_id='profile-1',
            platforms=None,
            kql_target_policy='both',
        )

        self.assertTrue(result.success)
        self.assertEqual(mock_job_create.call_args.kwargs['requested_platforms'], ['defender', 'sentinel'])
