"""
Management command: export_opentide_vocab

Exports ShareTide vocabulary entries from the database to an OpenTide
``Configurations/schema.toml`` file.  This file can then be committed to an
InitTide / OpenTide-TOS repository so that the OpenTide engine recognises the
custom vocabulary during pipeline runs.

Usage::

    # Write all supported vocab categories to a schema.toml file
    python manage.py export_opentide_vocab --output /path/to/Configurations/schema.toml

    # Export only specific categories
    python manage.py export_opentide_vocab \\
        --output schema.toml \\
        --categories dom_log_sources tvm_surface

    # Overwrite instead of merging with any existing file
    python manage.py export_opentide_vocab --output schema.toml --overwrite
"""

from __future__ import annotations

import os
from typing import List

from django.core.management.base import BaseCommand, CommandError

from playbooks.utils.schema_toml import (
    CATEGORY_TO_TOML_KEY,
    sharetide_entries_to_toml_entries,
    write_vocab_to_schema_toml,
)

# Categories exported by default (those with a schema.toml key mapping)
_DEFAULT_CATEGORIES: List[str] = list(CATEGORY_TO_TOML_KEY.keys())


class Command(BaseCommand):
    help = (
        "Export ShareTide vocabulary from the database to a "
        "Configurations/schema.toml file for use with an OpenTide repository."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            required=True,
            metavar="PATH",
            help="Destination path for the schema.toml file (created if absent).",
        )
        parser.add_argument(
            "--categories",
            nargs="+",
            default=None,
            metavar="CATEGORY",
            help=(
                "One or more ShareTideIndexEntry category names to export "
                f"(default: {', '.join(_DEFAULT_CATEGORIES)})."
            ),
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            default=False,
            help="Overwrite the output file instead of merging with existing entries.",
        )

    def handle(self, *args, **options):
        from platform_data.models import ShareTideIndexEntry

        categories: List[str] = options["categories"] or _DEFAULT_CATEGORIES
        output_path: str = os.path.abspath(options["output"])
        merge: bool = not options["overwrite"]

        # Validate requested categories
        unknown = [c for c in categories if c not in CATEGORY_TO_TOML_KEY]
        if unknown:
            self.stdout.write(
                self.style.WARNING(
                    f"Warning: the following categories have no schema.toml key mapping "
                    f"and will be skipped: {', '.join(unknown)}"
                )
            )
            categories = [c for c in categories if c in CATEGORY_TO_TOML_KEY]

        if not categories:
            raise CommandError("No exportable categories selected.")

        entries_by_category: dict = {}
        for category in categories:
            db_entries = list(
                ShareTideIndexEntry.objects
                .filter(category=category)
                .order_by('sort_order', 'value')
            )
            if not db_entries:
                self.stdout.write(
                    self.style.WARNING(f"No entries found for category '{category}' — skipping.")
                )
                continue
            entries_by_category[category] = sharetide_entries_to_toml_entries(
                category, db_entries
            )

        if not entries_by_category:
            raise CommandError("No vocabulary entries found to export.")

        try:
            write_vocab_to_schema_toml(output_path, entries_by_category, merge=merge)
        except Exception as exc:
            raise CommandError(f"Failed to write schema.toml: {exc}") from exc

        total = sum(len(v) for v in entries_by_category.values())
        action = "Merged" if merge else "Wrote"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {total} vocabulary entries across {len(entries_by_category)} "
                f"categories to {output_path}"
            )
        )
