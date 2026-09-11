import graphene
from graphene_django import DjangoObjectType
from django.core.exceptions import PermissionDenied
from django.utils import timezone
import logging

from .models import PainPoint, PainPointComment
from identity.decorators import role_required, Roles

logger = logging.getLogger(__name__)


class PainPointCommentType(DjangoObjectType):
    """GraphQL type for PainPointComment with thread support"""
    
    author_name = graphene.String()
    reply_count = graphene.Int()
    replies = graphene.List(lambda: PainPointCommentType)
    is_root_comment = graphene.Boolean()
    
    class Meta:
        model = PainPointComment
        fields = (
            'id', 'pain_point', 'parent_comment', 'author', 'content',
            'is_response_to_question', 'created_at', 'updated_at'
        )
    
    def resolve_author_name(self, info):
        return self.author.get_full_name() or self.author.username if self.author else 'Unknown'
    
    def resolve_reply_count(self, info):
        return self.reply_count
    
    def resolve_replies(self, info):
        return self.replies.all()
    
    def resolve_is_root_comment(self, info):
        return self.is_root_comment


class PainPointType(DjangoObjectType):
    """GraphQL type for PainPoint"""
    
    is_solved = graphene.Boolean()
    author_name = graphene.String()
    resolved_by_name = graphene.String()
    comments = graphene.List(PainPointCommentType)
    
    class Meta:
        model = PainPoint
        fields = (
            'id', 'author', 'organization', 'subject', 'description',
            'priority', 'status', 'resolved_by', 'resolved_at',
            'resolution_notes', 'created_at', 'updated_at'
        )
    
    def resolve_is_solved(self, info):
        return self.is_solved
    
    def resolve_author_name(self, info):
        return self.author.get_full_name() or self.author.username if self.author else 'Unknown'
    
    def resolve_resolved_by_name(self, info):
        return self.resolved_by.get_full_name() or self.resolved_by.username if self.resolved_by else None
    
    def resolve_comments(self, info):
        return self.comments.all()


# ==================== MUTATIONS ====================

class CreatePainPointMutation(graphene.Mutation):
    """Create a new pain point"""
    
    pain_point = graphene.Field(PainPointType)
    success = graphene.Boolean()
    message = graphene.String()
    
    class Arguments:
        subject = graphene.String(required=True)
        description = graphene.String(required=True)
        priority = graphene.String(required=True)
    
    def mutate(self, info, subject, description, priority):
        user = info.context.user
        
        # Check authentication
        if user.is_anonymous:
            return CreatePainPointMutation(
                pain_point=None,
                success=False,
                message='User must be authenticated to create a pain point'
            )

        if (getattr(user, 'role', '') or '').upper() == Roles.ELONE:
            return CreatePainPointMutation(
                pain_point=None,
                success=False,
                message='Read-only role: ElOne users cannot create pain points'
            )
        
        # Validate priority
        if priority not in ['LOW', 'MEDIUM', 'HIGH']:
            return CreatePainPointMutation(
                pain_point=None,
                success=False,
                message='Invalid priority. Must be LOW, MEDIUM, or HIGH'
            )
        
        # Validate subject length
        if len(subject) > 80:
            return CreatePainPointMutation(
                pain_point=None,
                success=False,
                message='Subject must be 80 characters or less'
            )
        
        try:
            pain_point = PainPoint.objects.create(
                author=user,
                organization=user.organization,
                subject=subject,
                description=description,
                priority=priority,
                status='OPEN'
            )
            
            logger.info(f"Pain point created: {pain_point.id} by {user.username}")
            
            return CreatePainPointMutation(
                pain_point=pain_point,
                success=True,
                message='Pain point created successfully'
            )
        except Exception as e:
            logger.error(f"Error creating pain point: {str(e)}")
            return CreatePainPointMutation(
                pain_point=None,
                success=False,
                message=f'Error creating pain point: {str(e)}'
            )


