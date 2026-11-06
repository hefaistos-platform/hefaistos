import uuid
from datetime import datetime, timezone

from django.test import SimpleTestCase

from playbooks import negative_tests as nt

RULE = 'DeviceProcessEvents | where FileName =~ "rundll32.exe"'
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def item(**over):
    base = nt.new_item('ADE4-01', 'Can the export be called by ordinal?', 'Yes, accepted.')
    base.update(over)
    return base


class NewItemTests(SimpleTestCase):
    def test_without_written_steps_a_template_is_used_and_marked(self):
        i = nt.new_item('ADE4-01', 'Q?', 'My answer')
        self.assertEqual(i['steps_source'], nt.STEPS_TEMPLATE)
        self.assertIn('Q?', i['steps'])
        self.assertIn('My answer', i['steps'])
        self.assertEqual((i['result'], i['expected'], i['tested_at']), (nt.NOT_RUN, nt.EXPECTED, None))

    def test_template_never_claims_a_result_or_invents_a_technique(self):
        text = nt.template_steps('Q?', 'A')
        self.assertNotIn('rundll32', text)
        self.assertNotIn('MiniDump', text)

    def test_written_steps_are_kept_and_marked_as_the_users(self):
        i = nt.new_item('x', 'Q', 'A', steps='1. run it\n2. look')
        self.assertEqual((i['steps'], i['steps_source']), ('1. run it\n2. look', nt.STEPS_USER))

    def test_ids_are_unique_valid_uuids(self):
        a, b = nt.new_item('x', 'Q', 'A'), nt.new_item('x', 'Q', 'A')
        self.assertNotEqual(a['id'], b['id'])
        uuid.UUID(a['id'])


class NormalizeTests(SimpleTestCase):
    def test_garbage_input_gives_an_empty_list(self):
        for raw in (None, 'x', 5, {'a': 1}, [None, 3, 'x', []]):
            self.assertEqual(nt.normalize(raw), [], raw)

    def test_invalid_result_resets_and_drops_result_metadata(self):
        out = nt.normalize([item(result='PASSED', tested_at='2026-01-01', rule_fingerprint='abc')])[0]
        self.assertEqual((out['result'], out['tested_at'], out['rule_fingerprint']), (nt.NOT_RUN, None, ''))

    def test_not_run_never_keeps_a_timestamp(self):
        out = nt.normalize([item(result=nt.NOT_RUN, tested_at='2026-01-01', rule_fingerprint='abc')])[0]
        self.assertEqual((out['tested_at'], out['rule_fingerprint']), (None, ''))

    def test_unknown_keys_dropped_and_expected_is_fixed(self):
        out = nt.normalize([{**item(), 'evil': '<script>', 'expected': 'Alert is raised'}])[0]
        self.assertNotIn('evil', out)
        self.assertEqual(out['expected'], nt.EXPECTED)

    def test_duplicate_and_missing_ids_are_repaired(self):
        i = item()
        out = nt.normalize([i, dict(i), {**i, 'id': 'nope'}])
        self.assertEqual(len(out), 2)
        self.assertEqual(len({o['id'] for o in out}), 2)

    def test_lengths_are_capped_and_line_breaks_kept_in_steps(self):
        out = nt.normalize([item(steps='a\r\nb' + 'x' * 9000, notes='n' * 9000)])[0]
        self.assertLessEqual(len(out['steps']), nt.LIMITS['steps'])
        self.assertLessEqual(len(out['notes']), nt.LIMITS['notes'])
        self.assertTrue(out['steps'].startswith('a\nb'))

    def test_list_is_capped(self):
        many = [{**item(), 'id': str(uuid.uuid4())} for _ in range(nt.MAX_TESTS + 20)]
        self.assertEqual(len(nt.normalize(many)), nt.MAX_TESTS)


class FingerprintTests(SimpleTestCase):
    def test_whitespace_changes_do_not_change_it_but_logic_does(self):
        self.assertEqual(nt.fingerprint(RULE), nt.fingerprint('  ' + RULE.replace(' | ', '\n|   ') + '\n'))
        self.assertNotEqual(nt.fingerprint(RULE), nt.fingerprint(RULE.replace('rundll32', 'regsvr32')))

    def test_empty_rule_has_no_fingerprint(self):
        self.assertEqual((nt.fingerprint(''), nt.fingerprint(None)), ('', ''))


