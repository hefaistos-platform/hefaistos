"""
OpenTIDE enrichment worker.

Listens to the RabbitMQ 'opentide.preview.requested' routing key and
processes OpenTIDE metadata preview tasks asynchronously (with optional AI enrichment),
following the same pattern as services/listener.py.
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

import pika

# --- Bootstrap Django ---
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django  # noqa: E402
django.setup()

logger = logging.getLogger(__name__)

# --- RabbitMQ configuration ---
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_USER = os.environ.get('RABBITMQ_USER', 'guest')
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))
EXCHANGE_NAME = 'hefaistos_events'
QUEUE_NAME = 'opentide_preview_tasks'
ROUTING_KEY = 'opentide.preview.requested'


def _read_secret(secret_name: str) -> str | None:
    path = f"/run/secrets/{secret_name}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


RABBITMQ_PASS = os.environ.get('RABBITMQ_PASS') or _read_secret('rabbitmq_pass') or 'guest'


def _build_preview_result(task):
    """
    Run the AI enrichment pipeline for *task* and return a serialisable dict
    that matches the PreviewOpenTideMetadata GraphQL type fields.
    """
    from playbooks.models import PlaybookGraph
    from playbooks.utils.opentide_compiler import (
        compile_mdr_yaml_with_ai,
        compile_bdr_yaml_with_ai,
        compile_dom_yaml_with_ai,
    )
    from playbooks.utils.opentide_validator import validate_mdr_structure

    use_ai_enrichment = task.use_ai_enrichment
    force_bdr_generation = task.force_bdr_generation
    user = task.user
    playbook = PlaybookGraph.objects.select_related(
        'organization', 'author', 'mitre_technique'
    ).prefetch_related('tags', 'linked_rules').get(pk=task.playbook_id)

    # Resolve AI settings
    ai_settings = None
    if use_ai_enrichment:
        try:
            from ai_assistant.models import UserAISettings
            from ai_assistant.schema import _get_effective_ai_settings
            user_ai_settings, _ = UserAISettings.objects.get_or_create(user=user)
            if user_ai_settings.enable_auto_enrichment:
                ai_settings = _get_effective_ai_settings(user_ai_settings)
        except Exception:
            pass

    # Compile MDR and DOM
    mdr_data = compile_mdr_yaml_with_ai(playbook, ai_settings, use_ai_enrichment)
    dom_data = compile_dom_yaml_with_ai(playbook, ai_settings, use_ai_enrichment)

    # BDR classification and generation
    ai_classification = None
    bdr_data = None
    bdr_applicable = False

    if ai_settings:
        try:
            from ai_assistant.opentide_enrichment import ai_classify_detection_type
            playbook_dict = {
                'title': playbook.title or '',
                'goal': playbook.goal or '',
                'technical_context': playbook.technical_context or '',
                'compliance': '',
            }
            ai_classification = ai_classify_detection_type(playbook_dict, ai_settings)
            bdr_applicable = (ai_classification == 'BUSINESS') or force_bdr_generation
        except Exception:
            bdr_applicable = force_bdr_generation

    if bdr_applicable or force_bdr_generation:
        bdr_data = compile_bdr_yaml_with_ai(
            playbook, ai_settings,
            force_generate=force_bdr_generation,
            use_ai_enrichment=use_ai_enrichment,
        )

    # Build field metadata list
    field_metadata = _extract_field_metadata(mdr_data, bdr_data, dom_data)

    # Validate
    is_valid, errors = validate_mdr_structure(mdr_data)

    # Strip internal tracking keys (_ai_generated, _validation_warning, etc.)
    _INTERNAL = frozenset(['_ai_generated', '_validation_warning'])
    mdr_out = {k: v for k, v in mdr_data.items() if k not in _INTERNAL}
    dom_out = {k: v for k, v in dom_data.items() if k not in _INTERNAL}
    bdr_out = ({k: v for k, v in bdr_data.items() if k not in _INTERNAL} if bdr_data else None)

    return {
        'mdr_yaml': mdr_out,
        'bdr_yaml': bdr_out,
        'dom_yaml': dom_out,
        'field_metadata': field_metadata,
        'ai_classification': ai_classification,
        'bdr_applicable': bdr_applicable,
        'validation_errors': errors if not is_valid else [],
        'total_fields': len(field_metadata),
        'ai_generated_count': sum(1 for f in field_metadata if f['ai_generated']),
        'user_provided_count': sum(1 for f in field_metadata if not f['ai_generated']),
    }


def _extract_field_metadata(mdr_data: dict, bdr_data, dom_data: dict) -> list:
    """Build a serialisable list of field metadata dicts (mirrors schema.py logic)."""

    def _get_nested(data, path):
        keys = path.split('.')
        val = data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return None
        return val

    def _field_type(value):
        if isinstance(value, bool):
            return 'boolean'
        if isinstance(value, (int, float)):
            return 'number'
        if isinstance(value, str):
            return 'string'
        if isinstance(value, list):
            return 'array'
        if isinstance(value, dict):
            return 'object'
        return 'unknown'

    metadata = []
    for prefix, data in (('mdr', mdr_data), ('dom', dom_data)):
        ai_gen = (data or {}).get('_ai_generated', {})
        for field_path, is_ai in ai_gen.items():
            value = _get_nested(data, field_path)
            metadata.append({
                'field_path': f"{prefix}.{field_path}",
                'value': json.dumps(value),
                'ai_generated': bool(is_ai),
                'source': 'ai' if is_ai else 'user',
                'field_type': _field_type(value),
            })

    if bdr_data:
        ai_gen_bdr = bdr_data.get('_ai_generated', {})
        for field_path, is_ai in ai_gen_bdr.items():
            value = _get_nested(bdr_data, field_path)
            metadata.append({
                'field_path': f"bdr.{field_path}",
                'value': json.dumps(value),
                'ai_generated': bool(is_ai),
                'source': 'ai' if is_ai else 'user',
                'field_type': _field_type(value),
            })

    return metadata


def process_preview_task(task_id: str):
    """Fetch the task from DB, run enrichment, and update the task record."""
    from django.utils import timezone
    from playbooks.models import OpentidePreviewTask

    try:
        task = OpentidePreviewTask.objects.select_related('playbook', 'user').get(pk=task_id)
    except OpentidePreviewTask.DoesNotExist:
        logger.error("OpentidePreviewTask %s not found; skipping.", task_id)
        return

    # Mark as running
    task.status = OpentidePreviewTask.TaskStatus.RUNNING
    task.started_at = timezone.now()
    task.save(update_fields=['status', 'started_at'])

    try:
        result_data = _build_preview_result(task)
        task.status = OpentidePreviewTask.TaskStatus.COMPLETED
        task.result_data = result_data
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'result_data', 'completed_at'])
        logger.info("OpentidePreviewTask %s completed successfully.", task_id)
    except Exception as exc:
        task.status = OpentidePreviewTask.TaskStatus.FAILED
        task.error_message = str(exc)
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'error_message', 'completed_at'])
        logger.error("OpentidePreviewTask %s failed: %s", task_id, exc)


def on_message_received(ch, method, properties, body):
    logger.info("Received message with routing key: %s", method.routing_key)

    try:
        payload = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError:
        logger.error("Could not decode message body as JSON; acknowledging and skipping.")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    if method.routing_key == ROUTING_KEY:
        task_id = payload.get('task_id')
        if not task_id:
            logger.error("Payload missing 'task_id'; acknowledging and skipping.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        process_preview_task(task_id)
    else:
        logger.debug("Ignoring unhandled routing key: %s", method.routing_key)

    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    logger.info("Starting OpenTIDE enrichment worker (connecting to %s)…", RABBITMQ_HOST)

    connection = None
    for attempt in range(1, 11):
        try:
            creds = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=creds,
                    heartbeat=600,
                    blocked_connection_timeout=300,
                )
            )
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning("Connection attempt %d/10 failed. Retrying in 5 seconds…", attempt)
            time.sleep(5)

    if not connection:
        logger.error("Could not connect to RabbitMQ after 10 attempts. Exiting.")
        sys.exit(1)

    logger.info("Connected to RabbitMQ.")
    channel = connection.channel()

    # Ensure the exchange exists
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)

    # Durable named queue so messages survive worker restarts
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY)

    # Process one message at a time to avoid overwhelming this worker
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message_received)

    logger.info("Waiting for opentide.preview.requested messages on queue '%s'…", QUEUE_NAME)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Shutting down OpenTIDE enrichment worker…")
        channel.stop_consuming()
        connection.close()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    main()