class ResolvePainPointMutation(graphene.Mutation):
    """Resolve (solve/close) a pain point - Admin only"""
    
    pain_point = graphene.Field(PainPointType)
    success = graphene.Boolean()
    message = graphene.String()
    
    class Arguments:
        pain_point_id = graphene.UUID(required=True)
        status = graphene.String(required=True)  # 'SOLVED' or 'CLOSED'
        resolution_notes = graphene.String()
    
    def mutate(self, info, pain_point_id, status, resolution_notes=''):
        user = info.context.user
        
        # Check authentication and admin status
        if user.is_anonymous:
            return ResolvePainPointMutation(
                pain_point=None,
                success=False,
                message='User must be authenticated'
            )
        
        if not (user.is_staff or user.is_superuser):
            return ResolvePainPointMutation(
                pain_point=None,
                success=False,
                message='Only admins can resolve pain points'
            )
        
        # Validate status
        if status not in ['SOLVED', 'CLOSED']:
            return ResolvePainPointMutation(
                pain_point=None,
                success=False,
                message='Invalid status. Must be SOLVED or CLOSED'
            )
        
        try:
            pain_point = PainPoint.objects.get(id=pain_point_id)
            
            if status == 'SOLVED':
                pain_point.mark_as_solved(user, resolution_notes)
            else:
                pain_point.mark_as_closed(user, resolution_notes)
            
            logger.info(f"Pain point {pain_point.id} marked as {status} by {user.username}")
            
            return ResolvePainPointMutation(
                pain_point=pain_point,
                success=True,
                message=f'Pain point marked as {status.lower()}'
            )
        except PainPoint.DoesNotExist:
            return ResolvePainPointMutation(
                pain_point=None,
                success=False,
                message='Pain point not found'
            )
        except Exception as e:
            logger.error(f"Error resolving pain point: {str(e)}")
            return ResolvePainPointMutation(
                pain_point=None,
                success=False,
                message=f'Error resolving pain point: {str(e)}'
            )


class ArchivePainPointMutation(graphene.Mutation):
    """Archive a resolved pain point - Admin only"""
    
    pain_point = graphene.Field(PainPointType)
    success = graphene.Boolean()
    message = graphene.String()
    
    class Arguments:
        pain_point_id = graphene.UUID(required=True)
    
    def mutate(self, info, pain_point_id):
        user = info.context.user
        
        # Check authentication and admin status
        if user.is_anonymous:
            return ArchivePainPointMutation(
                pain_point=None,
                success=False,
                message='User must be authenticated'
            )
        
        if not (user.is_staff or user.is_superuser):
            return ArchivePainPointMutation(
                pain_point=None,
                success=False,
                message='Only admins can archive pain points'
            )
        
        try:
            pain_point = PainPoint.objects.get(id=pain_point_id)
            
            if not pain_point.is_solved:
                return ArchivePainPointMutation(
                    pain_point=None,
                    success=False,
                    message='Only solved or closed pain points can be archived'
                )
            
            pain_point.archive()
            logger.info(f"Pain point {pain_point.id} archived by {user.username}")
            
            return ArchivePainPointMutation(
                pain_point=pain_point,
                success=True,
                message='Pain point archived successfully'
            )
        except PainPoint.DoesNotExist:
            return ArchivePainPointMutation(
                pain_point=None,
                success=False,
                message='Pain point not found'
            )
        except Exception as e:
            logger.error(f"Error archiving pain point: {str(e)}")
            return ArchivePainPointMutation(
                pain_point=None,
                success=False,
                message=f'Error archiving pain point: {str(e)}'
            )


class AddPainPointCommentMutation(graphene.Mutation):
    """Add a comment or reply to a pain point (with thread support)"""
    
    comment = graphene.Field(PainPointCommentType)
    success = graphene.Boolean()
    message = graphene.String()
    
    class Arguments:
        pain_point_id = graphene.UUID(required=True)
        content = graphene.String(required=True)
        parent_comment_id = graphene.UUID(required=False, description="ID of parent comment if replying to a comment")
        is_response_to_question = graphene.Boolean(
            required=False,
            default_value=False,
            description="Set to True if this comment answers an admin question"
        )
    
    def mutate(self, info, pain_point_id, content, parent_comment_id=None, is_response_to_question=False):
        user = info.context.user
        
        if user.is_anonymous:
            return AddPainPointCommentMutation(
                comment=None,
                success=False,
                message='User must be authenticated'
            )

        if (getattr(user, 'role', '') or '').upper() == Roles.ELONE:
            return AddPainPointCommentMutation(
                comment=None,
                success=False,
                message='Read-only role: ElOne users cannot add comments'
            )
        
        try:
            pain_point = PainPoint.objects.get(id=pain_point_id)
            
            # If replying to a comment, validate parent exists
            parent_comment = None
            if parent_comment_id:
                try:
                    parent_comment = PainPointComment.objects.get(id=parent_comment_id)
                    if parent_comment.pain_point.id != pain_point_id:
                        return AddPainPointCommentMutation(
                            comment=None,
                            success=False,
                            message='Parent comment does not belong to this pain point'
                        )
                except PainPointComment.DoesNotExist:
                    return AddPainPointCommentMutation(
                        comment=None,
                        success=False,
                        message='Parent comment not found'
                    )
            
            comment = PainPointComment.objects.create(
                pain_point=pain_point,
                author=user,
                content=content,
                parent_comment=parent_comment,
                is_response_to_question=is_response_to_question
            )
            
            comment_type = "reply" if parent_comment else "comment"
            logger.info(f"{comment_type.capitalize()} added to pain point {pain_point.id} by {user.username}")
            
            return AddPainPointCommentMutation(
                comment=comment,
                success=True,
                message=f'{comment_type.capitalize()} added successfully'
            )
        except PainPoint.DoesNotExist:
            return AddPainPointCommentMutation(
                comment=None,
                success=False,
                message='Pain point not found'
            )
        except Exception as e:
            logger.error(f"Error adding comment: {str(e)}")
            return AddPainPointCommentMutation(
                comment=None,
                success=False,
                message=f'Error adding comment: {str(e)}'
            )


