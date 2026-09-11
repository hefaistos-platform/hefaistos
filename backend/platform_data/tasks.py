"""
Async runners for platform-data import jobs.

Uses background threads so GraphQL mutations can return immediately while
long-running management commands execute. Job records are updated with status,
logs, and timestamps.
"""
import io
import logging
import threading
from datetime import datetime, timezone

from core.mcs_logging import emit_security_event

logger = logging.getLogger(__name__)


def _emit_import_audit_event(
    *,
    framework: str,
    action: str,
    outcome: str,
    level: str,
    reason: str,
    user_id: str | None,
    user_name: str | None,
    extra_context: dict | None = None,
):
    try:
        emit_security_event(
            level=level,
            logger_name='security.mcs',
            message=f'{framework} import {action}: {outcome}',
            event_action=f'platform_data.import.{framework}.{action}',
            event_outcome=outcome,
            asvs_event_code='BIZLOGIC-PLATFORM-DATA-IMPORT-01',
            event_reason=reason,
            user_id=user_id,
            user_name=user_name,
            extra_context=extra_context or {},
        )
    except Exception as exc:  # pragma: no cover - best effort audit trail
        logger.debug('Failed to emit platform-data import audit event: %s', exc)


def run_mitre_import_job(job_id: str) -> None:
    """
    Dispatch the import in a daemon thread.  Returns immediately; the thread
    updates the MitreImportJob row as it progresses.
    """
    t = threading.Thread(target=_execute_mitre_job, args=(job_id,), daemon=True)
    t.start()


def _execute_mitre_job(job_id: str) -> None:
    """Background thread: run the import command and persist results."""
    from django.core.management import call_command
    from platform_data.models import MitreImportJob

    try:
        job = MitreImportJob.objects.get(id=job_id)
    except MitreImportJob.DoesNotExist:
        logger.error("MitreImportJob %s not found", job_id)
        return

    job.status = MitreImportJob.Status.RUNNING
    job.started_at = datetime.now(tz=timezone.utc)
    job.save(update_fields=['status', 'started_at', 'updated_at'])

    _emit_import_audit_event(
        framework='mitre',
        action='start',
        outcome='success',
        level='informational',
        reason='MITRE import job started.',
        user_id=str(getattr(job.triggered_by, 'id', '') or '') or None,
        user_name=getattr(job.triggered_by, 'username', None),
        extra_context={
            'job_id': str(job.id),
            'version': job.version,
            'mode': job.mode,
        },
    )

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        call_command(
            'import_mitre_universal',
            mitre_version=job.version,
            mode=job.mode.lower(),
            stdout=stdout_buf,
            stderr=stderr_buf,
        )
        job.status = MitreImportJob.Status.SUCCESS
        job.error = stderr_buf.getvalue()
    except Exception as exc:
        logger.exception("MitreImportJob %s failed: %s", job_id, exc)
        job.status = MitreImportJob.Status.FAILED
        job.error = f"{exc}\n\n{stderr_buf.getvalue()}"

    job.log = stdout_buf.getvalue()
    job.finished_at = datetime.now(tz=timezone.utc)
    job.save(update_fields=['status', 'log', 'error', 'finished_at', 'updated_at'])

    _emit_import_audit_event(
        framework='mitre',
        action='finish',
        outcome='failure' if job.status == MitreImportJob.Status.FAILED else 'success',
        level='warning' if job.status == MitreImportJob.Status.FAILED else 'informational',
        reason=(job.error or job.log or job.status)[:500],
        user_id=str(getattr(job.triggered_by, 'id', '') or '') or None,
        user_name=getattr(job.triggered_by, 'username', None),
        extra_context={
            'job_id': str(job.id),
            'status': job.status,
            'mode': job.mode,
        },
    )


def run_chokepoint_import_job(job_id: str) -> None:
    """
    Dispatch a detection-chokepoints import in a daemon thread.
    """
    t = threading.Thread(target=_execute_chokepoint_job, args=(job_id,), daemon=True)
    t.start()


def _execute_chokepoint_job(job_id: str) -> None:
    """Background thread: run chokepoint import command and persist results."""
    from django.core.management import call_command
    from platform_data.models import ChokepointImportJob, ChokepointSnapshot

    try:
        job = ChokepointImportJob.objects.get(id=job_id)
    except ChokepointImportJob.DoesNotExist:
        logger.error("ChokepointImportJob %s not found", job_id)
        return

    job.status = ChokepointImportJob.Status.RUNNING
    job.started_at = datetime.now(tz=timezone.utc)
    job.save(update_fields=['status', 'started_at', 'updated_at'])

    _emit_import_audit_event(
        framework='chokepoints',
        action='start',
        outcome='success',
        level='informational',
        reason='Detection chokepoints import job started.',
        user_id=str(getattr(job.triggered_by, 'id', '') or '') or None,
        user_name=getattr(job.triggered_by, 'username', None),
        extra_context={
            'job_id': str(job.id),
            'source_repo': job.source_repo,
            'source_ref': job.source_ref,
            'mode': job.mode,
        },
    )

    snapshot = job.snapshot
    if snapshot is None:
        snapshot = ChokepointSnapshot.objects.create(
            source_repo=job.source_repo,
            source_ref=job.source_ref,
            status=ChokepointSnapshot.Status.STAGED,
            triggered_by=job.triggered_by,
        )
        job.snapshot = snapshot
        job.save(update_fields=['snapshot', 'updated_at'])

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        call_command(
            'import_detection_chokepoints',
            source_repo=job.source_repo,
            ref=job.source_ref,
            mode=job.mode.lower(),
            snapshot_id=str(snapshot.id),
            stdout=stdout_buf,
            stderr=stderr_buf,
        )
        snapshot.refresh_from_db(fields=['summary'])
        job.summary = snapshot.summary or {}
        job.status = ChokepointImportJob.Status.SUCCESS
        job.error = stderr_buf.getvalue()
    except Exception as exc:
        logger.exception("ChokepointImportJob %s failed: %s", job_id, exc)
        job.status = ChokepointImportJob.Status.FAILED
        job.error = f"{exc}\n\n{stderr_buf.getvalue()}"

    job.log = stdout_buf.getvalue()
    job.finished_at = datetime.now(tz=timezone.utc)
    job.save(update_fields=['status', 'summary', 'log', 'error', 'finished_at', 'updated_at'])

    _emit_import_audit_event(
        framework='chokepoints',
        action='finish',
        outcome='failure' if job.status == ChokepointImportJob.Status.FAILED else 'success',
        level='warning' if job.status == ChokepointImportJob.Status.FAILED else 'informational',
        reason=(job.error or job.log or job.status)[:500],
        user_id=str(getattr(job.triggered_by, 'id', '') or '') or None,
        user_name=getattr(job.triggered_by, 'username', None),
        extra_context={
            'job_id': str(job.id),
            'status': job.status,
            'mode': job.mode,
            'snapshot_id': str(job.snapshot_id) if job.snapshot_id else None,
        },
    )
