"""Django management command that starts the MVE validation worker."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Start the Machina Velocity Engine validation worker - a long-running "
        "RabbitMQ consumer that processes async MVE validation runs."
    )

    def handle(self, *args, **options):
        from playbooks.mve_validation_worker import main

        self.stdout.write(self.style.SUCCESS("Starting MVE validation worker..."))
        main()
