import re
import threading
import uuid
from typing import Any

from django.conf import settings
from django.db import models, close_old_connections
from django.utils import timezone

from organizations.models import MISPInstance, Organization
from playbooks.models import PlaybookGraph


class WaitingCase(models.Model):
    class LifecycleStatus(models.TextChoices):
        NEW = 'NEW', 'New'
        ENRICHING = 'ENRICHING', 'Enriching'
        READY = 'READY', 'Ready'
        PROMOTED = 'PROMOTED', 'Promoted'
        FAILED = 'FAILED', 'Failed'

    class SourceType(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        MISP = 'MISP', 'MISP'
        API = 'API', 'API'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='waiting_cases',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_waiting_cases',
    )

    source_type = models.CharField(max_length=16, choices=SourceType.choices, default=SourceType.MANUAL)
    misp_instance = models.ForeignKey(
        MISPInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waiting_cases',
    )
    misp_event_id = models.CharField(max_length=64, blank=True, default='')

    title = models.CharField(max_length=255)
    short_description = models.TextField(blank=True, default='')
    detection_objective = models.TextField(blank=True, default='')
    mapped_ttps = models.JSONField(default=list, blank=True)
    estimated_detection_complexity = models.CharField(max_length=64, blank=True, default='')
    raw_payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.NEW,
    )
    enrichment_error = models.TextField(blank=True, default='')
    promoted_graph = models.ForeignKey(
        PlaybookGraph,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waiting_cases',
    )
    promoted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['misp_instance', 'misp_event_id'],
                condition=models.Q(misp_event_id__gt=''),
                name='waiting_case_misp_instance_event_unique',
            ),
        ]

    def __str__(self):
        return self.title


