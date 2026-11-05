import copy
import tempfile
from pathlib import Path

import yaml
from django.test import SimpleTestCase

from ai_assistant import maieutic_questions as mq
from ai_assistant.maieutic_questions import QuestionContentError, validate_question

UPSTREAM_ADE_IDS = (
    'ADE1-01', 'ADE1-02',
    'ADE2-01', 'ADE2-02', 'ADE2-03', 'ADE2-04',
    'ADE3-01', 'ADE3-02', 'ADE3-03', 'ADE3-04', 'ADE3-05', 'ADE3-06',
    'ADE4-01', 'ADE4-02', 'ADE4-03', 'ADE4-04',
)
SHIPPED = UPSTREAM_ADE_IDS


def good():
    return copy.deepcopy(mq.load_questions()['ADE2-01'])


class ShippedQuestionTests(SimpleTestCase):
    def test_every_upstream_subcategory_has_exactly_one_question(self):
        self.assertEqual(sorted(mq.load_questions()), sorted(UPSTREAM_ADE_IDS))

    def test_every_design_flag_is_used_and_no_question_is_unreachable(self):
        used = set()
        for q in mq.load_questions().values():
            if q['applies_when']['type'] == 'design_flags_any':
                used |= set(q['applies_when']['flags'])
        self.assertEqual(used, set(mq.DESIGN_FLAGS))

    def test_every_checklist_ends_in_a_decision(self):
        for q in mq.load_questions().values():
            self.assertIn('decision', q['checklist'][-1].lower(), q['ade_id'])

    def test_each_question_stays_off_the_terms_users_do_not_know_yet(self):
        # Raw upstream ids belong in metadata, not in user-facing wording.
        for q in mq.load_questions().values():
            for field, text in mq._texts(q):
                self.assertNotRegex(str(text), r'ADE\d-\d\d', f"{q['ade_id']} {field}")

    def test_no_user_facing_text_treats_a_rule_as_the_starting_point(self):
        for q in mq.load_questions().values():
            for field, text in mq._texts(q):
                self.assertNotRegex(str(text), mq.FORBIDDEN_PHRASES, f"{q['ade_id']} {field}")

    def test_all_questions_are_open_ended_and_have_three_hint_rungs(self):
        for q in mq.load_questions().values():
            self.assertTrue(q['question'].strip().endswith('?'))
            self.assertEqual(list(q['hints']), list(mq.HINT_KEYS))

    def test_ade_ids_exist_in_the_upstream_taxonomy_numbering(self):
        # Four categories, so first digit 1..4; guards against typos in a new file.
        for ade_id in mq.load_questions():
            self.assertRegex(ade_id, r'^ADE[1-4]-\d{2}$')

    def test_rendering_uses_user_wording_or_a_plain_fallback(self):
        q = mq.load_questions()['ADE2-01']
        self.assertIn('rundll32', mq.render_text(q['question'], q, {'design_observable': 'rundll32'}))
        fallback = mq.render_text(q['question'], q, {})
        self.assertIn(q['placeholders']['design_observable'], fallback)
        self.assertNotIn('{', fallback)


class SelectionTests(SimpleTestCase):
    def ids(self, flags, **kw):
        return [(q['ade_id'], reason) for q, reason in mq.questions_for_design(flags, **kw)]

    def test_selection_is_deterministic_and_ordered(self):
        a = self.ids({'matches_process_name', 'names_specific_tool'})
        self.assertEqual(a, self.ids({'names_specific_tool', 'matches_process_name'}))
        self.assertEqual([i for i, _ in a], sorted(i for i, _ in a))

    def test_flags_trigger_only_their_questions(self):
        always = ('ADE4-04', 'always')
        self.assertEqual(self.ids({'multi_condition_single_event'}),
                         [('ADE3-04', 'design:multi_condition_single_event'), always])
        self.assertEqual(self.ids({'matches_process_name'}), [('ADE3-01', 'design:matches_process_name'), always])
        self.assertEqual(self.ids({'plans_exclusions'}), [('ADE4-01', 'design:plans_exclusions'), always])
        # ADE4-04 (field availability) applies to every design, so an empty design still gets it.
        self.assertEqual(self.ids(set()), [('ADE4-04', 'always')])

    def test_expert_mode_asks_everything_once_with_a_distinct_reason(self):
        asked = self.ids(set(), expert_all=True)
        self.assertEqual([i for i, _ in asked], sorted(SHIPPED))
        reasons = {i: r for i, r in asked}
        self.assertEqual(reasons.pop('ADE4-04'), 'always')
        self.assertTrue(all(r == 'expert_all' for r in reasons.values()))
        mixed = dict(self.ids({'matches_process_name'}, expert_all=True))
        self.assertEqual(mixed['ADE3-01'], 'design:matches_process_name')


class ValidatorRejectsBadContentTests(SimpleTestCase):
    def assertRejected(self, mutate, fragment):
        q = good()
        mutate(q)
        with self.assertRaisesMessage(QuestionContentError, fragment):
            validate_question(q)

    def test_yes_no_question_rejected(self):
        self.assertRejected(lambda q: q.update(question='Could an attacker use another tool?'), 'open-ended')
        self.assertRejected(lambda q: q.update(question='Do you cover other tools?'), 'open-ended')

    def test_rule_as_starting_point_rejected(self):
        self.assertRejected(lambda q: q.update(question='What does your rule miss?'), 'the/your rule')
        self.assertRejected(lambda q: q['hints'].update(where_to_look='Check the rule logic.'), 'the/your rule')

    def test_missing_or_extra_hint_rung_rejected(self):
        self.assertRejected(lambda q: q['hints'].pop('worked_example'), 'hints must have exactly')
        self.assertRejected(lambda q: q['hints'].update(extra='x'), 'hints must have exactly')

    def test_worked_example_needs_a_technique(self):
        self.assertRejected(lambda q: q['hints']['worked_example'].pop('technique'), 'technique')

    def test_undeclared_placeholder_rejected(self):
        self.assertRejected(lambda q: q.update(why_we_ask='Because {surprise}.'), 'not declared')

    def test_unknown_design_flag_rejected(self):
        self.assertRejected(lambda q: q['applies_when'].update(flags=['made_up']), 'unknown design flags')

    def test_id_must_match_ade_id(self):
        self.assertRejected(lambda q: q.update(id='ade-q-ade2-02'), 'id must match')

    def test_checklist_needs_two_items(self):
        self.assertRejected(lambda q: q.update(checklist=['one']), 'checklist')


class LoaderTests(SimpleTestCase):
    def test_duplicate_ade_id_in_two_files_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('a.yaml', 'b.yaml'):
                Path(tmp, name).write_text(yaml.safe_dump(good()), encoding='utf-8')
            with self.assertRaisesMessage(QuestionContentError, 'duplicate'):
                mq.load_questions.__wrapped__(tmp)
