"""Run scheduled MISP-to-Waiting-Room auto-pull jobs.

Mirrors organizations/management/commands/run_scheduled_hefaistos_pulls.py, adapted
for MISPInstance.auto_pull_enabled / auto_pull_schedule / auto_pull_tag / next_auto_pull_at.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from identity.models import CustomUser
from organizations.models import MISPInstance
from waiting_room.misp import import_waiting_cases_from_misp

logger = logging.getLogger(__name__)

_SCHEDULE_DELTAS = {
    'HOURLY': timedelta(hours=1),
    'DAILY': timedelta(days=1),
    'WEEKLY': timedelta(days=7),
}


def compute_next_misp_auto_pull_at(schedule: str, from_time=None):
    base = from_time or timezone.now()
    delta = _SCHEDULE_DELTAS.get(str(schedule or 'DAILY').strip().upper(), _SCHEDULE_DELTAS['DAILY'])
    return base + delta


class Command(BaseCommand):
    help = 'Processes scheduled MISP Waiting Room auto-pulls that are due for execution.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be pulled without executing the import.',
        )

    @staticmethod
    def _select_actor(instance: MISPInstance):
        admin_user = CustomUser.objects.filter(
            organization=instance.organization,
            role='ADMIN',
        ).order_by('id').first()
        if admin_user:
            return admin_user
        return CustomUser.objects.filter(organization=instance.organization).order_by('id').first()

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()

        self.stdout.write(f'[{now}] Checking for scheduled MISP auto-pulls...')

        instances_to_pull = list(
            MISPInstance.objects.filter(
                auto_pull_enabled=True,
            ).filter(
                Q(next_auto_pull_at__lte=now) | Q(next_auto_pull_at__isnull=True),
            ).select_related('organization').order_by('name')
        )

        if not instances_to_pull:
            self.stdout.write(self.style.WARNING('No MISP instances are due for scheduled auto-pull.'))
            return

        self.stdout.write(f'Found {len(instances_to_pull)} MISP instance(s) due for scheduled auto-pull.')
        successful = 0
        failed = 0

        for instance in instances_to_pull:
            schedule = instance.auto_pull_schedule or 'DAILY'
            tag = instance.auto_pull_tag or ''
            self.stdout.write(
                f'  -- Processing instance: {instance.name} (Org: {instance.organization.name}, tag={tag or "<none>"})'
            )

            if dry_run:
                next_pull = compute_next_misp_auto_pull_at(schedule, from_time=now)
                self.stdout.write(
                    self.style.SUCCESS(f'    [DRY RUN] Would trigger import; next auto pull at {next_pull}')
                )
                successful += 1
                continue

            actor = self._select_actor(instance)
            if actor is None:
                failed += 1
                self.stderr.write(self.style.ERROR('    No eligible actor found in organization; skipping instance.'))
                logger.warning(
                    'Scheduled MISP auto-pull skipped for instance=%s org=%s: no actor available',
                    instance.id,
                    instance.organization_id,
                )
                instance.next_auto_pull_at = compute_next_misp_auto_pull_at(schedule, from_time=timezone.now())
                instance.save(update_fields=['next_auto_pull_at', 'updated_at'])
                continue

            try:
                result = import_waiting_cases_from_misp(
                    instance=instance,
                    user=actor,
                    tag=tag or None,
                    limit=25,
                    run_ai_enrichment=False,
                )
                successful += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"    Import executed: {result['imported_count']} imported, "
                        f"{result['skipped_count']} skipped."
                    )
                )
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f'    Import failed: {exc}'))
                logger.exception(
                    'Error during scheduled MISP auto-pull for instance=%s org=%s',
                    instance.id,
                    instance.organization_id,
                )
            finally:
                instance.next_auto_pull_at = compute_next_misp_auto_pull_at(schedule, from_time=timezone.now())
                instance.save(update_fields=['next_auto_pull_at', 'updated_at'])
                self.stdout.write(f'    Next scheduled auto-pull: {instance.next_auto_pull_at}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Completed: {successful} successful, {failed} failed'))
