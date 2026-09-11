import uuid
from django.db import models
from organizations.models import Organization
from identity.models import CustomUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="The user who will receive the notification"
    )

    actor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="actions",
        help_text="The user who triggered the notification (e.g., the author)"
    )

    verb = models.CharField(max_length=255, help_text="The action, e.g., 'submitted a review for'")
    read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    # --- Generic Foreign Key ---
    # This allows us to point to a Playbook, a Review, a Task, etc.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=36) # UUIDs are 36 chars
    target = GenericForeignKey('content_type', 'object_id')
    # --- End GFK ---

    def __str__(self):
        return f"Notification for {self.recipient.username}"

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['recipient', 'read']),
        ]
