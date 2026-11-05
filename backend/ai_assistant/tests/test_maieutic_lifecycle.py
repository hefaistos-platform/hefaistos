from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_assistant import maieutic_lifecycle as lc
from ai_assistant.maieutic_models import MaieuticDraft
from core.schema import schema
from organizations.models import Organization
from playbooks.models import PlaybookGraph
from types import SimpleNamespace

READY_SPEC = {
    'hypothesis': {'title': 'LSASS access', 'technique': {'state': 'SET', 'id': 'T1003.001'}, 'goal': 'Detect credential dumping'},
}


class MaieuticLifecycleTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org A')
        self.other_org = Organization.objects.create(name='Org B')
        self.author = U.objects.create_user(username='author', organization=self.org, role='ANALYST')
        self.peer = U.objects.create_user(username='peer', organization=self.org, role='ANALYST')
        self.org_admin = U.objects.create_user(username='orgadmin', organization=self.org, role='ADMIN')
        self.foreign_admin = U.objects.create_user(username='foreignadmin', organization=self.other_org, role='ADMIN')
        self.superuser = U.objects.create_superuser(username='root', password='x' * 20, organization=self.org)

    def workbench(self, org=None):
        return PlaybookGraph.objects.create(organization=org or self.org, title='wb', author=self.author)

    def ready(self):
        d = lc.create_draft(self.author, name='s')
        return lc.update_draft(d.id, self.author, spec_patch=READY_SPEC)

    # --- visibility -------------------------------------------------------
    def test_only_author_sees_session_not_peer_admin_or_superuser(self):
        d = lc.create_draft(self.author)
        self.assertIsNotNone(lc.get_visible_draft(self.author, d.id))
        for other in (self.peer, self.org_admin, self.superuser, self.foreign_admin):
            self.assertIsNone(lc.get_visible_draft(other, d.id), other.username)
            self.assertEqual(lc.list_visible_drafts(other).count(), 0)

    def test_peer_cannot_update_someone_elses_session(self):
        d = lc.create_draft(self.author)
        with self.assertRaises(lc.MaieuticError):
            lc.update_draft(d.id, self.peer, name='hijack')
        with self.assertRaises(lc.MaieuticError):
            lc.update_draft(d.id, self.org_admin, name='hijack')

    # --- autosave ---------------------------------------------------------
    def test_patch_replaces_named_sections_only_and_meta_is_server_owned(self):
        d = lc.create_draft(self.author, tlp='AMBER')
        lc.update_draft(d.id, self.author, spec_patch={'hypothesis': {'title': 'a'}}, current_stage=2)
        d = lc.update_draft(d.id, self.author, spec_patch={'interrogation': {'x': 1}})
        self.assertEqual(d.spec['hypothesis'], {'title': 'a'})
        self.assertEqual(d.spec['interrogation'], {'x': 1})
        self.assertEqual(d.spec['meta']['current_stage'], 2)
        self.assertEqual(d.spec['meta']['tlp'], 'AMBER')
        with self.assertRaises(lc.MaieuticError):
            lc.update_draft(d.id, self.author, spec_patch={'meta': {'tlp': 'CLEAR'}})
        with self.assertRaises(lc.MaieuticError):
            lc.update_draft(d.id, self.author, spec_patch={'nonsense': {}})
        with self.assertRaises(lc.MaieuticError):
            lc.update_draft(d.id, self.author, current_stage=7)

    # --- finishing and locking -------------------------------------------
    def test_finish_requires_minimum_answers_and_same_org_workbench(self):
        d = lc.create_draft(self.author)
        with self.assertRaisesMessage(lc.MaieuticError, 'hypothesis.title'):
            lc.finish_draft(d.id, self.author, workbench=self.workbench(), outcome='WORKBENCH_WITHOUT_RULE')
        d = self.ready()
        with self.assertRaises(lc.MaieuticError):
            lc.finish_draft(d.id, self.author, workbench=self.workbench(self.other_org), outcome='WORKBENCH_WITHOUT_RULE')
        with self.assertRaises(lc.MaieuticError):
            lc.finish_draft(d.id, self.author, workbench=self.workbench(), outcome='BOGUS')

    def test_none_chosen_technique_satisfies_minimum(self):
        d = lc.create_draft(self.author)
        lc.update_draft(d.id, self.author, spec_patch={'hypothesis': {
            'title': 't', 'technique': {'state': 'NONE_CHOSEN'}, 'goal': 'g'}})
        done = lc.finish_draft(d.id, self.author, workbench=self.workbench(), outcome='WORKBENCH_WITH_RULE')
        self.assertEqual(done.status, 'FINISHED')
        self.assertIsNotNone(done.finished_at)

    def test_unknown_technique_does_not_satisfy_minimum(self):
        d = lc.create_draft(self.author)
        lc.update_draft(d.id, self.author, spec_patch={'hypothesis': {
            'title': 't', 'technique': {'state': 'UNKNOWN'}, 'goal': 'g'}})
        with self.assertRaisesMessage(lc.MaieuticError, 'hypothesis.technique'):
            lc.finish_draft(d.id, self.author, workbench=self.workbench(), outcome='WORKBENCH_WITHOUT_RULE')

    def test_finished_session_rejects_every_edit_including_tlp(self):
        d = self.ready()
        wb = self.workbench()
        lc.finish_draft(d.id, self.author, workbench=wb, outcome='WORKBENCH_WITHOUT_RULE')
        d.refresh_from_db()
        before = (d.spec, d.name, d.tlp_classification, d.current_stage)
        for kwargs in ({'name': 'x'}, {'spec_patch': {'hypothesis': {}}}, {'tlp': 'RED'}, {'current_stage': 2}):
            with self.assertRaisesMessage(lc.MaieuticError, 'locked'):
                lc.update_draft(d.id, self.author, **kwargs)
        with self.assertRaises(lc.MaieuticError):
            lc.finish_draft(d.id, self.author, workbench=wb, outcome='WORKBENCH_WITH_RULE')
        d.refresh_from_db()
        self.assertEqual(before, (d.spec, d.name, d.tlp_classification, d.current_stage))
        self.assertEqual(d.created_workbench_id, wb.id)
        self.assertEqual(d.outcome, 'WORKBENCH_WITHOUT_RULE')

    # --- sharing ----------------------------------------------------------
    def test_sharing_only_finished_and_never_for_imports(self):
        d = self.ready()
        with self.assertRaisesMessage(lc.MaieuticError, 'finished'):
            lc.set_sharing(d.id, self.author, allow=True)
        lc.finish_draft(d.id, self.author, workbench=self.workbench(), outcome='WORKBENCH_WITH_RULE')
        self.assertFalse(MaieuticDraft.objects.get(id=d.id).allow_remote_pull)
        self.assertTrue(lc.set_sharing(d.id, self.author, allow=True).allow_remote_pull)
        with self.assertRaises(lc.MaieuticError):
            lc.set_sharing(d.id, self.peer, allow=False)
        MaieuticDraft.objects.filter(id=d.id).update(imported_from='peer-x')
        with self.assertRaisesMessage(lc.MaieuticError, 'Imported'):
            lc.set_sharing(d.id, self.author, allow=False)

    # --- delete -----------------------------------------------------------
    def test_delete_rights(self):
        d = self.ready()
        wb = self.workbench()
        lc.finish_draft(d.id, self.author, workbench=wb, outcome='WORKBENCH_WITHOUT_RULE')
        for denied in (self.peer, self.foreign_admin):
            with self.assertRaises(lc.MaieuticError):
                lc.delete_draft(d.id, denied)
        lc.delete_draft(d.id, self.org_admin)
        self.assertFalse(MaieuticDraft.objects.filter(id=d.id).exists())
        self.assertTrue(PlaybookGraph.objects.filter(id=wb.id).exists(), 'Workbench must survive')

    def test_author_and_superuser_may_delete(self):
        a = lc.create_draft(self.author)
        lc.delete_draft(a.id, self.author)
        b = lc.create_draft(self.author)
        lc.delete_draft(b.id, self.superuser)
        self.assertEqual(MaieuticDraft.objects.count(), 0)

    # --- admin metadata view ---------------------------------------------
    def test_admin_index_scope_and_roles(self):
        lc.create_draft(self.author)
        foreign = get_user_model().objects.create_user(username='f', organization=self.other_org, role='ANALYST')
        lc.create_draft(foreign)
        self.assertEqual(lc.admin_index(self.org_admin).count(), 1)
        self.assertEqual(lc.admin_index(self.superuser).count(), 2)
        with self.assertRaises(lc.MaieuticError):
            lc.admin_index(self.author)


class MaieuticGraphqlTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org A')
        self.author = U.objects.create_user(username='author', organization=self.org, role='ANALYST')
        self.admin = U.objects.create_user(username='adm', organization=self.org, role='ADMIN')

    def run_q(self, q, user, variables=None):
        return schema.execute(q, variable_values=variables, context_value=SimpleNamespace(user=user))

    def test_admin_index_schema_has_no_content_fields(self):
        names = set(schema.graphql_schema.type_map['MaieuticAdminRowType'].fields)
        for forbidden in ('spec', 'specPatch', 'conversation', 'transcript', 'answers'):
            self.assertNotIn(forbidden, names)

    def test_roundtrip_and_privacy_over_graphql(self):
        r = self.run_q('mutation{createMaieuticDraft(name:"My"){draft{id name status isLocked}}}', self.author)
        self.assertIsNone(r.errors, r.errors)
        did = r.data['createMaieuticDraft']['draft']['id']
        r = self.run_q('mutation($i:UUID!){updateMaieuticDraft(draftId:$i,specPatch:{hypothesis:{title:"t"}}){draft{spec}}}',
                       self.author, {'i': did})
        self.assertIsNone(r.errors, r.errors)
        self.assertEqual(r.data['updateMaieuticDraft']['draft']['spec']['hypothesis'], {'title': 't'})
        # Admin cannot read the session...
        r = self.run_q('query($i:UUID!){maieuticDraft(id:$i){id}}', self.admin, {'i': did})
        self.assertIsNone(r.errors); self.assertIsNone(r.data['maieuticDraft'])
        # ...but sees metadata and may delete it.
        r = self.run_q('{maieuticAdminIndex{id authorUsername status}}', self.admin)
        self.assertIsNone(r.errors, r.errors)
        self.assertEqual(r.data['maieuticAdminIndex'][0]['authorUsername'], 'author')
        r = self.run_q('mutation($i:UUID!){deleteMaieuticDraft(draftId:$i){ok}}', self.admin, {'i': did})
        self.assertIsNone(r.errors, r.errors)
        self.assertEqual(MaieuticDraft.objects.count(), 0)
        # Analyst cannot use the admin index.
        r = self.run_q('{maieuticAdminIndex{id}}', self.author)
        self.assertIsNotNone(r.errors)
