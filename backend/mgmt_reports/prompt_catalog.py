"""Versioned system prompt catalog helpers for MGMT Cave."""

from importlib import import_module
from typing import Any, Dict, List

from django.db import transaction


SYSTEM_PROMPT_CATALOG_VERSION = "2026.06.25.1"


def get_system_prompt_catalog() -> List[Dict[str, Any]]:
    """Return the canonical system prompt definitions."""
    module = import_module("mgmt_reports.migrations.0002_seed_ai_prompts")
    prompts = getattr(module, "PROMPTS", [])
    if not isinstance(prompts, list):
        return []
    return prompts


@transaction.atomic
def sync_system_prompts(*, dry_run: bool = False, deactivate_missing: bool = False) -> Dict[str, Any]:
    """Upsert system prompts from the catalog into the AIPrompt table."""
    from .models import AIPrompt

    prompts = get_system_prompt_catalog()
    titles: set[str] = set()
    created = 0
    updated = 0

    for item in prompts:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        titles.add(title)

        if dry_run:
            exists = AIPrompt.objects.filter(title=title).exists()
            if exists:
                updated += 1
            else:
                created += 1
            continue

        _, was_created = AIPrompt.objects.update_or_create(
            title=title,
            defaults={
                "description": item.get("description", ""),
                "category": item.get("category", "ANALYTICS"),
                "prompt_template": str(item.get("prompt_template", "")).strip(),
                "is_system": True,
                "is_active": True,
                "required_role": item.get("required_role", "REVIEWER"),
                "order": int(item.get("order", 0)),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    deactivated = 0
    if deactivate_missing and titles:
        queryset = AIPrompt.objects.filter(is_system=True).exclude(title__in=titles)
        if dry_run:
            deactivated = queryset.count()
        else:
            deactivated = queryset.update(is_active=False)

    return {
        "catalog_version": SYSTEM_PROMPT_CATALOG_VERSION,
        "catalog_size": len(titles),
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
        "dry_run": dry_run,
    }
