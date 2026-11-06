import time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from core.schema import schema
from organizations.models import Organization
from playbooks import negative_tests as nt
from playbooks.models import PlaybookGraph
from playbooks.schema import (
    deserialize_playbook_graph, deserialize_playbook_graph_hex_v2, serialize_playbook_graph,
    serialize_playbook_graph_hex_v2, update_playbook_graph_from_hex_v2, update_playbook_graph_from_v1,
)

RULE = 'DeviceProcessEvents | where FileName =~ "rundll32.exe"'
RECORD = '''mutation($g:UUID!,$t:UUID!,$r:String,$s:String,$n:String){
  updateNegativeTest(graphId:$g,testId:$t,result:$r,steps:$s,notes:$n){negativeTests}}'''
READ = 'query($id:UUID!){playbookGraph(id:$id){negativeTests}}'


class NegativeTestApiBase(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.other_org = Organization.objects.create(name='Other')
        self.user = U.objects.create_user(username='nt_admin', organization=self.org, role='ADMIN')
        self.analyst = U.objects.create_user(username='nt_analyst', organization=self.org, role='ANALYST')
        self.auditor = U.objects.create_user(username='nt_auditor', organization=self.org, role='BOT_AUDITOR_ORG')
        self.outsider = U.objects.create_user(username='nt_out', organization=self.other_org, role='ADMIN')
        self.tests = [nt.new_item('ADE4-01', 'Ordinal export?', 'Accepted.')]
        self.graph = PlaybookGraph.objects.create(
            organization=self.org, author=self.user, title='wb', status='IDEA', detection_rule=RULE,
            negative_tests=self.tests, test_validation_status='PASSED')
        self.tid = self.tests[0]['id']
        patcher = patch('playbooks.l1_portal.upsert_l1_portal_snapshot')
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_gql(self, query, variables, user=None):
        user = user or self.user
        return schema.execute(query, variable_values=variables, context_value=SimpleNamespace(user=user))

    def record(self, user=None, **kw):
        variables = {'g': str(self.graph.id), 't': self.tid, 'r': None, 's': None, 'n': None, **kw}
        return self.run_gql(RECORD, variables, user)

    def stored(self):
        return PlaybookGraph.objects.get(pk=self.graph.pk)


class MutationTests(NegativeTestApiBase):
    def test_recording_a_result_is_stored_and_returned(self):
        result = self.record(r='NOT_DETECTED', n='Ran on lab-win-01')
        self.assertIsNone(result.errors)
        row = result.data['updateNegativeTest']['negativeTests'][0]
        self.assertEqual((row['result'], row['notes'], row['stale']), ('NOT_DETECTED', 'Ran on lab-win-01', False))
        self.assertEqual(self.stored().negative_tests[0]['result'], 'NOT_DETECTED')

    def test_recording_does_not_touch_version_updated_at_or_the_workbench_test_status(self):
        before = self.stored()
        time.sleep(0.01)
        self.assertIsNone(self.record(r='DETECTED').errors)
        after = self.stored()
        self.assertEqual((after.version, after.minor_version, after.updated_at, after.test_validation_status),
                         (before.version, before.minor_version, before.updated_at, 'PASSED'))
        self.assertEqual(after.last_tested_at, before.last_tested_at)

    def test_result_becomes_stale_when_the_rule_changes(self):
        self.record(r='NOT_DETECTED')
        read = lambda: self.run_gql(READ, {'id': str(self.graph.id)}).data['playbookGraph']['negativeTests'][0]['stale']
        self.assertFalse(read())
        PlaybookGraph.objects.filter(pk=self.graph.pk).update(detection_rule=RULE.replace('rundll32', 'regsvr32'))
        self.assertTrue(read())

    def test_editing_steps_clears_the_result(self):
        self.record(r='DETECTED')
        row = self.record(s='A different procedure').data['updateNegativeTest']['negativeTests'][0]
        self.assertEqual((row['steps'], row['result'], row['steps_source']), ('A different procedure', 'NOT_RUN', 'USER'))

    def test_invalid_input_is_rejected_and_nothing_changes(self):
        for kw in ({'r': 'PASSED'}, {'s': '   '}):
            result = self.record(**kw)
            self.assertTrue(result.errors, kw)
        self.assertEqual(self.stored().negative_tests[0]['result'], 'NOT_RUN')

    def test_unknown_test_id_is_rejected(self):
        result = self.run_gql(RECORD, {'g': str(self.graph.id), 't': '11111111-1111-1111-1111-111111111111', 'r': 'DETECTED'})
        self.assertTrue(result.errors)

    def test_analyst_may_record_but_auditor_anonymous_and_other_org_may_not(self):
        self.assertIsNone(self.record(user=self.analyst, r='NOT_DETECTED').errors)
        PlaybookGraph.objects.filter(pk=self.graph.pk).update(negative_tests=self.tests)
        for who in (self.auditor, AnonymousUser(), self.outsider):
            result = self.record(user=who, r='DETECTED')
            self.assertTrue(result.errors, who)
        self.assertEqual(self.stored().negative_tests[0]['result'], 'NOT_RUN')


class ExportImportTests(NegativeTestApiBase):
    def setUp(self):
        super().setUp()
        self.record(r='NOT_DETECTED', n='lab run')
        self.graph = self.stored()

    def test_both_export_formats_carry_the_tests(self):
        self.assertEqual(serialize_playbook_graph(self.graph)['playbook']['negative_tests'][0]['result'], 'NOT_DETECTED')
        self.assertEqual(serialize_playbook_graph_hex_v2(self.graph)['testing']['negative_tests'][0]['notes'], 'lab run')

    def test_import_round_trips_both_formats(self):
        for dump, load in ((serialize_playbook_graph, deserialize_playbook_graph),
                           (serialize_playbook_graph_hex_v2, deserialize_playbook_graph_hex_v2)):
            data = dump(self.graph)
            copy = load(data, self.org, self.user)
            self.assertEqual(copy.negative_tests[0]['id'], self.tid)
            self.assertEqual(copy.negative_tests[0]['result'], 'NOT_DETECTED')

    def test_import_sanitises_hostile_values(self):
        data = serialize_playbook_graph(self.graph)
        data['playbook']['negative_tests'] = [{'id': 'x', 'result': 'PASSED', 'steps': 's', 'evil': '<b>'}, 'junk', None]
        copy = deserialize_playbook_graph(data, self.org, self.user)
        self.assertEqual(len(copy.negative_tests), 1)
        self.assertEqual(copy.negative_tests[0]['result'], 'NOT_RUN')
        self.assertNotIn('evil', copy.negative_tests[0])

    def test_updating_from_an_older_file_keeps_recorded_results(self):
        data = serialize_playbook_graph(self.graph)
        del data['playbook']['negative_tests']
        update_playbook_graph_from_v1(data, self.graph, self.user)
        self.assertEqual(self.stored().negative_tests[0]['result'], 'NOT_DETECTED')
        data2 = serialize_playbook_graph_hex_v2(self.graph)
        del data2['testing']['negative_tests']
        update_playbook_graph_from_hex_v2(data2, self.graph, self.user)
        self.assertEqual(self.stored().negative_tests[0]['result'], 'NOT_DETECTED')

    def test_updating_from_a_file_with_the_key_replaces_them(self):
        data = serialize_playbook_graph(self.graph)
        data['playbook']['negative_tests'] = []
        update_playbook_graph_from_v1(data, self.graph, self.user)
        self.assertEqual(self.stored().negative_tests, [])
