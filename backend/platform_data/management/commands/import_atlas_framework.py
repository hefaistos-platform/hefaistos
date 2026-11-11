from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from platform_data.atlas_sync import (
    DEFAULT_ATLAS_REF,
    DEFAULT_ATLAS_REPO,
    fetch_latest_ref_sha,
    fetch_remote_atlas_text,
    list_remote_atlas_paths,
    normalize_git_ref,
)
from platform_data.models import (
    AtlasCaseStudy,
    AtlasMitigation,
    AtlasRelationship,
    AtlasTactic,
    AtlasTechnique,
    PlatformDataVersion,
)

ATLAS_ID_RE = re.compile(r"^AML\.(TA|T|M|CS)\d+.*$", re.IGNORECASE)


def _json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        candidates = [text, text.split("T")[0], text.split(" ")[0]]
        for candidate in candidates:
            if len(candidate) >= 8:
                try:
                    return date.fromisoformat(candidate[:10])
                except ValueError:
                    continue
    return None


def _extract_record_id(record: dict[str, Any]) -> str:
    for key in ("atlas_id", "id", "external_id", "atlasId"):
        value = record.get(key)
        if isinstance(value, str) and ATLAS_ID_RE.match(value.strip()):
            return value.strip().upper()
    if isinstance(record.get("x_mitre_atlas"), dict):
        for key in ("id", "atlas_id", "external_id"):
            value = record["x_mitre_atlas"].get(key)
            if isinstance(value, str) and ATLAS_ID_RE.match(value.strip()):
                return value.strip().upper()
    return ""


