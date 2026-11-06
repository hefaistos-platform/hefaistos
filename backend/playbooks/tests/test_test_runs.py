import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase

from core.schema import schema
from organizations.models import Organization
from playbooks import test_runs as tr
from playbooks.models import ActivityLog, PlaybookGraph
from playbooks.schema import (
    deserialize_playbook_graph, deserialize_playbook_graph_hex_v2, serialize_playbook_graph,
    serialize_playbook_graph_hex_v2, update_playbook_graph_from_hex_v2, update_playbook_graph_from_v1,
)

RULE = 'DeviceProcessEvents | where FileName =~ "rundll32.exe"'
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def add(runs=None, **over):
    args = dict(executed=True, fired=True, notes='lab-win-01', rule_text=RULE, user_name='red', now=NOW)
    args.update(over)
    return tr.add_run(runs or [], **args)


class AddRunTests(SimpleTestCase):
    def test_a_run_records_who_when_what_and_for_which_rule(self):
        run = add()[0]
        self.assertEqual((run['executed'], run['fired'], run['notes'], run['recorded_by']), (True, True, 'lab-win-01', 'red'))
        self.assertEqual(run['recorded_at'], NOW.isoformat())
        self.assertEqual(len(run['rule_fingerprint']), 16)
        uuid.UUID(run['id'])

    def test_executed_and_silent_is_a_valid_finding(self):
        run = add(fired=False)[0]
        self.assertEqual((run['executed'], run['fired']), (True, False))

    def test_a_run_that_did_not_happen_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'Test executed'):
            add(executed=False, fired=False)
        with self.assertRaisesRegex(ValueError, 'Test executed'):
            add(executed=False, fired=True)

    def test_non_boolean_flags_are_refused(self):
        for bad in ({'executed': 'yes'}, {'fired': 1}, {'fired': None}, {'executed': None}):
            with self.assertRaises(ValueError, msg=bad):
                add(**bad)

    def test_records_are_only_added_and_the_oldest_drops_past_the_cap(self):
        runs = []
        for i in range(tr.MAX_RUNS + 5):
            runs = add(runs, notes=f'run {i}')
        self.assertEqual(len(runs), tr.MAX_RUNS)
        self.assertEqual((runs[0]['notes'], runs[-1]['notes']), ('run 5', f'run {tr.MAX_RUNS + 4}'))

    def test_existing_records_are_not_modified_by_a_new_one(self):
        first = add(notes='first')
        second = add(first, notes='second')
        self.assertEqual(second[0], first[0])

    def test_text_is_capped_and_blank_notes_are_allowed(self):
        self.assertEqual(len(add(notes='x' * 5000)[0]['notes']), tr.LIMITS['notes'])
        self.assertEqual(add(notes=None)[0]['notes'], '')
        self.assertEqual(add(user_name='a\n  b')[0]['recorded_by'], 'a b')


class NormalizeTests(SimpleTestCase):
    def test_garbage_gives_an_empty_list(self):
        for raw in (None, 'x', 5, {}, [None, 'x', 3]):
            self.assertEqual(tr.normalize(raw), [], raw)

    def test_fired_without_executed_is_reset_and_unknown_keys_dropped(self):
        run = tr.normalize([{'id': 'junk', 'executed': False, 'fired': True, 'evil': '<b>', 'recorded_by': 'x'}])[0]
        self.assertEqual((run['executed'], run['fired']), (False, False))
        self.assertNotIn('evil', run)
        uuid.UUID(run['id'])

    def test_only_real_booleans_count(self):
        run = tr.normalize([{'executed': 'true', 'fired': 'true'}])[0]
        self.assertEqual((run['executed'], run['fired']), (False, False))

    def test_duplicate_ids_are_dropped_and_the_list_is_capped(self):
        same = str(uuid.uuid4())
        self.assertEqual(len(tr.normalize([{'id': same, 'executed': True}, {'id': same, 'executed': True}])), 1)
        many = [{'id': str(uuid.uuid4()), 'executed': True} for _ in range(tr.MAX_RUNS + 9)]
        kept = tr.normalize(many)
        self.assertEqual((len(kept), kept[-1]['id']), (tr.MAX_RUNS, many[-1]['id']))

    def test_fingerprint_must_look_like_one(self):
        self.assertEqual(tr.normalize([{'rule_fingerprint': '<script>'}])[0]['rule_fingerprint'], '')


