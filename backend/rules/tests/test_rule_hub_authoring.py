from types import SimpleNamespace
from unittest.mock import patch
import yaml
from django.core.exceptions import PermissionDenied
from django.test import TestCase, SimpleTestCase
from organizations.models import Organization
from identity.models import CustomUser
from playbooks.models import PlaybookGraph
from rules.models import DetectionRule
from rules.authoring import save_draft, document_for_rule, publish_yaml, preview_publish, publish_preview, validate_destination
from rules.schema import LinkRuleWorkbench, DuplicateRule


def document():
    return {'metadata': {'title': 'Suspicious process', 'description': 'Detect suspicious process execution.',
                         'author': 'analyst', 'mitre': {'technique_id': 'T1059'},
                         'response': {'severity': 'HIGH'}, 'status': 'experimental', 'tags': ['process']},
            'platforms': {'kql': {'query': 'DeviceProcessEvents | take 1'}}}


class RuleHubAuthoringTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Authoring')
        self.user = CustomUser.objects.create_user(username='analyst', organization=self.org, role='ANALYST')
        self.info = SimpleNamespace(context=SimpleNamespace(user=self.user))

    def test_save_reopen_uuid_and_multiple_same_format(self):
        first = save_draft(self.user, document())
        second = save_draft(self.user, document())
        self.assertNotEqual(first.sigma_id, second.sigma_id)
        self.assertIsNone(first.playbook_id)
        changed = document_for_rule(first)
        changed['platforms']['spl'] = {'query': 'index=main'}
        saved = save_draft(self.user, changed, first.pk)
        self.assertEqual(saved.sigma_id, first.sigma_id)
        self.assertIn('spl', document_for_rule(saved)['platforms'])
        self.assertEqual(DetectionRule.objects.count(), 2)

    def test_draft_publish_validation_and_free_preservation(self):
        rule = save_draft(self.user, {'metadata': {'title': 'Draft'}, 'platforms': {}})
        with self.assertRaises(ValueError):
            publish_yaml(rule)
        rule = save_draft(self.user, document(), rule.pk)
        payload = yaml.safe_load(publish_yaml(rule))
        self.assertEqual(payload['metadata']['uuid'], str(rule.sigma_id))
        self.assertEqual(set(payload), {'metadata', 'platforms'})
        doc = document(); raw = '\nrule example {\n\tcondition: true  \n}\n'
        doc['freeRule'] = {'content': raw, 'label': 'YARA', 'language': 'plaintext', 'extension': 'yara'}
        rule = save_draft(self.user, doc, rule.pk)
        self.assertEqual(document_for_rule(rule)['freeRule']['content'], raw)
        with self.assertRaisesRegex(ValueError, 'FREE/custom'):
            publish_yaml(rule)

    def test_link_unlink_preserves_primary_and_metadata(self):
        graph = PlaybookGraph.objects.create(title='Workbench', organization=self.org, author=self.user,
                                             detection_rule='primary', detection_rule_format='KQL')
        rule = save_draft(self.user, document())
        LinkRuleWorkbench.mutate(None, self.info, rule.pk, graph.pk)
        graph.refresh_from_db(); rule.refresh_from_db()
        self.assertEqual(graph.detection_rule, 'primary')
        self.assertEqual(rule.attached_workbench_id, graph.pk)
        self.assertIsNone(rule.playbook_id)
        self.assertEqual(document_for_rule(rule)['metadata']['title'], 'Suspicious process')
        LinkRuleWorkbench.mutate(None, self.info, rule.pk)
        rule.refresh_from_db()
        self.assertIsNone(rule.attached_workbench_id)
        self.assertTrue(DetectionRule.objects.filter(pk=rule.pk).exists())

    def test_permissions_cross_org_and_workbench_ownership(self):
        rule = save_draft(self.user, document())
        outsider = CustomUser.objects.create_user(username='other', organization=self.org, role='ANALYST')
        with self.assertRaises(PermissionDenied):
            save_draft(outsider, document(), rule.pk)
        other_org = Organization.objects.create(name='Other')
        graph = PlaybookGraph.objects.create(title='Other', organization=other_org, author=outsider)
        with self.assertRaises(PlaybookGraph.DoesNotExist):
            LinkRuleWorkbench.mutate(None, self.info, rule.pk, graph.pk)
        graph = PlaybookGraph.objects.create(title='Not mine', organization=self.org, author=outsider)
        with self.assertRaisesRegex(Exception, 'Workbench author'):
            LinkRuleWorkbench.mutate(None, self.info, rule.pk, graph.pk)

    def test_duplicate_workbench_owned_rule_without_modifying_source(self):
        rule = save_draft(self.user, document())
        graph = PlaybookGraph.objects.create(title='Workbench', organization=self.org, author=self.user)
        rule.playbook = graph; rule.save()
        with self.assertRaisesRegex(ValueError, 'owned by a Workbench'):
            save_draft(self.user, document(), rule.pk)
        copied = DuplicateRule.mutate(None, self.info, rule.pk).rule
        self.assertNotEqual(copied.sigma_id, rule.sigma_id)
        self.assertIsNone(copied.playbook_id)
        self.assertIsNone(copied.attached_workbench_id)

    @patch('rules.authoring.repository_client')
    def test_preview_publish_only_exact_rule_file(self, factory):
        rule = save_draft(self.user, document())
        client = factory.return_value
        client.resolve_commit_sha.return_value = 'head'; client.get_file_content.return_value = None
        client.commit_files.return_value = 'new-sha'; client.file_web_url.return_value = 'https://git.example/rule'
        preview = preview_publish(self.user, rule.pk, '1', 'main', 'rules/test.yaml')
        self.assertIn('/dev/null', preview['diff'])
        sha, url = publish_preview(self.user, preview['token'], 'Publish test')
        self.assertEqual(sha, 'new-sha')
        self.assertEqual(client.commit_files.call_args.kwargs['files'], {'rules/test.yaml': preview['content']})
        self.assertEqual(client.commit_files.call_args.kwargs['expected_head'], 'head')

    @patch('rules.authoring.repository_client')
    def test_stale_rule_branch_failure_noop_and_token_binding(self, factory):
        rule = save_draft(self.user, document()); client = factory.return_value
        client.resolve_commit_sha.return_value = 'head'; client.get_file_content.return_value = None
        preview = preview_publish(self.user, rule.pk, '1', 'main', 'rules/test.yaml')
        client.resolve_commit_sha.return_value = 'other'
        with self.assertRaisesRegex(ValueError, 'branch changed'):
            publish_preview(self.user, preview['token'], '')
        client.commit_files.assert_not_called(); client.resolve_commit_sha.return_value = 'head'
        changed = document(); changed['metadata']['title'] = 'Changed'
        save_draft(self.user, changed, rule.pk)
        with self.assertRaisesRegex(ValueError, 'rule changed'):
            publish_preview(self.user, preview['token'], '')
        preview = preview_publish(self.user, rule.pk, '1', 'main', 'rules/test.yaml')
        client.commit_files.side_effect = ValueError('Git rejected commit')
        with self.assertRaisesRegex(ValueError, 'Git rejected'):
            publish_preview(self.user, preview['token'], '')
        rule.refresh_from_db(); self.assertEqual(rule.title, 'Changed')
        other = CustomUser.objects.create_user(username='admin', organization=self.org, role='ADMIN')
        with self.assertRaises(PermissionDenied):
            publish_preview(other, preview['token'], '')
        client.get_file_content.return_value = publish_yaml(rule)
        preview = preview_publish(self.user, rule.pk, '1', 'main', 'rules/test.yaml')
        self.assertTrue(preview['unchanged'])
        with self.assertRaisesRegex(ValueError, 'No changes'):
            publish_preview(self.user, preview['token'], '')

    def test_graphql_draft_save_and_link_fields(self):
        import json
        from core.schema import schema
        context = SimpleNamespace(user=self.user)
        result = schema.execute(
            'mutation($document: JSONString!) { saveRuleDraft(document: $document) { rule { id editorDocument workbenchOwned canEdit } } }',
            variable_values={'document': json.dumps(document())}, context_value=context,
        )
        self.assertIsNone(result.errors)
        saved = result.data['saveRuleDraft']['rule']
        self.assertTrue(saved['canEdit'])
        self.assertFalse(saved['workbenchOwned'])
        self.assertEqual(json.loads(saved['editorDocument'])['metadata']['title'], 'Suspicious process')

    @patch('ai_assistant.schema._create_ai_task')
    @patch('ai_assistant.schema.UserAISettings.objects.get')
    def test_standalone_ai_uses_prompt_without_workbench(self, settings, create):
        from ai_assistant.schema import StartGenerateRuleTask
        import uuid
        create.return_value = SimpleNamespace(id=uuid.uuid4())
        with patch('ai_assistant.schema.PlaybookGraph.objects') as graphs:
            result = StartGenerateRuleTask.mutate(None, self.info, description='Detect process execution', telemetry_context='DeviceProcessEvents', output_format='KQL')
        self.assertTrue(result.success)
        graphs.prefetch_related.assert_not_called()
        context = create.call_args.args[2]['playbook_context']
        self.assertEqual(context['goal'], 'Detect process execution')
        self.assertEqual(context['technical_context'], 'DeviceProcessEvents')


