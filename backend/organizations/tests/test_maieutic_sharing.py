"""Instance Sharing scope MAIEUTIC (Docs/MAIEUTIC_3_SPEC.md section 9c)."""
import copy
import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from ai_assistant import maieutic_lifecycle as lc
from ai_assistant.maieutic_models import MaieuticDraft
from organizations.models import HefaistosInboundShareKey, HefaistosPullJob, HefaistosRemotePeer, Organization
from organizations.sharing import (
    LEGACY_ATOMIC_SCOPES,
    export_org_payload,
    hash_api_key,
    import_payload_into_org,
    key_allows_scope,
    pull_from_remote_peer,
    scopes_granted_by_key,
)
from platform_data.models import AdeSnapshot

FIVE: list[str] = list(LEGACY_ATOMIC_SCOPES)

SPEC = {
    'meta': {'spec_version': 1, 'tlp': 'AMBER', 'current_stage': 6, 'challenge_level': 'STANDARD'},
    'hypothesis': {'title': 'LSASS dump', 'goal': 'Detect credential dumping'},
    'interrogation': {'log_sources': [{'kind': 'LOG_SOURCE', 'ref_id': 'local-id', 'name': 'Sysmon'}]},
    'design': {'blueprint_text': 'rundll32 comsvcs'},
    'robustness': {'ade_ledger': [{
        'ade_id': 'ADE2-01', 'snapshot_id': 'LOCAL-SNAPSHOT-UUID', 'question_text': 'Q?',
        'answer_text': 'I also match procdump', 'disposition': 'HANDLED_IN_DESIGN',
    }]},
    'review': {'output_formats': ['KQL']},
}


def make_session(org, author, name='LSASS design', **kw):
    values = dict(
        organization=org, author=author, name=name, status='FINISHED', current_stage=6,
        spec=copy.deepcopy(SPEC), outcome='WORKBENCH_WITHOUT_RULE', finished_at=timezone.now(),
        allow_remote_pull=True, tlp_classification='AMBER',
    )
    values.update(kw)
    return MaieuticDraft.objects.create(**values)


class KeyRuleTests(SimpleTestCase):
    def test_a_key_created_before_maieutic_can_still_pull_all(self):
        self.assertTrue(key_allows_scope(FIVE, 'ALL'))

    def test_that_key_is_not_granted_maieutic(self):
        self.assertFalse(key_allows_scope(FIVE, 'MAIEUTIC'))
        self.assertEqual(scopes_granted_by_key(FIVE), set(FIVE))

    def test_all_marker_grants_everything_including_maieutic(self):
        self.assertTrue(key_allows_scope(['ALL'], 'MAIEUTIC'))
        self.assertEqual(scopes_granted_by_key(['ALL']), set(FIVE) | {'MAIEUTIC'})

    def test_maieutic_only_key(self):
        self.assertTrue(key_allows_scope(['MAIEUTIC'], 'MAIEUTIC'))
        for denied in ('ALL', 'WORKBENCH', 'RULES', 'ACH', 'ADVOPS', 'CAPABILITY'):
            self.assertFalse(key_allows_scope(['MAIEUTIC'], denied), denied)
        self.assertEqual(scopes_granted_by_key(['MAIEUTIC']), {'MAIEUTIC'})

    def test_incomplete_keys_still_cannot_pull_all(self):
        self.assertFalse(key_allows_scope(FIVE[:-1], 'ALL'))
        self.assertFalse(key_allows_scope(FIVE[:-1] + ['MAIEUTIC'], 'ALL'))
        self.assertTrue(key_allows_scope(FIVE + ['MAIEUTIC'], 'ALL'))


class ExportTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Source')
        self.other_org = Organization.objects.create(name='Other')
        self.author = get_user_model().objects.create_user(username='src', organization=self.org, role='ANALYST')
        self.snapshot = AdeSnapshot.objects.create(
            source_repo='https://github.com/example/ade', source_ref='main', source_sha='a' * 40, status='ACTIVE')
        self.keys = {}
        for label, scopes in (('five', FIVE), ('all', ['ALL']), ('maieutic', ['MAIEUTIC'])):
            raw = f'key-{label}'
            self.keys[label] = (raw, HefaistosInboundShareKey.objects.create(
                organization=self.org, name=label, key_hash=hash_api_key(raw), allowed_scopes=scopes))
        self.client = Client()

    def get(self, label, scope):
        raw, _ = self.keys[label]
        return self.client.get(f'/api/sharing/export?scope={scope}', **{'HTTP_X_HEFAISTOS_SHARE_KEY': raw})

    def titles(self, response):
        return [row['title'] for row in response.json()['maieutic_sessions']]

    def test_explicit_five_key_pulls_all_but_never_receives_sessions(self):
        make_session(self.org, self.author)
        response = self.get('five', 'ALL')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['maieutic_sessions'], [])
        self.assertNotIn('maieutic_sessions', response.json()['diagnostics'])
        self.assertEqual(self.get('five', 'MAIEUTIC').status_code, 403)

    def test_all_marker_key_receives_sessions_through_all(self):
        make_session(self.org, self.author)
        self.assertEqual(self.titles(self.get('all', 'ALL')), ['LSASS design'])

    def test_maieutic_only_key(self):
        make_session(self.org, self.author)
        self.assertEqual(self.titles(self.get('maieutic', 'MAIEUTIC')), ['LSASS design'])
        for scope in ('ALL', 'WORKBENCH', 'RULES'):
            self.assertEqual(self.get('maieutic', scope).status_code, 403, scope)

    def test_only_finished_opted_in_original_sessions_of_this_org_leave(self):
        make_session(self.org, self.author, name='ok')
        make_session(self.org, self.author, name='draft', status='IN_PROGRESS')
        make_session(self.org, self.author, name='private', allow_remote_pull=False)
        make_session(self.org, self.author, name='copy', imported_from='Some peer')
        make_session(self.other_org, None, name='foreign')
        response = self.get('maieutic', 'MAIEUTIC')
        self.assertEqual(self.titles(response), ['ok'])
        diag = response.json()['diagnostics']['maieutic_sessions']
        self.assertEqual((diag['exported'], diag['excluded_by_status'], diag['excluded_by_remote_pull_disabled']), (1, 1, 1))

    def test_tlp_maximum_applies_with_the_sessions_own_classification(self):
        make_session(self.org, self.author, name='amber', tlp_classification='AMBER')
        make_session(self.org, self.author, name='green', tlp_classification='GREEN')
        _, key = self.keys['maieutic']
        key.required_tlp_classification = 'GREEN'
        key.save()
        response = self.get('maieutic', 'MAIEUTIC')
        self.assertEqual(self.titles(response), ['green'])
        self.assertEqual(response.json()['diagnostics']['maieutic_sessions']['excluded_by_tlp'], 1)

    def test_duplicate_titles_are_sent_once(self):
        make_session(self.org, self.author, name='Same')
        make_session(self.org, self.author, name='same')
        self.assertEqual(len(self.titles(self.get('maieutic', 'MAIEUTIC'))), 1)

    def test_payload_carries_the_design_but_nothing_local(self):
        session = make_session(self.org, self.author, ade_snapshot=self.snapshot, created_workbench=None)
        row = self.get('maieutic', 'MAIEUTIC').json()['maieutic_sessions'][0]
        self.assertEqual(row['spec']['robustness']['ade_ledger'][0]['answer_text'], 'I also match procdump')
        self.assertEqual(row['spec']['design']['blueprint_text'], 'rundll32 comsvcs')
        self.assertIsNone(row['spec']['robustness']['ade_ledger'][0]['snapshot_id'])
        self.assertEqual(row['ade_source'], {'repo': 'https://github.com/example/ade', 'ref': 'main', 'sha': 'a' * 40})
        self.assertEqual((row['status'], row['tlp_classification'], row['source_id']), ('FINISHED', 'AMBER', str(session.pk)))
        text = str(row)
        for forbidden in ('conversation', 'transcript', 'created_workbench', 'author', 'LOCAL-SNAPSHOT-UUID', 'allow_remote_pull'):
            self.assertNotIn(forbidden, text, forbidden)
        # exporting must not change the stored session
        session.refresh_from_db()
        self.assertEqual(session.spec['robustness']['ade_ledger'][0]['snapshot_id'], 'LOCAL-SNAPSHOT-UUID')

    def test_a_session_with_an_unshareable_spec_is_skipped_not_fatal(self):
        make_session(self.org, self.author, name='broken', spec={'design': 'not an object'})
        make_session(self.org, self.author, name='fine')
        self.assertEqual(self.titles(self.get('maieutic', 'MAIEUTIC')), ['fine'])

    def test_toggle_controls_visibility_end_to_end(self):
        session = make_session(self.org, self.author, allow_remote_pull=False)
        self.assertEqual(self.titles(self.get('maieutic', 'MAIEUTIC')), [])
        lc.set_sharing(session.id, self.author, allow=True)
        self.assertEqual(self.titles(self.get('maieutic', 'MAIEUTIC')), ['LSASS design'])
        lc.set_sharing(session.id, self.author, allow=False)
        self.assertEqual(self.titles(self.get('maieutic', 'MAIEUTIC')), [])


