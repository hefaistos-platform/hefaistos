import graphene
from graphene_django import DjangoObjectType
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta
import logging

from .models import NewsPost, UserNewsRead, NewsSettings
from identity.decorators import role_required, Roles, is_bot_auditor_user
from core.rabbitmq import publish_event

logger = logging.getLogger(__name__)


class NewsPostType(DjangoObjectType):
    """GraphQL type for NewsPost"""
    
    is_active = graphene.Boolean()
    is_expired = graphene.Boolean()
    is_read = graphene.Boolean()
    
    class Meta:
        model = NewsPost
        fields = (
            'id', 'title', 'content', 'author', 'priority', 'category',
            'is_published', 'is_pinned', 'published_at', 'expires_at',
            'created_at', 'updated_at'
        )
    
    def resolve_is_active(self, info):
        return self.is_active
    
    def resolve_is_expired(self, info):
        return self.is_expired()
    
    def resolve_is_read(self, info):
        """Check if current user has read this post"""
        user = info.context.user
        if user.is_anonymous:
            return False
        return UserNewsRead.objects.filter(user=user, news_post=self).exists()


class UserNewsReadType(DjangoObjectType):
    """GraphQL type for UserNewsRead"""
    
    class Meta:
        model = UserNewsRead
        fields = ('id', 'user', 'news_post', 'read_at')


# ==================== QUERIES ====================

class Query(graphene.ObjectType):
    all_news = graphene.List(
        NewsPostType,
        limit=graphene.Int(default_value=50),
        offset=graphene.Int(default_value=0),
        category=graphene.String(),
        include_expired=graphene.Boolean(default_value=False),
        include_unpublished=graphene.Boolean(default_value=False),
        description="Get news posts (optionally include drafts for admins)"
    )
    
    news_post = graphene.Field(
        NewsPostType,
        id=graphene.UUID(required=True),
        description="Get a single news post by ID"
    )
    
    unread_news_count = graphene.Int(
        description="Count of unread news posts for current user"
    )
    
    pinned_news = graphene.List(
        NewsPostType,
        description="Get all pinned news posts"
    )

    news_settings = graphene.Field(
        graphene.JSONString,
        description="Get digest settings (enabled, day, hour)"
    )
    
    def resolve_all_news(self, info, limit=50, offset=0, category=None, include_expired=False, include_unpublished=False):
        """Get news posts; admins can request drafts via include_unpublished"""
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # Allow admins to list drafts for management; others stay limited to published posts
        if include_unpublished:
            if getattr(user, 'role', None) != Roles.ADMIN and not is_bot_auditor_user(user):
                raise PermissionDenied("Admin role required to view unpublished news")
            qs = NewsPost.objects.all()
        else:
            qs = NewsPost.objects.filter(is_published=True)
        
        # Filter out expired unless requested
        if not include_expired:
            now = timezone.now()
            qs = qs.filter(
                models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
            )
        
        # Filter by category if specified
        if category:
            qs = qs.filter(category=category)
        
        # Order by pinned first, then by published date
        qs = qs.order_by('-is_pinned', '-published_at')
        
        return qs[offset:offset + limit]
    
    def resolve_news_post(self, info, id):
        """Get a single news post"""
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        try:
            return NewsPost.objects.get(pk=id, is_published=True)
        except NewsPost.DoesNotExist:
            raise Exception("News post not found")
    
    def resolve_unread_news_count(self, info):
        """Count unread news for current user"""
        user = info.context.user
        if user.is_anonymous:
            return 0
        
        # Get all active published posts
        now = timezone.now()
        active_posts = NewsPost.objects.filter(
            is_published=True
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )
        
        # Get IDs of posts user has read
        read_post_ids = UserNewsRead.objects.filter(
            user=user
        ).values_list('news_post_id', flat=True)
        
        # Count posts not in read list
        unread_count = active_posts.exclude(id__in=read_post_ids).count()
        
        return unread_count
    
    def resolve_pinned_news(self, info):
        """Get all pinned news posts"""
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        now = timezone.now()
        return NewsPost.objects.filter(
            is_published=True,
            is_pinned=True
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )

    def resolve_news_settings(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        settings = NewsSettings.get_solo()
        return {
            'digestEnabled': settings.digest_enabled,
            'digestDay': settings.digest_day,
            'digestHour': settings.digest_hour,
        }


# ==================== MUTATIONS ====================

class CreateNewsPost(graphene.Mutation):
    """Create a new news post (Admin only)"""
    
    class Arguments:
        title = graphene.String()
        content = graphene.String(required=True)
        priority = graphene.String(default_value='MEDIUM')
        category = graphene.String(default_value='ANNOUNCEMENT')
        is_pinned = graphene.Boolean(default_value=False)
        expires_at = graphene.DateTime()
    
    news_post = graphene.Field(NewsPostType)
    success = graphene.Boolean()
    message = graphene.String()
    
    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, content, title='', priority='MEDIUM', category='ANNOUNCEMENT', is_pinned=False, expires_at=None):
        user = info.context.user
        
        # Validate content length
        if len(content) > 500:
            return CreateNewsPost(
                news_post=None,
                success=False,
                message="Content must be 500 characters or less"
            )
        
        # Create news post as draft
        news_post = NewsPost.objects.create(
            title=title,
            content=content,
            author=user,
            priority=priority,
            category=category,
            is_pinned=is_pinned,
            is_published=False,  # Start as draft
            expires_at=expires_at
        )
        
        logger.info(f"Admin {user.username} created news post {news_post.id}")
        
        return CreateNewsPost(
            news_post=news_post,
            success=True,
            message="News post created as draft"
        )


