import uuid
from django.db import models
from organizations.models import Organization
from identity.models import CustomUser
from playbooks.models import DetectionPlaybook

class ReviewRequest(models.Model):
    class ReviewStatus(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        APPROVED = 'APPROVED', 'Approved'
        CHANGES_REQUESTED = 'CHANGES_REQUESTED', 'Changes Requested'
        CLOSED = 'CLOSED', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    playbook = models.ForeignKey(
        DetectionPlaybook,
        on_delete=models.CASCADE,
        related_name="review_requests",
        help_text="The playbook being reviewed"
    )

    author = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="authored_review_requests",
        help_text="The user who requested the review"
    )

    reviewers = models.ManyToManyField(
        CustomUser,
        related_name="review_assignments",
        help_text="Users assigned to perform the review"
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="review_requests"
    )

    status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.OPEN
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review for '{self.playbook.title}' ({self.status})"

class ReviewComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    review_request = models.ForeignKey(
        ReviewRequest,
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="The review request this comment belongs to"
    )

    author = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="review_comments",
        help_text="The user who wrote the comment"
    )

    text = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Comment by {self.author.username} on {self.review_request.id}"

    class Meta:
        ordering = ['created_at'] # Show oldest comments first