class MISPImportLedger(models.Model):
    """Permanent record of MISP events already imported into the Waiting Room.

    Deliberately separate from WaitingCase: WaitingCase rows can be deleted by
    reviewers (DeleteWaitingCase), but the ledger row survives that deletion so a
    later importWaitingCasesFromMisp run never recreates a case for an event that
    was already reviewed and discarded. Only a ledger row deletion (explicit
    "forget this event" action, not implemented via the normal delete path) allows
    the same misp_event_id to be re-imported.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='misp_import_ledger_entries',
    )
    misp_instance = models.ForeignKey(
        MISPInstance,
        on_delete=models.CASCADE,
        related_name='misp_import_ledger_entries',
    )
    misp_event_id = models.CharField(max_length=64)
    misp_event_uuid = models.CharField(max_length=64, blank=True, default='')
    imported_at = models.DateTimeField(auto_now_add=True)
    waiting_case = models.ForeignKey(
        WaitingCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ledger_entries',
        help_text='The WaitingCase created at import time, if any. May become null if that case is later deleted.',
    )

    class Meta:
        ordering = ['-imported_at']
        constraints = [
            models.UniqueConstraint(
                fields=['misp_instance', 'misp_event_id'],
                name='misp_import_ledger_instance_event_unique',
            ),
        ]

    def __str__(self):
        return f'MISPImportLedger({self.misp_instance_id}:{self.misp_event_id})'


class WaitingCaseEnrichmentTask(models.Model):
    class TaskStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    waiting_case = models.ForeignKey(
        WaitingCase,
        on_delete=models.CASCADE,
        related_name='enrichment_tasks',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waiting_case_enrichment_tasks',
    )
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    result_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    import json

    clean = (raw_text or '').strip()
    if clean.startswith('```json'):
        clean = clean[7:].strip()
    if clean.startswith('```'):
        clean = clean[3:].strip()
    if clean.endswith('```'):
        clean = clean[:-3].strip()

    try:
        parsed = json.loads(clean)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _normalize_ttps(value) -> list[str]:
    if isinstance(value, list):
        raw = [str(v).strip().upper() for v in value]
    elif isinstance(value, str):
        raw = re.findall(r'T\d{4}(?:\.\d{3})?', value.upper())
    else:
        raw = []

    normalized: list[str] = []
    seen = set()
    for item in raw:
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _sanitize_prompt_text(value: Any, max_len: int = 4000) -> str:
    text = str(value or '')
    text = text.replace('\x00', '').strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _run_enrichment(task_id: str) -> None:
    close_old_connections()
    try:
        task = WaitingCaseEnrichmentTask.objects.select_related('waiting_case', 'requested_by').get(pk=task_id)
    except WaitingCaseEnrichmentTask.DoesNotExist:
        return

    claimed = WaitingCaseEnrichmentTask.objects.filter(
        pk=task_id,
        status=WaitingCaseEnrichmentTask.TaskStatus.PENDING,
    ).update(status=WaitingCaseEnrichmentTask.TaskStatus.RUNNING, started_at=timezone.now())
    if claimed != 1:
        return

    try:
        task.refresh_from_db()
        case = task.waiting_case

        from ai_assistant.models import UserAISettings
        from ai_assistant.schema import _get_effective_ai_settings
        from ai_assistant.engine import run_custom_prompt

        try:
            settings_obj = UserAISettings.objects.get(user=task.requested_by)
        except UserAISettings.DoesNotExist as exc:
            raise RuntimeError('AI settings are not configured for this user.') from exc
        effective = _get_effective_ai_settings(settings_obj)

        sanitized_payload = _sanitize_prompt_text(case.raw_payload)
        prompt = (
            "Return ONLY JSON with keys: short_description, detection_objective, mapped_ttps, "
            "estimated_detection_complexity. Keep short_description <= 400 chars. "
            "mapped_ttps must be an array of ATT&CK IDs.\n\n"
            f"Title: {_sanitize_prompt_text(case.title, 300)}\n"
            f"Short description: {_sanitize_prompt_text(case.short_description, 1200)}\n"
            f"Detection objective: {_sanitize_prompt_text(case.detection_objective, 1200)}\n"
            f"Mapped TTPs: {_sanitize_prompt_text(case.mapped_ttps, 600)}\n"
            f"Raw payload: {sanitized_payload}"
        )
        raw_response, provider = run_custom_prompt(
            effective,
            prompt,
            system_prompt=(
                "You are a senior detection engineer. Produce concise detection triage enrichment. "
                "Output valid JSON only."
            ),
        )

        payload = _extract_json_payload(raw_response)
        short_description = str(payload.get('short_description') or case.short_description or '').strip()
        detection_objective = str(payload.get('detection_objective') or case.detection_objective or '').strip()
        mapped_ttps = _normalize_ttps(payload.get('mapped_ttps') or case.mapped_ttps)
        complexity = str(payload.get('estimated_detection_complexity') or case.estimated_detection_complexity or '').strip()

        case.short_description = short_description
        case.detection_objective = detection_objective
        case.mapped_ttps = mapped_ttps
        case.estimated_detection_complexity = complexity
        case.status = WaitingCase.LifecycleStatus.READY
        case.enrichment_error = ''
        case.save(
            update_fields=[
                'short_description',
                'detection_objective',
                'mapped_ttps',
                'estimated_detection_complexity',
                'status',
                'enrichment_error',
                'updated_at',
            ]
        )

        task.status = WaitingCaseEnrichmentTask.TaskStatus.COMPLETED
        task.result_data = {'provider': provider, 'payload': payload}
        task.completed_at = timezone.now()
        task.error_message = ''
        task.save(update_fields=['status', 'result_data', 'completed_at', 'error_message'])
    except Exception as exc:
        try:
            case = task.waiting_case
            case.status = WaitingCase.LifecycleStatus.FAILED
            case.enrichment_error = str(exc)
            case.save(update_fields=['status', 'enrichment_error', 'updated_at'])
        except Exception:
            pass
        task.status = WaitingCaseEnrichmentTask.TaskStatus.FAILED
        task.error_message = str(exc)
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'error_message', 'completed_at'])
    finally:
        close_old_connections()


def queue_waiting_case_enrichment(waiting_case: WaitingCase, requested_by) -> WaitingCaseEnrichmentTask:
    task = WaitingCaseEnrichmentTask.objects.create(
        waiting_case=waiting_case,
        requested_by=requested_by,
        status=WaitingCaseEnrichmentTask.TaskStatus.PENDING,
    )
    waiting_case.status = WaitingCase.LifecycleStatus.ENRICHING
    waiting_case.enrichment_error = ''
    waiting_case.save(update_fields=['status', 'enrichment_error', 'updated_at'])

    threading.Thread(
        target=_run_enrichment,
        args=(str(task.id),),
        daemon=True,
        name=f'waiting-case-enrichment-{task.id}',
    ).start()
    return task