class ImportTests(TestCase):
    def setUp(self):
        self.source = Organization.objects.create(name='Source')
        self.target = Organization.objects.create(name='Target')
        U = get_user_model()
        self.src_user = U.objects.create_user(username='s', organization=self.source, role='ANALYST')
        self.actor = U.objects.create_user(username='t', organization=self.target, role='ADMIN')
        self.peer = HefaistosRemotePeer.objects.create(
            organization=self.target, name='Partner CERT', remote_url='https://example.com',
            remote_instance_id=uuid.uuid4(), default_scope='MAIEUTIC')

    def row(self, **over):
        make_session(self.source, self.src_user, name=over.pop('name', 'LSASS design'),
                     ade_snapshot=AdeSnapshot.objects.create(source_repo='https://x.test/ade', source_sha='b' * 40, status='ACTIVE'))
        row = export_org_payload(self.source, 'MAIEUTIC')['maieutic_sessions'][0]
        row.update(over)
        MaieuticDraft.objects.filter(organization=self.source).delete()
        return row

    def run_import(self, *rows, scope='MAIEUTIC'):
        payload = {'maieutic_sessions': list(rows)}
        return import_payload_into_org(payload, self.target, self.actor, self.peer, scope)

    def test_import_creates_a_locked_read_only_copy(self):
        summary, errors = self.run_import(self.row())
        self.assertEqual(errors, [])
        self.assertEqual(summary['maieutic_sessions'], {'created': 1, 'updated': 0, 'failed': 0, 'received': 1})
        copy_ = MaieuticDraft.objects.get(organization=self.target)
        self.assertEqual((copy_.status, copy_.outcome, copy_.tlp_classification), ('FINISHED', 'WORKBENCH_WITHOUT_RULE', 'AMBER'))
        self.assertEqual((copy_.author_id, copy_.imported_from), (self.actor.id, 'Partner CERT'))
        self.assertFalse(copy_.allow_remote_pull)
        self.assertIsNone(copy_.created_workbench_id)
        self.assertIsNone(copy_.ade_snapshot_id)  # never linked to a local snapshot
        self.assertEqual(copy_.spec['robustness']['ade_source']['sha'], 'b' * 40)
        self.assertIsNone(copy_.spec['robustness']['ade_ledger'][0]['snapshot_id'])
        self.assertEqual(copy_.spec['robustness']['ade_ledger'][0]['answer_text'], 'I also match procdump')
        self.assertEqual(copy_.spec['meta']['tlp'], 'AMBER')
        with self.assertRaises(lc.MaieuticError):
            lc.update_draft(copy_.id, self.actor, name='edit')

    def test_the_copy_cannot_be_shared_onward(self):
        self.run_import(self.row())
        copy_ = MaieuticDraft.objects.get(organization=self.target)
        with self.assertRaisesMessage(lc.MaieuticError, 'cannot be shared again'):
            lc.set_sharing(copy_.id, self.actor, allow=True)
        copy_.allow_remote_pull = True  # even if someone forced the flag, the exporter skips copies
        copy_.save()
        self.assertEqual(export_org_payload(self.target, 'MAIEUTIC')['maieutic_sessions'], [])

    def test_repeat_pull_updates_instead_of_duplicating(self):
        row = self.row()
        self.run_import(row)
        row['spec'] = {**row['spec'], 'design': {'blueprint_text': 'revised'}}
        row['tlp_classification'] = 'GREEN'
        summary, _ = self.run_import(row)
        self.assertEqual((summary['maieutic_sessions']['created'], summary['maieutic_sessions']['updated']), (0, 1))
        self.assertEqual(MaieuticDraft.objects.filter(organization=self.target).count(), 1)
        copy_ = MaieuticDraft.objects.get(organization=self.target)
        self.assertEqual((copy_.spec['design']['blueprint_text'], copy_.tlp_classification), ('revised', 'GREEN'))
        self.assertFalse(copy_.allow_remote_pull)

    def test_a_deleted_copy_is_recreated_on_the_next_pull(self):
        row = self.row()
        self.run_import(row)
        MaieuticDraft.objects.filter(organization=self.target).delete()
        summary, _ = self.run_import(row)
        self.assertEqual(summary['maieutic_sessions']['created'], 1)

    def test_it_never_overwrites_a_session_made_on_this_instance(self):
        row = self.row()
        self.run_import(row)
        local = MaieuticDraft.objects.get(organization=self.target)
        local.imported_from = ''
        local.save()
        summary, errors = self.run_import(row)
        self.assertEqual(summary['maieutic_sessions']['failed'], 1)
        self.assertIn('Refusing to overwrite', errors[0])

    def test_untrusted_input_is_rejected_per_row_without_stopping_the_rest(self):
        good = self.row(name='good')
        cases = {
            'not finished': self.row(name='a', status='IN_PROGRESS'),
            'no title': self.row(name='b', title='  '),
            'spec not object': self.row(name='c', spec=['x']),
            'section not object': self.row(name='d', spec={'design': 'x'}),
            'newer format': self.row(name='e', spec={'meta': {'spec_version': 99}}),
            'oversize': self.row(name='f', spec={'design': {'blob': 'x' * (600 * 1024)}}),
            'bad ledger': self.row(name='g', spec={'robustness': {'ade_ledger': ['x']}}),
            'not an object': 'just a string',
        }
        summary, errors = self.run_import(*cases.values(), good)
        self.assertEqual(summary['maieutic_sessions']['failed'], len(cases), errors)
        self.assertEqual(summary['maieutic_sessions']['created'], 1)
        self.assertEqual(list(MaieuticDraft.objects.filter(organization=self.target).values_list('name', flat=True)), ['good'])

    def test_unknown_sections_and_bad_values_are_dropped_not_stored(self):
        row = self.row(outcome='SOMETHING_ELSE', finished_at='not a date')
        row['spec']['extra_section'] = {'evil': True}
        self.run_import(row)
        copy_ = MaieuticDraft.objects.get(organization=self.target)
        self.assertNotIn('extra_section', copy_.spec)
        self.assertEqual(copy_.outcome, '')
        self.assertIsNotNone(copy_.finished_at)

    def test_unknown_tlp_becomes_unclear(self):
        self.run_import(self.row(tlp_classification='PURPLE'))
        self.assertEqual(MaieuticDraft.objects.get(organization=self.target).tlp_classification, 'UNCLEAR')


