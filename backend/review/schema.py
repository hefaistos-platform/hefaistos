import graphene
from graphene_django import DjangoObjectType
from .models import ReviewRequest, ReviewComment
from playbooks.models import DetectionPlaybook
from identity.models import CustomUser
from identity.schema import UserType
from identity.decorators import role_required, Roles
from core.rabbitmq import publish_event

class ReviewCommentType(DjangoObjectType):
    # Alias to support frontend queries expecting `user`
    user = graphene.Field(UserType)

    class Meta:
        model = ReviewComment
        fields = ("id", "review_request", "author", "text", "created_at")

    def resolve_user(self, info):
        return getattr(self, 'author', None)

class ReviewRequestType(DjangoObjectType):
    # Define a resolver for the 'comments' related field
    comments = graphene.List(ReviewCommentType)
    # Bridge fields for legacy UI expectations (use snake_case so GraphQL exposes camelCase)
    playbook_id = graphene.UUID(source='playbook_id')

    class Meta:
        model = ReviewRequest
        fields = ("id", "playbook", "author", "reviewers", "organization", "status", "created_at", "updated_at")

    # Declare graph_id outside the class to avoid DjangoObjectType auto-resolution issues
    graph_id = graphene.Field(graphene.UUID)

    def resolve_comments(self, info):
        # self is the ReviewRequest instance
        return self.comments.all()

    def resolve_graph_id(self, info):
        # Map canonical playbook-based review to an associated graph (first, if any)
        # This is a computed field - ReviewRequest links to DetectionPlaybook, which links to PlaybookGraph
        try:
            if not hasattr(self, 'playbook') or self.playbook is None:
                return None
            graph = self.playbook.graphs.first()
            return graph.id if graph else None
        except Exception:
            return None


# --- Mutations ---
class CreateReviewRequest(graphene.Mutation):
    class Arguments:
        playbook_id = graphene.UUID(required=True)
        # reviewer_ids removed (auto-assignment now)

    review_request = graphene.Field(ReviewRequestType)

    class Meta:
        description = "Creates a new peer review request for a playbook (auto-assigns reviewers; sets playbook status to REVIEW)."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, playbook_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # Security: Ensure playbook belongs to user's org
        try:
            playbook = DetectionPlaybook.objects.get(pk=playbook_id, organization=user.organization)
        except DetectionPlaybook.DoesNotExist:
            raise Exception("Playbook not found or you do not have permission")

        # Prevent duplicate OPEN review
        if ReviewRequest.objects.filter(playbook=playbook, status=ReviewRequest.ReviewStatus.OPEN).exists():
            raise Exception("An open review request already exists for this playbook.")

        # Transition playbook status -> REVIEW
        playbook.status = DetectionPlaybook.PlaybookStatus.REVIEW
        playbook.save(update_fields=['status', 'updated_at'])

        # Create the review request
        review_request = ReviewRequest.objects.create(
            playbook=playbook,
            author=user,
            organization=user.organization,
            status=ReviewRequest.ReviewStatus.OPEN
        )

        # Auto-assign all other users in the org (exclude author).
        # NOTE: Role-based filtering omitted (no 'role' field present on CustomUser yet).
        auto_reviewers = CustomUser.objects.filter(
            organization=user.organization
        ).exclude(pk=user.pk)

        if auto_reviewers.exists():
            review_request.reviewers.set(auto_reviewers)

        # Notify Admin/Reviewer users in org about new review request
        try:
            publish_event('review.requested', {
                'event': 'review.requested',
                'organization_id': str(user.organization_id),
                'playbook_id': str(playbook.id),
                'review_request_id': str(review_request.id),
                'title': playbook.title,
                'author_username': getattr(user, 'username', None),
            })
        except Exception:
            pass

        return CreateReviewRequest(review_request=review_request)


# Add this class inside backend/review/schema.py
class AddReviewComment(graphene.Mutation):
    class Arguments:
        review_request_id = graphene.UUID(required=True)
        text = graphene.String(required=True)

    comment = graphene.Field(ReviewCommentType)

    class Meta:
        description = "Adds a comment to an OPEN review request (org-scoped)."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, review_request_id, text):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # --- Security Check 1: Get the review and verify org ownership
        try:
            review_request = ReviewRequest.objects.get(
                pk=review_request_id,
                organization=user.organization
            )
        except ReviewRequest.DoesNotExist:
            raise Exception("Review request not found or you do not have permission")

        # --- Business Logic: Can only comment on OPEN reviews
        if review_request.status != ReviewRequest.ReviewStatus.OPEN:
            raise Exception("This review request is not open and cannot be commented on.")

        # --- Create the Comment ---
        comment = ReviewComment.objects.create(
            review_request=review_request,
            author=user,
            text=text
        )

        # Notify review participants of new comment
        try:
            publish_event('review.comment_added', {
                'event': 'review.comment_added',
                'organization_id': str(user.organization_id),
                'playbook_id': str(review_request.playbook_id),
                'review_request_id': str(review_request.id),
                'author_username': getattr(user, 'username', None),
            })
        except Exception:
            pass

        return AddReviewComment(comment=comment)


