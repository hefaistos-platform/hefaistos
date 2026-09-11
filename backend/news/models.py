from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import uuid

User = get_user_model()


class NewsPost(models.Model):
    """
    Platform-wide news and announcements.
    Supports markdown content, rich categories, and auto-expiration.
    """
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent')
    ]
    
    CATEGORY_CHOICES = [
        ('UPDATE', '🔄 Platform Update'),
        ('OUTAGE', '⚠️ Planned Outage'),
        ('FEATURE', '🚀 New Feature'),
        ('MAINTENANCE', '🔧 Maintenance'),
        ('ANNOUNCEMENT', '📢 General Announcement'),
        ('SECURITY', '🔒 Security Advisory')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, blank=True, help_text="Optional title for the news post")
    content = models.TextField(max_length=500, help_text="News content (supports Markdown, max 500 chars)")
    
    author = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='news_posts'
    )
    
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='MEDIUM',
        help_text="Priority level of the announcement"
    )
    
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='ANNOUNCEMENT',
        help_text="Category with emoji icon"
    )
    
    is_published = models.BooleanField(
        default=False,
        help_text="Whether this post is visible to users"
    )
    
    is_pinned = models.BooleanField(
        default=False,
        help_text="Pinned posts appear at the top"
    )
    
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the post was published"
    )
    
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Post will auto-hide after this date (default: 180 days from publish)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_pinned', '-published_at', '-created_at']
        indexes = [
            models.Index(fields=['is_published', 'expires_at']),
            models.Index(fields=['published_at']),
        ]
    
    def __str__(self):
        return f"{self.get_category_display()}: {self.title or self.content[:50]}"
    
    def save(self, *args, **kwargs):
        # Auto-set published_at when first published
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
            # Auto-set expiration to 180 days if not specified
            if not self.expires_at:
                self.expires_at = timezone.now() + timedelta(days=180)
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if the post has expired"""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    @property
    def is_active(self):
        """Check if post is published and not expired"""
        return self.is_published and not self.is_expired()


class UserNewsRead(models.Model):
    """
    Tracks which news posts each user has read.
    Used to display unread count badge.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='read_news'
    )
    news_post = models.ForeignKey(
        NewsPost,
        on_delete=models.CASCADE,
        related_name='read_by_users'
    )
    read_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'news_post')
        indexes = [
            models.Index(fields=['user', 'read_at']),
        ]
        verbose_name = 'User News Read Status'
        verbose_name_plural = 'User News Read Statuses'
    
    def __str__(self):
        return f"{self.user.username} read {self.news_post.id} at {self.read_at}"


class NewsSettings(models.Model):
    """Singleton settings for News feature (digest toggles, schedule)."""
    id = models.PositiveIntegerField(primary_key=True, default=1, editable=False)
    digest_enabled = models.BooleanField(default=True)
    digest_day = models.CharField(
        max_length=10,
        default='MONDAY',
        help_text='Day of week for digest (MONDAY..SUNDAY)'
    )
    digest_hour = models.PositiveSmallIntegerField(
        default=8,
        help_text='Hour (UTC) to send digest (0-23)'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'News Settings'
        verbose_name_plural = 'News Settings'

    def __str__(self):
        return f"NewsSettings(enabled={self.digest_enabled}, {self.digest_day}@{self.digest_hour})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
