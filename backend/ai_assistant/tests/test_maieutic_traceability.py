import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from ai_assistant import engine
from ai_assistant import maieutic_traceability as tr
from ai_assistant import maieutic_workbench as mw
from ai_assistant.tests.test_maieutic_workbench import SPEC

CONSTRAINTS = {
    'must_implement': ['Match on: rundll32 loading comsvcs.dll', 'Exclude: signed vendor updater because noisy'],
    'must_handle': [{'topic': 'Other tools?', 'engineer_says': 'I also match procdump', 'applies_to': 'x'}],
    'accepted_limitations': [{'topic': 'Renamed binary?', 'engineer_says': 'Not covered', 'status': 'ACCEPTED_LIMITATION',
                              'covered_by': ''}],
}


def reply(*entries):
    return json.dumps(list(entries))


class DecisionRefTests(SimpleTestCase):
    def test_refs_are_numbered_per_group_in_prompt_order(self):
        refs = tr.decision_refs(CONSTRAINTS)
        self.assertEqual([r['ref'] for r in refs], ['M1', 'M2', 'H1', 'L1'])
        self.assertEqual([r['group'] for r in refs],
                         ['MUST_IMPLEMENT', 'MUST_IMPLEMENT', 'MUST_HANDLE', 'ACCEPTED_LIMITATION'])
        self.assertIn('procdump', refs[2]['text'])

    def test_no_constraints_means_no_decisions(self):
        self.assertFalse(tr.has_decisions(None))
        self.assertFalse(tr.has_decisions({'must_implement': [], 'must_handle': [], 'accepted_limitations': []}))

    def test_prompt_block_uses_the_same_references(self):
        text = engine._format_maieutic_constraints_for_prompt({'maieutic_constraints': CONSTRAINTS})
        for ref in ('[M1]', '[M2]', '[H1]', '[L1]'):
            self.assertIn(ref, text)


class BuildTests(SimpleTestCase):
    def full(self):
        return reply(
            {'decision_ref': 'M1', 'implemented': 'yes', 'where': 'line 3', 'note': 'matched'},
            {'decision_ref': 'M2', 'implemented': 'partial', 'where': 'let Approved', 'note': 'placeholder'},
            {'decision_ref': 'H1', 'implemented': 'no', 'where': '', 'note': 'only rundll32'},
            {'decision_ref': 'L1', 'implemented': 'no', 'where': '', 'note': 'not covered'},
        )

    def test_complete_report_is_kept_in_prompt_order(self):
        rows = tr.build(self.full(), CONSTRAINTS)
        self.assertEqual([r['ref'] for r in rows], ['M1', 'M2', 'H1', 'L1'])
        self.assertEqual([r['implemented'] for r in rows], ['yes', 'partial', 'no', 'no'])
        self.assertTrue(all(r['status'] == tr.STATUS_OK for r in rows))

    def test_markdown_fence_is_tolerated(self):
        rows = tr.build('```json\n' + self.full() + '\n```', CONSTRAINTS)
        self.assertEqual(rows[0]['implemented'], 'yes')

    def test_unusable_output_marks_every_decision_not_reported_instead_of_passing(self):
        for raw in ('', 'no idea', '{"decision_ref": "M1"}', '[1, 2]', None):
            rows = tr.build(raw, CONSTRAINTS)
            self.assertEqual(len(rows), 4, raw)
            self.assertTrue(all(r['status'] == tr.STATUS_MISSING and r['implemented'] is None for r in rows), raw)

    def test_skipped_decision_stays_visible(self):
        rows = tr.build(reply({'decision_ref': 'M1', 'implemented': 'yes'}), CONSTRAINTS)
        self.assertEqual([r['status'] for r in rows], [tr.STATUS_OK, tr.STATUS_MISSING, tr.STATUS_MISSING, tr.STATUS_MISSING])

    def test_invented_references_are_dropped(self):
        rows = tr.build(reply({'decision_ref': 'M9', 'implemented': 'yes'}, {'decision_ref': 'M1', 'implemented': 'yes'}),
                        CONSTRAINTS)
        self.assertEqual([r['ref'] for r in rows], ['M1', 'M2', 'H1', 'L1'])

    def test_invalid_implemented_value_is_not_trusted(self):
        rows = tr.build(reply({'decision_ref': 'M1', 'implemented': 'definitely'}), CONSTRAINTS)
        self.assertIsNone(rows[0]['implemented'])
        self.assertEqual(rows[0]['status'], tr.STATUS_MISSING)

    def test_claiming_to_cover_an_accepted_limitation_is_flagged(self):
        for claim in ('yes', 'partial', 'YES'):
            rows = tr.build(reply({'decision_ref': 'L1', 'implemented': claim}), CONSTRAINTS)
            self.assertEqual(rows[3]['status'], tr.STATUS_CONFLICT, claim)

    def test_text_is_clipped(self):
        rows = tr.build(reply({'decision_ref': 'M1', 'implemented': 'yes', 'note': 'x' * 2000}), CONSTRAINTS)
        self.assertLessEqual(len(rows[0]['note']), tr.MAX_TEXT)


