import json
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, RequestFactory
from graphene_django.utils.testing import GraphQLTestCase
from organizations.models import Organization
from .models import DetectionPlaybook
from .views import attack_navigator_layer_json, issue_coverage_access_token
from tags.models import TenantTag
from rules.models import DetectionRule, RuleRepository
from data_catalog.models import DataSource
from platform_data.models import PlatformDataVersion
from playbooks.models import PlaybookGraph
from identity.decorators import Roles

class PlaybookAPITests(GraphQLTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()

        self.org_a = Organization.objects.create(name="Org A")
        self.user_a = User.objects.create_user(
            username="usera",
            password="password",
            organization=self.org_a
        )

        self.org_b = Organization.objects.create(name="Org B")
        self.user_b = User.objects.create_user(
            username="userb",
            password="password",
            organization=self.org_b
        )

        self.playbook_a = DetectionPlaybook.objects.create(
            title="Playbook A",
            organization=self.org_a
        )

    def test_user_cannot_tag_other_orgs_playbook(self):
        self.client.force_login(self.user_b)

        mutation = '''
            mutation UpdateTags($playbookId: UUID!, $tags: [String!]!) {
                updatePlaybookTags(playbookId: $playbookId, tagNames: $tags) {
                    playbook { id }
                }
            }
        '''
        variables = {
            "playbookId": str(self.playbook_a.id),
            "tags": ["malicious-tag"]
        }

        response = self.query(mutation, variables=variables)
        self.assertResponseHasErrors(response)

        content = json.loads(response.content)
        self.assertIn("not found or you do not have permission", content['errors'][0]['message'])

    def test_user_cannot_use_other_orgs_tags(self):
        TenantTag.objects.create(name="Tag B", organization=self.org_b)
        self.client.force_login(self.user_a)

        mutation = '''
            mutation UpdateTags($playbookId: UUID!, $tags: [String!]!) {
                updatePlaybookTags(playbookId: $playbookId, tagNames: $tags) {
                    playbook { id tags { name organization { name } } }
                }
            }
        '''
        variables = {
            "playbookId": str(self.playbook_a.id),
            "tags": ["Tag B"]
        }

        response = self.query(mutation, variables=variables)
        self.assertResponseNoErrors(response)

        content = json.loads(response.content)
        tags = content['data']['updatePlaybookTags']['playbook']['tags']

        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['name'], "Tag B")
        self.assertEqual(tags[0]['organization']['name'], "Org A")

    def test_user_cannot_link_other_orgs_rule(self):
        repository = RuleRepository.objects.create(
            name="Repo B",
            git_url="https://example.com/repo.git",
            organization=self.org_b
        )

        rule_b = DetectionRule.objects.create(
            title="Rule B",
            raw_content="content",
            organization=self.org_b,
            repository=repository
        )

        self.client.force_login(self.user_a)

        mutation = '''
            mutation UpdateLinks($playbookId: UUID!, $ruleIds: [ID!]!) {
                updatePlaybookLinks(playbookId: $playbookId, detectionRuleIds: $ruleIds) {
                    playbook { id }
                }
            }
        '''
        variables = {
            "playbookId": str(self.playbook_a.id),
            "ruleIds": [str(rule_b.id)]
        }

        response = self.query(mutation, variables=variables)
        self.assertResponseHasErrors(response)

        content = json.loads(response.content)
        self.assertIn("not found or you do not have permission", content['errors'][0]['message'])