class PresentTests(SimpleTestCase):
    def test_newest_first_and_stale_only_after_the_rule_changed(self):
        runs = add(add(notes='old'), notes='new', now=NOW + timedelta(hours=1))
        shown = tr.present(runs, RULE)
        self.assertEqual([r['notes'] for r in shown], ['new', 'old'])
        self.assertEqual([r['stale'] for r in shown], [False, False])
        self.assertEqual([r['stale'] for r in tr.present(runs, RULE.replace('rundll32', 'regsvr32'))], [True, True])
        self.assertEqual([r['stale'] for r in tr.present(runs, RULE + '   ')], [False, False])    # whitespace is not a change

    def test_summary(self):
        self.assertIsNone(tr.summary([]))
        self.assertEqual(tr.summary(tr.present(add(fired=False), RULE + ' x')), {'runs': 1, 'latest_fired': False, 'latest_stale': True})

    def test_export_drops_the_username_but_keeps_the_outcome(self):
        out = tr.for_export(add())
        self.assertEqual((out[0]['recorded_by'], out[0]['fired'], out[0]['notes']), ('', True, 'lab-win-01'))


RECORD = '''mutation($g:UUID!,$e:Boolean!,$f:Boolean!,$n:String){
  recordTestRun(graphId:$g,executed:$e,fired:$f,notes:$n){testRuns}}'''
READ = 'query($id:UUID!){playbookGraph(id:$id){testRuns}}'


