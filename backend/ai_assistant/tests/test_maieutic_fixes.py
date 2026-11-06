from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_assistant import maieutic_draft_schema as draft_schema
from ai_assistant import maieutic_lifecycle as lc
from ai_assistant.models import UserAISettings
from organizations.models import Organization


class StageOneTitleTests(TestCase):
    """The title typed in the New session dialog is also the required stage 1 title."""

    def setUp(self):
        self.org = Organization.objects.create(name='Org A')
        self.user = get_user_model().objects.create_user(username='author', organization=self.org, role='ANALYST')

    def hyp_title(self, draft):
        return ((draft.spec or {}).get('hypothesis') or {}).get('title')

    def test_named_session_has_its_stage_one_title(self):
        d = lc.create_draft(self.user, name='LSASS dump')
        self.assertEqual(self.hyp_title(d), 'LSASS dump')
        self.assertNotIn('hypothesis.title', lc.missing_for_workbench(d.spec))

    def test_unnamed_session_still_needs_a_title(self):
        d = lc.create_draft(self.user)
        self.assertEqual(d.name, 'New Maieutic session')
        self.assertIsNone(self.hyp_title(d))
        self.assertIn('hypothesis.title', lc.missing_for_workbench(d.spec))

    def test_blank_name_is_treated_as_unnamed(self):
        d = lc.create_draft(self.user, name='   ')
        self.assertIsNone(self.hyp_title(d))

    def test_rename_follows_while_the_title_is_untouched(self):
        d = lc.create_draft(self.user, name='First')
        d = lc.update_draft(d.id, self.user, name='Second')
        self.assertEqual(d.name, 'Second')
        self.assertEqual(self.hyp_title(d), 'Second')

    def test_rename_does_not_overwrite_a_title_edited_on_its_own(self):
        d = lc.create_draft(self.user, name='First')
        d = lc.update_draft(d.id, self.user, spec_patch={'hypothesis': {'title': 'My own wording'}})
        d = lc.update_draft(d.id, self.user, name='Second')
        self.assertEqual(d.name, 'Second')
        self.assertEqual(self.hyp_title(d), 'My own wording')

    def test_rename_in_the_same_call_as_a_hypothesis_edit_keeps_the_edit(self):
        d = lc.create_draft(self.user, name='First')
        d = lc.update_draft(d.id, self.user, name='Second',
                            spec_patch={'hypothesis': {'title': 'Edited', 'goal': 'g'}})
        self.assertEqual(self.hyp_title(d), 'Edited')

    def test_rename_fills_an_empty_title(self):
        d = lc.create_draft(self.user)
        d = lc.update_draft(d.id, self.user, name='Now named')
        self.assertEqual(self.hyp_title(d), 'Now named')


class AnswerCheckSettingsTests(TestCase):
    """The answer check must run on the same effective AI settings as rule generation."""

    def setUp(self):
        self.org = Organization.objects.create(name='Org A')
        self.user = get_user_model().objects.create_user(username='author', organization=self.org, role='ANALYST')

    def test_user_without_ai_settings_gets_none(self):
        self.assertIsNone(draft_schema._user_ai_settings(self.user))

    def test_uses_the_effective_settings_including_organization_ones(self):
        UserAISettings.objects.create(user=self.user, use_org_ai=True)
        sentinel = object()
        with patch('ai_assistant.schema._get_effective_ai_settings', return_value=sentinel) as eff:
            self.assertIs(draft_schema._user_ai_settings(self.user), sentinel)
        passed = eff.call_args.args[0]
        self.assertEqual(passed.user_id, self.user.id)

    def test_personal_settings_are_still_used_when_the_org_is_not_opted_in(self):
        mine = UserAISettings.objects.create(user=self.user, use_org_ai=False)
        result = draft_schema._user_ai_settings(self.user)
        self.assertEqual(result.pk, mine.pk)
