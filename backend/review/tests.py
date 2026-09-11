from django.test import TestCase, Client
from django.contrib.auth import get_user_model
import json
from organizations.models import Organization
from playbooks.models import DetectionPlaybook
from review.models import ReviewRequest
from graphene.test import Client as GrapheneClient
from core.schema import schema

User = get_user_model()


class ReviewWorkflowTests(TestCase):
    def setUp(self):
        """Set up test data for review workflow."""
        # Create an organization
        self.org = Organization.objects.create(name="Test Org")

        # Create users
        self.author = User.objects.create_user(
            username="author",
            email="author@test.com",
            password="testpass123",
            organization=self.org
        )
        self.reviewer = User.objects.create_user(
            username="reviewer",
            email="reviewer@test.com",
            password="testpass123",
            organization=self.org
        )

        # Create a playbook
        self.playbook_a = DetectionPlaybook.objects.create(
            title="Test Playbook A",
            description="A test playbook",
            status=DetectionPlaybook.PlaybookStatus.DEVELOPMENT,
            author=self.author,
            organization=self.org
        )

        # Initialize GraphQL client
        self.client = GrapheneClient(schema)

    def test_full_approval_workflow_happy_path(self):
        """Test the full approval workflow: create review -> approve -> close review."""
        
        # --- 1. Author creates a review request ---
        mutation_create = """
        mutation {
            createReviewRequest(playbookId: "%s", reviewerIds: ["%s"]) {
                reviewRequest {
                    id
                    status
                    playbook {
                        status
                    }
                }
            }
        }
        """ % (self.playbook_a.id, self.reviewer.id)

        response = self.client.execute(
            mutation_create,
            context_value=type('Context', (), {'user': self.author})()
        )

        self.assertNotIn('errors', response)
        review_data = response['data']['createReviewRequest']['reviewRequest']
        review_id = review_data['id']
        self.assertEqual(review_data['status'], 'OPEN')
        self.assertEqual(review_data['playbook']['status'], 'REVIEW')

        # Verify playbook status in DB
        self.playbook_a.refresh_from_db()
        self.assertEqual(self.playbook_a.status, DetectionPlaybook.PlaybookStatus.REVIEW)

        # --- 2. Reviewer approves the review ---
        mutation_approve = """
        mutation {
            approveReview(reviewRequestId: "%s") {
                reviewRequest {
                    id
                    status
                }
            }
        }
        """ % review_id

        response = self.client.execute(
            mutation_approve,
            context_value=type('Context', (), {'user': self.reviewer})()
        )

        self.assertNotIn('errors', response)
        review_data = response['data']['approveReview']['reviewRequest']
        self.assertEqual(review_data['status'], 'APPROVED')

        # --- 3. Author closes review ---
        mutation_close = """
        mutation {
            closeReview(reviewRequestId: "%s") {
                playbook {
                    status
                }
            }
        }
        """ % review_id

        response = self.client.execute(
            mutation_close,
            context_value=type('Context', (), {'user': self.author})()
        )

        self.assertNotIn('errors', response)
        # --- THIS ASSERTION NOW CHECKS FOR APPROVED ---
        self.assertEqual(response['data']['closeReview']['playbook']['status'], "APPROVED")

        # Verify final state in DB
        self.playbook_a.refresh_from_db()
        # --- THIS ASSERTION NOW CHECKS FOR APPROVED ---
        self.assertEqual(self.playbook_a.status, DetectionPlaybook.PlaybookStatus.APPROVED)
        review_obj = ReviewRequest.objects.get(pk=review_id)
        self.assertEqual(review_obj.status, ReviewRequest.ReviewStatus.CLOSED)