class PullTests(TestCase):
    def setUp(self):
        self.target = Organization.objects.create(name='Target')
        self.actor = get_user_model().objects.create_user(username='t', organization=self.target, role='ADMIN')
        self.peer = HefaistosRemotePeer.objects.create(
            organization=self.target, name='Old peer', remote_url='https://example.com',
            remote_instance_id=uuid.uuid4(), default_scope='ALL')
        self.peer.api_key = 'x'
        self.peer.save()

    def pull(self, payload, scope):
        info, export = Mock(status_code=200), Mock(status_code=200)
        info.json.return_value = {'instance_id': str(self.peer.remote_instance_id)}
        export.json.return_value = payload
        with patch('organizations.sharing.requests.get', side_effect=[info, export]):
            return pull_from_remote_peer(self.peer, self.actor, requested_scope=scope)

    def payload(self, scope, **extra):
        body = {
            'schema_version': '1.0', 'instance_id': str(self.peer.remote_instance_id), 'scope': scope,
            'workbenches': [], 'rules': [], 'ach': [], 'advops': [], 'capability_abstractions': [],
        }
        body.update(extra)
        return body

    def test_all_pull_from_a_peer_that_predates_maieutic_still_works(self):
        job = self.pull(self.payload('ALL'), 'ALL')  # no maieutic_sessions collection at all
        self.assertEqual(job.status, HefaistosPullJob.Status.COMPLETED)

    def test_explicit_maieutic_pull_needs_the_collection(self):
        with self.assertRaisesMessage(ValueError, 'must contain a list for maieutic_sessions'):
            self.pull(self.payload('MAIEUTIC'), 'MAIEUTIC')
        self.assertEqual(MaieuticDraft.objects.count(), 0)

    def test_all_pull_from_a_current_peer_imports_sessions(self):
        row = {'source_id': 'r1', 'title': 'Remote design', 'status': 'FINISHED', 'outcome': '',
               'tlp_classification': 'GREEN', 'spec': {'hypothesis': {'title': 'x'}}}
        job = self.pull(self.payload('ALL', maieutic_sessions=[row]), 'ALL')
        self.assertEqual(job.status, HefaistosPullJob.Status.COMPLETED)
        self.assertEqual(MaieuticDraft.objects.get(organization=self.target).imported_from, 'Old peer')
