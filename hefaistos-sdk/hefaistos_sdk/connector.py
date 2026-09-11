import pika
import os
import time
import logging
import json
import hashlib
from abc import ABC, abstractmethod
from .client import HefaistosApiClient, get_secret # <-- ADD get_secret

# Setup logger for the SDK
logger = logging.getLogger(__name__)

class BaseConnector(ABC):
    """
    An abstract base class for building HEFAISTOS RabbitMQ listeners.
    Handles connection, channel, queue binding, and message consuming.
    """

    def __init__(self, service_name, exchange_name='hefaistos_events'):
        self.service_name = service_name
        self.exchange_name = exchange_name

        # --- Get Config ---
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST')
        self.rabbitmq_user = os.environ.get('RABBITMQ_USER')
        self.rabbitmq_pass = get_secret('rabbitmq_pass', 'RABBITMQ_PASS')
        # Optional port support
        port_env = os.environ.get('RABBITMQ_PORT')
        try:
            self.rabbitmq_port = int(port_env) if port_env else 5672
        except ValueError:
            self.rabbitmq_port = 5672
        retry_delay_env = os.environ.get('CONNECTOR_REQUEUE_DELAY_SECONDS', '1')
        try:
            self.requeue_delay_seconds = max(float(retry_delay_env), 0.0)
        except ValueError:
            self.requeue_delay_seconds = 1.0
        max_retries_env = os.environ.get('CONNECTOR_MAX_RETRIES_PER_MESSAGE', '20')
        try:
            self.max_retries_per_message = max(int(max_retries_env), 0)
        except ValueError:
            self.max_retries_per_message = 20
        self._failure_counts = {}

        if not all([self.rabbitmq_host, self.rabbitmq_user, self.rabbitmq_pass]):
            raise ValueError("RABBITMQ_HOST, RABBITMQ_USER, and RABBITMQ_PASS env vars must be set.")

        # --- Init API Client ---
        try:
            self.api_client = HefaistosApiClient()
        except ValueError as e:
            logger.critical(f"Failed to initialize API client: {e}")
            raise

        self.connection = None
        self.channel = None
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    def connect(self):
        """
        Establishes a connection to RabbitMQ with retry logic.
        """
        logging.info(f"[{self.service_name}] Attempting to connect to RabbitMQ at {self.rabbitmq_host}...")

        for i in range(10): # Connection retry loop
            try:
                creds = pika.PlainCredentials(self.rabbitmq_user, self.rabbitmq_pass)
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(host=self.rabbitmq_host, port=self.rabbitmq_port, credentials=creds)
                )
                self.channel = self.connection.channel()

                # Ensure the exchange exists (matches the publisher)
                self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)

                logging.info(f"[{self.service_name}] RabbitMQ connection successful.")
                return True

            except pika.exceptions.AMQPConnectionError as e:
                logging.warning(f"[{self.service_name}] AMQP connection failed (Attempt {i+1}/10): {e}. Retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                # Catch DNS resolution errors (e.g., gaierror) and other transient failures
                logging.warning(f"[{self.service_name}] Connection attempt {i+1}/10 failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)

        logging.critical(f"[{self.service_name}] Could not connect to RabbitMQ. Exiting.")
        return False

    @abstractmethod
    def get_queue_bindings(self):
        """
        Abstract method. Must be implemented by the child class.
        Should return a list of tuples: (queue_name, routing_key)
        e.g., [('deploy_queue', 'playbook.deploy.testing')]
        """
        pass

    @abstractmethod
    def process_message(self, routing_key, payload):
        """
        Abstract method. This is where the connector's logic goes.
        Must be implemented by the child class.
        Return True on success, False on failure.
        """
        pass

    def _message_callback(self, ch, method, properties, body):
        """Internal callback for all messages."""
        routing_key = method.routing_key
        message_key = f"{routing_key}:{hashlib.sha256(body).hexdigest()}"
        logging.info(f"[{self.service_name}] Received message with routing key: {routing_key}")

        try:
            payload = json.loads(body.decode('utf-8'))

            # Call the user-defined processing logic
            success = self.process_message(routing_key, payload)

            if success:
                logging.info(f"[{self.service_name}] Successfully processed message. Sending ACK.")
                self._failure_counts.pop(message_key, None)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                failure_count = self._failure_counts.get(message_key, 0) + 1
                self._failure_counts[message_key] = failure_count
                logging.error(f"[{self.service_name}] Failed to process message. Sending NACK (requeue=True).")
                if self.max_retries_per_message > 0 and failure_count >= self.max_retries_per_message:
                    logging.error(
                        f"[{self.service_name}] Message failed {failure_count} times. "
                        f"Dropping without requeue (CONNECTOR_MAX_RETRIES_PER_MESSAGE={self.max_retries_per_message})."
                    )
                    self._failure_counts.pop(message_key, None)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return
                if self.requeue_delay_seconds > 0:
                    logging.warning(
                        f"[{self.service_name}] Requeue throttle active: sleeping "
                        f"{self.requeue_delay_seconds:.2f}s before NACK."
                    )
                    time.sleep(self.requeue_delay_seconds)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        except json.JSONDecodeError:
            logging.error(f"[{self.service_name}] Could not parse message body. Discarding: {body}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Don't requeue bad JSON
        except Exception as e:
            logging.error(f"[{self.service_name}] Unknown error in process_message: {e}. Sending NACK (requeue=True).")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def start_consuming(self):
        """
        The main blocking loop that connects, binds queues, and consumes messages.
        """
        if not self.connect():
            return # Failed to connect

        try:
            # Get queue/binding info from child class
            bindings = self.get_queue_bindings()
            if not bindings:
                logging.error(f"[{self.service_name}] No queue bindings defined. Exiting.")
                return

            self.channel.basic_qos(prefetch_count=1) # One message at a time

            for queue_name, routing_key in bindings:
                # Declare the durable queue
                self.channel.queue_declare(queue=queue_name, durable=True)
                # Bind it to the exchange
                self.channel.queue_bind(
                    exchange=self.exchange_name, 
                    queue=queue_name, 
                    routing_key=routing_key
                )
                # Start consuming from this queue
                self.channel.basic_consume(
                    queue=queue_name, 
                    on_message_callback=self._message_callback
                )
                logging.info(f"[{self.service_name}] Queue '{queue_name}' bound to key '{routing_key}'")

            logging.info(f"[{self.service_name}] Now consuming messages. To exit press CTRL+C")
            self.channel.start_consuming()

        except KeyboardInterrupt:
            logging.info(f"[{self.service_name}] Shutting down...")
        except Exception as e:
            logging.error(f"[{self.service_name}] Connector crashed: {e}")
        finally:
            if self.connection and self.connection.is_open:
                self.connection.close()
            logging.info(f"[{self.service_name}] Goodbye.")
