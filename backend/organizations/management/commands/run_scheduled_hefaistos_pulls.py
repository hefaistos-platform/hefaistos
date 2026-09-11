"""Run scheduled HEFAISTOS remote peer PULL jobs."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from identity.models import CustomUser
from organizations.models import HefaistosRemotePeer
from organizations.sharing import compute_next_auto_pull_at, pull_from_remote_peer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Processes scheduled HEFAISTOS remote peer pulls that are due for execution.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be pulled without executing pull jobs.',
        )

    @staticmethod
    def _select_actor(peer: HefaistosRemotePeer):
        if peer.created_by and peer.created_by.organization_id == peer.organization_id:
            return peer.created_by
        admin_user = CustomUser.objects.filter(
            organization=peer.organization,
            role='ADMIN',
        ).order_by('id').first()
        if admin_user:
            return admin_user
        return CustomUser.objects.filter(organization=peer.organization).order_by('id').first()

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()

        self.stdout.write(f'[{now}] Checking for scheduled HEFAISTOS remote pulls...')

        peers_to_pull = list(
            HefaistosRemotePeer.objects.filter(
                enabled=True,
                auto_pull_enabled=True,
            ).filter(
                Q(next_auto_pull_at__lte=now) | Q(next_auto_pull_at__isnull=True),
            ).select_related(
                'organization',
                'created_by',
            ).order_by('name')
        )

        if not peers_to_pull:
            self.stdout.write(self.style.WARNING('No remote peers are due for scheduled PULL.'))
            return

        self.stdout.write(f'Found {len(peers_to_pull)} remote peer(s) due for scheduled PULL.')
        successful = 0
        failed = 0

        for peer in peers_to_pull:
            schedule = peer.auto_pull_schedule or 'DAILY'
            self.stdout.write(f'  -- Processing peer: {peer.name} (Org: {peer.organization.name})')

            if dry_run:
                next_pull = compute_next_auto_pull_at(schedule, from_time=now)
                self.stdout.write(self.style.SUCCESS(f'    [DRY RUN] Would trigger PULL; next auto pull at {next_pull}'))
                successful += 1
                continue

            actor = self._select_actor(peer)
            if actor is None:
                failed += 1
                self.stderr.write(self.style.ERROR('    No eligible actor found in organization; skipping peer.'))
                logger.warning(
                    'Scheduled HEFAISTOS pull skipped for peer=%s org=%s: no actor available',
                    peer.id,
                    peer.organization_id,
                )
                peer.next_auto_pull_at = compute_next_auto_pull_at(schedule, from_time=timezone.now())
                peer.save(update_fields=['next_auto_pull_at', 'updated_at'])
                continue

            try:
                pull_from_remote_peer(peer, actor=actor, requested_scope=peer.default_scope)
                successful += 1
                self.stdout.write(self.style.SUCCESS('    Pull executed successfully.'))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f'    Pull failed: {exc}'))
                logger.exception(
                    'Error during scheduled HEFAISTOS pull for peer=%s org=%s',
                    peer.id,
                    peer.organization_id,
                )
            finally:
                peer.next_auto_pull_at = compute_next_auto_pull_at(schedule, from_time=timezone.now())
                peer.save(update_fields=['next_auto_pull_at', 'updated_at'])
                self.stdout.write(f'    Next scheduled pull: {peer.next_auto_pull_at}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Completed: {successful} successful, {failed} failed'))
