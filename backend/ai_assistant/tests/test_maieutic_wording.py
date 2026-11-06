import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from ai_assistant import maieutic_lifecycle as lc
from ai_assistant import maieutic_wording as w
from ai_assistant import maieutic_workbench as mw
from ai_assistant.models import UserAISettings
from ai_assistant.prompt_registry import resolve_prompt
from core.schema import schema
from organizations.models import Organization
from platform_data.models import MitreAttackTechnique

GOAL = 'detect lsass dump via comsvcs minidump through rundll32 on servers'
GOOD = 'Detect an LSASS dump made through rundll32 with the comsvcs MiniDump call, on servers.'
SPEC = {
    'hypothesis': {'title': 'LSASS dump', 'goal': GOAL, 'technique': {'state': 'SET', 'id': 'T1003.001', 'name': 'LSASS Memory'},
                   'scope_notes': 'Windows servers only, the backup agent is expected'},
    'design': {'blueprint_text': 'Look for rundll32 loading comsvcs.dll',
               'match_elements': [{'id': 'm1', 'description': 'rundll32 loading comsvcs.dll'}]},
    'playbook_tests': {'test_scenario': 'Run rundll32 comsvcs.dll MiniDump against the lsass process on a test host'},
}


def ai_returning(wording):
    return lambda system, user: json.dumps({'wording': wording})


class SanitizeTests(SimpleTestCase):
    def clean(self, suggestion, original=GOAL, spec=SPEC):
        return w.sanitize_suggestion(suggestion, original, spec)

    def test_a_pure_rewording_passes(self):
        self.assertEqual(self.clean(GOOD), (GOOD, None))

    def test_surrounding_quotes_are_stripped(self):
        self.assertEqual(self.clean(f'"{GOOD}"'), (GOOD, None))

    def test_a_new_content_word_is_rejected_because_the_ai_would_be_adding_something(self):
        self.assertEqual(self.clean('Detect credential dumping from LSASS memory on servers via rundll32.'), (None, 'UNUSABLE'))

    def test_a_new_number_or_id_is_rejected_even_though_it_is_short(self):
        for bad in ('Detect LSASS dump through rundll32 with comsvcs MiniDump on server 10.0.0.5.',
                    'Detect LSASS dump through rundll32 with comsvcs MiniDump, see T1003.',
                    'Detect LSASS dump through rundll32 with comsvcs MiniDump on port 445.'):
            self.assertEqual(self.clean(bad), (None, 'UNUSABLE'), bad)

    def test_numbers_the_user_wrote_are_allowed(self):
        original = 'detect lsass dump on port 445 via comsvcs minidump through rundll32'
        self.assertEqual(self.clean('Detect an LSASS dump through rundll32 and comsvcs MiniDump on port 445.', original), ('Detect an LSASS dump through rundll32 and comsvcs MiniDump on port 445.', None))

    def test_words_from_elsewhere_in_the_users_own_session_are_allowed(self):
        out, reason = self.clean('Detect a Memory dump through rundll32 and comsvcs minidump on servers, Windows servers only.')
        self.assertIsNone(reason, out)

    def test_unchanged_text_is_not_offered_back(self):
        self.assertEqual(self.clean(GOAL.upper()), (None, 'SAME'))
        self.assertEqual(self.clean('  ' + GOAL + '  '), (None, 'SAME'))

    def test_much_longer_text_is_rejected(self):
        self.assertEqual(self.clean(GOOD + ' ' + GOOD + ' ' + GOOD), (None, 'UNUSABLE'))

    def test_fences_and_new_lines_are_rejected_for_a_single_line_original(self):
        self.assertEqual(self.clean('```\n' + GOOD + '\n```'), (None, 'UNUSABLE'))
        self.assertEqual(self.clean(GOOD.replace(', on', ',\non')), (None, 'UNUSABLE'))

    def test_non_text_is_rejected(self):
        for bad in (None, 5, ['x'], {'a': 1}, '', '   '):
            self.assertEqual(self.clean(bad), (None, 'UNUSABLE'), bad)

    def test_non_english_words_are_checked_too(self):
        original = 'chci zachytit vypis pameti lsass pres comsvcs minidump a rundll32'
        spec = {'hypothesis': {'goal': original}}
        self.assertEqual(w.sanitize_suggestion('Zachytit výpis paměti lsass přes comsvcs minidump a rundll32.', original, spec),
                         (None, 'UNUSABLE'))   # inflected or accented forms are not in the user's text: rejected, on purpose
        self.assertEqual(w.sanitize_suggestion('Zachytit vypis pameti lsass pres comsvcs minidump a rundll32 pomocí přihlašovacích údajů.', original, spec),
                         (None, 'UNUSABLE'))

    def test_added_words_of_five_letters_or_more_are_caught_but_shorter_ones_are_a_known_gap(self):
        self.assertEqual(self.clean('Detect an LSASS dump through rundll32 with comsvcs MiniDump on servers, as admin.'), (None, 'UNUSABLE'))
        # Known limit, accepted: a 4-letter word cannot be told from a function word without a language model.
        self.assertIsNone(self.clean('Detect an LSASS dump through rundll32 with comsvcs MiniDump on servers, as root.')[1])

    def test_tampered_session_data_does_not_break_the_check(self):
        broken = {'hypothesis': {'goal': GOAL, 'attacker_methods': 7, 'technique': 'x'}, 'design': {'match_elements': 'oops', 'exclusions': 3},
                  'playbook_tests': 'no'}
        self.assertEqual(w.sanitize_suggestion(GOOD, GOAL, broken)[1], None)


