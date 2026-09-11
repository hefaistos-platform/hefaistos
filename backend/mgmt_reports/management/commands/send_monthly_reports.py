"""
Management command: send the monthly report email to all subscribed users.

Run on the 1st of each month (after capture_monthly_snapshot):
    python manage.py send_monthly_reports

Requires EMAIL_HOST / EMAIL_HOST_USER to be configured in settings.
"""
import calendar

from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone


_REPORT_EMAIL_SUBJECT = 'Hefaistos Monthly Security Operations Report'

_REPORT_EMAIL_BODY_TEMPLATE = """\
Hello {username},

Your monthly Hefaistos Security Operations report for {month_label} is ready.

--- Summary ---
ACH Analyses:       {ach_total} total  (+{ach_new} this month)
AdvOps Hunts:       {advops_total} total  (+{advops_new} this month)
Detection Workbenches: {wb_total} total  ({wb_active} actively deployed)
Detection Rules:    {rules_total} total  ({rules_active} active)

Log in to the MGMT Cave to view the full interactive report and AI insights:
{frontend_url}/mgmt-cave

---
You are receiving this email because you are listed as a report subscriber.
Administrators can manage the mailing list under MGMT Cave → Administration.
"""


class Command(BaseCommand):
    help = 'Send monthly report emails to all subscribed users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year', type=int,
            help='Override year for the report month',
        )
        parser.add_argument(
            '--month', type=int,
            help='Override month 1-12',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would be sent without actually sending',
        )

    def handle(self, *args, **options):
        from datetime import timedelta
        from django.conf import settings as django_settings
        from mgmt_reports.models import MonthlyReportSnapshot, ReportMailingList
        from mgmt_reports.schema import _compute_mgmt_cave_stats_payload

        now = timezone.now()
        if options['year'] and options['month']:
            year, month = options['year'], options['month']
        else:
            # Send report for previous calendar month
            first_of_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            prev = first_of_current - timedelta(days=1)
            year, month = prev.year, prev.month

        month_label = f'{calendar.month_name[month]} {year}'
        frontend_url = getattr(django_settings, 'FRONTEND_URL', 'https://localhost')

        subscribed = ReportMailingList.objects.filter(
            is_subscribed=True
        ).select_related('user', 'organization')

        sent_count = 0
        for entry in subscribed:
            user = entry.user
            org = entry.organization

            # Try to get the stored snapshot; fall back to live computation
            snap = MonthlyReportSnapshot.objects.filter(
                organization=org, year=year, month=month
            ).first()
            if snap:
                stats = snap.stats_json
            else:
                last_30d = now - timedelta(days=30)
                stats = _compute_mgmt_cave_stats_payload(org, last_30d)

            body = _REPORT_EMAIL_BODY_TEMPLATE.format(
                username=user.get_full_name() or user.username,
                month_label=month_label,
                ach_total=stats.get('ach', {}).get('total', 0),
                ach_new=stats.get('ach', {}).get('created_last_30d', 0),
                advops_total=stats.get('advops', {}).get('total', 0),
                advops_new=stats.get('advops', {}).get('created_last_30d', 0),
                wb_total=stats.get('workbench', {}).get('total', 0),
                wb_active=stats.get('workbench', {}).get('active_count', 0),
                rules_total=stats.get('rules', {}).get('total', 0),
                rules_active=stats.get('rules', {}).get('active_count', 0),
                frontend_url=frontend_url,
            )

            if options['dry_run']:
                self.stdout.write(
                    f'[DRY RUN] Would send to {user.email} ({user.username}) - {org}'
                )
                self.stdout.write(body)
                self.stdout.write('-' * 60)
            else:
                try:
                    message = EmailMessage(
                        subject=_REPORT_EMAIL_SUBJECT,
                        body=body,
                        from_email=django_settings.DEFAULT_FROM_EMAIL,
                        to=[django_settings.DEFAULT_FROM_EMAIL],
                        bcc=[user.email],
                    )
                    message.send(fail_silently=False)
                    sent_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  Sent to {user.email}'))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f'  Failed to send to {user.email}: {exc}'))

        if not options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'Done. Sent {sent_count} emails for {month_label}.'))
