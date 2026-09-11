import logging
from typing import Any

from graphql import GraphQLError

from core.mcs_logging import emit_security_event, extract_client_ip
from identity.decorators import Roles, is_bot_auditor_user, is_global_bot_auditor_user

logger = logging.getLogger(__name__)


_SENSITIVE_TOKENS = (
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authkey",
    "private_key",
    "privatekey",
    "credential",
    "smtp_password",
    "auth_key",
    "client_secret",
)

_BOT_ALLOWED_MUTATIONS = {
    # Auth/session lifecycle operations (no domain object mutation)
    "tokenAuth",
    "verifyToken",
    "refreshToken",
    "startMfaLogin",
    "verifyMfaLogin",
    "startPasswordlessLogin",
    "verifyPasswordlessLogin",
    "startOidcLogin",
    "completeOidcLogin",
}


def _request_from_context(context: Any):
    return context.get("request") if isinstance(context, dict) else context


def _user_from_context(context: Any):
    request = _request_from_context(context)
    user = getattr(request, "user", None)
    if user is not None:
        return user
    return context.get("user") if isinstance(context, dict) else None


def _operation_kind(info) -> str:
    operation = getattr(getattr(info, "operation", None), "operation", None)
    if hasattr(operation, "value"):
        operation = operation.value
    return str(operation or "").lower()


def _is_mutation(info) -> bool:
    return _operation_kind(info) == "mutation"


def _is_top_level_field(info) -> bool:
    path = getattr(info, "path", None)
    if not path:
        return True
    try:
        return len(path.as_list()) <= 1
    except Exception:
        return True


def _is_sensitive_field(field_name: str) -> bool:
    normalized = (field_name or "").strip().lower()
    if not normalized:
        return False
    if normalized in {"haspassword", "hastoken", "hasapikey", "hascredentials"}:
        return False
    return any(token in normalized for token in _SENSITIVE_TOKENS)


def _redact_value(value: Any):
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: "[REDACTED]" for key in value.keys()}
    if isinstance(value, (list, tuple)):
        return ["[REDACTED]" for _ in value]
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    return "[REDACTED]"


class GraphQLSecurityMiddleware:
    """
    Global GraphQL guardrails:
    1) Bot-auditor roles are strictly read-only (mutations denied).
    2) Sensitive fields are redacted for bot-auditor roles.
    3) Global bot auditors get platform-wide read scope for query evaluation.
    """

    def resolve(self, next, root, info, **kwargs):
        context = getattr(info, "context", None)
        user = _user_from_context(context)

        if not user or getattr(user, "is_anonymous", True):
            return next(root, info, **kwargs)

        if is_bot_auditor_user(user):
            if _is_mutation(info) and info.field_name not in _BOT_ALLOWED_MUTATIONS:
                source_ip = extract_client_ip(context)
                emit_security_event(
                    level="warning",
                    logger_name="AuthorizationService",
                    message=(
                        f"Read-only bot account '{getattr(user, 'username', 'unknown')}' "
                        f"attempted GraphQL mutation '{info.field_name}'."
                    ),
                    event_action="resource_access_denied",
                    event_outcome="failure",
                    asvs_event_code="AUTHZ-DENY-01",
                    event_reason="Read-only bot auditor accounts cannot execute mutations.",
                    event_category=["authorization"],
                    event_type=["denied", "failure"],
                    user_id=str(getattr(user, "id", "unknown")),
                    user_name=getattr(user, "username", None),
                    source_ip=source_ip,
                    request=context,
                    asvs_details={
                        "authorization": {
                            "resource_type": "graphql_mutation",
                            "resource_id": info.field_name,
                            "required_permission": "read_only",
                        }
                    },
                )
                raise GraphQLError("Read-only bot auditor accounts cannot perform write operations.")

            # Bot auditors are query-only. For read-path authorization checks, temporarily
            # elevate org bots to ADMIN role and global bots to platform-admin flags.
            is_query = _operation_kind(info) == "query"
            elevate_for_authorization = is_query and _is_top_level_field(info)
            original_role = getattr(user, "role", None)
            original_superuser = getattr(user, "is_superuser", False)
            original_staff = getattr(user, "is_staff", False)
            if elevate_for_authorization:
                user.role = Roles.ADMIN
                if is_global_bot_auditor_user(user):
                    user.is_superuser = True
                    user.is_staff = True

            try:
                resolved = next(root, info, **kwargs)
            finally:
                if elevate_for_authorization:
                    user.role = original_role
                    user.is_superuser = original_superuser
                    user.is_staff = original_staff

            if _is_sensitive_field(getattr(info, "field_name", "")):
                return _redact_value(resolved)
            return resolved

        return next(root, info, **kwargs)