class UpdateNewsPost(graphene.Mutation):
    """Update an existing news post (Admin only)"""
    
    class Arguments:
        id = graphene.UUID(required=True)
        title = graphene.String()
        content = graphene.String()
        priority = graphene.String()
        category = graphene.String()
        is_pinned = graphene.Boolean()
        expires_at = graphene.DateTime()
    
    news_post = graphene.Field(NewsPostType)
    success = graphene.Boolean()
    message = graphene.String()
    
    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id, **kwargs):
        user = info.context.user
        
        try:
            news_post = NewsPost.objects.get(pk=id)
        except NewsPost.DoesNotExist:
            return UpdateNewsPost(
                news_post=None,
                success=False,
                message="News post not found"
            )
        
        # Update fields
        if 'title' in kwargs:
            news_post.title = kwargs['title']
        if 'content' in kwargs:
            if len(kwargs['content']) > 500:
                return UpdateNewsPost(
                    news_post=None,
                    success=False,
                    message="Content must be 500 characters or less"
                )
            news_post.content = kwargs['content']
        if 'priority' in kwargs:
            news_post.priority = kwargs['priority']
        if 'category' in kwargs:
            news_post.category = kwargs['category']
        if 'is_pinned' in kwargs:
            news_post.is_pinned = kwargs['is_pinned']
        if 'expires_at' in kwargs:
            news_post.expires_at = kwargs['expires_at']
        
        news_post.save()
        
        logger.info(f"Admin {user.username} updated news post {news_post.id}")
        
        return UpdateNewsPost(
            news_post=news_post,
            success=True,
            message="News post updated"
        )


