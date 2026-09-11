"""
AI generation worker.

Listens to the RabbitMQ 'ai.generation.requested' routing key and processes
async AI generation tasks (generate rule, suggest improvements, generate similar
rules, populate workbench from threat report) following the same pattern as
services/opentide_enrichment_worker.py.
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
QUEUE_NAME = 'ai_generation_tasks'
ROUTING_KEY = 'ai.generation.requested'


def _read_secret(secret_name: str) -> str | None:
    path = f"/run/secrets/{secret_name}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


RABBITMQ_PASS = os.environ.get('RABBITMQ_PASS') or _read_secret('rabbitmq_pass') or 'guest'


def _mark_reference_files_used(reference_context: list[dict]):
    from ai_assistant.rag_templates import mark_reference_files_used

    mark_reference_files_used(reference_context)


def _resolve_rag_language(language_hint: str | None, *, rule_content: str | None = None) -> str | None:
    from ai_assistant.rag_templates import normalize_rag_language

    normalized = normalize_rag_language(language_hint, fallback='')
    if normalized:
        return normalized

    if rule_content and str(rule_content).strip():
        try:
            from rules.utils import detect_rule_format

            detected = detect_rule_format(str(rule_content))
            return normalize_rag_language(detected, fallback='')
        except Exception:
            return None

    return None


def _run_generate_rule(task) -> dict:
    """Execute generate_rule_bundle for the given task and return a result dict."""
    from ai_assistant.models import UserAISettings
    from ai_assistant.schema import _get_effective_ai_settings
    from ai_assistant.engine import generate_rule_bundle
    from ai_assistant.rag_templates import (
        build_reference_context_prompt,
        retrieve_reference_context,
    )

    user_settings = UserAISettings.objects.get(user=task.user)
    effective = _get_effective_ai_settings(user_settings)

    context = task.input_data.get('playbook_context', {})
    output_format = task.input_data.get('output_format', 'KQL')
    rag_language = _resolve_rag_language(output_format)

    reference_context = []
    if rag_language:
        try:
            org_id = getattr(getattr(task.user, 'organization', None), 'id', None)
            reference_context = retrieve_reference_context(
                playbook_context=context or {},
                language=rag_language,
                organization_id=str(org_id) if org_id else None,
                limit=6,
            )
            if reference_context:
                context = {
                    **(context or {}),
                    'reference_context_prompt': build_reference_context_prompt(reference_context),
                }
        except Exception as exc:
            logger.warning("RAG retrieval failed for task %s: %s", task.id, exc)

    bundle, provider = generate_rule_bundle(effective, context, output_format)
    _mark_reference_files_used(reference_context)
    return {
        'rule': bundle.get('primary_rule'),
        'quick_win_rule': bundle.get('quick_win_rule'),
        'robust_rule': bundle.get('robust_rule'),
        'generation_summary': bundle.get('generation_summary'),
        'correlation_ideas': bundle.get('correlation_ideas'),
        'expected_blind_spots': bundle.get('expected_blind_spots'),
        'test_guidance': bundle.get('test_guidance'),
        'provider_used': provider,
        'output_format': output_format,
        'reference_context': reference_context,
    }


def _run_suggest_improvements(task) -> dict:
    """Execute suggest_rule_improvements for the given task and return a result dict."""
    import re
    from ai_assistant.models import UserAISettings
    from ai_assistant.schema import _get_effective_ai_settings
    from ai_assistant.engine import suggest_rule_improvements
    from ai_assistant.rag_templates import build_reference_context_prompt, retrieve_reference_context

    user_settings = UserAISettings.objects.get(user=task.user)
    effective = _get_effective_ai_settings(user_settings)

    rule_content = task.input_data.get('rule_content', '')
    rule_format = task.input_data.get('rule_format', 'KQL')
    playbook_context = task.input_data.get('playbook_context') if isinstance(task.input_data.get('playbook_context'), dict) else {}
    rag_language = _resolve_rag_language(rule_format, rule_content=rule_content)

    reference_context = []
    if rag_language:
        try:
            org_id = getattr(getattr(task.user, 'organization', None), 'id', None)
            reference_context = retrieve_reference_context(
                playbook_context=playbook_context,
                rule_content=rule_content,
                language=rag_language,
                organization_id=str(org_id) if org_id else None,
                limit=6,
            )
            if reference_context:
                playbook_context = {
                    **(playbook_context or {}),
                    'reference_context_prompt': build_reference_context_prompt(reference_context),
                }
        except Exception as exc:
            logger.warning("RAG retrieval failed for suggest task %s: %s", task.id, exc)

    suggestions_text, provider = suggest_rule_improvements(
        effective,
        rule_content,
        rule_format,
        playbook_context,
    )
    _mark_reference_files_used(reference_context)

    improved_rule = None
    marker_match = re.search(
        r'[ \t]*---IMPROVED-RULE-START---[ \t]*\r?\n(.*?)\r?\n[ \t]*---IMPROVED-RULE-END---',
        suggestions_text,
        re.DOTALL,
    )
    if marker_match:
        improved_rule = marker_match.group(1).strip()
        suggestions_display = re.sub(
            r'\n?[ \t]*---IMPROVED-RULE-START---[ \t]*\r?\n.*?\r?\n[ \t]*---IMPROVED-RULE-END---[ \t]*\n?',
            '',
            suggestions_text,
            flags=re.DOTALL,
        ).strip()
    else:
        suggestions_display = suggestions_text

    return {
        'suggestions': suggestions_display,
        'improved_rule': improved_rule,
        'provider_used': provider,
        'reference_context': reference_context,
    }


def _run_generate_similar(task) -> dict:
    """Execute generate_similar_rules for the given task and return a result dict."""
    import re
    from ai_assistant.models import UserAISettings
    from ai_assistant.schema import _get_effective_ai_settings
    from ai_assistant.engine import generate_similar_rules
    from ai_assistant.rag_templates import build_reference_context_prompt, retrieve_reference_context

    user_settings = UserAISettings.objects.get(user=task.user)
    effective = _get_effective_ai_settings(user_settings)

    rule_content = task.input_data.get('rule_content', '')
    rule_format = task.input_data.get('rule_format', 'KQL')
    variation_type = task.input_data.get('variation_type', 'technique')
    num_variations = task.input_data.get('num_variations', 3)
    target_format = task.input_data.get('target_format')
    custom_instructions = task.input_data.get('custom_instructions')
    playbook_context = task.input_data.get('playbook_context') if isinstance(task.input_data.get('playbook_context'), dict) else {}

    source_fmt = (rule_format or 'KQL').upper()
    target_fmt = (target_format or source_fmt).upper()
    rag_language = _resolve_rag_language(target_fmt) or _resolve_rag_language(source_fmt, rule_content=rule_content)

    reference_context = []
    if rag_language:
        try:
            org_id = getattr(getattr(task.user, 'organization', None), 'id', None)
            reference_context = retrieve_reference_context(
                playbook_context=playbook_context,
                rule_content=rule_content,
                additional_text=custom_instructions,
                language=rag_language,
                organization_id=str(org_id) if org_id else None,
                limit=6,
            )
            if reference_context:
                playbook_context = {
                    **(playbook_context or {}),
                    'reference_context_prompt': build_reference_context_prompt(reference_context),
                }
        except Exception as exc:
            logger.warning("RAG retrieval failed for similar-rules task %s: %s", task.id, exc)

    generated_text, provider = generate_similar_rules(
        effective,
        rule_content,
        rule_format,
        playbook_context,
        variation_type,
        num_variations,
        target_format,
        custom_instructions,
    )
    _mark_reference_files_used(reference_context)

    # Normalize separator variants
    generated_text = re.sub(
        r'(?m)^\s*-{3,}\s*RULE\s*-{3,}\s*$',
        '---RULE---',
        generated_text,
        flags=re.IGNORECASE,
    )
    num_generated = generated_text.count('---RULE---') + 1 if '---RULE---' in generated_text else 1

    return {
        'generated_rules': generated_text,
        'provider_used': provider,
        'variation_type': variation_type,
        'num_generated': num_generated,
        'reference_context': reference_context,
    }


def _run_populate_workbench_from_threat_report(task) -> dict:
    """Extract structured workbench payload from a threat report PDF."""
    from ai_assistant.models import UserAISettings
    from ai_assistant.schema import _get_effective_ai_settings
    from ai_assistant.engine import extract_threat_report_workbench_payload

    user_settings = UserAISettings.objects.get(user=task.user)
    effective = _get_effective_ai_settings(user_settings)

    file_content = task.input_data.get('file_content', '')
    filename = task.input_data.get('filename', 'threat-report.pdf')
    logger.warning(
        "Threat-report task started in worker: task_id=%s user=%s filename=%s payload_chars=%d",
        task.id,
        getattr(task.user, 'username', 'unknown'),
        filename,
        len(file_content or ''),
    )

    result, provider = extract_threat_report_workbench_payload(
        effective,
        file_content,
        filename,
    )
    logger.warning(
        "Threat-report task AI call finished: task_id=%s provider=%s warnings=%d",
        task.id,
        provider,
        len(result.get('parse_warnings', []) or []),
    )

    return {
        'provider_used': provider,
        'filename': filename,
        'parsed_payload': result.get('parsed_payload', {}),
        'parse_warnings': result.get('parse_warnings', []),
        'raw_response': result.get('raw_response', ''),
    }


_TASK_HANDLERS = {
    'GENERATE_RULE': _run_generate_rule,
    'SUGGEST_IMPROVEMENTS': _run_suggest_improvements,
    'GENERATE_SIMILAR': _run_generate_similar,
    'POPULATE_THREAT_REPORT': _run_populate_workbench_from_threat_report,
}


def process_ai_task(task_id: str) -> None:
    """Fetch the task from DB, run the AI call, and update the task record."""
    from django.utils import timezone
    from ai_assistant.models import AIGenerationTask

    started_at = timezone.now()
    claimed = AIGenerationTask.objects.filter(
        pk=task_id,
        status=AIGenerationTask.TaskStatus.PENDING,
    ).update(
        status=AIGenerationTask.TaskStatus.RUNNING,
        started_at=started_at,
    )
    if claimed != 1:
        current = AIGenerationTask.objects.filter(pk=task_id).values_list('status', flat=True).first()
        if current is None:
            logger.error("AIGenerationTask %s not found; skipping.", task_id)
        else:
            logger.warning(
                "AIGenerationTask %s was already claimed (status=%s); worker will skip duplicate processing.",
                task_id,
                current,
            )
        return

    try:
        task = AIGenerationTask.objects.select_related('user').get(pk=task_id)
    except AIGenerationTask.DoesNotExist:
        logger.error("AIGenerationTask %s disappeared after claim; skipping.", task_id)
        return

    task.status = AIGenerationTask.TaskStatus.RUNNING
    task.started_at = started_at
    logger.warning(
        "AIGenerationTask %s picked by worker and marked RUNNING (type=%s).",
        task_id,
        task.task_type,
    )

    handler = _TASK_HANDLERS.get(task.task_type)
    if handler is None:
        task.status = AIGenerationTask.TaskStatus.FAILED
        task.error_message = f"Unknown task type: {task.task_type}"
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'error_message', 'completed_at'])
        logger.error("AIGenerationTask %s has unknown task_type '%s'.", task_id, task.task_type)
        return

    try:
        result_data = handler(task)
        task.status = AIGenerationTask.TaskStatus.COMPLETED
        task.result_data = result_data
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'result_data', 'completed_at'])
        logger.warning("AIGenerationTask %s (%s) completed successfully.", task_id, task.task_type)
    except Exception as exc:
        task.status = AIGenerationTask.TaskStatus.FAILED
        task.error_message = str(exc)
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'error_message', 'completed_at'])
        logger.exception("AIGenerationTask %s (%s) failed: %s", task_id, task.task_type, exc)


def on_message_received(ch, method, properties, body):
    logger.warning("Worker received message with routing key: %s", method.routing_key)

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
        process_ai_task(task_id)
    else:
        logger.warning("Received unexpected routing key: %s", method.routing_key)

    ch.basic_ack(delivery_tag=method.delivery_tag)


def run_worker(max_retries: int = 10, retry_delay: int = 5) -> None:
    """Connect to RabbitMQ and start consuming AI generation tasks."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)

    for attempt in range(1, max_retries + 1):
        try:
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=60,
                blocked_connection_timeout=300,
                connection_attempts=3,
                retry_delay=2,
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY)

            # Process one message at a time
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message_received)

            logger.info(
                "AI generation worker started. Listening on queue '%s' (routing key '%s').",
                QUEUE_NAME,
                ROUTING_KEY,
            )
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as exc:
            logger.warning(
                "RabbitMQ connection failed (attempt %d/%d): %s", attempt, max_retries, exc
            )
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                logger.error("Exhausted retries. Exiting.")
                raise
        except KeyboardInterrupt:
            logger.info("Worker stopped by keyboard interrupt.")
            break


if __name__ == '__main__':
    run_worker()
