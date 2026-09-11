import logging
from typing import List

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from news.models import NewsPost
from core.email_service import get_email_service
from core.email_templates import render_news_item_html, render_digest_html, render_simple_text

logger = logging.getLogger(__name__)


CATEGORY_EMOJI = {
    'UPDATE': '🔄',
    'OUTAGE': '⚠️',
    'FEATURE': '🚀',
    'MAINTENANCE': '🔧',
    'ANNOUNCEMENT': '📢',
    'SECURITY': '🔒'
}


class Command(BaseCommand):
    help = "Send a news digest email to all users with an email address."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20, help='Max number of recent news items to include')
        parser.add_argument('--dry-run', action='store_true', help='Print digest but do not send emails')

    def handle(self, *args, **options):
        limit = options['limit']
        dry = options['dry_run']

        service = get_email_service()
        
        # Check if email service is configured
        if not service.is_configured():
            self.stdout.write(self.style.ERROR('Email service is not configured. Check MAILGUN_API_KEY and MAILGUN_DOMAIN secrets.'))
            return

        # Gather active, published posts (most recent first)
        posts = NewsPost.objects.filter(is_published=True).order_by('-published_at')[:limit]
        if not posts:
            self.stdout.write(self.style.WARNING('No published news found.'))
            return

        items_html: List[str] = []
        for p in posts:
            emoji = CATEGORY_EMOJI.get(p.category, '')
            items_html.append(
                render_news_item_html(
                    title=p.title or 'News Update',
                    content_md=p.content,
                    category_label=f"{emoji} {p.category}",
                    priority=p.priority,
                    author_username=getattr(p.author, 'username', 'system'),
                    published_at_iso=(p.published_at or timezone.now()).isoformat(),
                )
            )

        html_body = render_digest_html(items_html)
        text_body = render_simple_text('Hefaistos News Digest', [f"- {p.title or p.content[:60]}" for p in posts])
        subject = f"Hefaistos News Digest ({timezone.now().date().isoformat()})"

        User = get_user_model()
        recipients = list(
            User.objects.filter(
                email_notify_news_digest=True,
            ).exclude(email__isnull=True).exclude(email__exact='').values_list('email', flat=True)
        )

        if not recipients:
            self.stdout.write(self.style.WARNING('No recipients found with email addresses.'))
            return

        self.stdout.write(self.style.SUCCESS(f"Preparing to send digest to {len(recipients)} recipients..."))

        if dry:
            print(subject)
            print(text_body[:400])
            return

        ok = service.send_message(
            to=recipients,
            subject=subject,
            text=text_body,
            html=html_body,
            hide_recipients=True,
        )
        if ok:
            self.stdout.write(self.style.SUCCESS('Digest sent successfully.'))
        else:
            self.stdout.write(self.style.ERROR('Failed to send digest. Check logs.'))
