"""
Import the Adversarial Detection Engineering (ADE) framework into a staged ``AdeSnapshot``.

Mirrors ``import_detection_chokepoints``: the command never activates a snapshot. An admin
reviews the diff on the Framework Updates page and promotes it.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from platform_data.ade_sync import (
    DEFAULT_ADE_REF,
    DEFAULT_ADE_REPO,
    KIND_SUBCATEGORY,
    build_entries,
    fetch_latest_ade_sha,
    fetch_remote_ade_text,
    list_remote_ade_paths,
    normalize_git_ref,
    select_ade_paths,
)
from platform_data.models import AdeEntry, AdeSnapshot


class Command(BaseCommand):
    help = "Import ADE framework content (taxonomy, likelihood checks, DLE, ITW) into a staged snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--source-repo", type=str, default=DEFAULT_ADE_REPO)
        parser.add_argument("--ref", type=str, default=DEFAULT_ADE_REF)
        parser.add_argument("--mode", type=str, choices=["remote", "local"], default="remote")
        parser.add_argument("--dir", type=str, default=None, help="Local checkout (required for --mode=local).")
        parser.add_argument("--snapshot-id", type=str, default=None, help="Existing AdeSnapshot UUID to refill.")

    def handle(self, *args, **options):
        mode = (options.get("mode") or "remote").lower().strip()
        source_repo = (options.get("source_repo") or DEFAULT_ADE_REPO).strip()
        source_ref = normalize_git_ref(options.get("ref"), default=DEFAULT_ADE_REF)
        snapshot_id = (options.get("snapshot_id") or "").strip() or None

        if mode == "local" and not options.get("dir"):
            raise CommandError("--dir is required when --mode=local")

        if snapshot_id:
            snapshot = AdeSnapshot.objects.get(id=snapshot_id)
            snapshot.status = AdeSnapshot.Status.STAGED
            snapshot.source_repo = source_repo
            snapshot.source_ref = source_ref
            snapshot.validation_errors = ""
            snapshot.summary = {}
            snapshot.entry_count = 0
            snapshot.save(update_fields=[
                "status", "source_repo", "source_ref", "validation_errors",
                "summary", "entry_count", "updated_at",
            ])
        else:
            snapshot = AdeSnapshot.objects.create(
                source_repo=source_repo, source_ref=source_ref, status=AdeSnapshot.Status.STAGED,
            )

        warnings: list[str] = []
        failed_paths: list[str] = []
        resolved_sha = ""

        try:
            file_rows: list[tuple[str, str]] = []
            if mode == "remote":
                try:
                    resolved_sha = fetch_latest_ade_sha(source_repo, source_ref) or ""
                except Exception as exc:
                    warnings.append(f"Could not resolve latest SHA for ref '{source_ref}': {exc}")
                paths = list_remote_ade_paths(source_repo, source_ref)
                if not paths:
                    raise CommandError("No ADE files found in the remote repository (layout may have changed).")
                for path in paths:
                    try:
                        file_rows.append((path, fetch_remote_ade_text(source_repo, source_ref, path)))
                    except Exception as exc:
                        failed_paths.append(path)
                        warnings.append(f"Failed to fetch {path}: {exc}")
            else:
                base_dir = Path(options["dir"]).expanduser().resolve()
                if not base_dir.exists():
                    raise CommandError(f"Local directory does not exist: {base_dir}")
                rel_paths = [
                    str(p.relative_to(base_dir)).replace("\\", "/")
                    for p in base_dir.rglob("*")
                    if p.is_file() and ".git" not in p.relative_to(base_dir).parts
                ]
                for rel in select_ade_paths(rel_paths):
                    file_rows.append((rel, (base_dir / rel).read_text(encoding="utf-8")))
                if not file_rows:
                    raise CommandError(f"No ADE files found under {base_dir}")

            built = build_entries(file_rows)
            warnings.extend(built["warnings"])
            entries = built["entries"]
            counts = built["counts"]

            summary = {
                "mode": mode.upper(),
                "source_repo": source_repo,
                "source_ref": source_ref,
                "source_sha": resolved_sha,
                "processed_files": len(file_rows),
                "failed_files": len(failed_paths),
                "failed_paths": failed_paths[:100],
                "counts": counts,
                "imported_entries": len(entries),
                "warning_count": len(warnings),
            }
            # The taxonomy is the point of this framework. If no subcategory parsed, the upstream
            # layout probably changed, so the snapshot must be FAILED and never promotable.
            has_taxonomy = counts.get(KIND_SUBCATEGORY, 0) > 0

            with transaction.atomic():
                AdeEntry.objects.filter(snapshot=snapshot).delete()
                if entries:
                    AdeEntry.objects.bulk_create(
                        [AdeEntry(snapshot=snapshot, **row) for row in entries], batch_size=500,
                    )
                snapshot.source_sha = resolved_sha or snapshot.source_sha
                snapshot.status = AdeSnapshot.Status.STAGED if has_taxonomy else AdeSnapshot.Status.FAILED
                snapshot.entry_count = len(entries)
                snapshot.summary = summary
                snapshot.validation_errors = "\n".join(warnings[:500])
                snapshot.save(update_fields=[
                    "source_sha", "status", "entry_count", "summary", "validation_errors", "updated_at",
                ])
            if not has_taxonomy:
                raise CommandError("ADE import found no taxonomy subcategories; upstream layout may have changed.")
            self.stdout.write(self.style.SUCCESS(
                f"Imported {len(entries)} ADE entries {counts} from {len(file_rows)} files "
                f"(warnings: {len(warnings)}). Snapshot={snapshot.id}"
            ))
        except Exception as exc:
            snapshot.status = AdeSnapshot.Status.FAILED
            snapshot.validation_errors = (
                f"{exc}\n\n{snapshot.validation_errors}".strip() if snapshot.validation_errors else str(exc)
            )
            snapshot.save(update_fields=["status", "validation_errors", "updated_at"])
            raise