def _extract_references(raw: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not raw:
        return refs
    for item in _as_list(raw):
        if not isinstance(item, dict):
            continue
        ref = {
            "source_name": _normalize_text(item.get("source_name") or item.get("sourceName")),
            "external_id": _normalize_text(item.get("external_id") or item.get("externalId")),
            "url": _normalize_text(item.get("url")),
            "description": _normalize_text(item.get("description")),
        }
        if ref["source_name"] or ref["external_id"] or ref["url"] or ref["description"]:
            refs.append(ref)
    return refs


def _extract_attack_reference(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return _json_compatible(raw)
    if isinstance(raw, list):
        return {
            "items": [
                _json_compatible(item)
                for item in raw
                if item is not None
            ]
        }
    return {"value": _normalize_text(raw)}


def _iter_yaml_documents(payload: str) -> Iterable[dict[str, Any]]:
    try:
        docs = list(yaml.safe_load_all(payload) or [])
    except yaml.YAMLError as exc:  # pragma: no cover - surfaced to management output
        raise CommandError(f"Failed to parse YAML: {exc}") from exc

    for document in docs:
        if isinstance(document, dict):
            yield document
        elif isinstance(document, list):
            for item in document:
                if isinstance(item, dict):
                    yield item


def _iter_atlas_objects(node: Any) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        atlas_id = _extract_record_id(node)
        if atlas_id:
            yield node
        for value in node.values():
            yield from _iter_atlas_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_atlas_objects(item)


def _maybe_record_relationship(record: dict[str, Any]) -> dict[str, Any] | None:
    source = _first_non_empty(
        record.get("source_ref"),
        record.get("sourceRef"),
        record.get("source_id"),
        record.get("sourceId"),
        record.get("source"),
    )
    target = _first_non_empty(
        record.get("target_ref"),
        record.get("targetRef"),
        record.get("target_id"),
        record.get("targetId"),
        record.get("target"),
    )
    relationship_type = _first_non_empty(
        record.get("relationship_type"),
        record.get("relationshipType"),
        record.get("relationship"),
        record.get("type"),
    )
    if not (source and target and relationship_type):
        return None

    source_text = str(source).strip()
    target_text = str(target).strip()
    if isinstance(source, dict):
        source_text = str(_first_non_empty(source.get("id"), source.get("atlas_id"), source.get("value")) or "").strip()
    if isinstance(target, dict):
        target_text = str(_first_non_empty(target.get("id"), target.get("atlas_id"), target.get("value")) or "").strip()
    if not (source_text.upper().startswith("AML.") and target_text.upper().startswith("AML.")):
        return None

    return {
        "source_atlas_id": source_text.upper(),
        "target_atlas_id": target_text.upper(),
        "relationship_type": str(relationship_type).strip(),
        "description": _normalize_text(record.get("description") or record.get("description")),
        "tactic_atlas_id": "",
        "step_id": "",
        "leads_to": [],
        "raw_payload": _json_compatible(record),
    }


class Command(BaseCommand):
    help = "Import MITRE ATLAS framework data into the ATLAS models."

    def add_arguments(self, parser):
        parser.add_argument("--source-repo", type=str, default=DEFAULT_ATLAS_REPO)
        parser.add_argument("--ref", type=str, default=DEFAULT_ATLAS_REF)
        parser.add_argument("--mode", type=str, choices=["remote", "local"], default="remote")
        parser.add_argument("--dir", type=str, default=None, help="Local checkout (required for --mode=local).")

    def handle(self, *args, **options):
        mode = (options.get("mode") or "remote").lower().strip()
        source_repo = (options.get("source_repo") or DEFAULT_ATLAS_REPO).strip()
        source_ref = normalize_git_ref(options.get("ref"), default=DEFAULT_ATLAS_REF)

        if mode == "local" and not options.get("dir"):
            raise CommandError("--dir is required when --mode=local")

        resolved_sha = ""
        file_rows: list[tuple[str, str]] = []
        warnings: list[str] = []

        if mode == "remote":
            try:
                resolved_sha = fetch_latest_ref_sha(source_repo, source_ref) or ""
            except Exception as exc:  # pragma: no cover
                warnings.append(f"Could not resolve latest SHA for ref '{source_ref}': {exc}")
            try:
                paths = list_remote_atlas_paths(source_repo, source_ref)
            except Exception as exc:
                raise CommandError(f"Unable to list ATLAS files: {exc}") from exc
            if not paths:
                raise CommandError("No ATLAS YAML files found in the remote repository.")
            for path in paths:
                try:
                    file_rows.append((path, fetch_remote_atlas_text(source_repo, source_ref, path)))
                except Exception as exc:
                    warnings.append(f"Failed to fetch {path}: {exc}")
        else:
            base_dir = Path(options["dir"]).expanduser().resolve()
            if not base_dir.exists():
                raise CommandError(f"Local directory does not exist: {base_dir}")
            for path in sorted(base_dir.rglob("*")):
                if not path.is_file():
                    continue
                lower = str(path).lower()
                if not (lower.endswith(".yaml") or lower.endswith(".yml")):
                    continue
                rel = path.relative_to(base_dir).as_posix()
                try:
                    file_rows.append((rel, path.read_text(encoding="utf-8")))
                except Exception as exc:
                    warnings.append(f"Failed to read {rel}: {exc}")
            if not file_rows:
                raise CommandError(f"No ATLAS YAML files found under {base_dir}")

        records_by_model: dict[str, list[dict[str, Any]]] = {
            "tactic": [],
            "technique": [],
            "mitigation": [],
            "case_study": [],
            "relationship": [],
        }
        seen_ids: set[str] = set()

        for _, payload in file_rows:
            for record in _iter_yaml_documents(payload):
                for node in _iter_atlas_objects(record):
                    atlas_id = _extract_record_id(node)
                    if not atlas_id:
                        continue
                    if atlas_id.upper() in seen_ids:
                        continue
                    seen_ids.add(atlas_id.upper())

                    relationship = _maybe_record_relationship(node)
                    if relationship:
                        records_by_model["relationship"].append(relationship)
                        continue

                    if atlas_id.upper().startswith("AML.TA"):
                        records_by_model["tactic"].append(node)
                    elif atlas_id.upper().startswith("AML.T"):
                        records_by_model["technique"].append(node)
                    elif atlas_id.upper().startswith("AML.M"):
                        records_by_model["mitigation"].append(node)
                    elif atlas_id.upper().startswith("AML.CS"):
                        records_by_model["case_study"].append(node)

        with transaction.atomic():
            AtlasRelationship.objects.all().delete()
            AtlasCaseStudy.objects.all().delete()
            AtlasMitigation.objects.all().delete()
            AtlasTechnique.objects.all().delete()
            AtlasTactic.objects.all().delete()

            for obj in records_by_model["tactic"]:
                atlas_id = _extract_record_id(obj).upper()
                AtlasTactic.objects.create(
                    atlas_id=atlas_id,
                    name=_normalize_text(_first_non_empty(obj.get("name"), obj.get("title"), obj.get("label"))) or atlas_id,
                    description=_normalize_text(_first_non_empty(obj.get("description"), obj.get("summary"), obj.get("details"))),
                    references=_extract_references(_first_non_empty(obj.get("references"), obj.get("external_references"), obj.get("externalReferences"))),
                    attack_reference=_extract_attack_reference(_first_non_empty(obj.get("attack_reference"), obj.get("attackReference"), obj.get("mitre_attack"))),
                    created_date=_coerce_date(_first_non_empty(obj.get("created_date"), obj.get("createdDate"), obj.get("created"))),
                    modified_date=_coerce_date(_first_non_empty(obj.get("modified_date"), obj.get("modifiedDate"), obj.get("modified"))),
                    atlas_uuid=None,
                    raw_payload=_json_compatible(obj),
                )

            for obj in records_by_model["technique"]:
                atlas_id = _extract_record_id(obj).upper()
                AtlasTechnique.objects.create(
                    atlas_id=atlas_id,
                    name=_normalize_text(_first_non_empty(obj.get("name"), obj.get("title"), obj.get("label"))) or atlas_id,
                    description=_normalize_text(_first_non_empty(obj.get("description"), obj.get("summary"), obj.get("details"))),
                    references=_extract_references(_first_non_empty(obj.get("references"), obj.get("external_references"), obj.get("externalReferences"))),
                    platforms=[_normalize_text(item) for item in _as_list(_first_non_empty(obj.get("platforms"), obj.get("platform"), obj.get("affected_platforms"))) if _normalize_text(item)],
                    maturity=_normalize_text(_first_non_empty(obj.get("maturity"), obj.get("maturity_level"), obj.get("stage"))),
                    attack_reference=_extract_attack_reference(_first_non_empty(obj.get("attack_reference"), obj.get("attackReference"), obj.get("mitre_attack"))),
                    created_date=_coerce_date(_first_non_empty(obj.get("created_date"), obj.get("createdDate"), obj.get("created"))),
                    modified_date=_coerce_date(_first_non_empty(obj.get("modified_date"), obj.get("modifiedDate"), obj.get("modified"))),
                    raw_payload=_json_compatible(obj),
                )

            for obj in records_by_model["mitigation"]:
                atlas_id = _extract_record_id(obj).upper()
                AtlasMitigation.objects.create(
                    atlas_id=atlas_id,
                    name=_normalize_text(_first_non_empty(obj.get("name"), obj.get("title"), obj.get("label"))) or atlas_id,
                    description=_normalize_text(_first_non_empty(obj.get("description"), obj.get("summary"), obj.get("details"))),
                    references=_extract_references(_first_non_empty(obj.get("references"), obj.get("external_references"), obj.get("externalReferences"))),
                    lifecycle_phases=[_normalize_text(item) for item in _as_list(_first_non_empty(obj.get("lifecycle_phases"), obj.get("lifecyclePhases"), obj.get("phases"))) if _normalize_text(item)],
                    categories=[_normalize_text(item) for item in _as_list(_first_non_empty(obj.get("categories"), obj.get("category"), obj.get("mitigation_categories"))) if _normalize_text(item)],
                    created_date=_coerce_date(_first_non_empty(obj.get("created_date"), obj.get("createdDate"), obj.get("created"))),
                    modified_date=_coerce_date(_first_non_empty(obj.get("modified_date"), obj.get("modifiedDate"), obj.get("modified"))),
                    raw_payload=_json_compatible(obj),
                )

            for obj in records_by_model["case_study"]:
                atlas_id = _extract_record_id(obj).upper()
                AtlasCaseStudy.objects.create(
                    atlas_id=atlas_id,
                    name=_normalize_text(_first_non_empty(obj.get("name"), obj.get("title"), obj.get("label"))) or atlas_id,
                    description=_normalize_text(_first_non_empty(obj.get("description"), obj.get("summary"), obj.get("details"))),
                    references=_extract_references(_first_non_empty(obj.get("references"), obj.get("external_references"), obj.get("externalReferences"))),
                    case_study_type=_normalize_text(_first_non_empty(obj.get("case_study_type"), obj.get("caseStudyType"), obj.get("type"), obj.get("study_type"))),
                    actor=_normalize_text(_first_non_empty(obj.get("actor"), obj.get("actor_name"), obj.get("actorName"))),
                    target=_normalize_text(_first_non_empty(obj.get("target"), obj.get("target_system"), obj.get("targetSystem"))),
                    reporter=_normalize_text(_first_non_empty(obj.get("reporter"), obj.get("reporter_name"), obj.get("reporterName"))),
                    start_date=_coerce_date(_first_non_empty(obj.get("start_date"), obj.get("startDate"))),
                    start_date_granularity=_normalize_text(_first_non_empty(obj.get("start_date_granularity"), obj.get("startDateGranularity"), obj.get("date_granularity"))),
                    end_date=_coerce_date(_first_non_empty(obj.get("end_date"), obj.get("endDate"))),
                    end_date_granularity=_normalize_text(_first_non_empty(obj.get("end_date_granularity"), obj.get("endDateGranularity"), obj.get("date_granularity"))),
                    created_date=_coerce_date(_first_non_empty(obj.get("created_date"), obj.get("createdDate"), obj.get("created"))),
                    modified_date=_coerce_date(_first_non_empty(obj.get("modified_date"), obj.get("modifiedDate"), obj.get("modified"))),
                    raw_payload=_json_compatible(obj),
                )

            for item in records_by_model["relationship"]:
                AtlasRelationship.objects.update_or_create(
                    source_atlas_id=item["source_atlas_id"],
                    target_atlas_id=item["target_atlas_id"],
                    relationship_type=item["relationship_type"],
                    step_id=item.get("step_id") or "",
                    defaults={
                        "description": item.get("description") or "",
                        "tactic_atlas_id": item.get("tactic_atlas_id") or "",
                        "leads_to": item.get("leads_to") or [],
                        "raw_payload": item.get("raw_payload") or {},
                    },
                )

        imported_version = resolved_sha[:12] if resolved_sha else source_ref
        PlatformDataVersion.objects.update_or_create(
            framework='atlas',
            defaults={'version': imported_version},
        )

        total_cards = (
            len(records_by_model["tactic"]) +
            len(records_by_model["technique"]) +
            len(records_by_model["mitigation"]) +
            len(records_by_model["case_study"]) +
            len(records_by_model["relationship"])
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported ATLAS data: {total_cards} records from {len(file_rows)} files "
                f"(warnings={len(warnings)})"
            )
        )
        for warning in warnings[:20]:
            self.stderr.write(f"WARNING: {warning}\n")
