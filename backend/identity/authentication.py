from django.contrib.auth import get_user_model
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from core.mcs_logging import emit_security_event
from .models import PersonalAPIToken


FALLBACK_AUTH_META_HEADERS = (
    'HTTP_X_HEFAISTOS_AUTHORIZATION',
    'HTTP_X_AUTHORIZATION',
    'HTTP_X_FORWARDED_AUTHORIZATION',
)


def _extract_bearer_token(request):
    auth = get_authorization_header(request).split()
    if auth:
        if auth[0].lower() != b'bearer':
            return None
        if len(auth) != 2:
            raise exceptions.AuthenticationFailed('Invalid Authorization header.')
        try:
            return auth[1].decode('utf-8')
        except UnicodeDecodeError as exc:
            raise exceptions.AuthenticationFailed('Invalid API token header encoding.') from exc

    for meta_header in FALLBACK_AUTH_META_HEADERS:
        raw_value = request.META.get(meta_header)
        if not raw_value:
            continue
        value = str(raw_value).strip()
        if not value:
            continue
        if value.lower().startswith('bearer '):
            value = value[7:].strip()
        if value:
            return value

    return None


def _resolve_user_from_payload(payload):
    if not isinstance(payload, dict):
        return None

    user_model = get_user_model()

    user_id = payload.get('user_id')
    if user_id:
        user = user_model.objects.filter(id=user_id).first()
        if user is not None:
            return user

    username_field = getattr(user_model, 'USERNAME_FIELD', 'username') or 'username'
    username = payload.get(username_field) or payload.get('username')
    if username:
        return user_model.objects.filter(**{username_field: username}).first()

    return None


class PersonalAPITokenAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer'

    def authenticate(self, request):
        raw_token = _extract_bearer_token(request)
        if not raw_token:
            return None

        if not raw_token.startswith(PersonalAPIToken.TOKEN_PREFIX):
            # Not a personal API token. Let other auth backends (JWT) handle it.
            return None

        token_obj = PersonalAPIToken.from_raw_token(raw_token)
        if token_obj is None:
            raise exceptions.AuthenticationFailed('Invalid API token.')
        if token_obj.revoked_at is not None:
            raise exceptions.AuthenticationFailed('API token revoked.')
        if token_obj.is_expired():
            raise exceptions.AuthenticationFailed('API token expired.')

        token_obj.mark_used()
        emit_security_event(
            level='informational',
            logger_name='security.mcs',
            message='Personal API token used',
            event_action='personal_api_token.authenticate',
            event_outcome='success',
            asvs_event_code='API-AUTH-SUCCESS-01',
            user_id=str(token_obj.user_id),
            user_name=getattr(token_obj.user, 'username', ''),
            request=request,
            extra_context={'token_id': str(token_obj.id), 'token_name': token_obj.name},
        )

        return (token_obj.user, token_obj)


class GraphQLJWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer'

    def authenticate(self, request):
        raw_token = _extract_bearer_token(request)
        if not raw_token:
            return None
        if raw_token.startswith(PersonalAPIToken.TOKEN_PREFIX):
            return None

        try:
            from graphql_jwt.utils import get_payload
            payload = get_payload(raw_token)
        except Exception:
            return None

        # Let SimpleJWT backend validate token_type semantics for those tokens.
        if isinstance(payload, dict) and payload.get('token_type'):
            return None

        user = _resolve_user_from_payload(payload)
        if user is None:
            raise exceptions.AuthenticationFailed('Invalid API token.')
        if not getattr(user, 'is_active', True):
            raise exceptions.AuthenticationFailed('User inactive or deleted.')

        return (user, raw_token)
