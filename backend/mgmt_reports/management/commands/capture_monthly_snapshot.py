"""
Management command: capture a monthly statistics snapshot for all organizations.

Run this once per month (e.g. on the 1st) via cron or a scheduled task:
    python manage.py capture_monthly_snapshot

It will store a MonthlyReportSnapshot for the previous calendar month so that
the historical trend queries have data to display.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Capture a monthly statistics snapshot for all organizations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year', type=int,
            help='Override year (default: previous month\'s year)',
        )
        parser.add_argument(
            '--month', type=int,
            help='Override month 1-12 (default: previous month)',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Overwrite an existing snapshot for the same period',
        )

    def handle(self, *args, **options):
        from datetime import timedelta
        from organizations.models import Organization
        from mgmt_reports.models import MonthlyReportSnapshot
        from mgmt_reports.schema import _compute_mgmt_cave_stats_payload

        now = timezone.now()

        if options['year'] and options['month']:
            year, month = options['year'], options['month']
        else:
            # Default: snapshot for the previous calendar month
            first_of_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            prev_month_last = first_of_current - timedelta(days=1)
            year, month = prev_month_last.year, prev_month_last.month

        # Use the last day of the target month as the reference point for "last 30d"
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        snapshot_date = now.replace(year=year, month=month, day=last_day,
                                    hour=23, minute=59, second=59, microsecond=0)
        last_30d = snapshot_date - timedelta(days=30)

        orgs = Organization.objects.all()
        created_count = 0
        skipped_count = 0

        for org in orgs:
            if not options['force']:
                if MonthlyReportSnapshot.objects.filter(organization=org, year=year, month=month).exists():
                    self.stdout.write(
                        self.style.WARNING(f'  Skipping {org} {year}-{month:02d} (already exists)')
                    )
                    skipped_count += 1
                    continue

            payload = _compute_mgmt_cave_stats_payload(org, last_30d)
            MonthlyReportSnapshot.objects.update_or_create(
                organization=org,
                year=year,
                month=month,
                defaults={'stats_json': payload},
            )
            created_count += 1
            self.stdout.write(self.style.SUCCESS(f'  Captured snapshot for {org} {year}-{month:02d}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Created/updated: {created_count}, skipped: {skipped_count}'
            )
        )