class RuleDestinationTests(SimpleTestCase):
    def test_rejects_traversal_and_invalid_branch(self):
        for path in ['../rule.yaml', '/rule.yaml', 'a/../rule.yaml', 'rule.txt', 'a\\rule.yaml', 'a//rule.yaml']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_destination('main', path)
        for branch in ['', 'a..b', 'a b', '-main']:
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                validate_destination(branch, 'rules/test.yaml')

    # This class uses no database; transport requests are mocked.

class RuleGitConflictTests(SimpleTestCase):
    def test_github_rejects_changed_head_before_creating_objects(self):
        from playbooks.repo_clients import RepoClient
        from unittest.mock import MagicMock
        client = RepoClient(repo_url='https://github.com/example/rules.git', token='test')
        response = MagicMock(status_code=200)
        response.json.return_value = {'object': {'sha': 'changed'}}
        with patch.object(client, '_get', return_value=response), patch.object(client, '_post') as post:
            with self.assertRaisesRegex(ValueError, 'Branch changed'):
                client._commit_files_github('main', {'rule.yaml': 'content'}, 'Publish', 'preview-head')
            post.assert_not_called()

    def test_gitlab_and_gitea_pass_commit_conflict_precondition(self):
        from playbooks.repo_clients import RepoClient
        from unittest.mock import MagicMock
        client = RepoClient(repo_url='https://gitlab.com/example/rules.git', token='test')
        response = MagicMock(status_code=201)
        response.json.return_value = {'id': 'committed', 'last_commit_id': 'file-head'}
        file_response = MagicMock(status_code=200)
        file_response.json.return_value = {'last_commit_id': 'file-head'}
        with patch.object(client, 'get_file_content', return_value='old'), patch.object(client, '_get', return_value=file_response), patch.object(client, '_post', return_value=response) as post:
            client._commit_files_gitlab('main', {'rule.yaml': 'new'}, 'Publish', 'preview-head')
            self.assertEqual(post.call_args.kwargs['json']['actions'][0]['last_commit_id'], 'file-head')
        client = RepoClient(repo_url='https://gitea.example/example/rules.git', token='test', provider='GITEA')
        existing = MagicMock(status_code=200); existing.json.return_value = {'sha': 'blob'}
        response.json.return_value = {'commit': {'sha': 'committed'}}
        with patch.object(client, '_get', return_value=existing), patch.object(client, '_put', return_value=response) as put:
            client._commit_files_gitea('main', {'rule.yaml': 'new'}, 'Publish', 'preview-head')
            self.assertEqual(put.call_args.kwargs['json']['last_commit_id'], 'preview-head')
