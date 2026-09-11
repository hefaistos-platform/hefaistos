import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from organizations.models import Organization

User = get_user_model()


class PainPoint(models.Model):
    """
    Pain Points (PAIN) - User feedback board for bugs, ideas, and complaints.
    Works like a sticky note board where users can report issues with the platform.
    Only admins/superadmins can mark as solved or closed.
    """
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]
    
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('SOLVED', 'Solved'),
        ('CLOSED', 'Closed'),
        ('ARCHIVED', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Author info (auto-filled when creating)
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pain_points_created'
    )
    
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='pain_points'
    )
    
    # Pain Point Content
    subject = models.CharField(
        max_length=80,
        help_text="Short description of the pain point (max 80 characters)"
    )
    
    description = models.TextField(
        max_length=2000,
        help_text="Detailed description of the issue, idea, or complaint"
    )
    
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='MEDIUM',
        help_text="Priority level: Low, Medium, or High"
    )
    
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='OPEN',
        help_text="Current status of the pain point"
    )
    
    # Resolution tracking
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pain_points_resolved'
    )
    
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the pain point was solved/closed"
    )
    
    resolution_notes = models.TextField(
        max_length=1000,
        blank=True,
        help_text="Admin notes on how the pain point was addressed"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['priority', 'status']),
            models.Index(fields=['author']),
        ]
    
    def __str__(self):
        return f"[{self.get_priority_display()}] {self.subject} - {self.get_status_display()}"
    
    def mark_as_solved(self, resolved_by_user, notes=''):
        """Mark this pain point as solved (only by admin/superadmin)"""
        self.status = 'SOLVED'
        self.resolved_by = resolved_by_user
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save()
    
    def mark_as_closed(self, resolved_by_user, notes=''):
        """Mark this pain point as closed without solution (only by admin/superadmin)"""
        self.status = 'CLOSED'
        self.resolved_by = resolved_by_user
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save()
    
    def archive(self):
        """Archive this pain point (moved to archive after being solved/closed)"""
        self.status = 'ARCHIVED'
        self.save()
    
    @property
    def is_solved(self):
        """Check if pain point is solved or closed"""
        return self.status in ['SOLVED', 'CLOSED']


class PainPointComment(models.Model):
    """
    Comments on pain points for additional context and discussion.
    Supports threaded/nested comments for conversation-style exchanges.
    Example: Admin asks "What part of portal?" and user replies in a thread.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    pain_point = models.ForeignKey(
        PainPoint,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    
    # Support for threaded comments (replies to comments)
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        help_text="Parent comment if this is a reply to another comment"
    )
    
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pain_point_comments'
    )
    
    content = models.TextField(max_length=1000)
    
    # Track if this comment addresses a question (useful for filtering unanswered questions)
    is_response_to_question = models.BooleanField(
        default=False,
        help_text="True if this comment is answering a question from admin"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['pain_point']),
            models.Index(fields=['author']),
            models.Index(fields=['parent_comment']),
            models.Index(fields=['pain_point', 'parent_comment']),
        ]
    
    def __str__(self):
        parent_info = f" (reply to {self.parent_comment.id})" if self.parent_comment else ""
        return f"Comment by {self.author.username} on {self.pain_point.subject}{parent_info}"
    
    @property
    def is_root_comment(self):
        """Check if this is a root-level comment (not a reply)"""
        return self.parent_comment is None
    
    @property
    def reply_count(self):
        """Get count of replies to this comment"""
        return self.replies.count()