class ApiBase(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.other_org = Organization.objects.create(name='Other')
        self.user = U.objects.create_user(username='tr_admin', organization=self.org, role='ADMIN')
        self.analyst = U.objects.create_user(username='tr_analyst', organization=self.org, role='ANALYST')
        self.auditor = U.objects.create_user(username='tr_auditor', organization=self.org, role='BOT_AUDITOR_ORG')
        self.outsider = U.objects.create_user(username='tr_out', organization=self.other_org, role='ADMIN')
        self.graph = PlaybookGraph.objects.create(
            organization=self.org, author=self.user, title='wb', status='IDEA', detection_rule=RULE, test_validation_status='NOT_TESTED')
        patcher = patch('playbooks.l1_portal.upsert_l1_portal_snapshot')
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_gql(self, query, variables, user=None):
        return schema.execute(query, variable_values=variables, context_value=SimpleNamespace(user=user or self.user))

    def record(self, user=None, executed=True, fired=True, notes='ran it'):
        return self.run_gql(RECORD, {'g': str(self.graph.id), 'e': executed, 'f': fired, 'n': notes}, user)

    def stored(self):
        return PlaybookGraph.objects.get(pk=self.graph.pk)


class MutationTests(ApiBase):
    def test_recording_stores_who_and_returns_newest_first(self):
        self.assertIsNone(self.record(notes='first').errors)
        result = self.record(user=self.analyst, fired=False, notes='second')
        self.assertIsNone(result.errors)
        rows = result.data['recordTestRun']['testRuns']
        self.assertEqual([(r['notes'], r['recorded_by'], r['fired']) for r in rows], [('second', 'tr_analyst', False), ('first', 'tr_admin', True)])
        self.assertEqual(len(self.stored().test_runs), 2)

    def test_recording_does_not_touch_version_updated_at_or_the_pipeline_status(self):
        before = self.stored()
        time.sleep(0.01)
        self.assertIsNone(self.record().errors)
        after = self.stored()
        self.assertEqual((after.version, after.minor_version, after.updated_at, after.test_validation_status),
                         (before.version, before.minor_version, before.updated_at, 'NOT_TESTED'))
        self.assertEqual(after.last_tested_at, before.last_tested_at)

    def test_a_run_that_did_not_happen_is_rejected_and_nothing_is_stored(self):
        result = self.record(executed=False, fired=False)
        self.assertIn('Test executed', str(result.errors[0]))
        self.assertEqual(self.stored().test_runs, [])

    def test_a_record_goes_stale_when_the_rule_changes(self):
        self.record()
        read = lambda: self.run_gql(READ, {'id': str(self.graph.id)}).data['playbookGraph']['testRuns'][0]['stale']
        self.assertFalse(read())
        PlaybookGraph.objects.filter(pk=self.graph.pk).update(detection_rule=RULE.replace('rundll32', 'regsvr32'))
        self.assertTrue(read())

    def test_it_is_written_to_the_activity_log_without_the_notes(self):
        self.record(notes='SECRET-NOTE')
        entry = ActivityLog.objects.filter(playbook=self.graph, action='Test run recorded').get()
        self.assertIn('rule fired', entry.details)
        self.assertNotIn('SECRET-NOTE', entry.details)

    def test_analyst_may_record_but_auditor_anonymous_and_other_org_may_not(self):
        self.assertIsNone(self.record(user=self.analyst).errors)
        PlaybookGraph.objects.filter(pk=self.graph.pk).update(test_runs=[])
        for who in (self.auditor, AnonymousUser(), self.outsider):
            self.assertTrue(self.record(user=who).errors, who)
        self.assertEqual(self.stored().test_runs, [])

    def test_a_workbench_without_records_returns_an_empty_list(self):
        self.assertEqual(self.run_gql(READ, {'id': str(self.graph.id)}).data['playbookGraph']['testRuns'], [])


class ExportImportTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.record(notes='lab run')
        self.graph = self.stored()
        self.run_id = self.graph.test_runs[0]['id']

    def test_both_export_formats_carry_the_outcome_but_not_the_username(self):
        v1 = serialize_playbook_graph(self.graph)['playbook']['test_runs'][0]
        v2 = serialize_playbook_graph_hex_v2(self.graph)['testing']['test_runs'][0]
        for row in (v1, v2):
            self.assertEqual((row['notes'], row['fired'], row['recorded_by']), ('lab run', True, ''))
        self.assertEqual(self.stored().test_runs[0]['recorded_by'], 'tr_admin')       # export never edits the stored record

    def test_import_round_trips_both_formats(self):
        for dump, load in ((serialize_playbook_graph, deserialize_playbook_graph),
                           (serialize_playbook_graph_hex_v2, deserialize_playbook_graph_hex_v2)):
            copy = load(dump(self.graph), self.org, self.user)
            self.assertEqual((copy.test_runs[0]['id'], copy.test_runs[0]['fired']), (self.run_id, True))

    def test_import_sanitises_hostile_values(self):
        data = serialize_playbook_graph(self.graph)
        data['playbook']['test_runs'] = [{'id': 'x', 'executed': False, 'fired': True, 'evil': '<b>'}, 'junk', None]
        copy = deserialize_playbook_graph(data, self.org, self.user)
        self.assertEqual(len(copy.test_runs), 1)
        self.assertEqual((copy.test_runs[0]['executed'], copy.test_runs[0]['fired']), (False, False))
        self.assertNotIn('evil', copy.test_runs[0])

    def test_updating_from_an_older_file_keeps_recorded_runs(self):
        data = serialize_playbook_graph(self.graph)
        del data['playbook']['test_runs']
        update_playbook_graph_from_v1(data, self.graph, self.user)
        self.assertEqual(len(self.stored().test_runs), 1)
        data2 = serialize_playbook_graph_hex_v2(self.graph)
        del data2['testing']['test_runs']
        update_playbook_graph_from_hex_v2(data2, self.graph, self.user)
        self.assertEqual(len(self.stored().test_runs), 1)

    def test_updating_from_a_file_with_the_key_replaces_them(self):
        data = serialize_playbook_graph(self.graph)
        data['playbook']['test_runs'] = []
        update_playbook_graph_from_v1(data, self.graph, self.user)
        self.assertEqual(self.stored().test_runs, [])