class GeneratorWiringTests(TestCase):
    BASE = {'title': 'T', 'technique_id': 'T1', 'technique_name': 'N', 'goal': 'G', 'technical_context': 'C'}

    def run_generator(self, context, model_reply):
        seen = {}
        user_settings = SimpleNamespace(user=SimpleNamespace(username='u', organization_id=None))
        with patch.object(engine, 'build_available', return_value=['X']), \
                patch.object(engine, '_resolve_provider', return_value='GPT-5'), \
                patch.object(engine, '_invoke_detection_generation_model', return_value=model_reply), \
                patch('ai_assistant.prompt_registry.resolve_prompt',
                      return_value=SimpleNamespace(instructions='S', provenance=lambda: {})):
            bundle, _provider = engine.generate_rule_bundle(user_settings, context, 'KQL',
                                                            on_prompt_prepared=lambda p: seen.update(p))
        return bundle, seen

    def response(self, trace):
        return ('---GENERATION-SUMMARY-START---\ns\n---GENERATION-SUMMARY-END---\n'
                '---PRIMARY-RULE-START---\nrule body\n---PRIMARY-RULE-END---\n'
                f'---TRACEABILITY-START---\n{trace}\n---TRACEABILITY-END---')

    def test_ordinary_workbench_is_unchanged(self):
        bundle, seen = self.run_generator(self.BASE, self.response('[]'))
        self.assertNotIn('traceability', bundle)
        self.assertNotIn('TRACEABILITY', seen['system_prompt'])
        self.assertNotIn('TRACEABILITY', seen['user_prompt'])
        self.assertNotIn('output_contract_extensions', seen)
        self.assertEqual(seen['output_contract_version'], 'rule-bundle-v1')

    def test_maieutic_workbench_asks_for_and_parses_the_trace(self):
        context = {**self.BASE, 'maieutic_constraints': CONSTRAINTS}
        trace = reply({'decision_ref': 'M1', 'implemented': 'yes', 'where': 'where clause', 'note': 'ok'})
        bundle, seen = self.run_generator(context, self.response(trace))
        self.assertIn('---TRACEABILITY-START---', seen['system_prompt'])
        self.assertIn('Fill the TRACEABILITY section', seen['user_prompt'])
        self.assertEqual(seen['output_contract_extensions'], ['traceability'])
        self.assertEqual(seen['output_contract_version'], 'rule-bundle-v1')
        self.assertEqual(len(bundle['traceability']), 4)
        self.assertEqual(bundle['traceability'][0]['implemented'], 'yes')
        self.assertEqual(bundle['traceability'][1]['status'], tr.STATUS_MISSING)
        self.assertEqual(bundle['primary_rule'], 'rule body')

    def test_missing_section_in_the_reply_does_not_break_generation(self):
        context = {**self.BASE, 'maieutic_constraints': CONSTRAINTS}
        bundle, _ = self.run_generator(context, '---PRIMARY-RULE-START---\nr\n---PRIMARY-RULE-END---')
        self.assertEqual(bundle['primary_rule'], 'r')
        self.assertTrue(all(r['status'] == tr.STATUS_MISSING for r in bundle['traceability']))

    def test_real_session_constraints_are_traceable(self):
        self.assertTrue(tr.has_decisions(mw.build_constraints(SPEC)))
