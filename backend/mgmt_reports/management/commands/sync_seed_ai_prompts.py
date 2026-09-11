from django.core.management.base import BaseCommand

from mgmt_reports.prompt_catalog import sync_system_prompts


class Command(BaseCommand):
    help = (
        "Sync MGMT Cave system AI prompts from the versioned catalog. "
        "Use this after prompt upgrades so existing environments receive updates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview create/update/deactivate counts without writing changes.",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Deactivate system prompts that are not in the current catalog.",
        )

    def handle(self, *args, **options):
        result = sync_system_prompts(
            dry_run=bool(options.get("dry_run")),
            deactivate_missing=bool(options.get("deactivate_missing")),
        )
        mode = "DRY-RUN" if result["dry_run"] else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"[{mode}] Prompt sync complete | version={result['catalog_version']} "
                    f"| catalog_size={result['catalog_size']} | created={result['created']} "
                    f"| updated={result['updated']} | deactivated={result['deactivated']}"
                )
            )
        )