class PublishNewsPost(graphene.Mutation):
    """Publish a news post (Admin only) - triggers RabbitMQ event"""
    
    class Arguments:
        id = graphene.UUID(required=True)
    
    news_post = graphene.Field(NewsPostType)
    success = graphene.Boolean()
    message = graphene.String()
    
    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        
        try:
            news_post = NewsPost.objects.get(pk=id)
        except NewsPost.DoesNotExist:
            return PublishNewsPost(
                news_post=None,
                success=False,
                message="News post not found"
            )
        
        if news_post.is_published:
            return PublishNewsPost(
                news_post=news_post,
                success=False,
                message="News post is already published"
            )
        
        # Publish the post
        news_post.is_published = True
        news_post.save()  # Auto-sets published_at and expires_at in model save()
        
        # Publish RabbitMQ event
        try:
            publish_event('news.published', {
                'event': 'news.published',
                'news_id': str(news_post.id),
                'title': news_post.title,
                'content': news_post.content,
                'priority': news_post.priority,
                'category': news_post.category,
                'author_username': user.username,
                'published_at': news_post.published_at.isoformat() if news_post.published_at else None
            })
            logger.info(f"Published RabbitMQ event for news post {news_post.id}")
        except Exception as e:
            logger.error(f"Failed to publish RabbitMQ event for news {news_post.id}: {e}")
        
        # Send email notification to users who have opted in for system messages
        try:
            from core.email_service import get_email_service
            from identity.models import CustomUser
            
            service = get_email_service()
            if service.is_configured():
                # Get users who want system message emails
                recipients = CustomUser.objects.filter(
                    email_notify_system_message=True,
                    email__isnull=False
                ).exclude(email='')
                
                recipient_emails = list(recipients.values_list('email', flat=True))
                
                if recipient_emails:
                    priority_emoji = {'LOW': '📋', 'NORMAL': '📰', 'HIGH': '⚠️', 'CRITICAL': '🚨'}.get(news_post.priority, '📰')
                    category_label = news_post.category or 'Announcement'
                    
                    service.send_message(
                        to=recipient_emails,
                        subject=f'{priority_emoji} [{category_label}] {news_post.title}',
                        text=f"""New announcement from HEFAISTOS

{news_post.title}

{news_post.content}

---
Priority: {news_post.priority}
Category: {category_label}
Published by: {user.username}
""",
                        html=f"""<html><body>
<h2>{priority_emoji} {news_post.title}</h2>
<p><em>Priority: {news_post.priority} | Category: {category_label} | Published by: {user.username}</em></p>
<hr/>
<div>{news_post.content}</div>
<hr/>
<p style="color: #666; font-size: 12px;">You are receiving this because you opted in for system message notifications. 
You can change this in your profile settings.</p>
</body></html>""",
                        hide_recipients=True,
                    )
                    logger.info(f"Sent news notification to {len(recipient_emails)} users for news post {news_post.id}")
        except Exception as e:
            logger.error(f"Failed to send news notification emails for {news_post.id}: {e}")
        
        logger.info(f"Admin {user.username} published news post {news_post.id}")
        
        return PublishNewsPost(
            news_post=news_post,
            success=True,
            message="News post published successfully"
        )


class UnpublishNewsPost(graphene.Mutation):
    """Unpublish a news post (Admin only)"""
    
    class Arguments:
        id = graphene.UUID(required=True)
    
    news_post = graphene.Field(NewsPostType)
    success = graphene.Boolean()
    message = graphene.String()
    
    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        
        try:
            news_post = NewsPost.objects.get(pk=id)
        except NewsPost.DoesNotExist:
            return UnpublishNewsPost(
                news_post=None,
                success=False,
                message="News post not found"
            )
        
        news_post.is_published = False
        news_post.save()
        
        logger.info(f"Admin {user.username} unpublished news post {news_post.id}")
        
        return UnpublishNewsPost(
            news_post=news_post,
            success=True,
            message="News post unpublished"
        )


class DeleteNewsPost(graphene.Mutation):
    """Delete a news post (Admin only)"""
    
    class Arguments:
        id = graphene.UUID(required=True)
    
    success = graphene.Boolean()
    message = graphene.String()
    
    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        
        try:
            news_post = NewsPost.objects.get(pk=id)
            news_post.delete()
            logger.info(f"Admin {user.username} deleted news post {id}")
            return DeleteNewsPost(success=True, message="News post deleted")
        except NewsPost.DoesNotExist:
            return DeleteNewsPost(success=False, message="News post not found")


