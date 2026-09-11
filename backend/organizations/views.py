"""Read-only sharing API endpoints for instance-to-instance PULL."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from organizations.sharing import (
    authenticate_inbound_key,
    effective_required_tags,
    export_org_payload,
    get_or_create_instance_identity,
    normalize_scope,
)


def _extract_share_key(request) -> str:
    return (
        request.headers.get('X-HEFAISTOS-SHARE-KEY', '')
        or request.META.get('HTTP_X_HEFAISTOS_SHARE_KEY', '')
    ).strip()


def _permission_denied(message: str):
    return JsonResponse({'detail': message}, status=403)


@require_GET
def sharing_instance_info(request):
    """Return remote instance metadata (requires a valid inbound share key)."""
    try:
        share_key = authenticate_inbound_key(
            _extract_share_key(request),
            requested_scope=None,
            touch_last_used=False,
        )
    except PermissionDenied as exc:
        return _permission_denied(str(exc))

    identity = get_or_create_instance_identity(
        organization=share_key.organization,
        create_if_missing=False,
    )
    return JsonResponse({
        'instance_id': str(identity.instance_id),
        'organization': share_key.organization.name,
        'allowed_scopes': list(share_key.allowed_scopes or []),
        'enforce_tag_filter': bool(share_key.enforce_tag_filter),
        'required_tags': effective_required_tags(share_key),
        'server_time': timezone.now().isoformat(),
        'mode': 'PULL_READ_ONLY',
    })


@require_GET
def sharing_export(request):
    """Export selected data scope for remote PULL (read-only endpoint)."""
    scope = request.GET.get('scope', 'ALL')
    try:
        normalized_scope = normalize_scope(scope)
        share_key = authenticate_inbound_key(
            _extract_share_key(request),
            requested_scope=normalized_scope,
            touch_last_used=False,
        )
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    except PermissionDenied as exc:
        return _permission_denied(str(exc))

    payload = export_org_payload(
        share_key.organization,
        normalized_scope,
        create_identity_if_missing=False,
        share_key=share_key,
    )
    payload['permissions'] = {
        'mode': 'PULL_READ_ONLY',
        'allowed_scopes': list(share_key.allowed_scopes or []),
        'enforce_tag_filter': bool(share_key.enforce_tag_filter),
        'required_tags': effective_required_tags(share_key),
    }
    return JsonResponse(payload)
