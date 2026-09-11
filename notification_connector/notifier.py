import logging
from hefaistos_sdk.connector import BaseConnector
from uuid import UUID

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def is_valid_uuid(value):
    """Check if a value is a valid UUID."""
    if not value:
        return False
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class NotificationConnector(BaseConnector):
    """
    Listens for domain events and creates notifications for recipients
    based on role and ownership rules.
    """

    def get_queue_bindings(self):
        """Defines what this connector listens to."""
        return [
            ('notification_queue', 'playbook.review.created'),
            ('notification_queue', 'review.requested'),
            ('notification_queue', 'review.approved'),
            ('notification_queue', 'review.changes_requested'),
            ('notification_queue', 'rule.created'),
            ('notification_queue', 'repository.created'),
            ('notification_queue', 'playbook.graph.status.changed'),
        ]

    def _notify_many(self, recipients, actor_id, org_id, verb, object_id, content_type):
        # Validate IDs are UUIDs
        if not is_valid_uuid(actor_id):
            logger.warning(f"[_notify_many] Invalid actor_id (not a UUID): {actor_id}. Skipping notifications.")
            return 0
        if not is_valid_uuid(org_id):
            logger.warning(f"[_notify_many] Invalid org_id (not a UUID): {org_id}. Skipping notifications.")
            return 0
        if not is_valid_uuid(object_id):
            logger.warning(f"[_notify_many] Invalid object_id (not a UUID): {object_id}. Skipping notifications.")
            return 0
        
        success = 0
        logger.info(f"[_notify_many] Attempting to notify {len(recipients)} recipients")
        for u in recipients:
            rid = u.get('id') if isinstance(u, dict) else u
            
            # Validate recipient ID
            if not is_valid_uuid(rid):
                logger.warning(f"[_notify_many] Invalid recipient_id (not a UUID): {rid}. Skipping recipient.")
                continue
            
            logger.info(f"[_notify_many] Creating notification for recipient={rid}, actor={actor_id}, verb='{verb}'")
            resp = self.api_client.create_notification(
                recipient_id=rid,
                actor_id=actor_id,
                org_id=org_id,
                verb=verb,
                object_id=object_id,
                content_type=content_type,
            )
            if resp:
                logger.info(f"[_notify_many] Notification created successfully: {resp}")
                success += 1
            else:
                logger.error(f"[_notify_many] Failed to create notification for recipient={rid}")
        return success

    def process_message(self, routing_key, payload):
        logger.info(f"[process_message] Processing {routing_key}: {payload}")
        
        # Common fields
        org_id = payload.get('organization_id') or payload.get('org_id')
        actor_id = payload.get('author_id') or payload.get('triggered_by_user_id') or payload.get('actor_id')
        
        logger.info(f"[process_message] org_id={org_id}, actor_id={actor_id}")

        if routing_key in ('playbook.review.created', 'review.requested'):
            graph_id = payload.get('graph_id')
            if not all([org_id, actor_id, graph_id]):
                logger.error(f"Message missing fields for review event: org_id={org_id}, actor_id={actor_id}, graph_id={graph_id}")
                return True

            # Get org users excluding actor, include role
            logger.info(f"[review] Fetching org users for org_id={org_id}, excluding actor_id={actor_id}")
            user_data = self.api_client.get_org_users(org_id, actor_id)
            logger.info(f"[review] get_org_users response: {user_data}")
            if user_data is None:
                logger.error("[review] Failed to fetch org users - returning False to retry")
                return False
            members = user_data.get('organization', {}).get('members', [])
            logger.info(f"[review] Found {len(members)} members in organization")
            admin_reviewer = [u for u in members if u.get('role') in ('ADMIN', 'REVIEWER')]
            logger.info(f"[review] Found {len(admin_reviewer)} admin/reviewer users")

            # Get graph details for title and author
            logger.info(f"[review] Fetching graph title for graph_id={graph_id}")
            graph_data = self.api_client.get_graph_title(graph_id)
            logger.info(f"[review] get_graph_title response: {graph_data}")
            if graph_data is None:
                logger.error("[review] Failed to fetch graph title - returning False to retry")
                return False
            
            pg = graph_data.get('playbookGraph')
            if pg is None:
                # PlaybookGraph doesn't exist in database - this is a data issue, not a transient error
                # Don't requeue; acknowledge and move on to prevent infinite loops
                logger.warning(f"[review] PlaybookGraph not found: {graph_id}. Skipping notification.")
                return True
            
            title = pg.get('title', 'a playbook graph')
            author = (pg.get('author') or {}).get('id')
            logger.info(f"[review] Graph title='{title}', author={author}")

            # Always notify creator/author
            recipients = admin_reviewer
            if author and author != actor_id:
                recipients = recipients + [{'id': author, 'role': 'OWNER'}]

            verb = f"submitted a review request for '{title}'"
            count = self._notify_many(recipients, actor_id, org_id, verb, graph_id, 'playbookGraph')
            logger.info(f"Notifications sent: {count}/{len(recipients)} for {routing_key}")
            return True

        if routing_key in ('review.approved', 'review.changes_requested'):
            # Notify the original author that their review was approved/rejected
            author_id = payload.get('author_id')
            playbook_id = payload.get('playbook_id')
            decision = payload.get('decision', 'finalized')
            
            if not all([org_id, actor_id, author_id]):
                logger.error(f"Message missing fields for review decision: {payload}")
                return True
            
            # The author should be notified (unless they are the actor)
            if author_id == actor_id:
                logger.info(f"Actor is author, no notification needed for {routing_key}")
                return True
            
            # Get graph_id from playbook for linking
            # We'll use playbook_id as the object for now
            object_id = playbook_id or 'unknown'
            
            if decision == 'APPROVED':
                verb = "approved your review request"
            else:
                verb = "requested changes on your review"
            
            # Notify the author
            resp = self.api_client.create_notification(
                recipient_id=author_id,
                actor_id=actor_id,
                org_id=org_id,
                verb=verb,
                object_id=object_id,
                content_type='playbook',
            )
            if resp:
                logger.info(f"Notification sent to author {author_id} for {routing_key}")
            else:
                logger.warning(f"Failed to send notification for {routing_key}")
            return True

        if routing_key == 'rule.created':
            rule_id = payload.get('rule_id')
            title = payload.get('title', 'a detection rule')
            creator_id = payload.get('creator_id')
            if not all([org_id, actor_id, rule_id]):
                logger.error(f"Message missing fields for rule.created: {payload}")
                return True
            
            user_data = self.api_client.get_org_users(org_id, actor_id)
            if user_data is None:
                logger.error("[rule] Failed to fetch org users - returning False to retry")
                return False
            
            members = user_data.get('organization', {}).get('members', [])
            if not members:
                logger.warning(f"[rule] No organization members found for org_id={org_id}. Skipping notification.")
                return True
            
            admins = [u for u in members if u.get('role') == 'ADMIN']
            if not admins:
                logger.warning(f"[rule] No admin users found in organization. Skipping notification.")
                return True

            recipients = admins
            # Always notify creator on changes
            if creator_id and creator_id != actor_id:
                recipients = recipients + [{'id': creator_id, 'role': 'OWNER'}]

            verb = f"created rule '{title}'"
            count = self._notify_many(recipients, actor_id, org_id, verb, rule_id, 'playbook')
            logger.info(f"Notifications sent: {count}/{len(recipients)} for rule.created")
            return True

        if routing_key == 'repository.created':
            repo_id = payload.get('repository_id')
            name = payload.get('name', 'a repository')
            if not all([org_id, actor_id, repo_id]):
                logger.error(f"Message missing fields for repository.created: {payload}")
                return True
            
            user_data = self.api_client.get_org_users(org_id, actor_id)
            if user_data is None:
                logger.error("[repo] Failed to fetch org users - returning False to retry")
                return False
            
            members = user_data.get('organization', {}).get('members', [])
            if not members:
                logger.warning(f"[repo] No organization members found for org_id={org_id}. Skipping notification.")
                return True
            
            admins = [u for u in members if u.get('role') == 'ADMIN']
            if not admins:
                logger.warning(f"[repo] No admin users found in organization. Skipping notification.")
                return True

            verb = f"added repository '{name}'"
            count = self._notify_many(admins, actor_id, org_id, verb, repo_id, 'playbook')
            logger.info(f"Notifications sent: {count}/{len(admins)} for repository.created")
            return True

        if routing_key == 'playbook.graph.status.changed':
            graph_id = payload.get('graph_id')
            status = payload.get('status')
            creator_id = payload.get('creator_id')
            if not all([org_id, actor_id, graph_id, status]):
                logger.error(f"Message missing fields for status.changed: {payload}")
                return True
            
            user_data = self.api_client.get_org_users(org_id, actor_id)
            if user_data is None:
                logger.error("[status] Failed to fetch org users - returning False to retry")
                return False
            
            members = user_data.get('organization', {}).get('members', [])
            if not members:
                logger.warning(f"[status] No organization members found for org_id={org_id}. Skipping notification.")
                return True
            
            admins = [u for u in members if u.get('role') == 'ADMIN']
            if not admins:
                logger.warning(f"[status] No admin users found in organization. Skipping notification.")
                return True

            recipients = admins
            if creator_id and creator_id != actor_id:
                recipients = recipients + [{'id': creator_id, 'role': 'OWNER'}]

            verb = f"changed workbench status to {status}"
            count = self._notify_many(recipients, actor_id, org_id, verb, graph_id, 'playbookGraph')
            logger.info(f"Notifications sent: {count}/{len(recipients)} for status.changed")
            return True

        logger.info(f"Unhandled routing key {routing_key}. ACKing.")
        return True


if __name__ == '__main__':
    logger.info("--- Starting HEFAISTOS Notification Connector (SDK v1.0) ---")
    connector = NotificationConnector(service_name="NotificationConnector")
    connector.start_consuming()