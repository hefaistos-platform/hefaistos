import graphene
from graphene_django import DjangoObjectType
from .models import Notification
from playbooks.schema import PlaybookType, PlaybookGraphType
from review.schema import ReviewRequestType
from identity.schema import UserType
from identity.models import CustomUser
from organizations.models import Organization
from playbooks.models import DetectionPlaybook
from django.contrib.contenttypes.models import ContentType
from identity.decorators import role_required, Roles

# --- A Union Type ---
# This tells GraphQL that the 'target' field can be one of several types.
class NotificationTargetType(graphene.Union):
	class Meta:
		types = (PlaybookType, PlaybookGraphType, ReviewRequestType)  # Added PlaybookGraphType


class NotificationType(DjangoObjectType):
	# We must override the 'target' field to use our Union
	target = graphene.Field(NotificationTargetType)
	# We must also override 'actor' to use the UserType
	actor = graphene.Field(UserType)

	class Meta:
		model = Notification
		fields = (
			"id",
			"recipient",
			"actor",
			"verb",
			"read",
			"timestamp",
			"target",
			"content_type",
			"object_id",
		)


# --- QUERIES ---
class Query(graphene.ObjectType):
	my_notifications = graphene.List(
		NotificationType,
		description="Retrieves all notifications for the logged-in user."
	)
	unread_notification_count = graphene.Int(
		description="Retrieves the count of unread notifications for the logged-in user."
	)

	def resolve_my_notifications(self, info):
		user = info.context.user
		if user.is_anonymous:
			raise Exception("Authentication credentials were not provided")

		# Use select_related to optimize the query
		return Notification.objects.filter(
			recipient=user,
			organization=user.organization
		).select_related('actor', 'content_type')

	def resolve_unread_notification_count(self, info):
		user = info.context.user
		if user.is_anonymous:
			return 0

		return Notification.objects.filter(
			recipient=user,
			organization=user.organization,
			read=False
		).count()


# --- MUTATIONS ---
class MarkNotificationAsRead(graphene.Mutation):
	class Arguments:
		id = graphene.UUID(required=True)

	notification = graphene.Field(NotificationType)

	class Meta:
		description = "Marks a single notification as read."

	@staticmethod
	@role_required([Roles.ADMIN, Roles.ANALYST])
	def mutate(root, info, id):
		user = info.context.user
		if user.is_anonymous:
			raise Exception("Authentication credentials were not provided")

		try:
			# Security Check: User can only mark their own notifications as read
			notification = Notification.objects.get(pk=id, recipient=user)
		except Notification.DoesNotExist:
			raise Exception("Notification not found or you do not have permission")

		notification.read = True
		notification.save(update_fields=['read'])

		return MarkNotificationAsRead(notification=notification)


class MarkAllNotificationsAsRead(graphene.Mutation):
	ok = graphene.Boolean()

	class Meta:
		description = "Marks all of the user's notifications as read."

	@staticmethod
	@role_required([Roles.ADMIN, Roles.ANALYST])
	def mutate(root, info):
		user = info.context.user
		if user.is_anonymous:
			raise Exception("Authentication credentials were not provided")

		Notification.objects.filter(recipient=user, read=False).update(read=True)
		return MarkAllNotificationsAsRead(ok=True)


