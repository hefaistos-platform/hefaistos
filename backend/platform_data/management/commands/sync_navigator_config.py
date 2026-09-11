from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from platform_data.navigator_sync import rebuild_navigator_config_only


class Command(BaseCommand):
    help = (
        "Rebuild /navigator-data/config.json and /navigator-data/data/index.json "
        "from already-downloaded local ATT&CK STIX bundles (no remote download)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--attack-version",
            type=str,
            help=(
                "ATT&CK version to anchor config/index generation (e.g. 19.1). "
                "If omitted, the newest local version with bundle files is used."
            ),
        )
        parser.add_argument(
            "--data-root",
            type=str,
            default="/navigator-data",
            help="Navigator data root directory (default: /navigator-data).",
        )

    def handle(self, *args, **options):
        version = options.get("attack_version")
        data_root = Path(options["data_root"])
        try:
            resolved = rebuild_navigator_config_only(version=version, data_root=data_root)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Navigator config/index refreshed successfully (version v{resolved}) at {data_root}."
            )
        )
