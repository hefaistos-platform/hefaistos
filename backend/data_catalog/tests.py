import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase
from organizations.models import Organization
from.models import DataSource
from platform_data.models import MitreAttackTechnique, MitreDataComponent, MitreDataSource

class DataCatalogAPITests(GraphQLTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()

        # Create Organization A and User A
        self.org_a = Organization.objects.create(name="Org A")
        self.user_a = User.objects.create_user(
            username="usera",
            password="password",
            organization=self.org_a,
            role='ADMIN',
        )

        # Create Organization B and User B
        self.org_b = Organization.objects.create(name="Org B")
        self.user_b = User.objects.create_user(
            username="userb",
            password="password",
            organization=self.org_b,
            role='ANALYST',
        )

        # Create a data source owned by Org A
        self.data_source_a = DataSource.objects.create(
            name="Sysmon A",
            organization=self.org_a
        )

    def test_user_cannot_add_field_to_other_orgs_data_source(self):
        """
        SECURITY TEST: Ensures a user from one org cannot add a field to a data source
        owned by another organization.
        """
        # Authenticate as User B (the "attacker")
        self.client.force_login(self.user_b)

        mutation = '''
            mutation AddField($dsId: ID!, $fieldName: String!) {
                addDataSourceField(dataSourceId: $dsId, fieldName: $fieldName) {
                    dataSourceField { id }
                }
            }
        '''
        variables = {
            "dsId": str(self.data_source_a.id),
            "fieldName": "malicious_field"
        }

        response = self.query(mutation, variables=variables)

        # Assert that the API returns an error
        self.assertResponseHasErrors(response)

        # Verify the error message indicates a permission issue or that the object was not found
        content = json.loads(response.content)
        self.assertIn("not found or you do not have permission", content['errors'][0]['message'])

    def test_import_mitre_required_data_sources_creates_catalog_entries_with_fields(self):
        self.client.force_login(self.user_a)

        technique = MitreAttackTechnique.objects.create(
            technique_id="T1111",
            stix_id="attack-pattern--aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            name="Test Technique",
            description="Technique for testing",
            url="https://attack.mitre.org/techniques/T1111/",
            revoked=False,
            deprecated=False,
        )
        mitre_source = MitreDataSource.objects.create(
            stix_id="x-mitre-data-source--aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            name="Windows Event Logs",
            description="MITRE source",
        )
        component = MitreDataComponent.objects.create(
            stix_id="x-mitre-data-component--aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            name="Process Creation",
            description="Process start telemetry",
            data_source=mitre_source,
        )
        component.techniques.add(technique)

        mutation = '''
            mutation ImportMitreRequired {
                importMitreRequiredDataSources {
                    createdCount
                    existingCount
                    updatedCount
                    totalCandidates
                }
            }
        '''

        response = self.query(mutation)
        self.assertResponseNoErrors(response)

        content = json.loads(response.content)
        payload = content["data"]["importMitreRequiredDataSources"]
        self.assertEqual(payload["createdCount"], 1)
        self.assertEqual(payload["existingCount"], 0)
        self.assertEqual(payload["totalCandidates"], 1)

        imported = DataSource.objects.get(
            organization=self.org_a,
            name="Windows Event Logs - Process Creation",
        )
        self.assertEqual(imported.platform, "Windows")
        imported_fields = set(imported.fields.values_list("field_name", flat=True))
        self.assertSetEqual(imported_fields, {"data_component", "provider", "channel"})

    def test_import_mitre_required_data_sources_skips_existing_and_revoked_links(self):
        self.client.force_login(self.user_a)

        active_technique = MitreAttackTechnique.objects.create(
            technique_id="T2222",
            stix_id="attack-pattern--bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            name="Active Technique",
            description="Active technique",
            url="https://attack.mitre.org/techniques/T2222/",
            revoked=False,
            deprecated=False,
        )
        revoked_technique = MitreAttackTechnique.objects.create(
            technique_id="T3333",
            stix_id="attack-pattern--cccccccc-cccc-cccc-cccc-cccccccccccc",
            name="Revoked Technique",
            description="Revoked technique",
            url="https://attack.mitre.org/techniques/T3333/",
            revoked=True,
            deprecated=False,
        )

        mitre_source = MitreDataSource.objects.create(
            stix_id="x-mitre-data-source--bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            name="Linux Logs",
            description="Linux provider",
        )
        active_component = MitreDataComponent.objects.create(
            stix_id="x-mitre-data-component--bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            name="Command Execution",
            description="Process command line telemetry",
            data_source=mitre_source,
        )
        active_component.techniques.add(active_technique)

        revoked_component = MitreDataComponent.objects.create(
            stix_id="x-mitre-data-component--cccccccc-cccc-cccc-cccc-cccccccccccc",
            name="Deprecated Signal",
            description="Deprecated",
            data_source=mitre_source,
        )
        revoked_component.techniques.add(revoked_technique)

        DataSource.objects.create(
            name="Linux Logs - Command Execution",
            organization=self.org_a,
            platform=None,
            description=None,
        )

        mutation = '''
            mutation ImportMitreRequired {
                importMitreRequiredDataSources {
                    createdCount
                    existingCount
                    updatedCount
                    totalCandidates
                }
            }
        '''

        response = self.query(mutation)
        self.assertResponseNoErrors(response)

        content = json.loads(response.content)
        payload = content["data"]["importMitreRequiredDataSources"]
        self.assertEqual(payload["createdCount"], 0)
        self.assertEqual(payload["existingCount"], 1)
        self.assertEqual(payload["updatedCount"], 1)
        self.assertEqual(payload["totalCandidates"], 1)

        existing = DataSource.objects.get(
            organization=self.org_a,
            name="Linux Logs - Command Execution",
        )
        self.assertEqual(existing.platform, "Linux")
        self.assertIsNotNone(existing.description)
        self.assertFalse(
            DataSource.objects.filter(
                organization=self.org_a,
                name="Linux Logs - Deprecated Signal",
            ).exists()
        )
        imported_fields = set(existing.fields.values_list("field_name", flat=True))
        self.assertSetEqual(imported_fields, {"data_component", "provider", "channel"})

    def test_non_admin_cannot_import_mitre_required_data_sources(self):
        self.client.force_login(self.user_b)

        mutation = '''
            mutation ImportMitreRequired {
                importMitreRequiredDataSources {
                    createdCount
                    existingCount
                    updatedCount
                    totalCandidates
                }
            }
        '''

        response = self.query(mutation)
        self.assertResponseHasErrors(response)
        content = json.loads(response.content)
        self.assertIn("permission", content['errors'][0]['message'].lower())

    @patch('data_catalog.tasks.run_mitre_deep_import_job')
    def test_admin_can_queue_deep_import_job(self, run_job_mock):
        self.client.force_login(self.user_a)

        mutation = '''
            mutation RunDeepImport {
                runMitreDeepImport {
                    job {
                        id
                        status
                        includeRevoked
                        totalAnalytics
                        processedAnalytics
                    }
                }
            }
        '''

        response = self.query(mutation)
        self.assertResponseNoErrors(response)

        content = json.loads(response.content)
        payload = content['data']['runMitreDeepImport']['job']
        self.assertIsNotNone(payload['id'])
        self.assertEqual(payload['status'], 'PENDING')
        self.assertEqual(payload['includeRevoked'], False)
        self.assertEqual(payload['totalAnalytics'], 0)
        self.assertEqual(payload['processedAnalytics'], 0)

        run_job_mock.assert_called_once()

    def test_non_admin_cannot_queue_deep_import_job(self):
        self.client.force_login(self.user_b)

        mutation = '''
            mutation RunDeepImport {
                runMitreDeepImport {
                    job { id }
                }
            }
        '''

        response = self.query(mutation)
        self.assertResponseHasErrors(response)
        content = json.loads(response.content)
        self.assertIn("permission", content['errors'][0]['message'].lower())