class CreateNotification(graphene.Mutation):
	class Arguments:
		recipient_id = graphene.ID(required=True)
		actor_id = graphene.ID(required=True)
		organization_id = graphene.UUID(required=True)
		verb = graphene.String(required=True)
		object_id = graphene.String(required=True)
		content_type = graphene.String(required=True, description="e.g., 'playbook'")

	notification = graphene.Field(NotificationType)

	class Meta:
		description = "Creates a new notification. (Used by internal services)"

	@staticmethod
	def mutate(root, info, recipient_id, actor_id, organization_id, verb, object_id, content_type):
		import logging
		logger = logging.getLogger(__name__)
		
		logger.info(f"[CreateNotification] Called with recipient_id={recipient_id}, actor_id={actor_id}, "
		            f"org_id={organization_id}, verb='{verb}', object_id={object_id}, content_type={content_type}")
		
		# Check authentication context
		user = info.context.user
		logger.info(f"[CreateNotification] Context user: {user}, is_anonymous: {user.is_anonymous if hasattr(user, 'is_anonymous') else 'N/A'}")
		
		# Service-to-service call; assumed trusted, but log if anonymous
		if hasattr(user, 'is_anonymous') and user.is_anonymous:
			logger.warning("[CreateNotification] Request made by anonymous user - may indicate auth issue")
		
		try:
			recipient = CustomUser.objects.get(pk=recipient_id)
			logger.info(f"[CreateNotification] Found recipient: {recipient.username} (id={recipient.id})")
			
			actor = CustomUser.objects.get(pk=actor_id)
			logger.info(f"[CreateNotification] Found actor: {actor.username} (id={actor.id})")
			
			organization = Organization.objects.get(pk=organization_id)
			logger.info(f"[CreateNotification] Found organization: {organization.name} (id={organization.id})")

			target_model = None
			ct_lower = content_type.lower()
			if ct_lower == 'playbook':
				target_model = ContentType.objects.get_for_model(DetectionPlaybook)
			elif ct_lower == 'playbookgraph':
				from playbooks.models import PlaybookGraph
				target_model = ContentType.objects.get_for_model(PlaybookGraph)
			elif ct_lower == 'reviewrequest':
				from review.models import ReviewRequest
				target_model = ContentType.objects.get_for_model(ReviewRequest)
			elif ct_lower == 'system':
				# System-wide message, associate with Organization for scoping
				target_model = ContentType.objects.get_for_model(Organization)
				object_id = str(organization_id)
			elif ct_lower == 'chat':
				# Chat message - associate with recipient (user) for simplicity
				target_model = ContentType.objects.get_for_model(CustomUser)
				object_id = str(recipient.id)
			else:
				logger.error(f"[CreateNotification] Invalid content_type: {content_type}")
				raise Exception(f"Invalid content_type: {content_type}")

			# Ensure target object exists
			target_exists = target_model.model_class().objects.filter(pk=object_id).exists()
			logger.info(f"[CreateNotification] Target object exists: {target_exists} (model={target_model.model}, pk={object_id})")
			if not target_exists:
				raise Exception("Target object not found")

			notification = Notification.objects.create(
				recipient=recipient,
				actor=actor,
				organization=organization,
				verb=verb,
				object_id=object_id,
				content_type=target_model
			)
			logger.info(f"[CreateNotification] SUCCESS - Created notification id={notification.id}")
			# --- Email Dispatch (optional, respects user preferences) ---
			try:
				from core.email_service import get_email_service
				service = get_email_service(organization=organization)
				
				# Skip if email service not configured
				if not service.is_configured():
					logger.info("[CreateNotification] Email service not configured, skipping email dispatch")
				else:
					from core.email_templates import login_link_text, login_link_html
					# Determine preference based on type
					should_email = False
					subject = ""
					text_body = ""
					html_body = ""

					if ct_lower == 'reviewrequest':
						should_email = bool(getattr(recipient, 'email_notify_review_approved', False)) and 'approved' in verb.lower()
						subject = "✅ Your Review Was Approved - HEFAISTOS"
						text_body = f"""Hello {recipient.username},

Your review request has been approved.

Details: {verb}

{login_link_text()}

Best regards,
The HEFAISTOS Team"""
						html_body = f"""<html><body>
<h2>✅ Review Approved</h2>
<p>Hello <strong>{recipient.username}</strong>,</p>
<p>Your review request has been approved.</p>
<p><strong>Details:</strong> {verb}</p>
{login_link_html()}
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
					elif ct_lower == 'system':
						should_email = bool(getattr(recipient, 'email_notify_system_message', False))
						subject = "📢 New System Message - HEFAISTOS"
						text_body = f"""Hello {recipient.username},

You have a new system message:

{verb}

{login_link_text()}

Best regards,
The HEFAISTOS Team"""
						html_body = f"""<html><body>
<h2>📢 System Message</h2>
<p>Hello <strong>{recipient.username}</strong>,</p>
<p>You have a new system message:</p>
<blockquote>{verb}</blockquote>
{login_link_html()}
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
					elif ct_lower == 'chat':
						actor_name = getattr(actor, 'username', 'Someone')
						should_email = bool(getattr(recipient, 'email_notify_chat_message', False))
						subject = f"💬 New Chat Message from {actor_name} - HEFAISTOS"
						text_body = f"""Hello {recipient.username},

{actor_name} sent you a new chat message:

{verb}

{login_link_text()}

Best regards,
The HEFAISTOS Team"""
						html_body = f"""<html><body>
<h2>💬 New Chat Message</h2>
<p>Hello <strong>{recipient.username}</strong>,</p>
<p><strong>{actor_name}</strong> sent you a new chat message:</p>
<blockquote>{verb}</blockquote>
{login_link_html()}
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
					elif ct_lower == 'playbookgraph':
						actor_name = getattr(actor, 'username', 'Someone')
						should_email = bool(getattr(recipient, 'email_notify_workbench_edited', False))
						subject = f"📝 Workbench Updated - HEFAISTOS"
						text_body = f"""Hello {recipient.username},

{actor_name} performed an action on your workbench:

{verb}

{login_link_text()}

Best regards,
The HEFAISTOS Team"""
						html_body = f"""<html><body>
<h2>📝 Workbench Updated</h2>
<p>Hello <strong>{recipient.username}</strong>,</p>
<p><strong>{actor_name}</strong> performed an action on your workbench:</p>
<blockquote>{verb}</blockquote>
{login_link_html()}
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""

					if should_email and recipient.email:
						service.send_message(
							to=[recipient.email],
							subject=subject,
							text=text_body,
							html=html_body,
						)
			except Exception as e:
				logger.error(f"[CreateNotification] Email dispatch failed: {e}")

			return CreateNotification(notification=notification)

		except CustomUser.DoesNotExist as e:
			logger.error(f"[CreateNotification] User not found: {e}")
			raise Exception(f"Failed to create notification: User not found - recipient_id={recipient_id}, actor_id={actor_id}")
		except Organization.DoesNotExist as e:
			logger.error(f"[CreateNotification] Organization not found: {e}")
			raise Exception(f"Failed to create notification: Organization not found - {organization_id}")
		except Exception as e:
			logger.error(f"[CreateNotification] Failed: {e}")
			raise Exception(f"Failed to create notification: {e}")


class Mutation(graphene.ObjectType):
	create_notification = CreateNotification.Field()
	mark_notification_as_read = MarkNotificationAsRead.Field()
	mark_all_notifications_as_read = MarkAllNotificationsAsRead.Field()

