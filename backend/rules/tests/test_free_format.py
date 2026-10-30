from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from graphql import GraphQLError

from identity.decorators import Roles
from rules.schema import (SaveDetectionRule, SaveAllDetectionRules, UpdateDetectionRule,
                          GenerateAllDetectionRules, GetAutocompleteOptions, ValidateRuleContent)
from ai_assistant.schema import (StartGenerateRuleTask, StartSuggestImprovementsTask,
                                 StartGenerateSimilarRulesTask, SuggestRuleImprovements,
                                 GenerateSimilarRules, RecommendReusableRuleFromRag)
from playbooks.models import PlaybookGraph


class FreeFormatTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(is_anonymous=False, role=Roles.ADMIN, username='tester',
                                    organization=SimpleNamespace(id=1), is_staff=False, is_superuser=False)
        self.info = SimpleNamespace(context=SimpleNamespace(user=self.user))

    def test_save_preserves_arbitrary_content_without_parsing_or_metadata_injection(self):
        contents = ['\nrule example {\n\tcondition: true  \n}\n',
                    '<?xml version="1.0"?>\n<arbitrary>value</arbitrary>\n',
                    'metadata: {}\nplatforms: {}\n', 'title: Sigma\n\tdetection: anything\n',
                    'rule yara_l { events: $e.metadata.event_type = "PROCESS_LAUNCH" }\n']
        for content in contents:
            with self.subTest(content=content), \
                 patch('rules.schema.PlaybookGraph.objects') as graphs, \
                 patch('rules.schema.RuleRepository.objects') as repos, \
                 patch('rules.schema.DetectionRule.objects') as rules, \
                 patch('rules.schema.detect_rule_format') as detect, \
                 patch('rules.schema.parse_rule_by_format') as parse, \
                 patch('rules.schema.inject_metadata') as inject, \
                 patch('rules.schema.invalidate_mgmt_cave_stats_cache'):
                graphs.select_for_update.return_value.get.return_value = SimpleNamespace(id=1, pk=1, title='Workbench', author=self.user, opentide_yaml={})
                repos.filter.return_value.first.return_value = MagicMock()
                saved = MagicMock(sigma_id='rule-id', custom_format_label='YARA', editor_language='plaintext', custom_file_extension='txt')
                rules.update_or_create.return_value = (saved, True)
                result = SaveDetectionRule.mutate(None, self.info, playbook_id=1, raw_yaml=content,
                                                 format='FREE', custom_format_label='YARA', editor_language='plaintext')
                self.assertTrue(result.success)
                self.assertTrue(result.filename.endswith('.txt'))
                self.assertEqual(saved.raw_content, content)
                defaults = rules.update_or_create.call_args.kwargs['defaults']
                self.assertEqual(defaults['raw_content'], content)
                self.assertEqual(defaults['custom_format_label'], 'YARA')
                self.assertEqual(defaults['editor_language'], 'plaintext')
                detect.assert_not_called()
                parse.assert_not_called()
                inject.assert_not_called()

    def test_bulk_save_passes_exact_free_content_and_preferences(self):
        content = '\n\trule sample {}  \n'
        with patch('rules.schema.SaveDetectionRule.mutate') as save, patch('rules.schema.PlaybookGraph.objects'):
            save.return_value = SimpleNamespace(success=True, filename='rule.txt', message='Saved')
            result = SaveAllDetectionRules.mutate(None, self.info, playbook_id=1, rules=[
                SimpleNamespace(format='FREE', content=content, custom_format_label='YARA-L', editor_language='yaml', custom_file_extension='yml')])
            self.assertTrue(result.success)
            self.assertEqual(save.call_args.kwargs['raw_yaml'], content)
            self.assertEqual(save.call_args.kwargs['custom_format_label'], 'YARA-L')
            self.assertEqual(save.call_args.kwargs['editor_language'], 'yaml')
            self.assertEqual(save.call_args.kwargs['custom_file_extension'], 'yml')

    def test_hub_edit_keeps_free_identity_and_metadata(self):
        rule = MagicMock(format='FREE', author='tester', title='Original', authoring_document=None)
        with patch('rules.schema.DetectionRule.objects.select_for_update') as rules, \
             patch('rules.schema.detect_rule_format') as detect, \
             patch('rules.schema.invalidate_mgmt_cave_stats_cache'):
            rules.return_value.get.return_value = rule
            result = UpdateDetectionRule.mutate(None, self.info, rule_id=1, raw_content='\n<rule/>\n')
            self.assertTrue(result.success)
            self.assertEqual(rule.raw_content, '\n<rule/>\n')
            self.assertEqual(rule.format, 'FREE')
            self.assertEqual(rule.title, 'Original')
            detect.assert_not_called()

    def test_free_has_no_autocomplete_validation_or_rag(self):
        self.assertEqual(GetAutocompleteOptions.mutate(None, self.info, 'FREE', '<xml/>', 1).result.suggestions, [])
        self.assertEqual(ValidateRuleContent.mutate(None, self.info, 'FREE', '<xml/>', 1).result.issues, [])
        self.assertFalse(RecommendReusableRuleFromRag.mutate(None, self.info, playbook_id=1, output_format='FREE').success)

    def test_free_content_is_excluded_from_workbench_ai_context(self):
        from ai_assistant.schema import _supported_workbench_logic
        self.assertEqual(_supported_workbench_logic(SimpleNamespace(detection_rule_format='FREE', detection_rule='secret custom rule')), '')
        self.assertEqual(_supported_workbench_logic(SimpleNamespace(detection_rule_format='KQL', detection_rule='SecurityEvent')), 'SecurityEvent')

    def test_free_cannot_be_generated_or_converted(self):
        for source, targets in [('FREE', ['KQL']), ('KQL', ['FREE'])]:
            self.assertFalse(GenerateAllDetectionRules.mutate(None, self.info, source, 'content', targets).success)
        calls = [
            (StartGenerateRuleTask, dict(playbook_id=1, output_format='FREE')),
            (StartSuggestImprovementsTask, dict(rule_content='rule', rule_format='FREE')),
            (StartGenerateSimilarRulesTask, dict(rule_content='rule', rule_format='FREE')),
            (StartGenerateSimilarRulesTask, dict(rule_content='rule', rule_format='KQL', target_format='FREE')),
            (SuggestRuleImprovements, dict(rule_content='rule', rule_format='FREE')),
            (GenerateSimilarRules, dict(rule_content='rule', target_format='FREE')),
        ]
        for mutation, kwargs in calls:
            with self.subTest(mutation=mutation.__name__), self.assertRaises(GraphQLError):
                mutation.mutate(None, self.info, **kwargs)

    def test_metadata_refresh_preserves_free_without_configuring_platform(self):
        content = {'content': '\n\trule {}\n', 'label': 'YARA', 'language': 'plaintext'}
        graph = PlaybookGraph(opentide_yaml={'metadata': {}, 'platforms': {}, 'freeRule': content})
        with patch('playbooks.utils.opentide_compiler.merge_metadata_with_platforms', return_value={'metadata': {'title': 'Updated'}, 'platforms': {}}):
            graph.auto_update_opentide_yaml()
        self.assertEqual(graph.opentide_yaml['freeRule'], content)
        self.assertEqual(graph.configured_platforms, [])