class MarkNewsAsRead(graphene.Mutation):
    """Mark a single news post as read"""
    
    class Arguments:
        news_id = graphene.UUID(required=True)
    
    success = graphene.Boolean()
    message = graphene.String()
    unread_count = graphene.Int()
    
    @staticmethod
    def mutate(root, info, news_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        try:
            news_post = NewsPost.objects.get(pk=news_id, is_published=True)
        except NewsPost.DoesNotExist:
            return MarkNewsAsRead(
                success=False,
                message="News post not found",
                unread_count=0
            )
        
        # Create read record (unique constraint prevents duplicates)
        UserNewsRead.objects.get_or_create(
            user=user,
            news_post=news_post
        )
        
        # Calculate new unread count
        now = timezone.now()
        active_posts = NewsPost.objects.filter(
            is_published=True
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )
        read_post_ids = UserNewsRead.objects.filter(user=user).values_list('news_post_id', flat=True)
        unread_count = active_posts.exclude(id__in=read_post_ids).count()
        
        return MarkNewsAsRead(
            success=True,
            message="News marked as read",
            unread_count=unread_count
        )


class MarkAllNewsAsRead(graphene.Mutation):
    """Mark all active news posts as read"""
    
    success = graphene.Boolean()
    message = graphene.String()
    marked_count = graphene.Int()
    
    @staticmethod
    def mutate(root, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        # Get all active published posts
        now = timezone.now()
        active_posts = NewsPost.objects.filter(
            is_published=True
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )
        
        # Get posts user hasn't read
        read_post_ids = UserNewsRead.objects.filter(user=user).values_list('news_post_id', flat=True)
        unread_posts = active_posts.exclude(id__in=read_post_ids)
        
        # Bulk create read records
        read_records = [
            UserNewsRead(user=user, news_post=post)
            for post in unread_posts
        ]
        UserNewsRead.objects.bulk_create(read_records, ignore_conflicts=True)
        
        count = len(read_records)
        logger.info(f"User {user.username} marked {count} news posts as read")
        
        return MarkAllNewsAsRead(
            success=True,
            message=f"Marked {count} news posts as read",
            marked_count=count
        )


class Mutation(graphene.ObjectType):
    create_news_post = CreateNewsPost.Field()
    update_news_post = UpdateNewsPost.Field()
    publish_news_post = PublishNewsPost.Field()
    unpublish_news_post = UnpublishNewsPost.Field()
    delete_news_post = DeleteNewsPost.Field()
    mark_news_as_read = MarkNewsAsRead.Field()
    mark_all_news_as_read = MarkAllNewsAsRead.Field()

    # Settings mutations
    set_news_settings = graphene.Field(
        graphene.JSONString,
        digest_enabled=graphene.Boolean(required=True),
        digest_day=graphene.String(),
        digest_hour=graphene.Int(),
        description="Update digest settings"
    )

    send_news_digest = graphene.Field(
        graphene.Boolean,
        limit=graphene.Int(default_value=20),
        description="Trigger sending the news digest now"
    )

    @staticmethod
    @role_required([Roles.ADMIN])
    def resolve_set_news_settings(root, info, digest_enabled, digest_day=None, digest_hour=None):
        settings = NewsSettings.get_solo()
        settings.digest_enabled = digest_enabled
        if digest_day:
            settings.digest_day = digest_day.upper()
        if digest_hour is not None:
            settings.digest_hour = digest_hour
        settings.save()
        return {
            'digestEnabled': settings.digest_enabled,
            'digestDay': settings.digest_day,
            'digestHour': settings.digest_hour,
        }

    @staticmethod
    @role_required([Roles.ADMIN])
    def resolve_send_news_digest(root, info, limit=20):
        from django.core.management import call_command
        try:
            call_command('send_news_digest', limit=limit)
            return True
        except Exception as e:
            logger.error(f"Error sending digest on-demand: {e}")
            return False


# Import Django models for Q queries
from django.db import models
