from types import SimpleNamespace
from unittest.mock import patch

import graphene
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db.models.deletion import RestrictedError
from django.test import TestCase
from graphql import GraphQLError

from ai_assistant.engine import generate_rule_bundle
from ai_assistant.models import AIGenerationTask, AIPromptAuditEvent, AIPromptConfiguration
from ai_assistant.prompt_defaults import PROMPT_DEFAULTS
from ai_assistant.prompt_registry import (create_draft, require_prompt_admin, resolve_prompt,
                                         restore_version, review_version)
from ai_assistant.quality_schema import Query, Mutation
from organizations.models import Organization


KEY = 'rule_generation.generate'


class PromptRegistryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Prompt pilot')
        cls.other_org = Organization.objects.create(name='Other installation tenant')
        User = get_user_model()
        cls.admin = User.objects.create_user('prompt-admin', organization=cls.org, role='ADMIN')
        cls.other_admin = User.objects.create_user('other-admin', organization=cls.other_org, role='ADMIN')
        cls.analyst = User.objects.create_user('service-analyst', organization=cls.org, role='ANALYST')
        cls.staff = User.objects.create_user('staff-user', organization=cls.org, role='ANALYST', is_staff=True)
        cls.superuser = User.objects.create_superuser('prompt-superuser', email='admin@example.test', password='test')

    def draft(self, text='Use the approved local telemetry schema.', *, scope=None, language='KQL', user=None):
        scope = self.org.id if scope is None else scope
        effective = resolve_prompt(KEY, organization_id=scope, language=language)
        return create_draft(user or self.admin, prompt_key=KEY, organization_id=scope, language=language,
                            instructions=text, change_reason='Correct recurring schema errors.',
                            base_fingerprint=effective.fingerprint)

    def approve(self, version):
        return review_version(self.superuser, version_id=version.id, approve=True,
                              review_note='Reviewed the instruction diff and representative outputs.')

    def restore(self, user, **kwargs):
        config = AIPromptConfiguration.objects.get(pk=kwargs['configuration_id'])
        current = resolve_prompt(KEY, organization_id=config.organization_id, language=config.language)
        inherited = resolve_prompt(KEY, organization_id=config.organization_id, language=config.language,
                                   skip_configuration_id=config.id)
        return restore_version(user, expected_fingerprint=current.fingerprint,
                               inherited_fingerprint=inherited.fingerprint, **kwargs)

    def test_default_works_without_seeding(self):
        resolved = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        self.assertEqual(resolved.source, 'DEFAULT')
        self.assertEqual(resolved.instructions, PROMPT_DEFAULTS[KEY]['instructions'])
        self.assertFalse(AIPromptConfiguration.objects.exists())

    def test_draft_does_not_change_generation_until_approval(self):
        version = self.draft()
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL').source, 'DEFAULT')
        self.approve(version)
        effective = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        self.assertEqual(effective.instructions, version.instructions)
        self.assertEqual(effective.version, str(version.id))
        self.assertEqual(list(AIPromptAuditEvent.objects.order_by('created_at').values_list('action', flat=True)),
                         ['DRAFT_CREATED', 'APPROVED_ACTIVATED'])

    def test_language_and_organization_overrides_are_isolated(self):
        self.approve(self.draft())
        self.assertEqual(resolve_prompt(KEY, organization_id=self.other_org.id, language='KQL').source, 'DEFAULT')
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='SPL').source, 'DEFAULT')

    def test_organization_wildcard_precedes_installation_language(self):
        base = resolve_prompt(KEY, language='KQL')
        installation = create_draft(self.superuser, prompt_key=KEY, organization_id=None, language='KQL',
                                    instructions='Installation KQL guidance.', change_reason='Installation baseline.',
                                    base_fingerprint=base.fingerprint)
        self.approve(installation)
        local = self.draft('Organization guidance for all formats.', language='*')
        self.approve(local)
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL').version, str(local.id))
        self.assertEqual(resolve_prompt(KEY, organization_id=self.other_org.id, language='KQL').version, str(installation.id))

    def test_rejected_version_cannot_be_activated(self):
        version = self.draft()
        review_version(self.admin, version_id=version.id, approve=False, review_note='Not supported by evidence.')
        with self.assertRaises(GraphQLError):
            self.restore(self.admin, configuration_id=version.configuration_id,
                            version_id=version.id, reason='Attempt restore.')
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL').source, 'DEFAULT')

    def test_stale_draft_cannot_replace_newly_approved_version(self):
        first = self.draft('First improvement.')
        second = self.draft('Another improvement based on the old prompt.')
        self.approve(first)
        with self.assertRaisesMessage(GraphQLError, 'effective prompt changed'):
            self.approve(second)
        second.refresh_from_db()
        self.assertEqual(second.status, 'DRAFT')

    def test_new_upstream_default_does_not_overwrite_local_version(self):
        version = self.draft()
        self.approve(version)
        with patch.dict(PROMPT_DEFAULTS, {KEY: {**PROMPT_DEFAULTS[KEY], 'version': 'future', 'instructions': 'New baseline.'}}):
            self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL').version, str(version.id))

    def test_upstream_change_invalidates_draft_based_on_default(self):
        version = self.draft()
        with patch.dict(PROMPT_DEFAULTS, {KEY: {**PROMPT_DEFAULTS[KEY], 'version': 'future'}}):
            with self.assertRaises(GraphQLError):
                self.approve(version)

    def test_rollback_and_reset_are_audited(self):
        first = self.draft('First improvement.')
        self.approve(first)
        second = self.draft('Second improvement.')
        self.approve(second)
        self.restore(self.admin, configuration_id=first.configuration_id, version_id=first.id,
                        reason='Second version regressed a validation case.')
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL').version, str(first.id))
        self.restore(self.admin, configuration_id=first.configuration_id, version_id=None,
                        reason='Return to the inherited baseline.')
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL').source, 'DEFAULT')
        event = AIPromptAuditEvent.objects.first()
        self.assertEqual(event.action, 'RESET_TO_INHERITED')
        self.assertEqual(event.previous_version_id, first.id)

    def test_versions_cannot_be_edited_after_creation(self):
        version = self.draft()
        version.instructions = 'Unreviewed mutation.'
        with self.assertRaises(ValidationError):
            version.save()

    def test_audited_version_is_protected_but_organization_can_be_deleted(self):
        version = self.draft()
        self.approve(version)
        with self.assertRaises(RestrictedError):
            version.delete()
        self.org.delete()
        self.assertFalse(AIPromptConfiguration.objects.filter(pk=version.configuration_id).exists())

    def test_permission_checks_have_no_staff_or_service_name_bypass(self):
        for user in [AnonymousUser(), self.analyst, self.staff, self.other_admin]:
            with self.subTest(user=str(user)), self.assertRaises(GraphQLError):
                require_prompt_admin(user, self.org.id)
        with self.assertRaises(GraphQLError):
            require_prompt_admin(self.admin, None)

    def test_cross_organization_review_and_restore_denied(self):
        version = self.draft()
        with self.assertRaises(GraphQLError):
            review_version(self.other_admin, version_id=version.id, approve=True, review_note='Approve.')
        self.approve(version)
        with self.assertRaises(GraphQLError):
            self.restore(self.other_admin, configuration_id=version.configuration_id,
                            version_id=None, reason='Reset.')

    def test_cannot_restore_version_from_another_configuration(self):
        first = self.draft()
        self.approve(first)
        second = self.draft(language='SPL')
        self.approve(second)
        with self.assertRaises(GraphQLError):
            self.restore(self.admin, configuration_id=first.configuration_id, version_id=second.id,
                            reason='Invalid cross-format restore.')

    def test_graphql_scope_and_review_round_trip(self):
        schema = graphene.Schema(query=Query, mutation=Mutation)
        ctx = SimpleNamespace(user=self.admin)
        result = schema.execute('{ aiQualityPrompts(language: "KQL") { promptKey effectiveFingerprint versions { id } } }', context_value=ctx)
        self.assertIsNone(result.errors)
        fingerprint = result.data['aiQualityPrompts'][0]['effectiveFingerprint']
        result = schema.execute('''mutation($base: String!) {
          createQualityPromptDraft(promptKey: "rule_generation.generate", language: "KQL",
            instructions: "Use local tables.", changeReason: "Schema correction.", baseFingerprint: $base) {
            version { id status diff }
          }
        }''', variable_values={'base': fingerprint}, context_value=ctx)
        self.assertIsNone(result.errors)
        version = result.data['createQualityPromptDraft']['version']
        self.assertEqual(version['status'], 'DRAFT')
        self.assertIn('+Use local tables.', version['diff'])
        result = schema.execute('''mutation($id: UUID!) {
          reviewQualityPromptVersion(versionId: $id, approve: true, reviewNote: "Reviewed.") {
            version { status }
          }
        }''', variable_values={'id': version['id']}, context_value=ctx)
        self.assertIsNone(result.errors)
        self.assertEqual(result.data['reviewQualityPromptVersion']['version']['status'], 'APPROVED')
        denied = schema.execute('{ aiQualityPrompts(installation: true) { promptKey } }', context_value=ctx)
        self.assertTrue(denied.errors)

    @patch('ai_assistant.engine._invoke_detection_generation_model')
    @patch('ai_assistant.engine._resolve_provider', return_value='GPT-5.5')
    @patch('ai_assistant.engine.build_available', return_value=['GPT-5.5'])
    def test_generation_uses_approved_prompt_and_records_exact_input(self, available, provider, invoke):
        version = self.draft()
        self.approve(version)
        invoke.return_value = '---PRIMARY-RULE-START---\nProcessEvents_CL | take 1\n---PRIMARY-RULE-END---'
        snapshots = []
        bundle, selected_provider = generate_rule_bundle(
            SimpleNamespace(), {'title': 'Pilot', 'technical_context': 'Custom telemetry.'}, 'KQL',
            organization_id=self.org.id, on_prompt_prepared=snapshots.append,
        )
        self.assertEqual(selected_provider, 'GPT-5.5')
        self.assertIn('ProcessEvents_CL', bundle['primary_rule'])
        snapshot = snapshots[0]
        self.assertEqual(snapshot['version'], str(version.id))
        self.assertIn(version.instructions, snapshot['system_prompt'])
        self.assertIn('---PRIMARY-RULE-START---', snapshot['system_prompt'])
        self.assertIn('Custom telemetry.', snapshot['user_prompt'])
        self.assertEqual(invoke.call_args.args[2:4], (snapshot['system_prompt'], snapshot['user_prompt']))

    @patch('ai_assistant.rag_templates.retrieve_reference_context')
    @patch('ai_assistant.schema._get_effective_ai_settings')
    @patch('ai_assistant.models.UserAISettings.objects.get')
    @patch('ai_assistant.engine._invoke_detection_generation_model')
    @patch('ai_assistant.engine._resolve_provider', return_value='GPT-5.5')
    @patch('ai_assistant.engine.build_available', return_value=['GPT-5.5'])
    def test_worker_persists_prompt_and_retrieved_excerpts(self, available, provider, invoke, settings, effective, retrieve):
        from services.ai_generation_worker import _run_generate_rule
        effective.return_value = SimpleNamespace()
        retrieve.return_value = [{'source_ref': 'pilot.jsonl:1', 'language': 'KQL', 'content': 'ProcessEvents_CL | take 1'}]
        invoke.return_value = '---PRIMARY-RULE-START---\nProcessEvents_CL | take 1\n---PRIMARY-RULE-END---'
        task = AIGenerationTask.objects.create(user=self.admin, task_type='GENERATE_RULE',
                                               organization=self.org,
                                               input_data={'playbook_context': {'title': 'Pilot'}, 'output_format': 'KQL'})
        with patch('services.ai_generation_worker._mark_reference_files_used'):
            result = _run_generate_rule(task)
        task.refresh_from_db()
        self.assertEqual(task.prompt_provenance['reference_context'], retrieve.return_value)
        self.assertIn('ProcessEvents_CL', task.prompt_provenance['user_prompt'])
        self.assertEqual(task.prompt_provenance['organization_id'], str(self.org.id))
        self.assertEqual(result['provider_used'], 'GPT-5.5')
        self.assertEqual(task.prompt_provenance['rag_status'], 'FOUND')

    def test_worker_refuses_generation_after_user_changes_organization(self):
        from services.ai_generation_worker import _run_generate_rule

        task = AIGenerationTask.objects.create(user=self.other_admin, organization=self.org,
                                               task_type='GENERATE_RULE', input_data={})
        with self.assertRaisesMessage(ValueError, 'organization no longer matches'):
            _run_generate_rule(task)

    def test_reset_rejects_changed_inherited_prompt(self):
        version = self.draft()
        self.approve(version)
        current = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        inherited = resolve_prompt(KEY, organization_id=self.org.id, language='KQL',
                                   skip_configuration_id=version.configuration_id)
        with patch.dict(PROMPT_DEFAULTS, {KEY: {**PROMPT_DEFAULTS[KEY], 'version': 'future'}}):
            with self.assertRaisesMessage(GraphQLError, 'inherited prompt changed'):
                restore_version(self.admin, configuration_id=version.configuration_id, version_id=None,
                                reason='Reset.', expected_fingerprint=current.fingerprint,
                                inherited_fingerprint=inherited.fingerprint)
