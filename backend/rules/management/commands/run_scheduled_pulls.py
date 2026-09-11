"""
Management command to run scheduled repository pulls.
This command should be run periodically via cron or Celery beat.
Example: */30 * * * * python manage.py run_scheduled_pulls
"""
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from rules.models import RuleRepository
from services.publisher import get_publisher

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Processes scheduled repository pulls that are due for execution.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be pulled without actually triggering pulls',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()

        self.stdout.write(f'[{now}] Checking for scheduled repository pulls...')

        # Find repositories that:
        # 1. Have auto_pull_enabled = True
        # 2. Have next_scheduled_pull <= now (or null, meaning never pulled on schedule)
        due_repos = RuleRepository.objects.filter(
            auto_pull_enabled=True,
            next_scheduled_pull__lte=now
        )

        # Also get repos where auto_pull is enabled but next_scheduled_pull is null
        # (first scheduled pull hasn't been set up yet)
        never_scheduled = RuleRepository.objects.filter(
            auto_pull_enabled=True,
            next_scheduled_pull__isnull=True
        )

        repos_to_pull = list(due_repos) + list(never_scheduled)

        if not repos_to_pull:
            self.stdout.write(self.style.WARNING('No repositories are due for scheduled pull.'))
            return

        self.stdout.write(f'Found {len(repos_to_pull)} repositories due for scheduled pull.')

        publisher = None if dry_run else get_publisher()
        successful = 0
        failed = 0

        for repo in repos_to_pull:
            try:
                self.stdout.write(f'  -- Processing: {repo.name} (Org: {repo.organization.name})')

                if dry_run:
                    self.stdout.write(self.style.SUCCESS(f'    [DRY RUN] Would trigger pull for {repo.name}'))
                else:
                    # Publish pull request to RabbitMQ (same pattern as PullRuleRepository mutation)
                    routing_key = "rule.repo.pull.requested"
                    message_body = {
                        "action": "pull_repo",
                        "repository_id": str(repo.id),
                        "organization_id": str(repo.organization.id),
                        "triggered_by_user_id": None,  # System-triggered, no user
                        "scheduled": True  # Flag to indicate this was a scheduled pull
                    }
                    publisher.publish_message(routing_key, message_body)
                    self.stdout.write(self.style.SUCCESS(f'    Published pull request for {repo.name}'))

                # Calculate next scheduled pull time based on schedule
                hours_map = {
                    '24H': 24,
                    '48H': 48,
                    '72H': 72,
                    'WEEKLY': 168,  # 7 * 24
                }
                schedule_hours = hours_map.get(repo.auto_pull_schedule, 24)
                next_pull = now + timedelta(hours=schedule_hours)

                if not dry_run:
                    repo.next_scheduled_pull = next_pull
                    repo.save(update_fields=['next_scheduled_pull'])
                    logger.info(f"Scheduled pull triggered for repository {repo.name}, next pull at {next_pull}")

                self.stdout.write(f'    Next scheduled pull: {next_pull}')
                successful += 1

            except Exception as e:
                failed += 1
                self.stderr.write(self.style.ERROR(f'    Error processing {repo.name}: {e}'))
                logger.exception(f"Error during scheduled pull for repository {repo.id}")

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Completed: {successful} successful, {failed} failed'))
