"""
Management command to run scheduled repository RAG template sync jobs.
This command should be run periodically by the scheduler service.
"""
import logging
import os
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from rules.models import RuleRepository
from services.publisher import get_publisher

logger = logging.getLogger(__name__)

DEFAULT_STALE_THRESHOLD_MINUTES = 90
ACTIVE_RAG_SYNC_STATUSES = (
    RuleRepository.RAGSyncStatus.QUEUED,
    RuleRepository.RAGSyncStatus.RUNNING,
)


def _parse_stale_threshold_minutes() -> int:
    raw_value = str(os.environ.get('RAG_SYNC_STALE_THRESHOLD_MINUTES', DEFAULT_STALE_THRESHOLD_MINUTES)).strip()
    try:
        return max(int(raw_value), 10)
    except ValueError:
        logger.warning(
            "Invalid RAG_SYNC_STALE_THRESHOLD_MINUTES='%s'. Falling back to %s minutes.",
            raw_value,
            DEFAULT_STALE_THRESHOLD_MINUTES,
        )
        return DEFAULT_STALE_THRESHOLD_MINUTES


def _parse_requeue_stale_enabled() -> bool:
    raw_value = str(os.environ.get('RAG_SYNC_WATCHDOG_REQUEUE_STALE', 'true')).strip().lower()
    return raw_value not in {'0', 'false', 'no', 'off'}


def _compute_next_scheduled_at(schedule_value: str):
    schedule = (schedule_value or '').upper()
    schedule_hours = {
        '24H': 24,
        '48H': 48,
        '72H': 72,
        'WEEKLY': 168,
    }
    hours = schedule_hours.get(schedule)
    if not hours:
        return None
    return timezone.now() + timedelta(hours=hours)


class Command(BaseCommand):
    help = 'Processes scheduled repository RAG sync jobs that are due for execution.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually queueing jobs',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()
        stale_threshold_minutes = _parse_stale_threshold_minutes()
        requeue_stale_enabled = _parse_requeue_stale_enabled()
        stale_cutoff = now - timedelta(minutes=stale_threshold_minutes)

        self.stdout.write(f'[{now}] Checking for scheduled repository RAG sync jobs...')

        stale_repos = RuleRepository.objects.filter(
            rag_sync_enabled=True,
            rag_last_sync_status__in=ACTIVE_RAG_SYNC_STATUSES,
        ).exclude(
            rag_sync_schedule=RuleRepository.RAGSyncSchedule.DISABLED,
        ).filter(
            Q(rag_last_sync_status_at__lte=stale_cutoff)
            | Q(rag_last_sync_status_at__isnull=True, updated_at__lte=stale_cutoff)
        )

        if stale_repos.exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Found {stale_repos.count()} stale RAG sync statuses '
                    f'(>{stale_threshold_minutes} minutes).'
                )
            )

            for repo in stale_repos:
                stale_status = (repo.rag_last_sync_status or 'UNKNOWN').upper()
                stale_message = (
                    f"Watchdog marked stale {stale_status} sync as FAILED after "
                    f"{stale_threshold_minutes} minutes without completion."
                )

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  -- [DRY RUN] Would mark stale status FAILED for: {repo.name} '
                            f'(status={stale_status})'
                        )
                    )
                    continue

                repo.rag_last_sync_status = RuleRepository.RAGSyncStatus.FAILED
                repo.rag_last_sync_status_at = now
                repo.rag_last_sync_error = stale_message
                repo.rag_last_synced = now
                update_fields = [
                    'rag_last_sync_status',
                    'rag_last_sync_status_at',
                    'rag_last_sync_error',
                    'rag_last_synced',
                ]

                if requeue_stale_enabled:
                    repo.rag_next_scheduled_sync = now
                    update_fields.append('rag_next_scheduled_sync')

                repo.save(update_fields=update_fields)
                logger.warning(
                    "Watchdog marked stale RAG sync as FAILED for repository %s (previous=%s, requeue=%s)",
                    repo.id,
                    stale_status,
                    requeue_stale_enabled,
                )

        repos_to_sync = RuleRepository.objects.filter(
            rag_sync_enabled=True,
        ).exclude(
            rag_sync_schedule=RuleRepository.RAGSyncSchedule.DISABLED,
        ).exclude(
            rag_last_sync_status__in=ACTIVE_RAG_SYNC_STATUSES,
        ).filter(
            Q(rag_next_scheduled_sync__lte=now) | Q(rag_next_scheduled_sync__isnull=True)
        )

        if not repos_to_sync.exists():
            self.stdout.write(self.style.WARNING('No repositories are due for scheduled RAG sync.'))
            return

        self.stdout.write(f'Found {repos_to_sync.count()} repositories due for scheduled RAG sync.')

        publisher = None if dry_run else get_publisher()
        successful = 0
        failed = 0

        for repo in repos_to_sync:
            try:
                self.stdout.write(f'  -- Processing: {repo.name} (Org: {repo.organization.name})')

                next_sync = _compute_next_scheduled_at(repo.rag_sync_schedule)

                if dry_run:
                    self.stdout.write(self.style.SUCCESS(f'    [DRY RUN] Would queue RAG sync for {repo.name}'))
                else:
                    routing_key = 'rule.repo.rag.sync.requested'
                    message_body = {
                        'action': 'sync_rag_repo',
                        'repository_id': str(repo.id),
                        'organization_id': str(repo.organization.id),
                        'triggered_by_user_id': None,
                        'scheduled': True,
                    }
                    publisher.publish_message(routing_key, message_body)
                    repo.rag_last_sync_status = RuleRepository.RAGSyncStatus.QUEUED
                    repo.rag_last_sync_status_at = now
                    repo.rag_last_sync_error = ''
                    repo.rag_next_scheduled_sync = next_sync
                    repo.save(
                        update_fields=[
                            'rag_last_sync_status',
                            'rag_last_sync_status_at',
                            'rag_last_sync_error',
                            'rag_next_scheduled_sync',
                        ]
                    )
                    logger.info(
                        "Scheduled RAG sync queued for repository %s, next sync at %s",
                        repo.name,
                        next_sync,
                    )
                    self.stdout.write(self.style.SUCCESS(f'    Queued RAG sync for {repo.name}'))

                if next_sync:
                    self.stdout.write(f'    Next scheduled RAG sync: {next_sync}')
                successful += 1
            except Exception as e:
                failed += 1
                self.stderr.write(self.style.ERROR(f'    Error processing {repo.name}: {e}'))
                logger.exception("Error during scheduled RAG sync for repository %s", repo.id)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Completed: {successful} successful, {failed} failed'))
