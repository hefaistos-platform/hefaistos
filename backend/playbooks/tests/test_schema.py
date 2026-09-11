from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from identity.decorators import Roles
from playbooks.schema import (
    DeleteDetectionPlaybook,
    DeletePlaybookGraph,
    PushPlaybookToGitHub,
    RefreshOpenTideMetadata,
    UpdatePlaybookOpenTideYaml,
)


class TestPushPlaybookToGitHubPlatformRules(SimpleTestCase):
    def _make_info(self):
        user = SimpleNamespace(
            is_anonymous=False,
            role=Roles.ADMIN,
            is_superuser=False,
            is_staff=False,
            username='analyst',
            organization=SimpleNamespace(id='org-1'),
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    @patch('playbooks.schema.ActivityLog.objects.create')
    @patch.object(PushPlaybookToGitHub, '_create_github_commit')
    @patch.object(PushPlaybookToGitHub, '_build_platform_rule_files')
    @patch('playbooks.schema.PlaybookGraph.objects')
    def test_mutation_push_platform_rules_only_uses_platform_directories(
        self,
        mock_graph_objects,
        mock_build_platform,
        mock_create_commit,
        _mock_activity,
    ):
        graph = MagicMock()
        graph.id = 'graph-1'
        graph.title = 'My Graph'
        mock_graph_objects.select_related.return_value.prefetch_related.return_value.get.return_value = graph
        mock_build_platform.return_value = ({
            'files': {
                'kql/test_rule.kql': 'DeviceProcessEvents | take 10',
                'splunk/test_rule.spl': 'index=main | head 10',
            },
            'primary_path': 'kql/test_rule.kql',
        }, [])

        result = PushPlaybookToGitHub.mutate(
            None,
            self._make_info(),
            graph_id='graph-1',
            github_token='token',
            repo_owner='acme',
            repo_name='repo',
            push_opentide_bundle=False,
            push_platform_rules=True,
        )

        self.assertTrue(result.success)
        files = mock_create_commit.call_args.kwargs['files']
        self.assertEqual(set(files.keys()), {'kql/test_rule.kql', 'splunk/test_rule.spl'})

    @patch('playbooks.schema.ActivityLog.objects.create')
    @patch.object(PushPlaybookToGitHub, '_create_github_commit')
    @patch.object(PushPlaybookToGitHub, '_build_platform_rule_files')
    @patch.object(PushPlaybookToGitHub, '_build_opentide_bundle')
    @patch('playbooks.schema.PlaybookGraph.objects')
    def test_mutation_merges_bundle_and_platform_rule_files(
        self,
        mock_graph_objects,
        mock_build_bundle,
        mock_build_platform,
        mock_create_commit,
        _mock_activity,
    ):
        graph = MagicMock()
        graph.id = 'graph-2'
        graph.title = 'My Graph'
        mock_graph_objects.select_related.return_value.prefetch_related.return_value.get.return_value = graph

        mock_build_bundle.return_value = ({
            'files': {
                'Objects/Detection Rules/mdr_test.yaml': 'name: mdr_test',
            },
            'primary_path': 'Objects/Detection Rules/mdr_test.yaml',
        }, [])
        mock_build_platform.return_value = ({
            'files': {
                'kql/mdr_test.kql': 'DeviceProcessEvents | where true',
            },
            'primary_path': 'kql/mdr_test.kql',
        }, [])

        result = PushPlaybookToGitHub.mutate(
            None,
            self._make_info(),
            graph_id='graph-2',
            github_token='token',
            repo_owner='acme',
            repo_name='repo',
            push_opentide_bundle=True,
            push_platform_rules=True,
        )

        self.assertTrue(result.success)
        files = mock_create_commit.call_args.kwargs['files']
        self.assertIn('Objects/Detection Rules/mdr_test.yaml', files)
        self.assertIn('kql/mdr_test.kql', files)


class TestSuperuserDeletePermissions(SimpleTestCase):
    def _make_info(self):
        user = SimpleNamespace(
            is_anonymous=False,
            role=Roles.VIEWER,
            is_superuser=True,
            is_staff=False,
            username='platform-admin',
            id='su-1',
            organization=None,
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    @patch('playbooks.schema.PlaybookGraph.objects.get')
    def test_delete_playbook_graph_allows_superuser_without_org_or_author_match(self, mock_get):
        graph = MagicMock()
        graph.author_id = 'other-user'
        graph.status = 'DRAFT'
        graph.playbooks.all.return_value = []
        mock_get.return_value = graph

        result = DeletePlaybookGraph.mutate(None, self._make_info(), graph_id='graph-1')

        self.assertTrue(result.ok)
        mock_get.assert_called_once_with(pk='graph-1')
        graph.delete.assert_called_once()

    @patch('playbooks.schema.DetectionPlaybook.objects.get')
    def test_delete_detection_playbook_allows_superuser_without_org_filter(self, mock_get):
        playbook = MagicMock()
        mock_get.return_value = playbook

        result = DeleteDetectionPlaybook.mutate(None, self._make_info(), playbook_id='pb-1')

        self.assertTrue(result.ok)
        mock_get.assert_called_once_with(pk='pb-1')
        playbook.delete.assert_called_once()


class TestOpenTideMutationsStatusStability(SimpleTestCase):
    def _make_user(self):
        return SimpleNamespace(
            is_anonymous=False,
            role=Roles.ADMIN,
            is_superuser=False,
            is_staff=False,
            username='admin',
            id='user-1',
            organization=SimpleNamespace(id='org-1'),
        )

    @patch('playbooks.schema.ActivityLog.objects.create')
    @patch('playbooks.schema.PlaybookGraph.objects.get')
    def test_update_opentide_yaml_does_not_update_status_field(self, mock_get, _mock_activity):
        user = self._make_user()
        graph = MagicMock()
        graph.id = 'graph-1'
        graph.author = user
        graph.organization = user.organization
        graph.configured_platforms = []
        graph.status = 'DEPLOYED'
        mock_get.return_value = graph

        result = UpdatePlaybookOpenTideYaml.mutate(
            None,
            SimpleNamespace(context=SimpleNamespace(user=user)),
            graph_id='graph-1',
            opentide_yaml='{"metadata":{"title":"test"},"platforms":{}}',
            configured_platforms=['kql'],
        )

        self.assertTrue(result.success)
        graph.save.assert_called_once_with(update_fields=['opentide_yaml', 'configured_platforms', 'updated_at'])

    @patch('playbooks.schema.ActivityLog.objects.create')
    @patch('playbooks.schema.PlaybookGraph.objects.get')
    def test_refresh_opentide_metadata_does_not_update_status_field(self, mock_get, _mock_activity):
        user = self._make_user()
        graph = MagicMock()
        graph.id = 'graph-2'
        graph.author = user
        graph.organization = user.organization
        graph.opentide_yaml = {'metadata': {'title': 'test'}}
        graph.status = 'DEPLOYED'
        mock_get.return_value = graph

        result = RefreshOpenTideMetadata.mutate(
            None,
            SimpleNamespace(context=SimpleNamespace(user=user)),
            playbook_id='graph-2',
        )

        self.assertTrue(result.success)
        graph.auto_update_opentide_yaml.assert_called_once_with()
        graph.save.assert_called_once_with(update_fields=['opentide_yaml', 'configured_platforms', 'updated_at'])
