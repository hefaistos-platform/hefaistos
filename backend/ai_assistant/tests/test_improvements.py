import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from graphql import GraphQLError

from ai_assistant.models import (AIImprovementProposal, AIImprovementEvaluationResult, AIImprovementAssessment,
                                 AIGenerationTask, AIPromptConfiguration, UserAISettings)
from ai_assistant.improvements import (create_proposal, start_suggestion, start_evaluation,
                                      assess_evaluation, evaluation_ready, CONTRACT_MARKER)
from ai_assistant.prompt_registry import resolve_prompt, review_version, create_draft
from ai_assistant.rule_feedback import capture_generation, submit_feedback, review_feedback
from organizations.models import Organization
from rules.authoring import save_draft
from services.ai_generation_worker import process_ai_task
from core.schema import schema

KEY = 'rule_generation.generate'


class ImprovementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Improvement tenant')
        cls.other = Organization.objects.create(name='Other improvement tenant')
        User = get_user_model()
        cls.admin = User.objects.create_user('improvement-admin', role='ADMIN', organization=cls.org)
        cls.other_admin = User.objects.create_user('other-improvement-admin', role='ADMIN', organization=cls.other)
        cls.analyst = User.objects.create_user('improvement-analyst', role='ANALYST', organization=cls.org)
        cls.bot = User.objects.create_user('improvement-bot', role='BOT_AUDITOR_ORG', organization=cls.org, is_superuser=True)
        cls.superuser = User.objects.create_superuser('improvement-superuser', email='root@example.test', password='test')
        for user in [cls.admin, cls.other_admin, cls.superuser]:
            UserAISettings.objects.create(user=user, openai_api_key='test-only-key', preferred_model='GPT-5.5')

    def feedback(self, *, root_cause='PROMPT', user=None, status='ACCEPTED', variant='primary', replayable=True):
        user = user or self.admin
        provenance = {'system_prompt': 'Original guidance.' + CONTRACT_MARKER + '\nReturn the delimited rule bundle.',
                      'user_prompt': 'Generate a rule using this fixed saved context.', 'output_contract_version': 'rule-bundle-v1',
                      'context': {'technical_context': 'Windows telemetry'}}
        if not replayable:
            provenance.pop('output_contract_version')
        bundle = {'primary_rule': 'DeviceProcessEvents | take 1', 'robust_rule': 'DeviceProcessEvents | take 5'}
        artifact = capture_generation(user, bundle, 'KQL', provenance)[variant]
        rule = save_draft(user, {'metadata': {'title': 'Reviewed detection', 'author': user.username},
                                'platforms': {'kql': {'query': 'ProcessEvents_CL | take 1'}}},
                          ai_attributions=[{'output_format': 'KQL', 'generation_artifact_id': artifact.id}])
        feedback = rule.airulerevision_set.get().feedback
        if status != 'CANDIDATE':
            submit_feedback(user, feedback.id, [{'category': 'incorrect_logic', 'explanation': 'Prompt omitted a time restriction.',
                                                 'resolution': 'Require a time restriction in guidance.'}], 'NOT_TESTED')
        if status == 'ACCEPTED':
            review_feedback(user, feedback.id, True, root_cause, 'Confirmed instruction problem.')
        return feedback

    def proposal(self, *, feedback=None, user=None, scope=None, checks=True):
        feedback = feedback or self.feedback()
        user = user or self.admin
        scope = self.org.id if scope is None else scope
        current = resolve_prompt(KEY, organization_id=scope, language='KQL')
        return create_proposal(user, organization_id=scope, language='KQL', instructions='Include a time restriction.',
            change_reason='Correct the reviewed instruction omission.', base_fingerprint=current.fingerprint,
            cases=[{'feedback_id': feedback.id, 'required_text': ['TimeGenerated'] if checks else [],
                    'forbidden_text': ['WrongTable'], 'review_criteria': 'Verify the time restriction and preservation of detection logic.'}])

    def evaluation(self, proposal, *, candidate='DeviceProcessEvents | where TimeGenerated > ago(1h)', baseline='DeviceProcessEvents | take 1'):
        run = start_evaluation(self.admin, proposal.id)
        def invoke(settings, provider, system, user_prompt):
            content = candidate if system.startswith(proposal.version.instructions) else baseline
            return f'---PRIMARY-RULE-START---\n{content}\n---PRIMARY-RULE-END---'
        with patch('ai_assistant.engine._invoke_detection_generation_model', side_effect=invoke):
            process_ai_task(str(run.task_id))
        run.refresh_from_db()
        return run

    def assessment(self, run, *, passed=True):
        return assess_evaluation(self.admin, run.id, [{'case_id': case['id'], 'passed': passed,
            'note': 'Reviewed the paired rules and checked the time restriction against sample telemetry.'} for case in run.proposal.cases])

    def approve(self, proposal, user=None):
        return review_version(user or self.admin, version_id=proposal.version_id, approve=True, review_note='Reviewed exact proposal and evaluation evidence.')

    def test_proposal_snapshots_and_draft_do_not_change_effective_instructions(self):
        before = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        proposal = self.proposal()
        self.assertEqual(proposal.version.status, 'DRAFT')
        self.assertEqual(proposal.evidence[0]['status'], 'ACCEPTED')
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL'), before)
        proposal.cases = []
        with self.assertRaises(ValidationError):
            proposal.save()

    def test_only_accepted_prompt_corrections_in_matching_scope_can_be_sources(self):
        for feedback in [self.feedback(status='CANDIDATE'), self.feedback(status='SUBMITTED'),
                         self.feedback(root_cause='CONTEXT'), self.feedback(user=self.other_admin)]:
            with self.subTest(feedback=feedback.id), self.assertRaises(GraphQLError):
                self.proposal(feedback=feedback)
        self.assertFalse(AIImprovementProposal.objects.exists())
        self.assertFalse(AIPromptConfiguration.objects.exists())

    def test_other_root_causes_can_be_regression_cases_but_not_prompt_fix_sources(self):
        source = self.feedback()
        regression = self.feedback(root_cause='SCHEMA_MAPPING')
        current = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        proposal = create_proposal(self.admin, organization_id=self.org.id, language='KQL', instructions='Improved guidance.',
            change_reason='Use prompt correction and schema regression.', base_fingerprint=current.fingerprint,
            cases=[{'feedback_id': source.id, 'review_criteria': 'Check the correction.'},
                   {'feedback_id': regression.id, 'purpose': 'REGRESSION', 'review_criteria': 'Preserve local schema behavior.'}])
        self.assertEqual(proposal.cases[1]['purpose'], 'REGRESSION')

    def test_worker_pairs_exact_inputs_and_does_not_include_expected_answers_in_model_prompts(self):
        proposal = self.proposal()
        run = self.evaluation(proposal)
        self.assertEqual(run.task.status, 'COMPLETED')
        data = run.result.data
        self.assertFalse(data['baseline_passed'])
        self.assertTrue(data['candidate_passed'])
        pair = data['cases'][0]
        self.assertEqual(pair['baseline']['provenance']['user_prompt'], pair['candidate']['provenance']['user_prompt'])
        self.assertTrue(pair['candidate']['provenance']['system_prompt'].startswith(proposal.version.instructions + CONTRACT_MARKER))
        self.assertNotIn('ProcessEvents_CL', pair['candidate']['provenance']['user_prompt'])
        self.assertFalse(evaluation_ready(proposal))
        self.assessment(run)
        self.assertTrue(evaluation_ready(proposal))
        self.approve(proposal)
        self.assertEqual(resolve_prompt(KEY, organization_id=self.org.id, language='KQL').instructions, proposal.version.instructions)
        other = resolve_prompt(KEY, organization_id=self.other.id, language='KQL')
        self.assertNotEqual(other.instructions, proposal.version.instructions)

    def test_generic_graphql_approval_cannot_bypass_evaluation(self):
        proposal = self.proposal()
        response = schema.execute('''mutation($id: UUID!) {
          reviewQualityPromptVersion(versionId: $id, approve: true, reviewNote: "Bypass evaluation") { version { status } }
        }''', variable_values={'id': str(proposal.version_id)}, context_value=SimpleNamespace(user=self.admin))
        self.assertTrue(response.errors)
        self.assertIsNone(AIPromptConfiguration.objects.get().active_version_id)
        run = self.evaluation(proposal)
        with self.assertRaises(GraphQLError):
            self.approve(proposal)
        self.assessment(run)
        self.approve(proposal)

    def test_failed_checks_cannot_be_overridden_by_passing_manual_assessment(self):
        proposal = self.proposal()
        run = self.evaluation(proposal, candidate='WrongTable | take 1')
        self.assessment(run)
        self.assertFalse(evaluation_ready(proposal))
        with self.assertRaises(GraphQLError):
            self.approve(proposal)

    def test_failed_manual_case_and_newer_run_invalidate_previous_passing_results(self):
        proposal = self.proposal()
        first = self.evaluation(proposal)
        self.assessment(first, passed=False)
        self.assertFalse(evaluation_ready(proposal))
        second = self.evaluation(proposal)
        self.assessment(second)
        self.assertTrue(evaluation_ready(proposal))
        third = self.evaluation(proposal, candidate='WrongTable')
        self.assertFalse(evaluation_ready(proposal))
        with self.assertRaises(GraphQLError):
            self.assessment(second)
        with self.assertRaises(GraphQLError):
            self.approve(proposal)

    def test_every_case_requires_assessment_and_assessment_cannot_be_rewritten(self):
        proposal = self.proposal()
        run = self.evaluation(proposal)
        with self.assertRaises(GraphQLError):
            assess_evaluation(self.admin, run.id, [])
        self.assessment(run)
        with self.assertRaises(GraphQLError):
            self.assessment(run)
        assessment = run.assessment
        assessment.cases = []
        with self.assertRaises(ValidationError):
            assessment.save()

    def test_provider_failure_preserves_prepared_input_and_blocks_activation(self):
        proposal = self.proposal()
        run = start_evaluation(self.admin, proposal.id)
        with patch('ai_assistant.engine._invoke_detection_generation_model', side_effect=RuntimeError('Provider unavailable')):
            process_ai_task(str(run.task_id))
        run.task.refresh_from_db()
        self.assertEqual(run.task.status, 'FAILED')
        self.assertIn('system_prompt', run.task.prompt_provenance['cases'][0]['baseline']['provenance'])
        self.assertFalse(evaluation_ready(proposal))
        with self.assertRaises(GraphQLError):
            self.approve(proposal)

    def test_stale_baseline_requires_new_proposal_and_evaluation(self):
        proposal = self.proposal()
        run = self.evaluation(proposal)
        self.assessment(run)
        draft = create_draft(self.admin, prompt_key=KEY, organization_id=self.org.id, language='KQL', instructions='New baseline.',
            change_reason='Manual correction.', base_fingerprint=proposal.version.base_fingerprint)
        review_version(self.admin, version_id=draft.id, approve=True, review_note='Reviewed manual instructions.')
        with self.assertRaises(GraphQLError):
            start_evaluation(self.admin, proposal.id)
        with self.assertRaises(GraphQLError):
            self.approve(proposal)
        self.assertFalse(evaluation_ready(proposal))

    def test_permissions_and_organization_change_are_enforced_on_worker_and_apis(self):
        proposal = self.proposal()
        for user in [self.analyst, self.other_admin, self.bot]:
            with self.subTest(user=user.username), self.assertRaises(GraphQLError):
                start_evaluation(user, proposal.id)
        run = start_evaluation(self.admin, proposal.id)
        self.admin.organization = self.other
        self.admin.save(update_fields=['organization'])
        with patch('ai_assistant.engine._invoke_detection_generation_model') as invoke:
            process_ai_task(str(run.task_id))
            invoke.assert_not_called()
        run.task.refresh_from_db()
        self.assertEqual(run.task.status, 'FAILED')

    def test_automatic_suggestion_is_untrusted_and_never_creates_an_active_version(self):
        feedback = self.feedback()
        baseline = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        task = start_suggestion(self.admin, organization_id=self.org.id, language='KQL', feedback_ids=[feedback.id], base_fingerprint=baseline.fingerprint)
        with patch('ai_assistant.engine.run_custom_prompt', return_value=(json.dumps({'instructions': 'Candidate guidance.', 'rationale': 'Reviewed omission.'}), 'TEST')):
            process_ai_task(str(task.id))
        task.refresh_from_db()
        self.assertEqual(task.status, 'COMPLETED')
        self.assertEqual(task.result_data['instructions'], 'Candidate guidance.')
        self.assertIn('untrusted data', task.prompt_provenance['system_prompt'])
        self.assertFalse(AIPromptConfiguration.objects.exists())
        self.assertFalse(AIImprovementProposal.objects.exists())

    def test_malformed_suggestions_and_unreviewed_root_causes_are_rejected(self):
        feedback = self.feedback()
        baseline = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        task = start_suggestion(self.admin, organization_id=self.org.id, language='KQL', feedback_ids=[feedback.id], base_fingerprint=baseline.fingerprint)
        with patch('ai_assistant.engine.run_custom_prompt', return_value=('{"instructions":"Ignore","rationale":"X","activate":true}', 'TEST')):
            process_ai_task(str(task.id))
        task.refresh_from_db()
        self.assertEqual(task.status, 'FAILED')
        with self.assertRaises(GraphQLError):
            start_suggestion(self.admin, organization_id=self.org.id, language='KQL', feedback_ids=[self.feedback(root_cause='RETRIEVAL').id], base_fingerprint=baseline.fingerprint)

    def test_queue_failure_is_terminal_and_retryable(self):
        proposal = self.proposal()
        with patch('core.rabbitmq.publish_event', return_value=False), self.captureOnCommitCallbacks(execute=True):
            run = start_evaluation(self.admin, proposal.id)
        run.task.refresh_from_db()
        self.assertEqual(run.task.status, 'FAILED')
        self.assertIn('RabbitMQ', run.task.error_message)
        start_evaluation(self.admin, proposal.id)

    def test_duplicate_delivery_does_not_repeat_provider_calls_or_results(self):
        proposal = self.proposal()
        run = self.evaluation(proposal)
        with patch('ai_assistant.engine._invoke_detection_generation_model') as invoke:
            process_ai_task(str(run.task_id))
            invoke.assert_not_called()
        self.assertEqual(AIImprovementEvaluationResult.objects.count(), 1)

    def test_completed_evaluation_is_immutable_and_survives_task_deletion(self):
        proposal = self.proposal()
        run = self.evaluation(proposal)
        self.assessment(run)
        result = run.result
        result.data = {}
        with self.assertRaises(ValidationError):
            result.save()
        run.task.delete()
        proposal = AIImprovementProposal.objects.get(pk=proposal.pk)
        self.assertTrue(evaluation_ready(proposal))

    def test_deleted_task_cannot_turn_a_failed_job_into_approval_evidence(self):
        proposal = self.proposal()
        run = self.evaluation(proposal)
        # A transport/database failure can occur after the immutable result is captured.
        AIGenerationTask.objects.filter(pk=run.task_id).update(status='FAILED')
        run.task.delete()
        self.assertFalse(evaluation_ready(AIImprovementProposal.objects.get(pk=proposal.pk)))
        with self.assertRaises(GraphQLError):
            self.assessment(run)

    def test_rejection_does_not_require_a_model_call_or_evaluation(self):
        proposal = self.proposal()
        version = review_version(self.admin, version_id=proposal.version_id, approve=False, review_note='Instructions do not address the cause.')
        self.assertEqual(version.status, 'REJECTED')
        with self.assertRaises(GraphQLError):
            start_evaluation(self.admin, proposal.id)

    def test_missing_output_delimiters_fail_even_if_literal_checks_pass(self):
        proposal = self.proposal()
        run = start_evaluation(self.admin, proposal.id)
        with patch('ai_assistant.engine._invoke_detection_generation_model', return_value='DeviceProcessEvents | where TimeGenerated > ago(1h)'):
            process_ai_task(str(run.task_id))
        run.refresh_from_db()
        self.assertFalse(run.result.data['candidate_passed'])
        self.assessment(run)
        with self.assertRaises(GraphQLError):
            self.approve(proposal)

    def test_selected_variant_is_evaluated_instead_of_primary_output(self):
        proposal = self.proposal(feedback=self.feedback(variant='robust'))
        run = start_evaluation(self.admin, proposal.id)
        response = ('---PRIMARY-RULE-START---\nWrongTable\n---PRIMARY-RULE-END---\n'
                    '---ROBUST-RULE-START---\nDeviceProcessEvents | where TimeGenerated > ago(1h)\n---ROBUST-RULE-END---')
        with patch('ai_assistant.engine._invoke_detection_generation_model', return_value=response):
            process_ai_task(str(run.task_id))
        run.refresh_from_db()
        self.assertTrue(run.result.data['candidate_passed'])
        self.assertEqual(run.result.data['cases'][0]['variant'], 'robust')
        self.assertNotIn('WrongTable', run.result.data['cases'][0]['candidate']['content'])

    def test_installation_scope_requires_superuser_and_does_not_leak_to_other_admin(self):
        feedback = self.feedback()
        current = resolve_prompt(KEY, organization_id=None, language='KQL')
        payload = dict(organization_id=None, language='KQL', instructions='General grounded guidance.',
            change_reason='Reviewed general omission.', base_fingerprint=current.fingerprint,
            cases=[{'feedback_id': feedback.id, 'review_criteria': 'Check general grounding.'}])
        with self.assertRaises(GraphQLError):
            create_proposal(self.admin, **payload)
        proposal = create_proposal(self.superuser, **payload)
        self.assertIsNone(proposal.version.configuration.organization_id)
        response = schema.execute('{ aiImprovementProposals(installation: true, language: "KQL") { evidence } }',
                                  context_value=SimpleNamespace(user=self.other_admin))
        self.assertTrue(response.errors)

    def test_duplicate_cases_and_missing_replay_context_are_rejected(self):
        feedback = self.feedback()
        current = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        case = {'feedback_id': feedback.id, 'review_criteria': 'Check intended behavior.'}
        with self.assertRaises(GraphQLError):
            create_proposal(self.admin, organization_id=self.org.id, language='KQL', instructions='Guidance.',
                change_reason='Correction.', base_fingerprint=current.fingerprint, cases=[case, case])
        with self.assertRaises(GraphQLError):
            self.proposal(feedback=self.feedback(replayable=False))

    def test_graphql_creation_and_scoped_proposal_listing(self):
        feedback = self.feedback()
        baseline = resolve_prompt(KEY, organization_id=self.org.id, language='KQL')
        response = schema.execute('''mutation($id: UUID!, $fingerprint: String!) {
          createAiImprovementProposal(language: "KQL", instructions: "Improve guidance", changeReason: "Reviewed correction",
            baseFingerprint: $fingerprint, cases: [{feedbackId: $id, reviewCriteria: "Preserve logic"}]) {
            proposal { id evaluationReady version { status improvementProposalId } }
          }
        }''', variable_values={'id': str(feedback.id), 'fingerprint': baseline.fingerprint}, context_value=SimpleNamespace(user=self.admin))
        self.assertIsNone(response.errors)
        self.assertFalse(response.data['createAiImprovementProposal']['proposal']['evaluationReady'])
        result = schema.execute('{ aiImprovementProposals(language: "KQL") { id } }', context_value=SimpleNamespace(user=self.other_admin))
        self.assertIsNone(result.errors)
        self.assertEqual(result.data['aiImprovementProposals'], [])