class RefreshOriginTests(SimpleTestCase):
    def spec(self, text, **record):
        return {'hypothesis': {'goal': text}, 'meta': {'text_origin': {'hypothesis.goal': {'accepted_text': GOOD, 'origin': 'x', **record}}}}

    def test_origin_follows_the_current_text(self):
        self.assertEqual(w.refresh_origins(self.spec(GOOD))['hypothesis.goal']['origin'], 'AI_REWORDED')
        self.assertEqual(w.refresh_origins(self.spec(GOOD + ' More.'))['hypothesis.goal']['origin'], 'AI_REWORDED_EDITED')
        self.assertEqual(w.refresh_origins(self.spec('  ' + GOOD.replace(' ', '  ') + ' '))['hypothesis.goal']['origin'], 'AI_REWORDED')

    def test_an_emptied_field_loses_its_record(self):
        self.assertEqual(w.refresh_origins(self.spec('   ')), {})

    def test_unknown_fields_and_malformed_records_are_dropped(self):
        spec = {'hypothesis': {'goal': GOOD}, 'meta': {'text_origin': {'robustness.ade_ledger': {'accepted_text': 'x'}, 'hypothesis.goal': 'junk'}}}
        self.assertEqual(w.refresh_origins(spec), {})
        self.assertEqual(w.refresh_origins({}), {})


class RewordTests(TestCase):
    def test_without_ai_nothing_is_called(self):
        self.assertEqual(w.reword(SPEC, 'hypothesis.goal'), {'suggestion': None, 'reason': 'NO_AI', 'called': False})

    def test_provider_failure_is_not_counted(self):
        def boom(s, u):
            raise RuntimeError('down')
        self.assertEqual(w.reword(SPEC, 'hypothesis.goal', ai_call=boom), {'suggestion': None, 'reason': 'PROVIDER_ERROR', 'called': False})

    def test_a_good_answer_is_returned_and_counted(self):
        self.assertEqual(w.reword(SPEC, 'hypothesis.goal', ai_call=ai_returning(GOOD)), {'suggestion': GOOD, 'reason': None, 'called': True})

    def test_json_wrapped_in_chatter_still_works(self):
        out = w.reword(SPEC, 'hypothesis.goal', ai_call=lambda s, u: 'Sure! ' + json.dumps({'wording': GOOD}) + ' Hope it helps.')
        self.assertEqual(out['suggestion'], GOOD)

    def test_garbage_and_added_content_give_no_suggestion_but_are_counted(self):
        for raw in ('not json', '{"wording": 5}', '{}', json.dumps({'wording': 'Detect credential dumping from LSASS memory.'}), ''):
            out = w.reword(SPEC, 'hypothesis.goal', ai_call=lambda s, u, raw=raw: raw)
            self.assertIsNone(out['suggestion'], raw)
            self.assertTrue(out['called'], raw)

    def test_the_users_text_is_sent_as_data_and_the_default_prompt_forbids_additions(self):
        seen = {}
        w.reword(SPEC, 'hypothesis.goal', ai_call=lambda s, u: seen.update(system=s, user=u) or ai_returning(GOOD)(s, u))
        self.assertIn('<<<\n' + GOAL + '\n>>>', seen['user'])
        self.assertIn('Never add a fact', seen['system'])
        self.assertEqual(resolve_prompt(w.PROMPT_KEY, organization_id=None).instructions, seen['system'])


class WordingFlowTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.author = U.objects.create_user(username='author', organization=self.org, role='ANALYST')
        self.other = U.objects.create_user(username='other', organization=self.org, role='ANALYST')
        MitreAttackTechnique.objects.create(technique_id='T1003.001', name='LSASS Memory')
        d = lc.create_draft(self.author, name='s')
        self.draft = lc.update_draft(d.id, self.author, spec_patch={k: v for k, v in SPEC.items()})

    def spec(self):
        self.draft.refresh_from_db()
        return self.draft.spec

    def suggest(self, field='hypothesis.goal', wording=GOOD):
        spec, text = lc.prepare_wording(self.draft.id, self.author, field)
        result = w.reword(spec, field, ai_call=ai_returning(wording))
        return text, lc.store_wording(self.draft.id, self.author, field, text, result)

    def test_only_the_four_free_text_fields_are_available(self):
        for field in ('robustness.ade_ledger', 'hypothesis.title', 'design.match_elements', 'playbook_tests.negative_tests',
                      'review.output_formats', 'hypothesis', 'meta.text_origin', ''):
            with self.assertRaisesMessage(lc.MaieuticError, 'not available'):
                lc.prepare_wording(self.draft.id, self.author, field)
            with self.assertRaisesMessage(lc.MaieuticError, 'not available'):
                lc.accept_wording(self.draft.id, self.author, field)

    def test_short_text_gets_no_help(self):
        lc.update_draft(self.draft.id, self.author, spec_patch={'hypothesis': {**SPEC['hypothesis'], 'goal': 'too short'}})
        with self.assertRaisesMessage(lc.MaieuticError, 'at least 25'):
            lc.prepare_wording(self.draft.id, self.author, 'hypothesis.goal')

    def test_only_the_author_can_ask_and_never_after_finish(self):
        with self.assertRaisesMessage(lc.MaieuticError, 'not found'):
            lc.prepare_wording(self.draft.id, self.other, 'hypothesis.goal')
        from playbooks.models import PlaybookGraph
        wb = PlaybookGraph.objects.create(organization=self.org, title='wb', author=self.author)
        self.suggest()
        lc.finish_draft(self.draft.id, self.author, workbench=wb, outcome='WORKBENCH_WITHOUT_RULE')
        for call in (lambda: lc.prepare_wording(self.draft.id, self.author, 'hypothesis.goal'),
                     lambda: lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal'),
                     lambda: lc.restore_wording(self.draft.id, self.author, 'hypothesis.goal')):
            with self.assertRaisesMessage(lc.MaieuticError, 'locked'):
                call()

    def test_five_suggestions_per_field_then_no_more_but_other_fields_still_work(self):
        for i in range(5):
            _, out = self.suggest()
            self.assertEqual(out['remaining'], 4 - i)
        with self.assertRaisesMessage(lc.MaieuticError, 'used all'):
            lc.prepare_wording(self.draft.id, self.author, 'hypothesis.goal')
        lc.prepare_wording(self.draft.id, self.author, 'hypothesis.scope_notes')

    def test_only_calls_that_reached_the_provider_are_counted(self):
        text = lc.prepare_wording(self.draft.id, self.author, 'hypothesis.goal')[1]
        out = lc.store_wording(self.draft.id, self.author, 'hypothesis.goal', text, {'suggestion': None, 'reason': 'PROVIDER_ERROR', 'called': False})
        self.assertEqual(out, {'stored': False, 'remaining': 5, 'text_changed': False})

    def test_a_suggestion_is_pending_until_accepted_and_changes_nothing(self):
        before = self.spec()['hypothesis']['goal']
        _, out = self.suggest()
        self.assertTrue(out['stored'])
        self.assertEqual(self.spec()['hypothesis']['goal'], before)
        self.assertNotIn('text_origin', self.spec()['meta'])

    def test_text_typed_while_the_ai_worked_makes_the_suggestion_obsolete(self):
        spec, text = lc.prepare_wording(self.draft.id, self.author, 'hypothesis.goal')
        result = w.reword(spec, 'hypothesis.goal', ai_call=ai_returning(GOOD))
        lc.update_draft(self.draft.id, self.author, spec_patch={'hypothesis': {**SPEC['hypothesis'], 'goal': GOAL + ' and workstations'}})
        out = lc.store_wording(self.draft.id, self.author, 'hypothesis.goal', text, result)
        self.assertEqual((out['stored'], out['text_changed'], out['remaining']), (False, True, 4))
        with self.assertRaisesMessage(lc.MaieuticError, 'no suggestion'):
            lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')

    def test_accepting_writes_the_wording_and_the_server_records_the_origin(self):
        self.suggest()
        value, origins = lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        self.assertEqual(value, GOOD)
        spec = self.spec()
        self.assertEqual(spec['hypothesis']['goal'], GOOD)
        self.assertEqual(spec['hypothesis']['title'], 'LSASS dump')           # the rest of the section is untouched
        record = spec['meta']['text_origin']['hypothesis.goal']
        self.assertEqual((record['origin'], record['original_text'], record['accepted_text']), ('AI_REWORDED', GOAL, GOOD))
        self.assertEqual(origins, spec['meta']['text_origin'])
        self.assertNotIn('hypothesis.goal', spec['meta']['wording']['pending'])
        with self.assertRaisesMessage(lc.MaieuticError, 'no suggestion'):
            lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')   # single use

    def test_text_edited_between_the_suggestion_and_accepting_is_never_overwritten(self):
        self.suggest()
        lc.update_draft(self.draft.id, self.author, spec_patch={'hypothesis': {**SPEC['hypothesis'], 'goal': GOAL + ' plus mine'}})
        with self.assertRaisesMessage(lc.MaieuticError, 'changed'):
            lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        self.assertEqual(self.spec()['hypothesis']['goal'], GOAL + ' plus mine')
        self.assertNotIn('text_origin', self.spec()['meta'])

    def test_origin_becomes_edited_when_the_user_changes_it_and_goes_when_they_clear_it(self):
        self.suggest()
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        patch_goal = lambda text: lc.update_draft(self.draft.id, self.author, spec_patch={'hypothesis': {**self.spec()['hypothesis'], 'goal': text}})
        patch_goal(GOOD)                                                      # an autosave of the same text
        self.assertEqual(self.spec()['meta']['text_origin']['hypothesis.goal']['origin'], 'AI_REWORDED')
        patch_goal(GOOD + ' Also workstations.')
        self.assertEqual(self.spec()['meta']['text_origin']['hypothesis.goal']['origin'], 'AI_REWORDED_EDITED')
        patch_goal('')
        self.assertNotIn('text_origin', self.spec()['meta'])

    def test_the_client_cannot_write_or_forge_origin(self):
        with self.assertRaisesMessage(lc.MaieuticError, 'meta is managed'):
            lc.update_draft(self.draft.id, self.author, spec_patch={'meta': {'text_origin': {'hypothesis.goal': {'origin': 'AI_REWORDED', 'accepted_text': GOAL}}}})
        forged = {**SPEC['hypothesis'], 'text_origin': {'hypothesis.goal': {'origin': 'AI_REWORDED'}}}
        lc.update_draft(self.draft.id, self.author, spec_patch={'hypothesis': forged})
        self.assertNotIn('text_origin', self.spec()['meta'])

    def test_putting_my_text_back_restores_exactly_what_the_user_wrote(self):
        self.suggest()
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        value, origins = lc.restore_wording(self.draft.id, self.author, 'hypothesis.goal')
        self.assertEqual((value, origins), (GOAL, {}))
        self.assertEqual(self.spec()['hypothesis']['goal'], GOAL)
        self.assertNotIn('text_origin', self.spec()['meta'])
        with self.assertRaisesMessage(lc.MaieuticError, 'no AI wording'):
            lc.restore_wording(self.draft.id, self.author, 'hypothesis.goal')

    def test_restore_is_refused_after_the_user_edited_the_wording(self):
        self.suggest()
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        lc.update_draft(self.draft.id, self.author, spec_patch={'hypothesis': {**self.spec()['hypothesis'], 'goal': GOOD + ' Edited.'}})
        with self.assertRaisesMessage(lc.MaieuticError, 'edited'):
            lc.restore_wording(self.draft.id, self.author, 'hypothesis.goal')
        self.assertEqual(self.spec()['hypothesis']['goal'], GOOD + ' Edited.')

    def test_a_second_wording_keeps_the_first_original_for_restoring(self):
        self.suggest()
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        self.suggest(wording='Detect an LSASS dump made through rundll32 using the comsvcs MiniDump call on servers.')
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        self.assertEqual(lc.restore_wording(self.draft.id, self.author, 'hypothesis.goal')[0], GOAL)

    def test_other_fields_keep_independent_records(self):
        self.suggest()
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        self.suggest('hypothesis.scope_notes', 'Windows servers only, and the backup agent is expected.')
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.scope_notes')
        self.assertEqual(set(self.spec()['meta']['text_origin']), {'hypothesis.goal', 'hypothesis.scope_notes'})
        lc.restore_wording(self.draft.id, self.author, 'hypothesis.scope_notes')
        self.assertEqual(set(self.spec()['meta']['text_origin']), {'hypothesis.goal'})

    def test_the_workbench_gets_the_text_and_no_trace_of_how_it_was_worded(self):
        self.suggest()
        lc.accept_wording(self.draft.id, self.author, 'hypothesis.goal')
        fields = mw.workbench_fields(self.spec())
        self.assertTrue(fields['goal'].startswith(GOOD))
        self.assertNotIn('AI_REWORDED', json.dumps(fields, default=str))
        self.assertNotIn('text_origin', json.dumps(fields, default=str))
        self.assertNotIn('wording', json.dumps(fields, default=str).lower().replace('wording help', ''))


class GraphqlTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.author = U.objects.create_user(username='author', organization=self.org, role='ANALYST')
        d = lc.create_draft(self.author, name='s')
        self.draft = lc.update_draft(d.id, self.author, spec_patch={k: v for k, v in SPEC.items()})

    def run_q(self, q, variables=None, expect_errors=False):
        r = schema.execute(q, variable_values=variables, context_value=SimpleNamespace(user=self.author))
        if not expect_errors:
            self.assertIsNone(r.errors, r.errors)
        return r

    SUGGEST = ('mutation($d:UUID!,$f:String!){suggestMaieuticWording(draftId:$d,field:$f){suggestion message remaining}}')

    def test_availability_follows_the_users_ai_settings(self):
        q = 'query{maieuticWordingAvailable}'
        self.assertFalse(self.run_q(q).data['maieuticWordingAvailable'])
        UserAISettings.objects.create(user=self.author)
        self.assertTrue(self.run_q(q).data['maieuticWordingAvailable'])

    def test_without_an_ai_provider_the_user_is_told_and_nothing_is_counted(self):
        out = self.run_q(self.SUGGEST, {'d': str(self.draft.id), 'f': 'hypothesis.goal'}).data['suggestMaieuticWording']
        self.assertIsNone(out['suggestion'])
        self.assertIn('AI provider', out['message'])
        self.assertEqual(out['remaining'], 5)

    def test_suggest_accept_restore_end_to_end(self):
        UserAISettings.objects.create(user=self.author)
        ids = {'d': str(self.draft.id), 'f': 'hypothesis.goal'}
        with patch('ai_assistant.engine.run_custom_prompt', return_value=(json.dumps({'wording': GOOD}), 'x')):
            out = self.run_q(self.SUGGEST, ids).data['suggestMaieuticWording']
        self.assertEqual((out['suggestion'], out['message'], out['remaining']), (GOOD, None, 4))
        accepted = self.run_q('mutation($d:UUID!,$f:String!){acceptMaieuticWording(draftId:$d,field:$f){value textOrigin}}', ids).data['acceptMaieuticWording']
        self.assertEqual(accepted['value'], GOOD)
        self.assertEqual(accepted['textOrigin']['hypothesis.goal']['origin'], 'AI_REWORDED')
        restored = self.run_q('mutation($d:UUID!,$f:String!){restoreMaieuticWording(draftId:$d,field:$f){value textOrigin}}', ids).data['restoreMaieuticWording']
        self.assertEqual((restored['value'], restored['textOrigin']), (GOAL, {}))

    def test_a_wording_that_adds_content_is_withheld_with_an_explanation(self):
        UserAISettings.objects.create(user=self.author)
        with patch('ai_assistant.engine.run_custom_prompt', return_value=(json.dumps({'wording': 'Detect credential theft from LSASS memory.'}), 'x')):
            out = self.run_q(self.SUGGEST, {'d': str(self.draft.id), 'f': 'hypothesis.goal'}).data['suggestMaieuticWording']
        self.assertIsNone(out['suggestion'])
        self.assertIn('without adding something you did not write', out['message'])
        self.assertEqual(out['remaining'], 4)

    def test_errors_are_shown_as_graphql_errors(self):
        r = self.run_q(self.SUGGEST, {'d': str(self.draft.id), 'f': 'robustness.ade_ledger'}, expect_errors=True)
        self.assertIn('not available', str(r.errors[0]))
