import pika
import os
import json
import time
import logging

# --- Bootstrap Django so we can update the database ---
import django
from pathlib import Path
import sys

# Ensure 'backend' folder is on sys.path so 'core.settings' is importable
BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend/
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from playbooks.models import DetectionPlaybook  # noqa: E402

logger = logging.getLogger(__name__)

# --- Read Configuration from Environment ---
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_USER = os.environ.get('RABBITMQ_USER', 'guest')

def _read_secret(secret_name: str) -> str | None:
    path = f"/run/secrets/{secret_name}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

# Prefer explicit env var; fallback to docker secret 'rabbitmq_pass'
RABBITMQ_PASS = os.environ.get('RABBITMQ_PASS') or _read_secret('rabbitmq_pass') or 'guest'
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))

EXCHANGE_NAME = 'hefaistos_events'

def on_message_received(ch, method, properties, body):
    """
    This function is called every time a message is received.
    """
    print("\n[+] --- New Message Received ---")
    print(f"    Routing Key: {method.routing_key}")

    try:
        # Decode the message body from bytes and parse as JSON
        payload = json.loads(body.decode('utf-8'))
        print("    Payload:")
        print(json.dumps(payload, indent=4))
    except json.JSONDecodeError:
        print(f"    Body (Not JSON): {body.decode('utf-8')}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    try:
        # Handle deploy-to-testing events
        if method.routing_key == 'playbook.deploy.testing' or payload.get('action') == 'deploy_to_testing':
            playbook_id = payload.get('playbook_id')
            organization_id = payload.get('organization_id')
            if not playbook_id or not organization_id:
                raise ValueError('Missing playbook_id or organization_id in payload')

            try:
                pb = DetectionPlaybook.objects.get(pk=playbook_id, organization_id=organization_id)
            except DetectionPlaybook.DoesNotExist:
                raise ValueError(f'Playbook {playbook_id} not found for organization {organization_id}')

            # Only transition APPROVED -> TESTING
            if pb.status == DetectionPlaybook.PlaybookStatus.APPROVED:
                pb.status = DetectionPlaybook.PlaybookStatus.TESTING
                pb.save(update_fields=['status', 'updated_at'])
                print(f"    -> Playbook {pb.id} status set to TESTING")
            else:
                print(f"    -> Playbook {pb.id} status not updated (current: {pb.status})")
        else:
            # Unknown or unhandled routing key; just log
            print("    -> No handler for this routing key; message acknowledged.")
    except Exception as e:
        logger.error(f"Listener processing error: {e}")

    print("[+] --- Waiting for next message ---")
    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    print("--- Starting Hefaistos event listener ---")
    print(f"Attempting to connect to {RABBITMQ_HOST}...")

    connection = None

    # Add retry logic in case RabbitMQ isn't fully booted
    for i in range(10):
        try:
            creds = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=creds)
            )
            break # Connection successful
        except pika.exceptions.AMQPConnectionError:
            print(f"Connection failed (Attempt {i+1}/10). Retrying in 5 seconds...")
            time.sleep(5)

    if not connection:
        print("Could not connect to RabbitMQ. Exiting.")
        return

    print("Connection successful!")
    channel = connection.channel()

    # Ensure the exchange exists (matches the publisher)
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

    # Create a temporary, exclusive queue.
    # 'exclusive=True' means the queue will be deleted when this listener disconnects.
    result = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue

    # --- Bind the queue to the exchange ---
    # The '#' symbol is a wildcard that means "bind to ALL routing keys"
    # This is perfect for our "hello world" test.
    binding_key = "#"
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=queue_name, routing_key=binding_key)

    print(f"[*] Queue '{queue_name}' is bound to '{EXCHANGE_NAME}' with key '{binding_key}'")
    print("[*] Waiting for messages. To exit press CTRL+C")

    # Start consuming messages
    channel.basic_consume(queue=queue_name, on_message_callback=on_message_received)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("Shutting down listener...")
        channel.stop_consuming()
        connection.close()
        print("Goodbye.")

if __name__ == '__main__':
    main()