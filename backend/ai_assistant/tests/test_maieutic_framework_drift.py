from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_assistant import maieutic_lifecycle as lc
from ai_assistant import maieutic_planner as mp
from ai_assistant import maieutic_workbench as mw
from core.schema import schema
from organizations.models import Organization
from platform_data.models import AdeEntry, AdeSnapshot, MitreAttackTechnique

from .test_maieutic_planner_questioner import DESIGN, PLANNED_FOR_DESIGN

QUERY = ('query($i:UUID!){maieuticAdePlan(draftId:$i){openCount items{adeId state ledgerEntry} '
         'frameworkDrift{pinnedLabel activeLabel removed changed pinnedSnapshotId activeSnapshotId}}}')


def snapshot(status, sha, topics):
    snap = AdeSnapshot.objects.create(status=status, source_sha=sha)
    for ade_id, source_hash in topics.items():
        AdeEntry.objects.create(snapshot=snap, entry_key=f'SUBCATEGORY:{ade_id}', kind='SUBCATEGORY',
                                ade_id=ade_id, title=ade_id, source_hash=source_hash)
    return snap


def promote(old, new):
    old.status = AdeSnapshot.Status.ARCHIVED
    old.save(update_fields=['status'])
    new.status = AdeSnapshot.Status.ACTIVE
    new.save(update_fields=['status'])


class FrameworkDriftTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.author = U.objects.create_user(username='author', organization=self.org, role='ANALYST')
        MitreAttackTechnique.objects.create(technique_id='T1003.001', name='LSASS Memory')
        d = lc.create_draft(self.author, name='s')
        self.draft = lc.update_draft(d.id, self.author, spec_patch={k: DESIGN[k] for k in ('hypothesis', 'design')})
        self.old = snapshot(AdeSnapshot.Status.ACTIVE, 'a' * 40, {'ADE2-01': 'h1', 'ADE2-02': 'h2', 'ADE9-01': 'x'})

    def answer(self, ade='ADE2-01', disposition='ACCEPTED_LIMITATION'):
        return lc.record_ade_answer(self.draft.id, self.author, ade_id=ade, disposition=disposition,
                                    answer_text='regsvr32 also loads it; my plan covers rundll32 only')

    def plan(self):
        r = schema.execute(QUERY, variable_values={'i': str(self.draft.id)}, context_value=SimpleNamespace(user=self.author))
        self.assertIsNone(r.errors, r.errors)
        return r.data['maieuticAdePlan']

    def upgrade(self, topics, sha='b' * 40):
        new = snapshot(AdeSnapshot.Status.STAGED, sha, topics)
        promote(self.old, new)
        return new

    def test_no_note_when_nothing_was_answered_yet_or_nothing_changed(self):
        self.assertIsNone(self.plan()['frameworkDrift'])
        self.upgrade({'ADE2-01': 'new-hash'})
        self.assertIsNone(self.plan()['frameworkDrift'])   # not pinned yet: nothing was answered against the old one
        self.answer()                                       # now pinned to the new active one
        self.assertIsNone(self.plan()['frameworkDrift'])

    def test_removed_topic_is_reported_but_the_session_keeps_working(self):
        self.answer('ADE2-01')
        new = self.upgrade({'ADE2-02': 'h2', 'ADE9-01': 'x'})
        drift = self.plan()['frameworkDrift']
        self.assertEqual(drift['removed'], ['ADE2-01'])
        self.assertEqual(drift['changed'], [])
        self.assertEqual((drift['pinnedLabel'], drift['activeLabel']), ('a' * 12, 'b' * 12))
        self.assertEqual((drift['pinnedSnapshotId'], drift['activeSnapshotId']), (str(self.old.id), str(new.id)))
        plan = self.plan()
        by_id = {i['adeId']: i for i in plan['items']}
        self.assertEqual([i['adeId'] for i in plan['items']], PLANNED_FOR_DESIGN)   # nothing hidden
        self.assertEqual(by_id['ADE2-01']['state'], 'ANSWERED')                      # nothing reopened
        self.assertEqual(plan['openCount'], len(PLANNED_FOR_DESIGN) - 1)
        self.answer('ADE2-02')                                                        # still answerable
        self.assertEqual(self.plan()['openCount'], len(PLANNED_FOR_DESIGN) - 2)

    def test_answer_to_a_removed_topic_still_reaches_the_workbench_as_a_negative_test(self):
        self.answer('ADE2-01')
        self.upgrade({'ADE2-02': 'h2'})
        with patch('core.rabbitmq.publish_event', return_value=True):
            wb, _ = mw.create_workbench_from_draft(self.draft.id, self.author, exit_mode=mw.EXIT_WITHOUT_RULE)
        self.assertEqual([t['source_ref'] for t in wb.negative_tests], ['ADE2-01'])
        self.assertIn('regsvr32 also loads it', wb.blind_spots)

    def test_changed_definition_is_reported_without_reopening_the_question(self):
        self.answer('ADE2-02')
        self.upgrade({'ADE2-01': 'h1', 'ADE2-02': 'h2-edited', 'ADE9-01': 'x'})
        plan = self.plan()
        self.assertEqual(plan['frameworkDrift']['changed'], ['ADE2-02'])
        self.assertEqual(plan['frameworkDrift']['removed'], [])
        self.assertEqual(next(i for i in plan['items'] if i['adeId'] == 'ADE2-02')['state'], 'ANSWERED')

    def test_topics_this_session_does_not_use_are_not_mentioned(self):
        self.answer('ADE2-01')
        self.upgrade({'ADE2-01': 'h1', 'ADE2-02': 'h2'})   # ADE9-01 removed, but this session never plans it
        self.assertIsNone(self.plan()['frameworkDrift'])

    def test_a_changed_definition_of_a_topic_this_session_does_not_use_is_not_mentioned(self):
        self.answer('ADE2-01')
        self.upgrade({'ADE2-01': 'h1', 'ADE2-02': 'h2', 'ADE9-01': 'edited-upstream'})
        self.assertIsNone(self.plan()['frameworkDrift'])

    def test_only_a_changed_question_text_reopens_it(self):
        self.answer('ADE2-01')
        self.upgrade({'ADE2-01': 'changed-upstream'})
        self.assertEqual(next(i for i in self.plan()['items'] if i['adeId'] == 'ADE2-01')['state'], 'ANSWERED')
        entry = self.draft.__class__.objects.get(id=self.draft.id).spec['robustness']['ade_ledger'][0]
        stale = {'robustness': {'ade_ledger': [{**entry, 'question_version': 0}]}}
        lc.update_draft(self.draft.id, self.author, spec_patch=stale)
        self.assertEqual(next(i for i in self.plan()['items'] if i['adeId'] == 'ADE2-01')['state'], 'STALE')


class PureDriftTests(TestCase):
    def test_edge_cases(self):
        a = snapshot(AdeSnapshot.Status.ARCHIVED, 'a' * 40, {'ADE2-01': '', 'ADE2-02': 'h'})
        b = snapshot(AdeSnapshot.Status.ACTIVE, '', {'ADE2-01': '', 'ADE2-02': 'h'})
        ids = {'ADE2-01', 'ADE2-02'}
        self.assertIsNone(mp.framework_drift(None, b, ids))
        self.assertIsNone(mp.framework_drift(a, None, ids))
        self.assertIsNone(mp.framework_drift(a, a, ids))
        self.assertIsNone(mp.framework_drift(a, b, ids))   # identical content, two imports
        self.assertIsNone(mp.framework_drift(a, b, set()))
        c = snapshot(AdeSnapshot.Status.STAGED, '', {'ADE2-01': 'now-set', 'ADE2-02': 'h'})
        drift = mp.framework_drift(a, c, ids)
        self.assertEqual(drift['changed'], ['ADE2-01'])
        self.assertEqual((drift['pinned_label'], drift['active_label']), ('a' * 12, 'main'))   # no commit known: the ref
