"""Regression coverage for maximum TLP policy and inherited rule classifications."""
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from tags.models import TenantTag
from django.test import TestCase, SimpleTestCase
from organizations.models import Organization, HefaistosInboundShareKey
from organizations.sharing import export_org_payload, hash_api_key
from playbooks.models import PlaybookGraph, CapabilityAbstraction
from playbooks.utils.tlp import allowed_tlp_classifications, normalize_tlp_maximum, TLP_LEVELS
from rules.models import DetectionRule, RuleRepository
from ach.models import ACHAnalysis
from advops.models import ADVOPSReport
from platform_data.models import MitreAttackTechnique


class MaximumPolicyTests(SimpleTestCase):
    def test_every_maximum_includes_lower_levels_and_unclear(self):
        for index, level in enumerate(TLP_LEVELS):
            with self.subTest(level=level):
                self.assertEqual(allowed_tlp_classifications(level), (*TLP_LEVELS[:index + 1], 'UNCLEAR'))
        self.assertEqual(normalize_tlp_maximum(None), 'RED')
        self.assertEqual(normalize_tlp_maximum('tlp:green'), 'GREEN')
        self.assertEqual(normalize_tlp_maximum('tlp:unclear'), 'UNCLEAR')
        self.assertEqual(allowed_tlp_classifications('UNCLEAR'), ('UNCLEAR',))
        for value in ('invalid', ''):
            with self.assertRaises(ValueError):
                normalize_tlp_maximum(value)


class SharingTlpTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='TLP source')
        self.admin = get_user_model().objects.create_user(username='tlp_admin', organization=self.org, role='ADMIN')
        self.repository = RuleRepository.objects.create(organization=self.org, name='TLP rules', git_url='https://example.com/rules.git')
        self.key = HefaistosInboundShareKey.objects.create(
            organization=self.org, name='GREEN maximum', key_hash=hash_api_key('tlp-test-key'),
            allowed_scopes=['ALL'], required_tlp_classification='GREEN',
        )
        self.technique = MitreAttackTechnique.objects.create(
            technique_id='T1059', stix_id='attack-pattern--sharing-tlp', name='Command interpreter',
        )

    def graph(self, title, tlp='GREEN', **kwargs):
        return PlaybookGraph.objects.create(organization=self.org, title=title, status='DEPLOYED',
                                            allow_remote_pull=True, tlp_classification=tlp, **kwargs)

    def test_all_scopes_apply_green_maximum_and_report_exclusions(self):
        for index, level in enumerate((*TLP_LEVELS, 'UNCLEAR')):
            graph = self.graph(level, level)
            DetectionRule.objects.create(repository=self.repository, organization=self.org, title=level, format='SIGMA', playbook=graph)
            ACHAnalysis.objects.create(owner=self.admin, title=level, status='APPROVED', allow_remote_pull=True, tlp_classification=level)
            ADVOPSReport.objects.create(organization=self.org, author=self.admin, hunt_id=f'ADV-TLP-{index}',
                                        hypothesis=level, status='DEPLOYED', allow_remote_pull=True, tlp_classification=level)
            CapabilityAbstraction.objects.create(organization=self.org, technique=self.technique, abstraction_layer='TOOL',
                component_artifact=level, review_status='APPROVED', allow_remote_pull=True, tlp_classification=level)
        for maximum in (*TLP_LEVELS, 'UNCLEAR'):
            self.key.required_tlp_classification = maximum
            payload = export_org_payload(self.org, 'ALL', share_key=self.key)
            expected = set(allowed_tlp_classifications(maximum))
            for collection in ('workbenches', 'rules', 'ach', 'advops', 'capability_abstractions'):
                with self.subTest(maximum=maximum, collection=collection):
                    self.assertEqual({PlaybookGraph.objects.get(pk=item['source_id']).tlp_classification if collection == 'workbenches' else item['tlp_classification'] for item in payload[collection]}, expected)
                    self.assertEqual(payload['diagnostics'][collection]['excluded_by_tlp'], 6 - len(expected))
                    self.assertEqual(payload['diagnostics'][collection]['deduplicated'], 0)

    def test_tags_and_tlp_combine_before_name_deduplication(self):
        allowed = self.graph('Same name', 'GREEN')
        tag = TenantTag.objects.create(name='PULL', organization=self.org)
        allowed.tags.add(tag)
        self.graph('Missing tag', 'GREEN')
        restricted = self.graph('Same name', 'RED')
        restricted.tags.add(tag)
        self.key.enforce_tag_filter = True
        self.key.required_tags = ['PULL']
        payload = export_org_payload(self.org, 'WORKBENCH', share_key=self.key)
        self.assertEqual([item['source_id'] for item in payload['workbenches']], [str(allowed.pk)])
        self.assertEqual(payload['diagnostics']['workbenches']['excluded_by_tags'], 1)
        self.assertEqual(payload['diagnostics']['workbenches']['excluded_by_tlp'], 1)
        self.assertEqual(payload['diagnostics']['workbenches']['deduplicated'], 0)

    def test_rule_owner_precedes_attachment_and_reclassification_updates_snapshot(self):
        owner = self.graph('Owner', 'AMBER')
        attached = self.graph('Attached', 'RED')
        rule = DetectionRule.objects.create(repository=self.repository, organization=self.org, title='Owned', playbook=owner, attached_workbench=attached)
        attachment_rule = DetectionRule.objects.create(repository=self.repository, organization=self.org, title='Attached only', attached_workbench=attached)
        self.assertEqual(rule.tlp_classification, 'AMBER')
        self.assertEqual(attachment_rule.effective_tlp_classification, 'RED')
        attached.tlp_classification = 'CLEAR'
        attached.save(update_fields=['tlp_classification'])
        rule.refresh_from_db()
        attachment_rule.refresh_from_db()
        self.assertEqual(rule.tlp_classification, 'AMBER')
        self.assertEqual(attachment_rule.tlp_classification, 'CLEAR')
        owner.tlp_classification = 'UNCLEAR'
        owner.save(update_fields=['tlp_classification'])
        rule.refresh_from_db()
        self.assertEqual(rule.effective_tlp_classification, 'UNCLEAR')
        rule.playbook = None
        rule.attached_workbench = None
        rule.save()
        self.assertEqual(rule.effective_tlp_classification, 'UNCLEAR')

    def test_capability_default_and_rule_fallback(self):
        capability = CapabilityAbstraction.objects.create(organization=self.org, technique=self.technique,
                                                          abstraction_layer='TOOL', component_artifact='Default')
        self.assertEqual(capability.tlp_classification, 'AMBER+STRICT')
        rule = DetectionRule.objects.create(repository=self.repository, organization=self.org, title='Imported', tlp_classification='RED')
        self.assertEqual(rule.effective_tlp_classification, 'RED')

    def test_key_update_validation_and_tenant_admin_permissions(self):
        from organizations.schema import UpdateHefaistosInboundShareKeyTlp
        from graphql import GraphQLError
        info = SimpleNamespace(context=SimpleNamespace(user=self.admin))
        result = UpdateHefaistosInboundShareKeyTlp.mutate(None, info, id=self.key.pk, required_tlp_classification='CLEAR')
        self.assertTrue(result.success)
        self.key.refresh_from_db()
        self.assertEqual(self.key.required_tlp_classification, 'CLEAR')
        result = UpdateHefaistosInboundShareKeyTlp.mutate(None, info, id=self.key.pk, required_tlp_classification='UNCLEAR')
        self.assertTrue(result.success)
        self.key.refresh_from_db()
        self.assertEqual(self.key.required_tlp_classification, 'UNCLEAR')
        with self.assertRaises(GraphQLError):
            UpdateHefaistosInboundShareKeyTlp.mutate(None, info, id=self.key.pk, required_tlp_classification='invalid')
        self.admin.organization = Organization.objects.create(name='Other tenant')
        with self.assertRaises(GraphQLError):
            UpdateHefaistosInboundShareKeyTlp.mutate(None, info, id=self.key.pk, required_tlp_classification='RED')
        self.admin.organization = self.org
        self.admin.role = 'ANALYST'
        with self.assertRaises(PermissionDenied):
            UpdateHefaistosInboundShareKeyTlp.mutate(None, info, id=self.key.pk, required_tlp_classification='RED')

    def test_key_creation_accepts_unclear_and_preserves_red_default(self):
        from organizations.schema import CreateHefaistosInboundShareKey
        info = SimpleNamespace(context=SimpleNamespace(user=self.admin))
        for classification in ('UNCLEAR', None):
            kwargs = {'required_tlp_classification': classification} if classification else {}
            result = CreateHefaistosInboundShareKey.mutate(None, info, name=f'New policy {classification}', allowed_scopes=['ALL'], **kwargs)
            self.assertTrue(result.success)
            result.key.refresh_from_db()
            self.assertEqual(result.key.required_tlp_classification, classification or 'RED')

    def test_endpoints_advertise_maximum_and_enforce_it(self):
        self.graph('Allowed', 'GREEN')
        self.graph('Restricted', 'AMBER+STRICT')
        for path in ('/api/sharing/info', '/api/sharing/export?scope=WORKBENCH'):
            response = self.client.get(path, HTTP_X_HEFAISTOS_SHARE_KEY='tlp-test-key')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get('permissions', response.json())['required_tlp_classification'], 'GREEN')
        self.assertEqual(len(response.json()['workbenches']), 1)
