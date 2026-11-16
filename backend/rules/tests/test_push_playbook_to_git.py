from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from identity.decorators import Roles
from rules.schema import PushPlaybookToGit


class PushPlaybookToGitRuleSelectionTests(SimpleTestCase):
    """The destination repository decides where rules go, not which rules are selected.

    SaveDetectionRule files every Workbench rule under the org's placeholder "Rule Repo", so the
    push must select rules by Workbench regardless of the destination repository.
    """

    def _info(self):
        user = SimpleNamespace(
            is_anonymous=False,
            role=Roles.ADMIN,
            is_superuser=False,
            is_staff=False,
            username='admin',
            id='user-1',
            organization=SimpleNamespace(id='org-1'),
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    def _repo(self, git_url='https://github.com/acme/detections.git'):
        repo = MagicMock()
        repo.id = 'repo-dest'
        repo.name = 'detections'
        repo.git_url = git_url
        repo.token = 'tok'
        repo.username = 'acme'
        return repo

    def _rule(self, rule_id='rule-1'):
        return SimpleNamespace(
            id=rule_id,
            title='Rule',
            raw_content='DeviceProcessEvents | take 1',
            author='me',
            format='KQL',
            custom_file_extension=None,
        )

    def _run(self, repo, rules, graph_status='APPROVED'):
        graph = MagicMock()
        graph.status = graph_status
        publisher = MagicMock()
        with patch('rules.schema.PlaybookGraph.objects') as graphs, \
                patch('rules.schema.RuleRepository.objects') as repos, \
                patch('rules.schema.DetectionRule.objects') as rule_objects, \
                patch('rules.schema.get_publisher', return_value=publisher):
            graphs.get.return_value = graph
            repos.get.return_value = repo
            rule_objects.filter.return_value = rules
            result = PushPlaybookToGit.mutate(None, self._info(), graphId='graph-1', repositoryId='repo-dest')
            return result, publisher, rule_objects

    def test_rules_selected_by_workbench_not_by_destination_repository(self):
        repo = self._repo()
        result, publisher, rule_objects = self._run(repo, [self._rule()])

        kwargs = rule_objects.filter.call_args.kwargs
        self.assertIn('playbook', kwargs)
        self.assertNotIn('repository', kwargs)
        self.assertTrue(result.ok)
        self.assertEqual(result.queued_count, 1)
        publisher.publish_message.assert_called_once()

    def test_payload_targets_the_selected_repository(self):
        repo = self._repo()
        _, publisher, _ = self._run(repo, [self._rule('r1'), self._rule('r2')])

        self.assertEqual(publisher.publish_message.call_count, 2)
        _, payload = publisher.publish_message.call_args.args
        self.assertEqual(payload['repository_id'], 'repo-dest')
        self.assertEqual(payload['config']['url'], 'https://github.com/acme/detections.git')

    def test_no_saved_rules_is_an_error_not_a_silent_success(self):
        result, publisher, _ = self._run(self._repo(), [])

        self.assertFalse(result.ok)
        self.assertEqual(result.queued_count, 0)
        self.assertIn('no saved rules', result.message)
        publisher.publish_message.assert_not_called()

    def test_repository_without_git_url_is_rejected(self):
        result, publisher, rule_objects = self._run(self._repo(git_url=None), [self._rule()])

        self.assertFalse(result.ok)
        self.assertIn('no Git URL', result.message)
        publisher.publish_message.assert_not_called()
        rule_objects.filter.assert_not_called()

    def test_unapproved_workbench_is_still_refused(self):
        with self.assertRaises(Exception) as ctx:
            self._run(self._repo(), [self._rule()], graph_status='DRAFT')
        self.assertIn('APPROVED or DEPLOYED', str(ctx.exception))
