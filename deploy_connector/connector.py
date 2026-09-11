import logging
from hefaistos_sdk.connector import BaseConnector

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DeployConnector(BaseConnector):
    """
    Listens for 'playbook.deploy.testing' events and updates the 
    playbook status in the HEFAISTOS API.
    """

    def get_queue_bindings(self):
        """Defines what this connector listens to."""
        return [
            ('deploy_queue', 'playbook.deploy.testing')
        ]

    def process_message(self, routing_key, payload):
        """
        This is the core logic. It is called by BaseConnector.
        """
        playbook_id = payload.get('playbook_id')
        if not playbook_id:
            logger.error("Message is missing 'playbook_id'. Discarding.")
            return False # False = NACK (requeue)

        logger.info(f"Processing deploy request for playbook_id: {playbook_id}")

        # Call the API helper from the parent class
        response = self.api_client.update_playbook_status(playbook_id, "TESTING")

        if response is None:
            logger.error(f"Failed to update status for {playbook_id}.")
            return False # Failed, requeue

        logger.info(f"Successfully updated status for {playbook_id} to TESTING.")
        return True # Success, ACK


if __name__ == '__main__':
    logger.info("--- Starting HEFAISTOS Deploy Connector (SDK v1.0) ---")
    connector = DeployConnector(service_name="DeployConnector")
    connector.start_consuming()