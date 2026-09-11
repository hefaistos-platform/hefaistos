import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from ach.models import ACHAnalysis
from advops.models import ADVOPSReport
from organizations.models import (
    HefaistosInboundShareKey,
    HefaistosInstanceIdentity,
    HefaistosRemotePeer,
    Organization,
)
from organizations.sharing import (
    compute_next_auto_pull_at,
    hash_api_key,
    import_payload_into_org,
    key_allows_scope,
    normalize_auto_pull_schedule,
)
from playbooks.models import PlaybookGraph
from rules.models import DetectionRule, RuleRepository


class SharingScopePermissionTests(TestCase):
    def test_key_allows_scope_rules(self):
        self.assertTrue(key_allows_scope(['ALL'], 'WORKBENCH'))
        self.assertTrue(key_allows_scope(['WORKBENCH', 'RULES', 'ACH', 'ADVOPS'], 'ALL'))
        self.assertTrue(key_allows_scope(['ADVOPS'], 'ADVOPS'))
        self.assertTrue(key_allows_scope(['RULES'], 'RULES'))
        self.assertFalse(key_allows_scope(['WORKBENCH'], 'ALL'))
        self.assertFalse(key_allows_scope(['WORKBENCH'], 'RULES'))


class SharingApiEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name='Sharing Org')
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username='sharing_admin',
            password='pass1234',
            organization=self.org,
            role='ADMIN',
        )
        self.raw_key = 'hefshare_test_readonly_key'
        HefaistosInboundShareKey.objects.create(
            organization=self.org,
            name='test-key',
            key_hash=hash_api_key(self.raw_key),
            key_hint='test...key',
            allowed_scopes=['WORKBENCH'],
            is_active=True,
            created_by=self.admin,
        )

    def test_sharing_info_requires_valid_key(self):
        response = self.client.get('/api/sharing/info')
        self.assertEqual(response.status_code, 403)

    def test_sharing_info_returns_instance_metadata(self):
        response = self.client.get(
            '/api/sharing/info',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': self.raw_key},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn('instance_id', body)
        self.assertEqual(body.get('mode'), 'PULL_READ_ONLY')

    def test_export_scope_must_be_allowed(self):
        denied = self.client.get(
            '/api/sharing/export?scope=RULES',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': self.raw_key},
        )
        self.assertEqual(denied.status_code, 403)

        allowed = self.client.get(
            '/api/sharing/export?scope=WORKBENCH',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': self.raw_key},
        )
        self.assertEqual(allowed.status_code, 200)
        body = allowed.json()
        self.assertEqual(body.get('scope'), 'WORKBENCH')
        self.assertIn('workbenches', body)
        self.assertEqual(body.get('permissions', {}).get('mode'), 'PULL_READ_ONLY')

    def test_export_endpoint_is_read_only(self):
        response = self.client.post(
            '/api/sharing/export',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': self.raw_key},
        )
        self.assertEqual(response.status_code, 405)

    def test_get_endpoints_do_not_mutate_remote_state(self):
        self.assertEqual(HefaistosInstanceIdentity.objects.count(), 0)
        key_obj = HefaistosInboundShareKey.objects.get(organization=self.org, name='test-key')
        self.assertIsNone(key_obj.last_used_at)

        info_response = self.client.get(
            '/api/sharing/info',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': self.raw_key},
        )
        self.assertEqual(info_response.status_code, 200)

        export_response = self.client.get(
            '/api/sharing/export?scope=WORKBENCH',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': self.raw_key},
        )
        self.assertEqual(export_response.status_code, 200)

        key_obj.refresh_from_db()
        self.assertIsNone(key_obj.last_used_at)
        self.assertEqual(HefaistosInstanceIdentity.objects.count(), 0)

    def test_export_all_only_returns_deployed_finished_items(self):
        all_scope_key = 'hefshare_test_all_scope_key'
        HefaistosInboundShareKey.objects.create(
            organization=self.org,
            name='all-scope-key',
            key_hash=hash_api_key(all_scope_key),
            key_hint='all...key',
            allowed_scopes=['ALL'],
            is_active=True,
            created_by=self.admin,
        )

        deployed_workbench = PlaybookGraph.objects.create(
            title='WB Deployed',
            organization=self.org,
            author=self.admin,
            status='DEPLOYED',
            allow_remote_pull=True,
        )
        non_deployed_workbench = PlaybookGraph.objects.create(
            title='WB Draft',
            organization=self.org,
            author=self.admin,
            status='DEVELOPMENT',
            allow_remote_pull=True,
        )
        repository = RuleRepository.objects.create(
            organization=self.org,
            name='Share Rules',
            git_url='https://example.com/rules.git',
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repository,
            title='Rule In Deployed WB',
            format='KQL',
            raw_content='rule: deployed',
            playbook=deployed_workbench,
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repository,
            title='Rule In Non-Deployed WB',
            format='KQL',
            raw_content='rule: non-deployed',
            playbook=non_deployed_workbench,
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repository,
            title='Rule Without Workbench',
            format='KQL',
            raw_content='rule: detached',
            playbook=None,
        )

        ACHAnalysis.objects.create(
            title='ACH Finished',
            owner=self.admin,
            status='FINISHED',
            allow_remote_pull=True,
        )
        ACHAnalysis.objects.create(
            title='ACH Research',
            owner=self.admin,
            status='RESEARCH',
            allow_remote_pull=True,
        )

        response = self.client.get(
            '/api/sharing/export?scope=ALL',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': all_scope_key},
        )
        self.assertEqual(response.status_code, 200)

        body = response.json()
        workbench_names = {((doc.get('metadata') or {}).get('name') or '').strip() for doc in (body.get('workbenches') or [])}
        rule_names = {(doc.get('title') or '').strip() for doc in (body.get('rules') or [])}
        ach_names = {(doc.get('title') or '').strip() for doc in (body.get('ach') or [])}

        self.assertEqual(workbench_names, {'WB Deployed'})
        self.assertEqual(rule_names, {'Rule In Deployed WB'})
        self.assertEqual(ach_names, {'ACH Finished'})
        self.assertEqual((body.get('rules') or [{}])[0].get('playbook_status'), 'DEPLOYED')
        self.assertEqual((body.get('ach') or [{}])[0].get('status'), 'FINISHED')

    def test_export_default_deny_requires_allow_remote_pull_toggle(self):
        all_scope_key = 'hefshare_default_deny_key'
        HefaistosInboundShareKey.objects.create(
            organization=self.org,
            name='default-deny-key',
            key_hash=hash_api_key(all_scope_key),
            key_hint='deny...key',
            allowed_scopes=['ALL'],
            is_active=True,
            created_by=self.admin,
        )

        denied_workbench = PlaybookGraph.objects.create(
            title='WB Blocked',
            organization=self.org,
            author=self.admin,
            status='DEPLOYED',
            allow_remote_pull=False,
        )
        allowed_workbench = PlaybookGraph.objects.create(
            title='WB Allowed',
            organization=self.org,
            author=self.admin,
            status='DEPLOYED',
            allow_remote_pull=True,
        )

        repository = RuleRepository.objects.create(
            organization=self.org,
            name='Rule Scope Repo',
            git_url='https://example.com/scope-rules.git',
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repository,
            title='Rule Blocked',
            format='KQL',
            raw_content='rule: blocked',
            playbook=denied_workbench,
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repository,
            title='Rule Allowed',
            format='KQL',
            raw_content='rule: allowed',
            playbook=allowed_workbench,
        )

        ACHAnalysis.objects.create(
            title='ACH Blocked',
            owner=self.admin,
            status='FINISHED',
            allow_remote_pull=False,
        )
        ACHAnalysis.objects.create(
            title='ACH Allowed',
            owner=self.admin,
            status='FINISHED',
            allow_remote_pull=True,
        )

        response = self.client.get(
            '/api/sharing/export?scope=ALL',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': all_scope_key},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        workbench_names = {((doc.get('metadata') or {}).get('name') or '').strip() for doc in (body.get('workbenches') or [])}
        rule_names = {(doc.get('title') or '').strip() for doc in (body.get('rules') or [])}
        ach_names = {(doc.get('title') or '').strip() for doc in (body.get('ach') or [])}

        self.assertEqual(workbench_names, {'WB Allowed'})
        self.assertEqual(rule_names, {'Rule Allowed'})
        self.assertEqual(ach_names, {'ACH Allowed'})

    def test_export_tag_filter_restricts_workbench_and_rules(self):
        tagged_key = 'hefshare_tag_policy_key'
        HefaistosInboundShareKey.objects.create(
            organization=self.org,
            name='tag-policy-key',
            key_hash=hash_api_key(tagged_key),
            key_hint='tag...key',
            allowed_scopes=['ALL'],
            enforce_tag_filter=True,
            required_tags=['PULL'],
            is_active=True,
            created_by=self.admin,
        )

        allowed_graph = PlaybookGraph.objects.create(
            title='WB Tagged',
            organization=self.org,
            author=self.admin,
            status='DEPLOYED',
            allow_remote_pull=True,
        )
        allowed_graph.tags.add('PULL')

        blocked_graph = PlaybookGraph.objects.create(
            title='WB Untagged',
            organization=self.org,
            author=self.admin,
            status='DEPLOYED',
            allow_remote_pull=True,
        )
        blocked_graph.tags.add('INTERNAL')

        repository = RuleRepository.objects.create(
            organization=self.org,
            name='Tag Rule Repo',
            git_url='https://example.com/tag-rules.git',
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repository,
            title='Rule Tagged',
            format='KQL',
            raw_content='rule: tagged',
            playbook=allowed_graph,
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repository,
            title='Rule Untagged',
            format='KQL',
            raw_content='rule: untagged',
            playbook=blocked_graph,
        )

        response = self.client.get(
            '/api/sharing/export?scope=ALL',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': tagged_key},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        workbench_names = {((doc.get('metadata') or {}).get('name') or '').strip() for doc in (body.get('workbenches') or [])}
        rule_names = {(doc.get('title') or '').strip() for doc in (body.get('rules') or [])}

        self.assertEqual(workbench_names, {'WB Tagged'})
        self.assertEqual(rule_names, {'Rule Tagged'})
        self.assertEqual(body.get('permissions', {}).get('enforce_tag_filter'), True)
        self.assertEqual(body.get('permissions', {}).get('required_tags'), ['PULL'])

    def test_export_advops_scope_honors_status_and_toggle(self):
        advops_key = 'hefshare_advops_scope_key'
        HefaistosInboundShareKey.objects.create(
            organization=self.org,
            name='advops-scope-key',
            key_hash=hash_api_key(advops_key),
            key_hint='adv...key',
            allowed_scopes=['ADVOPS'],
            is_active=True,
            created_by=self.admin,
        )

        ADVOPSReport.objects.create(
            hunt_id='ADV-2026-06-001',
            hypothesis='Allowed hunt',
            status='DEPLOYED',
            priority='MEDIUM',
            author=self.admin,
            organization=self.org,
            allow_remote_pull=True,
        )
        ADVOPSReport.objects.create(
            hunt_id='ADV-2026-06-002',
            hypothesis='Not enabled',
            status='DEPLOYED',
            priority='MEDIUM',
            author=self.admin,
            organization=self.org,
            allow_remote_pull=False,
        )
        ADVOPSReport.objects.create(
            hunt_id='ADV-2026-06-003',
            hypothesis='Wrong status',
            status='RESEARCH',
            priority='MEDIUM',
            author=self.admin,
            organization=self.org,
            allow_remote_pull=True,
        )

        response = self.client.get(
            '/api/sharing/export?scope=ADVOPS',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': advops_key},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        hunt_ids = {(entry.get('hunt_id') or '').strip() for entry in (body.get('advops') or [])}
        self.assertEqual(hunt_ids, {'ADV-2026-06-001'})

    def test_export_all_includes_advops_when_allowed(self):
        all_scope_key = 'hefshare_all_includes_advops_key'
        HefaistosInboundShareKey.objects.create(
            organization=self.org,
            name='all-includes-advops',
            key_hash=hash_api_key(all_scope_key),
            key_hint='all...adv',
            allowed_scopes=['ALL'],
            is_active=True,
            created_by=self.admin,
        )

        ADVOPSReport.objects.create(
            hunt_id='ADV-2026-06-010',
            hypothesis='Included in ALL',
            status='DEPLOYED',
            priority='HIGH',
            author=self.admin,
            organization=self.org,
            allow_remote_pull=True,
        )

        response = self.client.get(
            '/api/sharing/export?scope=ALL',
            **{'HTTP_X_HEFAISTOS_SHARE_KEY': all_scope_key},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        hunt_ids = {(entry.get('hunt_id') or '').strip() for entry in (body.get('advops') or [])}
        self.assertEqual(hunt_ids, {'ADV-2026-06-010'})


class SharingImportRulesTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Sharing Import Org')
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username='sharing_import_admin',
            password='pass1234',
            organization=self.org,
            role='ADMIN',
        )
        self.peer = HefaistosRemotePeer.objects.create(
            organization=self.org,
            name='Remote Peer',
            remote_url='https://remote-hefaistos.example.com',
            remote_instance_id=uuid.uuid4(),
            default_scope='ALL',
            verify_ssl=True,
            allow_self_signed=False,
            enabled=True,
            created_by=self.admin,
        )

    @staticmethod
    def _minimal_hex_payload(title: str, status: str) -> dict:
        return {
            'hex_format': '2.0',
            'metadata': {
                'name': title,
                'status': status,
                'tags': [],
            },
            'strategy': {
                'mitre_techniques': [],
            },
            'capability_abstraction': {
                'layers': [],
            },
            'detection_logic': {
                'detection_rule': '',
                'blind_spots': [],
            },
            'operational_context': {
                'goal': '',
                'technical_context': '',
                'false_positives': [],
                'triage_guidance': '',
                'response_playbook': '',
            },
            'testing': {
                'test_scenario': '',
                'test_expected_output': '',
                'target_file_path': '',
            },
            'soar_configuration': {
                'alert_trigger': '',
                'default_severity': 'MEDIUM',
                'enrichment_steps': [],
                'containment_steps': [],
                'notification_steps': [],
                'downstream_correlation_requirements': {},
            },
            'graph_structure': {
                'nodes': [],
                'edges': [],
            },
            'audit_trail': {
                'robustness_level': 0,
                'data_source_robustness': '',
                'notes': '',
                'validation_status': 'Not validated',
            },
        }

    def test_import_deduplicates_by_name_case_insensitive(self):
        payload = {
            'workbenches': [
                self._minimal_hex_payload('Duplicate WB', 'DEPLOYED'),
                self._minimal_hex_payload('duplicate wb', 'DEPLOYED'),
            ],
            'rules': [
                {
                    'title': 'Duplicate Rule',
                    'format': 'KQL',
                    'status': '',
                    'description': 'Rule 1',
                    'author': 'remote',
                    'raw_content': 'rule: one',
                    'playbook_title': 'Duplicate WB',
                    'playbook_status': 'DEPLOYED',
                },
                {
                    'title': 'duplicate rule',
                    'format': 'SPL',
                    'status': '',
                    'description': 'Rule 2',
                    'author': 'remote',
                    'raw_content': 'rule: two',
                    'playbook_title': 'Duplicate WB',
                    'playbook_status': 'DEPLOYED',
                },
            ],
            'ach': [
                {
                    'title': 'Duplicate ACH',
                    'description': 'Analysis 1',
                    'status': 'FINISHED',
                    'saved_as_template': False,
                    'hypotheses': [],
                    'evidence': [],
                    'matrix': [],
                },
                {
                    'title': 'duplicate ach',
                    'description': 'Analysis 2',
                    'status': 'FINISHED',
                    'saved_as_template': True,
                    'hypotheses': [],
                    'evidence': [],
                    'matrix': [],
                },
            ],
        }

        summary, errors = import_payload_into_org(
            payload=payload,
            organization=self.org,
            actor=self.admin,
            peer=self.peer,
            requested_scope='ALL',
        )

        self.assertEqual(errors, [])
        self.assertEqual(
            PlaybookGraph.objects.filter(organization=self.org, title__iexact='duplicate wb').count(),
            1,
        )
        self.assertEqual(
            DetectionRule.objects.filter(organization=self.org, title__iexact='duplicate rule').count(),
            1,
        )
        self.assertEqual(
            ACHAnalysis.objects.filter(owner=self.admin, title__iexact='duplicate ach').count(),
            1,
        )
        self.assertEqual(summary['workbenches']['created'], 1)
        self.assertEqual(summary['workbenches']['updated'], 1)
        self.assertEqual(summary['rules']['created'], 1)
        self.assertEqual(summary['rules']['updated'], 1)
        self.assertEqual(summary['ach']['created'], 1)
        self.assertEqual(summary['ach']['updated'], 1)

    def test_import_rejects_non_deployed_or_non_finished_entries(self):
        payload = {
            'workbenches': [self._minimal_hex_payload('Non Deployed WB', 'DEVELOPMENT')],
            'rules': [{
                'title': 'Rule Non Deployed',
                'format': 'KQL',
                'raw_content': 'rule: no',
                'playbook_title': 'WB',
                'playbook_status': 'DEVELOPMENT',
            }],
            'ach': [{
                'title': 'ACH Non Finished',
                'description': 'No',
                'status': 'RESEARCH',
                'hypotheses': [],
                'evidence': [],
                'matrix': [],
            }],
        }

        summary, errors = import_payload_into_org(
            payload=payload,
            organization=self.org,
            actor=self.admin,
            peer=self.peer,
            requested_scope='ALL',
        )

        self.assertEqual(summary['workbenches']['failed'], 1)
        self.assertEqual(summary['rules']['failed'], 1)
        self.assertEqual(summary['ach']['failed'], 1)
        self.assertEqual(PlaybookGraph.objects.filter(organization=self.org).count(), 0)
        self.assertEqual(DetectionRule.objects.filter(organization=self.org).count(), 0)
        self.assertEqual(ACHAnalysis.objects.filter(owner=self.admin).count(), 0)
        self.assertEqual(len(errors), 3)


class SharingAutoPullScheduleHelperTests(TestCase):
    def test_normalize_auto_pull_schedule(self):
        self.assertEqual(normalize_auto_pull_schedule('daily'), 'DAILY')
        self.assertEqual(normalize_auto_pull_schedule('WEEKLY'), 'WEEKLY')
        with self.assertRaises(ValueError):
            normalize_auto_pull_schedule('MONTHLY')

    def test_compute_next_auto_pull_at(self):
        base = timezone.now().replace(microsecond=0)
        self.assertEqual(compute_next_auto_pull_at('DAILY', from_time=base), base + timedelta(days=1))
        self.assertEqual(compute_next_auto_pull_at('WEEKLY', from_time=base), base + timedelta(days=7))


class SharingScheduledAutoPullCommandTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Sharing Auto Pull Org')
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username='sharing_auto_pull_admin',
            password='pass1234',
            organization=self.org,
            role='ADMIN',
        )
        self.peer = HefaistosRemotePeer.objects.create(
            organization=self.org,
            name='Auto Pull Peer',
            remote_url='https://remote-hefaistos.example.com',
            remote_instance_id=uuid.uuid4(),
            default_scope='ALL',
            auto_pull_enabled=True,
            auto_pull_schedule='DAILY',
            next_auto_pull_at=timezone.now() - timedelta(minutes=10),
            verify_ssl=True,
            allow_self_signed=False,
            enabled=True,
            created_by=self.admin,
        )

    @patch('organizations.management.commands.run_scheduled_hefaistos_pulls.pull_from_remote_peer')
    def test_command_triggers_due_peer_and_updates_next_run(self, pull_mock):
        before = timezone.now()
        call_command('run_scheduled_hefaistos_pulls')

        pull_mock.assert_called_once()
        self.peer.refresh_from_db()
        self.assertIsNotNone(self.peer.next_auto_pull_at)
        self.assertGreaterEqual(self.peer.next_auto_pull_at, before + timedelta(hours=23))
        self.assertLessEqual(self.peer.next_auto_pull_at, before + timedelta(days=1, minutes=10))

    @patch('organizations.management.commands.run_scheduled_hefaistos_pulls.pull_from_remote_peer')
    def test_command_skips_disabled_auto_pull(self, pull_mock):
        self.peer.auto_pull_enabled = False
        self.peer.save(update_fields=['auto_pull_enabled', 'updated_at'])

        call_command('run_scheduled_hefaistos_pulls')
        pull_mock.assert_not_called()

    @patch('organizations.management.commands.run_scheduled_hefaistos_pulls.pull_from_remote_peer')
    def test_command_uses_weekly_schedule_for_next_run(self, pull_mock):
        self.peer.auto_pull_schedule = 'WEEKLY'
        self.peer.next_auto_pull_at = timezone.now() - timedelta(minutes=5)
        self.peer.save(update_fields=['auto_pull_schedule', 'next_auto_pull_at', 'updated_at'])
        before = timezone.now()

        call_command('run_scheduled_hefaistos_pulls')

        pull_mock.assert_called_once()
        self.peer.refresh_from_db()
        self.assertIsNotNone(self.peer.next_auto_pull_at)
        self.assertGreaterEqual(self.peer.next_auto_pull_at, before + timedelta(days=6, hours=23))
        self.assertLessEqual(self.peer.next_auto_pull_at, before + timedelta(days=7, minutes=10))
