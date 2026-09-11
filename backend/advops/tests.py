from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase
from django.test import TestCase, SimpleTestCase
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from .models import ADVOPSReport
from .schema import DeleteADVOPSReport, generate_next_hunt_id
from organizations.models import Organization


class HuntIDGenerationTests(TestCase):
    """Tests for unique hunt ID generation"""

    def setUp(self):
        """Set up test organization and user"""
        User = get_user_model()
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(
            username="testuser",
            password="password",
            organization=self.org
        )

    def test_generate_next_hunt_id_starts_at_001(self):
        """Test that the first hunt ID generated is 001"""
        hunt_id = generate_next_hunt_id(self.org)
        # The format should be ADV-YYYY-MM-001
        self.assertTrue(hunt_id.endswith('-001'))
        self.assertTrue(hunt_id.startswith('ADV-'))

    def test_generate_next_hunt_id_increments(self):
        """Test that hunt IDs increment correctly"""
        # Generate and create first hunt
        hunt_id_1 = generate_next_hunt_id(self.org)
        ADVOPSReport.objects.create(
            hunt_id=hunt_id_1,
            hypothesis="Test hypothesis 1",
            author=self.user,
            organization=self.org
        )

        # Generate second hunt ID - should be incremented
        hunt_id_2 = generate_next_hunt_id(self.org)
        self.assertNotEqual(hunt_id_1, hunt_id_2)
        
        # Extract the numbers
        num_1 = int(hunt_id_1.split('-')[-1])
        num_2 = int(hunt_id_2.split('-')[-1])
        self.assertEqual(num_2, num_1 + 1)

    def test_generate_multiple_unique_hunt_ids(self):
        """Test that multiple consecutive hunt IDs are unique"""
        hunt_ids = []
        
        # Generate and create 5 hunts
        for i in range(5):
            hunt_id = generate_next_hunt_id(self.org)
            # Ensure it's unique
            self.assertNotIn(hunt_id, hunt_ids)
            hunt_ids.append(hunt_id)
            
            # Create the hunt
            ADVOPSReport.objects.create(
                hunt_id=hunt_id,
                hypothesis=f"Test hypothesis {i}",
                author=self.user,
                organization=self.org
            )
        
        # Verify all IDs are unique
        self.assertEqual(len(hunt_ids), len(set(hunt_ids)))
        
        # Verify they increment consecutively
        for i in range(1, len(hunt_ids)):
            num_prev = int(hunt_ids[i-1].split('-')[-1])
            num_curr = int(hunt_ids[i].split('-')[-1])
            self.assertEqual(num_curr, num_prev + 1)

    def test_hunt_id_unique_per_organization(self):
        """Test that hunt IDs are unique per organization"""
        User = get_user_model()
        
        # Create second organization
        org2 = Organization.objects.create(name="Test Org 2")
        user2 = User.objects.create_user(
            username="testuser2",
            password="password",
            organization=org2
        )
        
        # Generate hunt IDs for both orgs
        hunt_id_org1 = generate_next_hunt_id(self.org)
        hunt_id_org2 = generate_next_hunt_id(org2)
        
        # Both can have the same format (e.g., ADV-2026-02-001)
        # Create hunts in both orgs
        ADVOPSReport.objects.create(
            hunt_id=hunt_id_org1,
            hypothesis="Org 1 hypothesis",
            author=self.user,
            organization=self.org
        )
        
        ADVOPSReport.objects.create(
            hunt_id=hunt_id_org2,
            hypothesis="Org 2 hypothesis",
            author=user2,
            organization=org2
        )
        
        # Both should succeed (same ID allowed in different orgs)
        self.assertEqual(ADVOPSReport.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(ADVOPSReport.objects.filter(organization=org2).count(), 1)


class ADVOPSReportAPITests(GraphQLTestCase):
    """GraphQL API tests for ADVOPS reports"""
    
    def setUp(self):
        """Set up test organization and user"""
        super().setUp()
        User = get_user_model()
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(
            username="testuser",
            password="password",
            organization=self.org
        )
    
    def test_next_hunt_id_query_returns_unique_ids(self):
        """Test that nextHuntId query returns different IDs when called multiple times"""
        self.client.force_login(self.user)
        
        query = '''
            query {
                nextHuntId
            }
        '''
        
        # Query for first ID
        response1 = self.query(query)
        self.assertResponseNoErrors(response1)
        hunt_id_1 = response1.json()['data']['nextHuntId']
        
        # Create a report with this ID
        create_mutation = '''
            mutation CreateReport($input: ADVOPSReportInput!) {
                createAdvopsReport(input: $input) {
                    report {
                        id
                        huntId
                    }
                }
            }
        '''
        variables = {
            'input': {
                'huntId': hunt_id_1,
                'hypothesis': 'Test hypothesis'
            }
        }
        create_response = self.query(create_mutation, variables=variables)
        self.assertResponseNoErrors(create_response)
        
        # Query for second ID
        response2 = self.query(query)
        self.assertResponseNoErrors(response2)
        hunt_id_2 = response2.json()['data']['nextHuntId']
        
        # The second ID should be different from the first
        self.assertNotEqual(hunt_id_1, hunt_id_2)
        
        # Extract numbers and verify increment
        num_1 = int(hunt_id_1.split('-')[-1])
        num_2 = int(hunt_id_2.split('-')[-1])
        self.assertEqual(num_2, num_1 + 1)


class DeleteADVOPSReportSuperuserTests(SimpleTestCase):
    def _make_info(self):
        user = SimpleNamespace(
            is_anonymous=False,
            is_superuser=True,
            organization=None,
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    @patch("advops.schema.ADVOPSReport.objects.get")
    def test_delete_advops_report_superuser_bypasses_org_filter(self, mock_get):
        report = MagicMock()
        mock_get.return_value = report

        result = DeleteADVOPSReport.mutate(None, None, self._make_info(), id="rep-1")

        self.assertTrue(result.ok)
        mock_get.assert_called_once_with(id="rep-1")
        report.delete.assert_called_once()