# ==================== QUERIES ====================

class Query(graphene.ObjectType):
    """Pain Points queries"""
    
    all_pain_points = graphene.List(
        PainPointType,
        limit=graphene.Int(default_value=50),
        offset=graphene.Int(default_value=0),
        status=graphene.String(),
        priority=graphene.String(),
        include_archived=graphene.Boolean(default_value=False),
        description="Get all pain points platform-wide (excludes archived by default)"
    )
    
    pain_point = graphene.Field(
        PainPointType,
        id=graphene.UUID(required=True),
        description="Get a single pain point by ID"
    )
    
    pain_points_by_priority = graphene.List(
        PainPointType,
        priority=graphene.String(required=True),
        description="Get pain points filtered by priority"
    )
    
    open_pain_points_count = graphene.Int(
        description="Count of open pain points platform-wide"
    )
    
    def resolve_all_pain_points(self, info, limit=50, offset=0, status=None, priority=None, include_archived=False):
        user = info.context.user
        
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        
        # Platform-wide: return pain points from all organizations
        queryset = PainPoint.objects.all()
        
        # Exclude archived by default
        if not include_archived:
            queryset = queryset.exclude(status='ARCHIVED')
        
        # Filter by status if provided
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by priority if provided
        if priority:
            queryset = queryset.filter(priority=priority)
        
        return queryset[offset:offset + limit]
    
    def resolve_pain_point(self, info, id):
        user = info.context.user
        
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        
        try:
            # Platform-wide: any authenticated user can read any pain point
            return PainPoint.objects.get(id=id)
        except PainPoint.DoesNotExist:
            return None
    
    def resolve_pain_points_by_priority(self, info, priority):
        user = info.context.user
        
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        
        if priority not in ['LOW', 'MEDIUM', 'HIGH']:
            raise Exception("Invalid priority")
        
        # Platform-wide: return pain points from all organizations filtered by priority
        return PainPoint.objects.filter(
            priority=priority
        ).exclude(status='ARCHIVED')
    
    def resolve_open_pain_points_count(self, info):
        user = info.context.user
        
        if user.is_anonymous:
            return 0
        
        # Platform-wide: count all open pain points across all organizations
        return PainPoint.objects.filter(
            status='OPEN'
        ).count()
    
    pain_points_with_pending_questions = graphene.List(
        PainPointType,
        description="Get pain points that have unanswered admin questions (requires admin role)"
    )
    
    def resolve_pain_points_with_pending_questions(self, info):
        user = info.context.user
        
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        
        # Only admins can see pending questions report
        if not (user.is_admin or user.is_superuser):
            raise Exception("Permission denied. Admin role required.")
        
        # Find pain points where there are comments without responses
        # i.e., comments without parent that have no is_response_to_question=True children
        from django.db.models import Q, Exists, OuterRef
        
        # Platform-wide: find open pain points that have unanswered admin questions across all orgs
        pain_points_with_questions = PainPoint.objects.filter(
            status='OPEN'
        ).exclude(status='ARCHIVED').filter(
            comments__parent_comment__isnull=True,
            comments__author__is_staff=True
        ).distinct()
        
        return pain_points_with_questions


# ==================== MUTATIONS SCHEMA ====================

class Mutation(graphene.ObjectType):
    """Pain Points mutations"""
    create_pain_point = CreatePainPointMutation.Field()
    resolve_pain_point = ResolvePainPointMutation.Field()
    archive_pain_point = ArchivePainPointMutation.Field()
    add_pain_point_comment = AddPainPointCommentMutation.Field()
