from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from ai_assistant import maieutic_lifecycle as lc
from ai_assistant import maieutic_workbench as mw
from ai_assistant.tests.test_maieutic_workbench import SPEC, ledger_entry
from organizations.models import Organization
from playbooks import negative_tests as nt
from playbooks.models import MitreAttackTechnique


def with_play(**play):
    return {**SPEC, 'playbook_tests': {**SPEC['playbook_tests'], **play}}


class StepListTests(SimpleTestCase):
    def test_well_formed_steps_are_mapped_in_the_shape_the_workbench_expects(self):
        f = mw.workbench_fields(with_play(
            enrichment_steps=[{'action': 'Lookup host', 'input': 'hostname', 'output': 'owner', 'description': 'CMDB'}],
            containment_steps=[{'action': 'Isolate host', 'critical': True, 'description': 'EDR'}],
            notification_steps=[{'channel': 'email', 'recipient': 'soc@example.org', 'template': 'T1'}]))
        self.assertEqual(f['enrichment_steps'], [{'action': 'Lookup host', 'input': 'hostname', 'output': 'owner', 'description': 'CMDB'}])
        self.assertEqual(f['containment_steps'], [{'action': 'Isolate host', 'description': 'EDR', 'critical': True}])
        self.assertEqual(f['notification_steps'], [{'channel': 'email', 'recipient': 'soc@example.org', 'template': 'T1'}])

    def test_empty_lists_are_not_written_so_the_model_default_applies(self):
        f = mw.workbench_fields(SPEC)
        for key in ('enrichment_steps', 'containment_steps', 'notification_steps'):
            self.assertNotIn(key, f)

    def test_entries_without_their_key_field_or_of_the_wrong_type_are_dropped(self):
        f = mw.workbench_fields(with_play(
            enrichment_steps=[{'input': 'x'}, {'action': '  '}, 'junk', None, 5, {'action': 'Keep'}],
            notification_steps=[{'recipient': 'a@b'}]))
        self.assertEqual([s['action'] for s in f['enrichment_steps']], ['Keep'])
        self.assertNotIn('notification_steps', f)

    def test_critical_is_a_real_boolean_never_a_truthy_string(self):
        for raw in ('yes', 'false', 1, None):
            f = mw.workbench_fields(with_play(containment_steps=[{'action': 'A', 'critical': raw}]))
            self.assertIs(f['containment_steps'][0]['critical'], False, raw)

    def test_unknown_keys_dropped_text_clipped_and_count_capped(self):
        f = mw.workbench_fields(with_play(enrichment_steps=[
            {'action': 'A', 'description': 'd' * 9000, 'evil': 'x'}] + [{'action': f'a{i}'} for i in range(100)]))
        self.assertNotIn('evil', f['enrichment_steps'][0])
        self.assertLessEqual(len(f['enrichment_steps'][0]['description']), 2000)
        self.assertEqual(len(f['enrichment_steps']), mw.MAX_STEPS)


class NegativeTestMappingTests(SimpleTestCase):
    def test_only_accepted_limitations_become_tests(self):
        tests = mw.negative_tests_from_spec(SPEC)
        self.assertEqual([t['source_ref'] for t in tests], ['ADE2-02'])
        self.assertIn('Older Windows builds are not covered', tests[0]['accepted_as'])

    def test_unknown_not_applicable_covered_elsewhere_and_handled_never_become_tests(self):
        refs = {t['source_ref'] for t in mw.negative_tests_from_spec(SPEC)}
        self.assertTrue(refs.isdisjoint({'ADE2-01', 'ADE3-01', 'ADE4-01', 'ADE4-02'}))

    def test_users_own_steps_win_over_the_template(self):
        spec = with_play(negative_tests=[{'from_ade_id': 'ADE2-02', 'steps': '1. run on Win7\n2. check'}])
        t = mw.negative_tests_from_spec(spec)[0]
        self.assertEqual((t['steps'], t['steps_source']), ('1. run on Win7\n2. check', nt.STEPS_USER))

    def test_without_written_steps_the_template_is_used_and_marked(self):
        t = mw.negative_tests_from_spec(SPEC)[0]
        self.assertEqual(t['steps_source'], nt.STEPS_TEMPLATE)
        self.assertEqual((t['result'], t['expected']), (nt.NOT_RUN, nt.EXPECTED))

    def test_steps_for_a_limitation_that_is_no_longer_accepted_are_ignored(self):
        spec = with_play(negative_tests=[{'from_ade_id': 'ADE4-01', 'steps': 'orphan'}, {'from_ade_id': 'GONE', 'steps': 'x'}])
        self.assertEqual([t['source_ref'] for t in mw.negative_tests_from_spec(spec)], ['ADE2-02'])

    def test_session_without_limitations_writes_no_negative_tests(self):
        spec = {**SPEC, 'robustness': {'ade_ledger': [ledger_entry('ADE4-01', 'UNKNOWN', '')]}}
        self.assertNotIn('negative_tests', mw.workbench_fields(spec))

    def test_nothing_about_unanswered_work_reaches_the_workbench(self):
        text = repr(mw.workbench_fields(SPEC)).lower()
        for phrase in ('not known yet', 'not answered', 'still open', 'not run'):
            self.assertNotIn(phrase, text.replace("'result': 'not_run'", ''))


class CreateWritesThemTests(TestCase):
    def test_the_created_workbench_holds_the_lists_and_negative_tests(self):
        U = get_user_model()
        org = Organization.objects.create(name='Org')
        author = U.objects.create_user(username='author', organization=org, role='ANALYST')
        MitreAttackTechnique.objects.create(technique_id='T1003.001', name='LSASS Memory')
        d = lc.create_draft(author, name='s')
        spec = with_play(containment_steps=[{'action': 'Isolate', 'critical': True}],
                         negative_tests=[{'from_ade_id': 'ADE2-02', 'steps': 'run it'}])
        d = lc.update_draft(d.id, author, spec_patch=dict(spec))
        with patch('core.rabbitmq.publish_event', return_value=True):
            wb, _tasks = mw.create_workbench_from_draft(d.id, author, exit_mode=mw.EXIT_WITHOUT_RULE)
        self.assertEqual(wb.containment_steps, [{'action': 'Isolate', 'description': '', 'critical': True}])
        self.assertEqual(len(wb.negative_tests), 1)
        self.assertEqual((wb.negative_tests[0]['steps'], wb.negative_tests[0]['result']), ('run it', nt.NOT_RUN))
        self.assertEqual(wb.test_validation_status, 'NOT_TESTED')
