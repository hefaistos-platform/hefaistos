from functools import wraps
from django.core.exceptions import PermissionDenied
from .models import CustomUser
import logging
from core.mcs_logging import emit_security_event, extract_client_ip

logger = logging.getLogger(__name__)

# Expose the roles for easy import by other modules
Roles = CustomUser.Roles

BOT_AUDITOR_ROLES = {
    Roles.BOT_AUDITOR_ORG,
    Roles.BOT_AUDITOR_GLOBAL,
}


def is_bot_auditor_role(role: str | None) -> bool:
    return (role or '') in BOT_AUDITOR_ROLES


def is_bot_auditor_user(user) -> bool:
    return bool(user and not getattr(user, 'is_anonymous', True) and is_bot_auditor_role(getattr(user, 'role', None)))


def is_global_bot_auditor_user(user) -> bool:
    return bool(user and not getattr(user, 'is_anonymous', True) and getattr(user, 'role', None) == Roles.BOT_AUDITOR_GLOBAL)

def role_required(roles: list):
    """
    A decorator that checks if a logged-in user has one of the required roles.
    `roles` is a list of strings, e.g., [Roles.ADMIN, Roles.ANALYST]
    Service accounts (connector_svc or usernames containing 'service') bypass role checks.
    Platform admins (is_superuser or is_staff) also bypass org-scoped role checks —
    the ADMIN role is scoped to the user's own organization only.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Attempt to find 'info' object (which has .context)
            info = None
            for arg in args:
                if hasattr(arg, 'context'):
                    info = arg
                    break
            
            if info:
                user = info.context.user

                # Check 1: Is user logged in?
                if user.is_anonymous:
                    logger.warning(f"[role_required] Anonymous user attempted to access {func.__name__}")
                    emit_security_event(
                        level='warning',
                        logger_name='AuthorizationService',
                        message=f"Anonymous request denied for '{func.__name__}' because authentication is required.",
                        event_action='resource_access_denied',
                        event_outcome='failure',
                        asvs_event_code='AUTHZ-DENY-01',
                        event_reason='Authentication required.',
                        event_category=['authorization'],
                        event_type=['denied', 'failure'],
                        user_id='anonymous',
                        source_ip=extract_client_ip(info.context),
                        request=info.context,
                        asvs_details={
                            'authorization': {
                                'resource_type': 'graphql_mutation',
                                'resource_id': func.__name__,
                                'required_permission': f"role:{','.join(roles)}",
                            }
                        },
                    )
                    raise PermissionDenied("You must be logged in to perform this action.")

                # Check 2: Allow service accounts to bypass role checks
                is_service_account = (
                    hasattr(user, 'username') and 
                    (user.username == 'connector_svc' or 'service' in user.username.lower())
                )
                
                if is_service_account:
                    logger.info(f"[role_required] Service account '{user.username}' allowed access to {func.__name__}")
                    # Service accounts bypass role checks for connector operations
                    return func(*args, **kwargs)

                operation = getattr(getattr(info, 'operation', None), 'operation', None)
                if hasattr(operation, 'value'):
                    operation = operation.value
                operation_kind = str(operation or '').lower()

                # Check 3: Bot auditors are strictly read-only.
                # Allow role-gated QUERY resolvers so bots can inspect the platform.
                # Deny non-query operations (mutations/other write-like operations).
                if is_bot_auditor_user(user):
                    if operation_kind == 'query':
                        logger.info(
                            f"[role_required] Bot auditor '{user.username}' allowed read access to {func.__name__}"
                        )
                        return func(*args, **kwargs)
                    logger.warning(f"[role_required] Bot auditor '{user.username}' denied write access to {func.__name__}")
                    emit_security_event(
                        level='warning',
                        logger_name='AuthorizationService',
                        message=(
                            f"Read-only bot account '{user.username}' attempted write access "
                            f"to '{func.__name__}'."
                        ),
                        event_action='resource_access_denied',
                        event_outcome='failure',
                        asvs_event_code='AUTHZ-DENY-01',
                        event_reason='Read-only bot auditor accounts cannot perform write operations.',
                        event_category=['authorization'],
                        event_type=['denied', 'failure'],
                        user_id=str(getattr(user, 'id', 'unknown')),
                        user_name=getattr(user, 'username', None),
                        source_ip=extract_client_ip(info.context),
                        request=info.context,
                        asvs_details={
                            'authorization': {
                                'resource_type': 'graphql_mutation',
                                'resource_id': func.__name__,
                                'required_permission': f"role:{','.join(roles)}",
                            }
                        },
                    )
                    raise PermissionDenied("Read-only bot auditor accounts cannot perform this action.")

                # Check 4: Allow platform admins (superuser/staff) to bypass org-scoped role checks
                if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
                    logger.info(f"[role_required] Platform admin '{user.username}' (superuser={user.is_superuser}, staff={user.is_staff}) allowed access to {func.__name__}")
                    return func(*args, **kwargs)

                # Check 5: Does user have the required role?
                if user.role not in roles:
                    logger.warning(f"[role_required] User '{user.username}' with role '{user.role}' denied access to {func.__name__} (requires {roles})")
                    emit_security_event(
                        level='warning',
                        logger_name='AuthorizationService',
                        message=(
                            f"Access denied for user '{user.username}' to '{func.__name__}'. "
                            f"Role '{user.role}' is not permitted."
                        ),
                        event_action='resource_access_denied',
                        event_outcome='failure',
                        asvs_event_code='AUTHZ-DENY-01',
                        event_reason=f"Required one of: {', '.join(roles)}.",
                        event_category=['authorization'],
                        event_type=['denied', 'failure'],
                        user_id=str(getattr(user, 'id', 'unknown')),
                        user_name=getattr(user, 'username', None),
                        source_ip=extract_client_ip(info.context),
                        request=info.context,
                        asvs_details={
                            'authorization': {
                                'resource_type': 'graphql_mutation',
                                'resource_id': func.__name__,
                                'required_permission': f"role:{','.join(roles)}",
                            }
                        },
                    )
                    raise PermissionDenied(f"You do not have permission. Requires one of: {', '.join(roles)}")

                logger.info(f"[role_required] User '{user.username}' with role '{user.role}' allowed access to {func.__name__}")

            # If all checks pass, run the original mutation
            return func(*args, **kwargs)
        return wrapper
    return decorator
