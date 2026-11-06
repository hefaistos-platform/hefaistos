from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from ai_assistant import maieutic_lifecycle as lc
from ai_assistant import maieutic_workbench as mw
from ai_assistant.engine import _format_maieutic_constraints_for_prompt
from ai_assistant.models import AIGenerationTask, UserAISettings
from ai_assistant.maieutic_models import MaieuticDraft
from core.schema import schema
from organizations.models import Organization
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph


def ledger_entry(ade, disposition, answer='', **kw):
    return {'ade_id': ade, 'disposition': disposition, 'answer_text': answer,
            'question_text': f'Question for {ade}?', 'question_version': 1, 'reference': None, 'design_ref': None, **kw}


SPEC = {
    'hypothesis': {'title': 'LSASS dump', 'technique': {'state': 'SET', 'id': 'T1003.001', 'name': 'LSASS Memory'},
                   'goal': 'Detect credential dumping from LSASS', 'attacker_methods': ['comsvcs MiniDump', 'procdump'],
                   'scope_notes': 'Windows servers only'},
    'interrogation': {
        'log_sources': [{'kind': 'LOG_SOURCE', 'ref_id': 'l1', 'name': 'Sysmon Process Creation', 'coverage_status_at_pick': 'ACTIVE'}],
        'fields': [{'id': 'f1', 'standard_name': 'CommandLine', 'siem_field_name': 'winlog.cmd', 'attacker_controlled': 'YES', 'note': ''}],
        'benign_lookalikes': ['Backup agent reads LSASS'],
    },
    'design': {
        'match_elements': [{'id': 'm1', 'description': 'rundll32 loading comsvcs.dll', 'anchor_type': 'FILE_OR_PROCESS_NAME', 'attacker_changeable': 'FREELY'}],
        'exclusions': [{'what': 'signed vendor updater', 'why': 'noisy'}],
        'windows_thresholds': {'time_window': '5m', 'alert_threshold': 3, 'aggregation_field': 'host'},
        'correlations': ['same host'],
        'blueprint_text': 'Look for rundll32 minidump of LSASS',
    },
    'robustness': {'ade_ledger': [
        ledger_entry('ADE2-01', 'HANDLED_IN_DESIGN', 'I also match procdump', design_ref='match_element:m1'),
        ledger_entry('ADE2-02', 'ACCEPTED_LIMITATION', 'Older Windows builds are not covered'),
        ledger_entry('ADE3-01', 'COVERED_BY_OTHER_RULE', 'The EDR rule sees it', reference='RULE-9'),
        ledger_entry('ADE4-01', 'UNKNOWN', ''),
        ledger_entry('ADE4-02', 'NOT_APPLICABLE', 'no relevance'),
    ]},
    'playbook_tests': {'triage_guidance': 'Check parent process', 'response_playbook': 'Isolate host', 'alert_trigger': 'Any hit',
                       'default_severity': 'HIGH', 'test_scenario': 'Run comsvcs MiniDump', 'test_expected_output': 'dump file'},
    'review': {'output_formats': ['SPL', 'WAZUH', 'NOPE']},
}