class WorkbenchNotesPermissionsTests(GraphQLTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.org = Organization.objects.create(name="Notes Org")
        self.author = User.objects.create_user(
            username="notes_author",
            password="password",
            organization=self.org,
            role=Roles.ANALYST,
        )
        self.other_analyst = User.objects.create_user(
            username="notes_other",
            password="password",
            organization=self.org,
            role=Roles.ANALYST,
        )
        self.admin = User.objects.create_user(
            username="notes_admin",
            password="password",
            organization=self.org,
            role=Roles.ADMIN,
        )
        self.graph = PlaybookGraph.objects.create(
            title="Notes Graph",
            organization=self.org,
            author=self.author,
            notes="Initial investigation notes",
        )

    def _update_notes(self, notes_value):
        mutation = """
            mutation UpdateWorkbenchNotes($graphId: UUID!, $notes: String) {
                updatePlaybookDetails(graphId: $graphId, notes: $notes) {
                    graph { id notes }
                }
            }
        """
        return self.query(
            mutation,
            variables={"graphId": str(self.graph.id), "notes": notes_value},
        )

    def test_non_author_analyst_cannot_clear_existing_notes(self):
        self.client.force_login(self.other_analyst)
        response = self._update_notes("")
        self.assertResponseHasErrors(response)
        content = json.loads(response.content)
        self.assertIn("Only the workbench author or an admin can clear notes.", content['errors'][0]['message'])
        self.graph.refresh_from_db()
        self.assertEqual(self.graph.notes, "Initial investigation notes")

    def test_author_can_clear_existing_notes(self):
        self.client.force_login(self.author)
        response = self._update_notes("")
        self.assertResponseNoErrors(response)
        self.graph.refresh_from_db()
        self.assertEqual(self.graph.notes, "")

    def test_admin_can_clear_existing_notes(self):
        self.client.force_login(self.admin)
        response = self._update_notes("")
        self.assertResponseNoErrors(response)
        self.graph.refresh_from_db()
        self.assertEqual(self.graph.notes, "")


class CoverageLayerJsonViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        User = get_user_model()
        self.org = Organization.objects.create(name="Test Org")
        self.user_with_org = User.objects.create_user(
            username="withorg", password="password", organization=self.org
        )
        self.user_no_org = User.objects.create_user(
            username="noorg", password="password", organization=None
        )

    def test_returns_400_when_user_has_no_organization(self):
        """Authenticated users without an organization receive 400, not 500."""
        request = self.factory.get('/api/coverage/layer.json')
        request.user = self.user_no_org
        response = attack_navigator_layer_json(request)
        self.assertEqual(response.status_code, 400)

    def test_returns_200_for_user_with_organization(self):
        """Authenticated users with an organization receive a valid JSON layer."""
        PlatformDataVersion.objects.update_or_create(
            framework='enterprise-attack',
            defaults={'version': '19.1'},
        )
        request = self.factory.get('/api/coverage/layer.json')
        request.user = self.user_with_org
        response = attack_navigator_layer_json(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('techniques', data)
        self.assertIn('name', data)
        self.assertEqual(data['versions']['attack'], '19.1')
        self.assertEqual(data['versions']['navigator'], '5.2.0')
        self.assertEqual(data['versions']['layer'], '4.5')
        self.assertIn('sorting', data)
        self.assertIn('layout', data)
        self.assertIn('hideDisabled', data)
        self.assertEqual(data['layout']['expandedSubtechniques'], 'all')
        self.assertNotIn('expandedSubtechniques', data)
        self.assertEqual(data['gradient']['minValue'], 0)
        self.assertEqual(data['gradient']['maxValue'], 100)

        if data['techniques']:
            technique = data['techniques'][0]
            self.assertIn('metadata', technique)
            self.assertIn('links', technique)
            self.assertIn('showSubtechniques', technique)

    def test_returns_403_for_unauthenticated_request(self):
        """Unauthenticated requests receive 403."""
        request = self.factory.get('/api/coverage/layer.json')
        request.user = AnonymousUser()
        response = attack_navigator_layer_json(request)
        self.assertEqual(response.status_code, 403)

    def test_issue_coverage_token_requires_authentication(self):
        request = self.factory.get('/api/coverage/token')
        request.user = AnonymousUser()
        response = issue_coverage_access_token(request)
        self.assertEqual(response.status_code, 403)

    def test_issue_coverage_token_returns_scoped_short_token(self):
        request = self.factory.get('/api/coverage/token')
        request.user = self.user_with_org
        response = issue_coverage_access_token(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn('token', payload)
        self.assertTrue(payload['token'])
        self.assertEqual(payload.get('scope'), 'coverage:read')
        self.assertGreater(payload.get('expiresIn', 0), 0)
        self.assertEqual(response.get('Cache-Control'), 'no-store')

    def test_layer_json_accepts_short_lived_coverage_token(self):
        PlatformDataVersion.objects.update_or_create(
            framework='enterprise-attack',
            defaults={'version': '19.1'},
        )

        issue_request = self.factory.get('/api/coverage/token')
        issue_request.user = self.user_with_org
        issue_response = issue_coverage_access_token(issue_request)
        self.assertEqual(issue_response.status_code, 200)
        issued = json.loads(issue_response.content)
        coverage_token = issued.get('token')
        self.assertTrue(coverage_token)

        layer_request = self.factory.get('/api/coverage/layer.json', {'token': coverage_token})
        layer_request.user = AnonymousUser()
        layer_response = attack_navigator_layer_json(layer_request)
        self.assertEqual(layer_response.status_code, 200)
        layer_payload = json.loads(layer_response.content)
        self.assertIn('techniques', layer_payload)

    def test_includes_subtechniques_from_workbench_rule_content(self):
        """
        MITRE IDs present only in Workbench rule text should still color
        techniques/sub-techniques in the Coverage layer.
        """
        PlatformDataVersion.objects.update_or_create(
            framework='enterprise-attack',
            defaults={'version': '19.1'},
        )
        # Seed ATT&CK records that can be validated by the coverage endpoint.
        from platform_data.models import MitreAttackTechnique
        parent = MitreAttackTechnique.objects.create(
            technique_id='T1059',
            stix_id='attack-pattern--t1059',
            name='Command and Scripting Interpreter',
            url='https://attack.mitre.org/techniques/T1059',
            domain='enterprise-attack',
            revoked=False,
            deprecated=False,
        )
        MitreAttackTechnique.objects.create(
            technique_id='T1059.001',
            stix_id='attack-pattern--t1059-001',
            name='PowerShell',
            url='https://attack.mitre.org/techniques/T1059/001',
            domain='enterprise-attack',
            revoked=False,
            deprecated=False,
        )
        MitreAttackTechnique.objects.create(
            technique_id='T1059.003',
            stix_id='attack-pattern--t1059-003',
            name='Windows Command Shell',
            url='https://attack.mitre.org/techniques/T1059/003',
            domain='enterprise-attack',
            revoked=False,
            deprecated=False,
        )

        graph = PlaybookGraph.objects.create(
            title="WB Test",
            organization=self.org,
            author=self.user_with_org,
            status='DEPLOYED',
            mitre_technique=parent,
        )
        repo = RuleRepository.objects.create(
            organization=self.org,
            name='Repo',
            git_url='https://example.com/repo.git',
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repo,
            title='Rule with sub-technique',
            description='Detect ATT&CK T1059.001 activity',
            raw_content='metadata: mitre_technique: T1059.001',
            playbook=graph,
            format='KQL',
        )

        request = self.factory.get('/api/coverage/layer.json')
        request.user = self.user_with_org
        response = attack_navigator_layer_json(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        techniques = {t.get('techniqueID'): t for t in data.get('techniques', [])}
        technique_ids = set(techniques.keys())
        total_children = 2
        expected_parent_score = round(1 / total_children * 100)

        self.assertIn('T1059.001', technique_ids)
        self.assertIn('T1059', technique_ids)
        self.assertEqual(data['layout']['expandedSubtechniques'], 'all')
        self.assertEqual(techniques['T1059.001']['color'], '#1a9850')
        self.assertNotEqual(techniques['T1059']['color'], '#1a9850')
        self.assertNotEqual(techniques['T1059']['color'], '#a1d99b')
        self.assertEqual(techniques['T1059']['score'], expected_parent_score)

    def test_deployed_workbench_colors_directly_mapped_technique(self):
        PlatformDataVersion.objects.update_or_create(
            framework='enterprise-attack',
            defaults={'version': '19.1'},
        )
        from platform_data.models import MitreAttackTechnique
        t1078 = MitreAttackTechnique.objects.create(
            technique_id='T1078',
            stix_id='attack-pattern--t1078',
            name='Valid Accounts',
            url='https://attack.mitre.org/techniques/T1078',
            domain='enterprise-attack',
            revoked=False,
            deprecated=False,
        )
        PlaybookGraph.objects.create(
            title="WB Deployed",
            organization=self.org,
            author=self.user_with_org,
            status='DEPLOYED',
            mitre_technique=t1078,
        )

        request = self.factory.get('/api/coverage/layer.json')
        request.user = self.user_with_org
        response = attack_navigator_layer_json(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        techniques = {t.get('techniqueID'): t for t in data.get('techniques', [])}
        self.assertIn('T1078', techniques)
        self.assertEqual(techniques['T1078']['color'], '#1a9850')
        self.assertEqual(techniques['T1078']['score'], 100)

    def test_deployed_rule_status_contributes_even_if_workbench_draft(self):
        PlatformDataVersion.objects.update_or_create(
            framework='enterprise-attack',
            defaults={'version': '19.1'},
        )
        from platform_data.models import MitreAttackTechnique
        MitreAttackTechnique.objects.create(
            technique_id='T1003',
            stix_id='attack-pattern--t1003',
            name='OS Credential Dumping',
            url='https://attack.mitre.org/techniques/T1003',
            domain='enterprise-attack',
            revoked=False,
            deprecated=False,
        )
        MitreAttackTechnique.objects.create(
            technique_id='T1003.001',
            stix_id='attack-pattern--t1003-001',
            name='LSASS Memory',
            url='https://attack.mitre.org/techniques/T1003/001',
            domain='enterprise-attack',
            revoked=False,
            deprecated=False,
        )
        MitreAttackTechnique.objects.create(
            technique_id='T1003.002',
            stix_id='attack-pattern--t1003-002',
            name='Security Account Manager',
            url='https://attack.mitre.org/techniques/T1003/002',
            domain='enterprise-attack',
            revoked=False,
            deprecated=False,
        )

        graph = PlaybookGraph.objects.create(
            title="WB Draft",
            organization=self.org,
            author=self.user_with_org,
            status='DRAFT',
            mitre_technique=None,
        )
        repo = RuleRepository.objects.create(
            organization=self.org,
            name='Repo Draft',
            git_url='https://example.com/repo.git',
        )
        DetectionRule.objects.create(
            organization=self.org,
            repository=repo,
            title='Deployed rule only',
            description='Credential dumping detection',
            raw_content='T1003.001',
            playbook=graph,
            status='deployed',
            format='KQL',
        )

        request = self.factory.get('/api/coverage/layer.json')
        request.user = self.user_with_org
        response = attack_navigator_layer_json(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        techniques = {t.get('techniqueID'): t for t in data.get('techniques', [])}
        self.assertIn('T1003.001', techniques)
        self.assertIn('T1003', techniques)
        self.assertEqual(techniques['T1003.001']['color'], '#1a9850')
        self.assertNotEqual(techniques['T1003']['color'], '#1a9850')

    def test_layout_object_contains_expanded_subtechniques(self):
        PlatformDataVersion.objects.update_or_create(
            framework='enterprise-attack',
            defaults={'version': '19.1'},
        )
        request = self.factory.get('/api/coverage/layer.json')
        request.user = self.user_with_org
        response = attack_navigator_layer_json(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('layout', data)
        self.assertEqual(data['layout'].get('expandedSubtechniques'), 'all')
        self.assertTrue(data.get('selectSubtechniquesWithParent'))
        self.assertNotIn('expandedSubtechniques', data)
