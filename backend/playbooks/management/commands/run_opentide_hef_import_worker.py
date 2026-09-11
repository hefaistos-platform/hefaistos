"""Django management command that starts the OpenTIDE HEF import worker."""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Start the OpenTIDE HEF import worker - a long-running RabbitMQ consumer '
        'that processes async HEF import jobs queued by queueOpenTideHefImport.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--max-retries', type=int, default=10)
        parser.add_argument('--retry-delay', type=int, default=5)

    def handle(self, *args, **options):
        from playbooks.hef_import_worker import run_worker

        self.stdout.write(self.style.SUCCESS('Starting OpenTIDE HEF import worker...'))
        run_worker(
            max_retries=options['max_retries'],
            retry_delay=options['retry_delay'],
        )
        self.stdout.write(self.style.WARNING('OpenTIDE HEF import worker stopped.'))
