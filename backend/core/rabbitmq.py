import pika
import os
import json
import logging

logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_USER = os.environ.get('RABBITMQ_USER', 'guest')

# First try to read from RABBITMQ_PASS environment variable
RABBITMQ_PASS = os.environ.get('RABBITMQ_PASS')

# If not found, try to read from RABBITMQ_PASS_FILE (Docker secret path)
if not RABBITMQ_PASS:
    secret_path = os.environ.get('RABBITMQ_PASS_FILE', '/run/secrets/rabbitmq_pass')
    try:
        if os.path.exists(secret_path):
            with open(secret_path, 'r', encoding='utf-8') as f:
                RABBITMQ_PASS = f.read().strip()
    except Exception as e:
        logger.warning(f"Failed to read RabbitMQ password from {secret_path}: {e}")

# Fallback to guest password if nothing is configured
RABBITMQ_PASS = RABBITMQ_PASS or 'guest'
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))
EXCHANGE_NAME = 'hefaistos_events'


class RabbitMQPublishError(Exception):
    """Raised when a message fails to publish to RabbitMQ."""
    pass


def publish_event(routing_key, payload, raise_on_error=False):
    """
    Publishes an event to the RabbitMQ exchange.
    
    Args:
        routing_key: The routing key for the message
        payload: The message payload (dict)
        raise_on_error: If True, raises RabbitMQPublishError on failure.
                       If False (default), just logs the error for backward compatibility.
    
    Returns:
        True on success, False on failure (when raise_on_error=False)
    
    Raises:
        RabbitMQPublishError: When publishing fails and raise_on_error=True
    """
    connection = None
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=credentials,
            heartbeat=30,  # send heartbeats every 30s
            blocked_connection_timeout=300,  # fail if blocked too long
            connection_attempts=5,
            retry_delay=5,  # seconds between attempts
            socket_timeout=10
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

        message_body = json.dumps(payload)
        
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=message_body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                content_type='application/json'
            )
        )
        
        logger.info(f"Published event '{routing_key}': {payload}")
        return True
        
    except Exception as e:
        error_msg = f"Failed to publish event '{routing_key}': {e}"
        logger.error(error_msg)
        if raise_on_error:
            raise RabbitMQPublishError(error_msg) from e
        return False
    finally:
        if connection and connection.is_open:
            try:
                connection.close()
            except Exception:
                pass