# Add this class inside backend/review/schema.py
class ApproveReview(graphene.Mutation):
    class Arguments:
        review_request_id = graphene.UUID(required=True)

    review_request = graphene.Field(ReviewRequestType)

    class Meta:
        description = "Approves an OPEN review request (must be non-author; transitions review to APPROVED)."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, review_request_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # --- Security Check: Get the review and verify org ownership
        try:
            review_request = ReviewRequest.objects.get(
                pk=review_request_id,
                organization=user.organization
            )
        except ReviewRequest.DoesNotExist:
            raise Exception("Review request not found or you do not have permission")

        # --- Business Logic 1: Can only approve OPEN reviews
        if review_request.status != ReviewRequest.ReviewStatus.OPEN:
            raise Exception("This review is not open.")

        # --- Business Logic 2: Author cannot approve their own review
        if review_request.author == user:
            raise Exception("You cannot approve your own review request.")

        # --- Set the Status ---
        review_request.status = ReviewRequest.ReviewStatus.APPROVED
        review_request.save(update_fields=['status', 'updated_at'])

        # Notify owner that review was approved
        try:
            publish_event('review.approved', {
                'event': 'review.approved',
                'organization_id': str(user.organization_id),
                'playbook_id': str(review_request.playbook_id),
                'review_request_id': str(review_request.id),
            })
        except Exception:
            pass

        # Create a notification for the review author and send email (if opted-in)
        try:
            from django.contrib.contenttypes.models import ContentType
            from notifications.models import Notification
            ct = ContentType.objects.get_for_model(ReviewRequest)
            Notification.objects.create(
                recipient=review_request.author,
                actor=user,
                organization=user.organization,
                verb='Approved your review',
                object_id=str(review_request.id),
                content_type=ct,
            )
            # Email dispatch respecting preferences
            from core.email_service import get_email_service
            if getattr(review_request.author, 'email_notify_review_approved', False) and review_request.author.email:
                service = get_email_service(organization=user.organization)
                if service.is_configured():
                    from core.email_templates import login_link_text, login_link_html
                    playbook_title = getattr(review_request.playbook, 'title', str(review_request.playbook_id))
                    service.send_message(
                        to=[review_request.author.email],
                        subject='✅ Your Review Was Approved - HEFAISTOS',
                        text=f"""Hello {review_request.author.username},

Great news! Your review request has been approved.

Workbench: {playbook_title}
Approved by: {user.username}

{login_link_text()}

Best regards,
The HEFAISTOS Team""",
                        html=f"""<html><body>
<h2>✅ Review Approved!</h2>
<p>Hello <strong>{review_request.author.username}</strong>,</p>
<p>Great news! Your review request has been approved.</p>
<ul>
<li><strong>Workbench:</strong> {playbook_title}</li>
<li><strong>Approved by:</strong> {user.username}</li>
</ul>
{login_link_html()}
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
                    )
        except Exception:
            pass

        return ApproveReview(review_request=review_request)

    # Add this class inside backend/review/schema.py
class RequestChanges(graphene.Mutation):
    class Arguments:
        review_request_id = graphene.UUID(required=True)
        comment_text = graphene.String(required=True, description="Reason for requesting changes.")

    review_request = graphene.Field(ReviewRequestType)

    class Meta:
        description = "Requests changes on an OPEN review (must be non-author; sets status to CHANGES_REQUESTED and adds mandatory comment)."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, review_request_id, comment_text):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # --- Security Check: Get the review and verify org ownership
        try:
            review_request = ReviewRequest.objects.get(
                pk=review_request_id,
                organization=user.organization
            )
        except ReviewRequest.DoesNotExist:
            raise Exception("Review request not found or you do not have permission")

        # --- Business Logic 1: Can only act on OPEN reviews
        if review_request.status != ReviewRequest.ReviewStatus.OPEN:
            raise Exception("This review is not open.")

        # --- Business Logic 2: Author cannot request changes on their own review
        if review_request.author == user:
            raise Exception("You cannot request changes on your own review request.")

        # --- Set the Status ---
        review_request.status = ReviewRequest.ReviewStatus.CHANGES_REQUESTED
        review_request.save(update_fields=['status', 'updated_at'])

        # --- Add the required comment ---
        ReviewComment.objects.create(
            review_request=review_request,
            author=user,
            text=comment_text
        )

        # Notify owner that changes were requested
        try:
            publish_event('review.changes_requested', {
                'event': 'review.changes_requested',
                'organization_id': str(user.organization_id),
                'playbook_id': str(review_request.playbook_id),
                'review_request_id': str(review_request.id),
            })
        except Exception:
            pass

        return RequestChanges(review_request=review_request)


# Add this class inside backend/review/schema.py
class CloseReview(graphene.Mutation):
    class Arguments:
        review_request_id = graphene.UUID(required=True)

    # Return the updated playbook (lazy dotted path avoids import cycle)
    playbook = graphene.Field('playbooks.schema.PlaybookType')

    class Meta:
        description = "Closes an APPROVED review (author only) and moves playbook to APPROVED; marks review CLOSED."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, review_request_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # --- Security Check: Get the review and verify org ownership
        try:
            review_request = ReviewRequest.objects.select_related('playbook', 'author').get(
                pk=review_request_id,
                organization=user.organization
            )
        except ReviewRequest.DoesNotExist:
            raise Exception("Review request not found or you do not have permission")

        # --- Business Logic 1: Only the review author can close it
        if review_request.author != user:
            raise Exception("Only the author can close this review request.")

        # --- Business Logic 2: Can only close APPROVED reviews
        if review_request.status != ReviewRequest.ReviewStatus.APPROVED:
            raise Exception("This review must be approved before it can be closed.")

        # --- Action 1: Close the review
        review_request.status = ReviewRequest.ReviewStatus.CLOSED
        review_request.save(update_fields=['status', 'updated_at'])

        # --- Action 2: Update the playbook status (the main goal)
        playbook = review_request.playbook
        playbook.status = DetectionPlaybook.PlaybookStatus.APPROVED
        playbook.save(update_fields=['status', 'updated_at'])

        return CloseReview(playbook=playbook)


# Add this class inside backend/review/schema.py
class ReopenReview(graphene.Mutation):
    class Arguments:
        review_request_id = graphene.UUID(required=True)
        comment_text = graphene.String(required=False, description="Optional comment about what was changed.")

    review_request = graphene.Field(ReviewRequestType)

    class Meta:
        description = "Re-opens a CHANGES_REQUESTED review (author only) by setting status back to OPEN; optional comment prefixed with [REOPEN]."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, review_request_id, comment_text=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # --- Security Check: Get the review and verify org ownership
        try:
            review_request = ReviewRequest.objects.get(
                pk=review_request_id,
                organization=user.organization
            )
        except ReviewRequest.DoesNotExist:
            raise Exception("Review request not found or you do not have permission")

        # --- Business Logic 1: Only the review author can reopen it
        if review_request.author != user:
            raise Exception("Only the author can reopen this review request.")

        # --- Business Logic 2: Can only reopen 'CHANGES_REQUESTED' reviews
        if review_request.status != ReviewRequest.ReviewStatus.CHANGES_REQUESTED:
            raise Exception("This review is not in 'CHANGES_REQUESTED' state.")

        # --- Action: Set status back to OPEN
        review_request.status = ReviewRequest.ReviewStatus.OPEN
        review_request.save(update_fields=['status', 'updated_at'])

        # --- Optional: Add a comment
        if comment_text:
            ReviewComment.objects.create(
                review_request=review_request,
                author=user,
                text=f"[REOPEN] {comment_text}"
            )

        return ReopenReview(review_request=review_request)
# Add this Query class before the Mutation class
class Query(graphene.ObjectType):
    review_request = graphene.Field(
        ReviewRequestType,
        id=graphene.UUID(required=True),
        description="Retrieves a single review request by its ID."
    )

    playbook_reviews = graphene.List(
        ReviewRequestType,
        playbook_id=graphene.UUID(required=True),
        description="Retrieves all review requests for a specific playbook."
    )

    def resolve_review_request(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        try:
            # Security: Ensures user can only query reviews in their org
            return ReviewRequest.objects.get(pk=id, organization=user.organization)
        except ReviewRequest.DoesNotExist:
            return None

    def resolve_playbook_reviews(self, info, playbook_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # Security: Ensures user can only query reviews in their org
        return ReviewRequest.objects.filter(
            playbook_id=playbook_id,
            organization=user.organization
        ).order_by('-created_at')


# Root mutation for this app
class Mutation(graphene.ObjectType):
    create_review_request = CreateReviewRequest.Field()
    add_review_comment = AddReviewComment.Field()
    approve_review = ApproveReview.Field()
    request_changes = RequestChanges.Field()
    close_review = CloseReview.Field()
    reopen_review = ReopenReview.Field()