class MappingTests(SimpleTestCase):
    def test_workbench_fields_follow_the_spec_mapping(self):
        f = mw.workbench_fields(SPEC)
        self.assertEqual(f['title'], 'LSASS dump')
        self.assertIn('Detect credential dumping from LSASS', f['goal'])
        self.assertIn('- comsvcs MiniDump', f['goal'])
        self.assertIn('Sysmon Process Creation (ACTIVE)', f['technical_context'])
        self.assertIn('CommandLine -> winlog.cmd; attacker can control it: YES', f['technical_context'])
        self.assertIn('Look for rundll32 minidump of LSASS', f['technical_context'])
        self.assertIn('- Backup agent reads LSASS', f['false_positives'])
        self.assertIn('- signed vendor updater (noisy)', f['false_positives'])
        self.assertEqual((f['time_window'], f['alert_threshold'], f['aggregation_field']), ('5m', 3, 'host'))
        self.assertEqual((f['default_severity'], f['alert_trigger']), ('HIGH', 'Any hit'))
        self.assertEqual(f['downstream_correlation_requirements'], {'correlationScope': 'same host'})
        self.assertNotIn('telemetry_requirements', f)  # deliberately not written
        self.assertNotIn('robustness_level', f)

    def test_blind_spots_hold_limitations_and_unanswered_count_but_not_unknowns(self):
        blind = mw.workbench_fields(SPEC)['blind_spots']
        self.assertIn('Accepted limitation: Question for ADE2-02? Older Windows builds are not covered', blind)
        self.assertIn('Covered elsewhere: Question for ADE3-01? The EDR rule sees it (covered by: RULE-9)', blind)
        # Not knowing is not a blind spot or a coverage gap.
        self.assertNotIn('Not known yet', blind)
        self.assertNotIn('ADE4-01', blind)
        self.assertNotIn('no relevance', blind)  # NOT_APPLICABLE is not a limitation
        self.assertIn('evasion question(s) were not answered', blind)

    def test_invalid_values_are_dropped_not_stored(self):
        spec = {**SPEC, 'playbook_tests': {'default_severity': 'EXTREME', 'alert_trigger': '  '},
                'design': {'windows_thresholds': {'alert_threshold': 'many', 'time_window': 'x' * 50}}}
        f = mw.workbench_fields(spec)
        self.assertNotIn('default_severity', f)
        self.assertNotIn('alert_trigger', f)
        self.assertNotIn('alert_threshold', f)
        self.assertEqual(len(f['time_window']), 20)

    def test_constraint_groups(self):
        c = mw.build_constraints(SPEC)
        self.assertTrue(any(i.startswith('Match on: rundll32') for i in c['must_implement']))
        self.assertIn('Exclude: signed vendor updater because noisy', c['must_implement'])
        self.assertEqual(c['must_handle'], [{'topic': 'Question for ADE2-01?', 'engineer_says': 'I also match procdump',
                                              'applies_to': 'rundll32 loading comsvcs.dll'}])
        self.assertEqual({i['status'] for i in c['accepted_limitations']}, {'ACCEPTED_LIMITATION', 'COVERED_BY_OTHER_RULE'})

    def test_formats_always_start_with_kql_and_ignore_unknown(self):
        self.assertEqual(mw.selected_formats(SPEC), ['KQL', 'SPL', 'WAZUH'])
        self.assertEqual(mw.selected_formats({}), ['KQL'])
        self.assertEqual(mw.selected_formats({'review': {'output_formats': ['KQL', 'KQL', 'AQL']}}), ['KQL', 'AQL'])


class PromptTests(SimpleTestCase):
    def test_no_block_without_constraints(self):
        self.assertEqual(_format_maieutic_constraints_for_prompt({}), '')
        self.assertEqual(_format_maieutic_constraints_for_prompt({'maieutic_constraints': {}}), '')

    def test_block_separates_the_three_groups(self):
        text = _format_maieutic_constraints_for_prompt({'maieutic_constraints': mw.build_constraints(SPEC)})
        for part in ('MUST IMPLEMENT', 'MUST HANDLE', 'ACCEPTED LIMITATIONS', 'I also match procdump', 'covered by: RULE-9'):
            self.assertIn(part, text)
        # An unknown answer is not handed to the rule as a limitation to list as a blind spot.
        self.assertNotIn('[UNKNOWN]', text)
        self.assertNotIn('ADE4-01', text)

    def test_generator_prompt_only_changes_when_constraints_exist(self):
        from ai_assistant import engine
        seen = []
        base = {'title': 'T', 'technique_id': 'T1', 'technique_name': 'N', 'goal': 'G', 'technical_context': 'C'}
        user_settings = SimpleNamespace(user=SimpleNamespace(username='u', organization_id=None))
        with patch.object(engine, 'build_available', return_value=['X']), patch.object(engine, '_resolve_provider', return_value='GPT-5'), \
                patch.object(engine, '_invoke_detection_generation_model', return_value=''), \
                patch.object(engine, 'resolve_prompt', create=True), \
                patch('ai_assistant.prompt_registry.resolve_prompt', return_value=SimpleNamespace(instructions='S', provenance=lambda: {})):
            engine.generate_rule_bundle(user_settings, base, 'KQL', on_prompt_prepared=lambda p: seen.append(p['user_prompt']))
            engine.generate_rule_bundle(user_settings, {**base, 'maieutic_constraints': mw.build_constraints(SPEC)}, 'KQL',
                                        on_prompt_prepared=lambda p: seen.append(p['user_prompt']))
        plain, with_block = seen
        self.assertNotIn('DESIGN DECISIONS', plain)
        self.assertNotIn('Honour the DESIGN DECISIONS', plain)
        self.assertIn('<design_constraints>', with_block)
        self.assertIn('Honour the DESIGN DECISIONS', with_block)


class CreateTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.author = U.objects.create_user(username='author', organization=self.org, role='ANALYST')
        MitreAttackTechnique.objects.create(technique_id='T1003.001', name='LSASS Memory')
        d = lc.create_draft(self.author, name='s')
        self.draft = lc.update_draft(d.id, self.author, spec_patch={k: v for k, v in SPEC.items()})

    def create(self, mode, draft=None):
        with patch('core.rabbitmq.publish_event', return_value=True) as pub:
            result = mw.create_workbench_from_draft((draft or self.draft).id, self.author, exit_mode=mode)
        return result, pub

    def test_without_rule_creates_workbench_and_locks_session(self):
        (wb, tasks), pub = self.create(mw.EXIT_WITHOUT_RULE)
        self.assertEqual(tasks, [])
        pub.assert_not_called()
        self.assertTrue(wb.goal.startswith('Detect credential'))
        self.assertEqual(wb.mitre_technique.technique_id, 'T1003.001')
        self.assertEqual((wb.author_id, wb.organization_id, wb.status), (self.author.id, self.org.id, 'IDEA'))
        self.assertEqual(wb.time_window, '5m')
        self.assertTrue(any(m['role'] == 'user' and m['content'] == 'I also match procdump' for m in wb.conversation_history))
        d = MaieuticDraft.objects.get(id=self.draft.id)
        self.assertEqual((d.status, d.outcome, d.created_workbench_id), ('FINISHED', 'WORKBENCH_WITHOUT_RULE', wb.id))
        with self.assertRaisesMessage(lc.MaieuticError, 'locked'):
            lc.update_draft(d.id, self.author, name='again')

    def test_with_rule_needs_ai_settings_and_leaves_nothing_behind_without_them(self):
        with self.assertRaisesMessage(lc.MaieuticError, 'AI provider'):
            self.create(mw.EXIT_WITH_RULE)
        self.assertEqual(PlaybookGraph.objects.count(), 0)
        self.assertEqual(MaieuticDraft.objects.get(id=self.draft.id).status, 'IN_PROGRESS')

    def test_with_rule_queues_one_frozen_task_per_format(self):
        UserAISettings.objects.create(user=self.author)
        with self.captureOnCommitCallbacks(execute=True):
            (wb, tasks), pub = self.create(mw.EXIT_WITH_RULE)
        self.assertEqual([t.input_data['output_format'] for t in tasks], ['KQL', 'SPL', 'WAZUH'])
        t = tasks[0]
        self.assertEqual((t.input_data['playbook_id'], t.input_data['maieutic_workbench_id']), (str(wb.id), str(wb.id)))
        self.assertEqual(t.input_data['playbook_context']['maieutic_constraints']['must_handle'][0]['engineer_says'], 'I also match procdump')
        self.assertEqual(pub.call_count, 3)
        self.assertEqual(MaieuticDraft.objects.get(id=self.draft.id).outcome, 'WORKBENCH_WITH_RULE')

    def test_missing_minimum_creates_nothing(self):
        d = lc.create_draft(self.author, name='empty')
        with self.assertRaisesMessage(lc.MaieuticError, 'Missing required answers'):
            self.create(mw.EXIT_WITHOUT_RULE, draft=d)
        self.assertEqual(PlaybookGraph.objects.count(), 0)

    def test_cannot_create_twice_or_for_someone_elses_session(self):
        self.create(mw.EXIT_WITHOUT_RULE)
        with self.assertRaisesMessage(lc.MaieuticError, 'locked'):
            self.create(mw.EXIT_WITHOUT_RULE)
        other = get_user_model().objects.create_user(username='o', organization=self.org, role='ANALYST')
        d2 = lc.create_draft(self.author, name='x')
        with self.assertRaisesMessage(lc.MaieuticError, 'not found'):
            mw.create_workbench_from_draft(d2.id, other, exit_mode=mw.EXIT_WITHOUT_RULE)

    def test_bad_exit_value(self):
        with self.assertRaisesMessage(lc.MaieuticError, 'exit must be'):
            mw.create_workbench_from_draft(self.draft.id, self.author, exit_mode='NOW')


class WriteBackTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.user = U.objects.create_user(username='a', organization=self.org, role='ANALYST')
        self.wb = PlaybookGraph.objects.create(organization=self.org, author=self.user, title='wb')

    def task(self, fmt, **extra):
        return AIGenerationTask.objects.create(
            user=self.user, organization=self.org, task_type='GENERATE_RULE',
            input_data={'output_format': fmt, 'maieutic_workbench_id': str(self.wb.id), **extra})

    def test_kql_goes_to_detection_rule_but_never_overwrites_user_text(self):
        self.assertTrue(mw.apply_generation_result(self.task('KQL'), {'rule': 'DeviceProcessEvents | where x', 'validation_status': 'VALID'}))
        self.wb.refresh_from_db()
        self.assertEqual((self.wb.detection_rule, self.wb.detection_rule_format), ('DeviceProcessEvents | where x', 'KQL'))
        self.assertFalse(mw.apply_generation_result(self.task('KQL'), {'rule': 'something else'}))
        self.wb.refresh_from_db()
        self.assertEqual(self.wb.detection_rule, 'DeviceProcessEvents | where x')

    def test_other_formats_go_to_opentide_platforms(self):
        for fmt, slot, key in (('SPL', 'spl', 'query'), ('EQL', 'elastic', 'query'), ('AQL', 'qradar', 'query'), ('WAZUH', 'wazuh', 'rule')):
            self.assertTrue(mw.apply_generation_result(self.task(fmt), {'rule': f'{fmt} rule'}))
        self.wb.refresh_from_db()
        p = self.wb.opentide_yaml['platforms']
        self.assertEqual((p['spl']['query'], p['elastic']['query'], p['qradar']['query'], p['wazuh']['rule']),
                         ('SPL rule', 'EQL rule', 'AQL rule', 'WAZUH rule'))
        self.assertEqual(set(self.wb.configured_platforms), {'spl', 'elastic', 'qradar', 'wazuh'})

    def test_rejected_or_foreign_results_are_ignored(self):
        self.assertFalse(mw.apply_generation_result(self.task('KQL'), {'rule': None, 'validation_status': 'ADVISORY_REVIEW_REQUIRED'}))
        t = self.task('KQL')
        t.input_data = {'output_format': 'KQL'}  # no maieutic marker
        self.assertFalse(mw.apply_generation_result(t, {'rule': 'x'}))
        other_org = Organization.objects.create(name='Other')
        t2 = AIGenerationTask.objects.create(user=self.user, organization=other_org, task_type='GENERATE_RULE',
                                             input_data={'output_format': 'KQL', 'maieutic_workbench_id': str(self.wb.id)})
        self.assertFalse(mw.apply_generation_result(t2, {'rule': 'x'}))
        self.wb.refresh_from_db()
        self.assertEqual(self.wb.detection_rule, '')

    def test_worker_stores_the_result_after_completion(self):
        from services import ai_generation_worker as w
        t = self.task('KQL')
        with patch.dict(w._TASK_HANDLERS, {'GENERATE_RULE': lambda task: {'rule': 'KQL from worker', 'validation_status': 'VALID'}}):
            w.process_ai_task(str(t.id))
        t.refresh_from_db()
        self.wb.refresh_from_db()
        self.assertEqual((t.status, self.wb.detection_rule), ('COMPLETED', 'KQL from worker'))

    def test_a_failing_write_back_does_not_fail_the_task(self):
        from services import ai_generation_worker as w
        t = self.task('KQL')
        with patch.dict(w._TASK_HANDLERS, {'GENERATE_RULE': lambda task: {'rule': 'r'}}), \
                patch('ai_assistant.maieutic_workbench.apply_generation_result', side_effect=RuntimeError('boom')):
            w.process_ai_task(str(t.id))
        t.refresh_from_db()
        self.assertEqual(t.status, 'COMPLETED')

    def test_status_lists_only_my_tasks_for_that_workbench(self):
        self.task('KQL')
        t2 = self.task('SPL')
        t2.status, t2.result_data = 'COMPLETED', {'rule': 'r', 'validation_status': 'VALID'}
        t2.save()
        U = get_user_model()
        stranger = U.objects.create_user(username='z', organization=self.org, role='ANALYST')
        rows = mw.generation_status(self.wb.id, self.user)
        self.assertEqual([(r['output_format'], r['status'], r['has_rule']) for r in rows], [('KQL', 'PENDING', False), ('SPL', 'COMPLETED', True)])
        self.assertEqual(mw.generation_status(self.wb.id, stranger), [])


class GraphqlTests(TestCase):
    def test_mutation_and_status_query(self):
        U = get_user_model()
        org = Organization.objects.create(name='Org')
        user = U.objects.create_user(username='a', organization=org, role='ANALYST')
        d = lc.create_draft(user, name='s')
        lc.update_draft(d.id, user, spec_patch=SPEC)
        ctx = SimpleNamespace(user=user)
        r = schema.execute('mutation($i:UUID!){createWorkbenchFromMaieuticDraft(draftId:$i,exit:"CREATE_WITHOUT_RULE"){workbenchId queuedFormats draft{status outcome isLocked}}}',
                           variable_values={'i': str(d.id)}, context_value=ctx)
        self.assertIsNone(r.errors, r.errors)
        out = r.data['createWorkbenchFromMaieuticDraft']
        self.assertEqual(out['queuedFormats'], [])
        self.assertEqual(out['draft'], {'status': 'FINISHED', 'outcome': 'WORKBENCH_WITHOUT_RULE', 'isLocked': True})
        r2 = schema.execute('query($w:UUID!){maieuticGenerationStatus(workbenchId:$w){status}}',
                            variable_values={'w': out['workbenchId']}, context_value=ctx)
        self.assertIsNone(r2.errors)
        self.assertEqual(r2.data['maieuticGenerationStatus'], [])
        r3 = schema.execute('mutation($i:UUID!){createWorkbenchFromMaieuticDraft(draftId:$i,exit:"CREATE_WITHOUT_RULE"){workbenchId}}',
                            variable_values={'i': str(d.id)}, context_value=ctx)
        self.assertIn('locked', r3.errors[0].message)
