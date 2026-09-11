import pika
import logging
import json
import time
from django.conf import settings

logger = logging.getLogger(__name__)


class RabbitMQPublishError(Exception):
    """Raised when a message fails to publish to RabbitMQ."""
    pass


class EventPublisher:
    """
    A service class for publishing messages to RabbitMQ.
    Manages its own connection and channel with automatic reconnection.
    """

    def __init__(self):
        logger.info("Initializing EventPublisher...")
        self.connection = None
        self.channel = None
        self._connect_with_retry()

    def _connect_with_retry(self, max_retries=3, retry_delay=2):
        """Establishes connection with retry logic."""
        for attempt in range(max_retries):
            try:
                self._do_connect()
                return True
            except Exception as e:
                logger.warning(f"RabbitMQ connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        logger.error("Failed to connect to RabbitMQ after all retries.")
        return False

    def _do_connect(self):
        """Internal method to establish the actual connection."""
        # Close any existing stale connection
        self._close_connection()
        
        creds = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                credentials=creds,
                port=int(settings.RABBITMQ_PORT),
                heartbeat=30,
                blocked_connection_timeout=300,
                connection_attempts=3,
                retry_delay=2
            )
        )
        self.channel = self.connection.channel()
        self.channel.exchange_declare(
            exchange='hefaistos_events', 
            exchange_type='topic', 
            durable=True
        )
        logger.info("RabbitMQ connection successful. Exchange 'hefaistos_events' declared.")

    def _close_connection(self):
        """Safely close existing connection if any."""
        try:
            if self.channel and self.channel.is_open:
                self.channel.close()
        except Exception:
            pass
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
        except Exception:
            pass
        self.channel = None
        self.connection = None

    def is_connected(self):
        """Check if the connection and channel are active."""
        try:
            return (
                self.connection is not None and 
                self.connection.is_open and 
                self.channel is not None and 
                self.channel.is_open
            )
        except Exception:
            return False

    def _ensure_connection(self):
        """Re-establish connection if lost."""
        if not self.is_connected():
            logger.warning("RabbitMQ connection lost. Reconnecting...")
            return self._connect_with_retry()
        return True

    def publish_message(self, routing_key, message_body):
        """
        Publishes a message to the 'hefaistos_events' exchange.

        :param routing_key: The topic key (e.g., "playbook.review.created")
        :param message_body: A Python dictionary to be sent as JSON.
        :raises RabbitMQPublishError: If the message cannot be published after retries.
        """
        last_error = None
        
        # Try up to 2 times (initial + 1 retry after reconnect)
        for attempt in range(2):
            try:
                if not self._ensure_connection():
                    raise RabbitMQPublishError("Cannot establish RabbitMQ connection")

                body_json = json.dumps(message_body)

                self.channel.basic_publish(
                    exchange='hefaistos_events',
                    routing_key=routing_key,
                    body=body_json,
                    properties=pika.BasicProperties(
                        content_type='application/json',
                        delivery_mode=pika.DeliveryMode.Persistent
                    )
                )
                logger.info(f"Published message to '{routing_key}': {body_json}")
                return True  # Success

            except pika.exceptions.AMQPConnectionError as e:
                last_error = e
                logger.warning(f"AMQP connection error on publish attempt {attempt + 1}: {e}")
                # Force reconnect on next attempt
                self._close_connection()
                
            except pika.exceptions.AMQPChannelError as e:
                last_error = e
                logger.warning(f"AMQP channel error on publish attempt {attempt + 1}: {e}")
                # Force reconnect on next attempt
                self._close_connection()
                
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error publishing to '{routing_key}': {e}")
                break  # Don't retry unknown errors

        # All retries failed
        error_msg = f"Failed to publish message to '{routing_key}' after retries: {last_error}"
        logger.error(error_msg)
        raise RabbitMQPublishError(error_msg)

    def close(self):
        """Closes the connection."""
        self._close_connection()
        logger.info("RabbitMQ connection closed.")


# --- SINGLETON PATTERN ---
# We create one instance here for the entire Django application to use.
# Note: Lazy initialization to avoid blocking on import if RabbitMQ is slow
_publisher = None

def get_publisher():
    """
    A getter function to access the single publisher instance.
    Uses lazy initialization to avoid blocking on module import.
    """
    global _publisher
    if _publisher is None:
        _publisher = EventPublisher()
    return _publisher
# --- END SINGLETON ---