from django.test import TestCase
from django.contrib.auth import get_user_model
from organizations.models import Organization
from rules.models import DetectionRule
from playbooks.schema import (UpdatePlaybookDetails, serialize_playbook_graph_hex_v2,
                              deserialize_playbook_graph_hex_v2)


class FreeFormatPersistenceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='FREE tests')
        self.user = get_user_model().objects.create_user(username='free-tester', organization=self.organization, role=Roles.ADMIN)
        self.info = SimpleNamespace(context=SimpleNamespace(user=self.user))
        self.graph = PlaybookGraph.objects.create(title='FREE Workbench', organization=self.organization, author=self.user)

    def test_save_reload_metadata_update_and_hex_roundtrip(self):
        raw = '\n\trule example { strings: $a = "`literal`" condition: $a }  \n'
        free = {'content': raw, 'label': 'YARA', 'language': 'plaintext', 'extension': 'yara'}
        self.graph.opentide_yaml = {'platforms': {}, 'freeRule': free}
        self.graph.save()
        UpdatePlaybookDetails.mutate(None, self.info, graph_id=self.graph.pk,
                                     detection_rule=raw, detection_rule_format='FREE')
        result = SaveDetectionRule.mutate(None, self.info, playbook_id=self.graph.pk, raw_yaml=raw,
                                          format='FREE', custom_format_label='YARA', editor_language='plaintext', custom_file_extension='.YARA')
        self.assertTrue(result.success)
        saved = DetectionRule.objects.get(playbook=self.graph, format='FREE')
        self.assertEqual(saved.raw_content, raw)
        self.assertEqual(saved.custom_format_label, 'YARA')
        self.assertEqual(saved.custom_file_extension, 'yara')
        self.assertTrue(result.filename.endswith('.yara'))
        # A later ordinary metadata/tag update must not inject comments into FREE.
        UpdatePlaybookDetails.mutate(None, self.info, graph_id=self.graph.pk, tags=['test'])
        self.graph.refresh_from_db()
        self.assertEqual(self.graph.detection_rule, raw)
        self.assertEqual(self.graph.detection_rule_format, 'FREE')
        self.graph.auto_update_opentide_yaml()
        self.graph.save()
        exported = serialize_playbook_graph_hex_v2(self.graph)
        self.assertEqual(exported['detection_logic']['free_rule'], free)
        self.assertEqual(exported['detection_logic']['rule_format'], 'free')
        imported = deserialize_playbook_graph_hex_v2(exported, self.organization, self.user)
        imported.refresh_from_db()
        self.assertEqual(imported.detection_rule, raw)
        self.assertEqual(imported.detection_rule_format, 'FREE')
        self.assertEqual(imported.opentide_yaml['freeRule'], free)
        self.assertNotIn('free', imported.configured_platforms)

    def test_custom_extensions_accept_user_choice_and_preserve_on_later_save(self):
        for extension in ('.yara', 'yml', '.XML', 'yara-l', 'rules.yaml'):
            with self.subTest(extension=extension):
                result = SaveDetectionRule.mutate(None, self.info, playbook_id=self.graph.pk,
                                                  raw_yaml='arbitrary content', format='FREE', custom_file_extension=extension)
                self.assertTrue(result.success)
                expected = extension.lstrip('.').lower()
                self.assertTrue(result.filename.endswith('.' + expected))
                saved = DetectionRule.objects.get(playbook=self.graph, format='FREE')
                self.assertEqual(saved.custom_file_extension, expected)
                again = SaveDetectionRule.mutate(None, self.info, playbook_id=self.graph.pk,
                                                 raw_yaml='edited content', format='FREE')
                self.assertTrue(again.filename.endswith('.' + expected))

    def test_invalid_extension_is_rejected_without_changing_saved_rule(self):
        for extension in ('', '.', '../yara', 'a/b', 'a\\b', 'a b', '.yara..xml', 'x' * 21):
            with self.subTest(extension=extension):
                result = SaveDetectionRule.mutate(None, self.info, playbook_id=self.graph.pk,
                                                  raw_yaml='content', format='FREE', custom_file_extension=extension)
                self.assertFalse(result.success)
        self.assertFalse(DetectionRule.objects.filter(playbook=self.graph).exists())