class ApplyUpdateTests(SimpleTestCase):
    def setUp(self):
        self.items = [item()]
        self.tid = self.items[0]['id']

    def update(self, **kw):
        return nt.apply_update(self.items, self.tid, rule_text=RULE, now=NOW, **kw)[0]

    def test_recording_a_result_stamps_time_and_rule_fingerprint(self):
        out = self.update(result=nt.NOT_DETECTED)
        self.assertEqual(out['result'], nt.NOT_DETECTED)
        self.assertEqual(out['tested_at'], NOW.isoformat())
        self.assertEqual(out['rule_fingerprint'], nt.fingerprint(RULE))

    def test_resetting_to_not_run_clears_the_record(self):
        self.items = nt.apply_update(self.items, self.tid, rule_text=RULE, result=nt.DETECTED, now=NOW)
        out = self.update(result=nt.NOT_RUN)
        self.assertEqual((out['result'], out['tested_at'], out['rule_fingerprint']), (nt.NOT_RUN, None, ''))

    def test_editing_steps_clears_a_recorded_result(self):
        self.items = nt.apply_update(self.items, self.tid, rule_text=RULE, result=nt.NOT_DETECTED, now=NOW)
        out = self.update(steps='new procedure')
        self.assertEqual((out['steps'], out['steps_source'], out['result']), ('new procedure', nt.STEPS_USER, nt.NOT_RUN))

    def test_unchanged_steps_keep_the_result(self):
        self.items = nt.apply_update(self.items, self.tid, rule_text=RULE, result=nt.NOT_DETECTED, now=NOW)
        out = self.update(steps=self.items[0]['steps'])
        self.assertEqual(out['result'], nt.NOT_DETECTED)

    def test_steps_and_result_in_one_call_keep_the_new_result(self):
        out = self.update(steps='new procedure', result=nt.DETECTED)
        self.assertEqual((out['steps'], out['result']), ('new procedure', nt.DETECTED))

    def test_notes_do_not_touch_the_result(self):
        self.items = nt.apply_update(self.items, self.tid, rule_text=RULE, result=nt.DETECTED, now=NOW)
        out = self.update(notes='saw alert 42')
        self.assertEqual((out['notes'], out['result']), ('saw alert 42', nt.DETECTED))

    def test_invalid_input_raises_and_changes_nothing(self):
        for kw in ({'result': 'PASSED'}, {'steps': '   '}):
            with self.assertRaises(ValueError, msg=kw):
                self.update(**kw)
        with self.assertRaises(ValueError):
            nt.apply_update(self.items, str(uuid.uuid4()), rule_text=RULE, result=nt.DETECTED)

    def test_other_tests_are_untouched(self):
        other = {**item(), 'id': str(uuid.uuid4())}
        out = nt.apply_update([self.items[0], other], self.tid, rule_text=RULE, result=nt.DETECTED, now=NOW)
        self.assertEqual(out[1]['result'], nt.NOT_RUN)


class PresentTests(SimpleTestCase):
    def test_result_is_stale_only_after_the_rule_changed(self):
        base = item()
        recorded = nt.apply_update([base], base['id'], rule_text=RULE, result=nt.NOT_DETECTED, now=NOW)
        self.assertFalse(nt.present(recorded, RULE)[0]['stale'])
        self.assertFalse(nt.present(recorded, RULE + '  ')[0]['stale'])
        self.assertTrue(nt.present(recorded, RULE.replace('rundll32', 'regsvr32'))[0]['stale'])
        self.assertTrue(nt.present(recorded, '')[0]['stale'])

    def test_not_run_is_never_stale(self):
        self.assertFalse(nt.present([item()], 'anything')[0]['stale'])


class SummaryTests(SimpleTestCase):
    def test_counts(self):
        rows = [{'result': nt.NOT_RUN}, {'result': nt.DETECTED, 'stale': True}, {'result': nt.NOT_DETECTED}]
        self.assertEqual(nt.summary(rows), {nt.NOT_RUN: 1, nt.NOT_DETECTED: 1, nt.DETECTED: 1, 'stale': 1})
