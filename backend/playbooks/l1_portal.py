"""Shared helpers for L1 portal snapshot and share URL generation."""

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings

from playbooks.models import DetectionPlaybook, L1PortalEntry, PlaybookGraph

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _normalize_base_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    # Docker/env files are sometimes authored with quoted values.
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        raw = raw[1:-1].strip()
    if not raw:
        return ""
    if not raw.lower().startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _host_from_url(value: str | None) -> str:
    try:
        return (urlparse(value or "").hostname or "").lower()
    except Exception:
        return ""


def _is_local_host(host: str) -> bool:
    return host in _LOCAL_HOSTS or host.endswith(".localhost")


def build_l1_portal_title(graph: PlaybookGraph) -> str:
    base = (getattr(graph, 'title', '') or 'Workbench').strip()
    return f"{base} PB"


def build_l1_portal_share_url(token, request=None) -> str:
    token_value = str(token)
    relative_path = f"/l1-portal/{token_value}"

    public_base = _normalize_base_url(getattr(settings, 'PUBLIC_BASE_URL', ''))
    if public_base:
        return f"{public_base}{relative_path}"

    frontend_base = _normalize_base_url(getattr(settings, 'FRONTEND_URL', ''))
    frontend_host = _host_from_url(frontend_base)
    # If FRONTEND_URL is explicitly external, prefer it over request host
    # to avoid leaking internal localhost links in generated share URLs.
    if frontend_base and frontend_host and not _is_local_host(frontend_host):
        return f"{frontend_base}{relative_path}"

    if request is not None:
        try:
            request_url = request.build_absolute_uri(relative_path)
            if request_url:
                return request_url
        except Exception:
            pass

    if frontend_base:
        return f"{frontend_base}{relative_path}"

    return relative_path


def upsert_l1_portal_snapshot(graph: PlaybookGraph | None) -> L1PortalEntry | None:
    if graph is None:
        return None

    if (getattr(graph, 'status', '') or '').upper() != str(DetectionPlaybook.PlaybookStatus.DEPLOYED):
        return None

    defaults = {
        'organization': graph.organization,
        'title': build_l1_portal_title(graph),
        'response_playbook': graph.response_playbook or '',
        'known_false_positives': graph.false_positives or '',
        'blind_spots_coverage_gaps': graph.blind_spots or '',
    }

    entry, created = L1PortalEntry.objects.get_or_create(
        graph=graph,
        defaults=defaults,
    )
    if created:
        return entry

    changed = False
    for field, value in defaults.items():
        if getattr(entry, field) != value:
            setattr(entry, field, value)
            changed = True

    if changed:
        entry.save(
            update_fields=[
                'organization',
                'title',
                'response_playbook',
                'known_false_positives',
                'blind_spots_coverage_gaps',
                'updated_at',
            ]
        )

    return entry
