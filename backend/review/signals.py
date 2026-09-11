from services.publisher import get_publisher
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging
from .models import ReviewRequest

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ReviewRequest)
def create_review_notification(sender, instance, created, **kwargs):
    """
    Publishes an event to RabbitMQ when a new ReviewRequest is created.
    """
    logger.info(f"[signals] ReviewRequest post_save fired: created={created}, instance_id={instance.id}")
    
    # Only run on creation
    if not created:
        logger.info(f"[signals] Not a creation event, skipping")
        return

    review_request = instance
    author = review_request.author
    
    logger.info(f"[signals] Processing review creation: author={author}, playbook_id={review_request.playbook_id}")

    # --- START OF REFACTOR ---
    #
    # REMOVED:
    # recipients = CustomUser.objects.filter(...)
    # target_content_type = ContentType.objects.get_for_model(...)
    # notification_list = []
    # Notification.objects.bulk_create(notification_list)
    #
    # ADDED:

    # 1. Define the routing key
    routing_key = "playbook.review.created"

    # 2. Compute graph_id from the playbook relationship
    # ReviewRequest -> playbook (DetectionPlaybook) -> graphs (PlaybookGraph)
    graph_id = None
    try:
        if review_request.playbook:
            graph = review_request.playbook.graphs.first()
            if graph:
                graph_id = str(graph.id)
                logger.info(f"[signals] Found graph_id={graph_id} from playbook")
            else:
                logger.warning(f"[signals] No graphs found for playbook {review_request.playbook_id}")
        else:
            logger.warning(f"[signals] No playbook on review request")
    except Exception as e:
        logger.error(f"[signals] Error getting graph_id: {e}")

    # 3. Define the message payload
    message_body = {
        "action": "review_created",
        "review_request_id": str(review_request.id),
        "graph_id": graph_id,  # Computed from playbook -> graphs relationship
        "playbook_id": str(review_request.playbook_id) if review_request.playbook_id else None,
        "author_id": str(author.id) if author else None,
        "organization_id": str(author.organization_id) if author else None
    }
    
    logger.info(f"[signals] Publishing event: routing_key={routing_key}, payload={message_body}")

    # 4. Get the publisher instance and publish
    try:
        publisher = get_publisher()
        publisher.publish_message(routing_key, message_body)
        logger.info(f"[signals] Successfully published {routing_key} event")
    except Exception as e:
        # Log the error, but don't block the main request
        logger.error(f"Failed to publish review_created event: {e}")

    # --- END OF REFACTOR ---

    # --- END OF REFACTOR ---
