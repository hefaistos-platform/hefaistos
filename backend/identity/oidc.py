import hashlib
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import urlencode

import jwt
import requests
from django.core import signing
from django.utils import timezone
from jwt.algorithms import RSAAlgorithm

from core.mcs_logging import extract_client_ip


class OidcAuthError(Exception):
    pass


@dataclass
class OidcProviderConfig:
    provider: str
    issuer: str
    discovery_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str
    email_claim: str
    username_claim: str
    role_claim: str


_DISCOVERY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DISCOVERY_CACHE_SECONDS = 300
# Allow small provider/server clock drift during JWT time-claim validation.
_OIDC_TOKEN_CLOCK_SKEW_SECONDS = 300
_OIDC_CA_DIR = os.path.join(tempfile.gettempdir(), "hefaistos_oidc_ca")


def _normalize_scopes(scopes: str | None) -> str:
    raw = (scopes or "").strip()
    if not raw:
        return "openid profile email"
    return " ".join([part for part in raw.split() if part])


def _hash_optional(value: str | None, size: int = 16) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:size]


def _provider_slug(provider: str | None) -> str:
    value = (provider or "").strip().lower()
    if value in {"entra", "oidc"}:
        return value
    raise OidcAuthError("Unsupported OIDC provider")


def build_provider_config(settings_obj, provider: str) -> OidcProviderConfig:
    slug = _provider_slug(provider)

    if slug == "entra":
        tenant_id = (settings_obj.entra_tenant_id or "").strip()
        client_id = (settings_obj.entra_client_id or "").strip()
        client_secret = settings_obj.entra_client_secret
        redirect_uri = (settings_obj.entra_redirect_uri or "").strip()
        if not all([tenant_id, client_id, client_secret, redirect_uri]):
            raise OidcAuthError("Entra OIDC is not fully configured")
        issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        discovery_url = f"{issuer}/.well-known/openid-configuration"
        return OidcProviderConfig(
            provider="entra",
            issuer=issuer,
            discovery_url=discovery_url,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=_normalize_scopes(settings_obj.entra_scopes),
            email_claim=(settings_obj.entra_email_claim or "preferred_username").strip(),
            username_claim=(settings_obj.entra_username_claim or "preferred_username").strip(),
            role_claim=(settings_obj.entra_role_claim or "roles").strip(),
        )

    issuer = (settings_obj.oidc_issuer_url or "").strip().rstrip("/")
    client_id = (settings_obj.oidc_client_id or "").strip()
    client_secret = settings_obj.oidc_client_secret
    redirect_uri = (settings_obj.oidc_redirect_uri or "").strip()
    if not all([issuer, client_id, client_secret, redirect_uri]):
        raise OidcAuthError("Generic OIDC is not fully configured")
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    return OidcProviderConfig(
        provider="oidc",
        issuer=issuer,
        discovery_url=discovery_url,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=_normalize_scopes(settings_obj.oidc_scopes),
        email_claim=(settings_obj.oidc_email_claim or "email").strip(),
        username_claim=(settings_obj.oidc_username_claim or "preferred_username").strip(),
        role_claim=(settings_obj.oidc_role_claim or "roles").strip(),
    )


def _oidc_verify_value(settings_obj) -> bool | str:
    verify_ssl = bool(getattr(settings_obj, "oidc_verify_ssl", True))
    cert_pem = str(getattr(settings_obj, "oidc_ca_certificate", "") or "").strip()
    if not verify_ssl:
        return False
    if not cert_pem:
        return True
    digest = hashlib.sha256(cert_pem.encode("utf-8")).hexdigest()
    os.makedirs(_OIDC_CA_DIR, exist_ok=True)
    cert_path = os.path.join(_OIDC_CA_DIR, f"{digest}.pem")
    if not os.path.exists(cert_path):
        with open(cert_path, "w", encoding="utf-8") as cert_file:
            cert_file.write(cert_pem)
            if not cert_pem.endswith("\n"):
                cert_file.write("\n")
        os.chmod(cert_path, 0o600)
    return cert_path


def _is_provider_enabled(settings_obj, provider: str) -> bool:
    slug = _provider_slug(provider)
    if slug == "entra":
        return bool(settings_obj.enable_entra)
    return bool(settings_obj.enable_oidc)


def _verify_marker(verify: bool | str) -> str:
    if isinstance(verify, str):
        return f"cert:{verify}"
    return "verify:true" if verify else "verify:false"


def _get_discovery_document(discovery_url: str, verify: bool | str) -> dict[str, Any]:
    now = time()
    cache_key = f"{discovery_url}|{_verify_marker(verify)}"
    cached = _DISCOVERY_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _DISCOVERY_CACHE_SECONDS:
        return cached[1]

    response = requests.get(discovery_url, timeout=10, verify=verify)
    if response.status_code >= 400:
        raise OidcAuthError(f"OIDC discovery failed with status {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise OidcAuthError("OIDC discovery response is invalid")
    _DISCOVERY_CACHE[cache_key] = (now, payload)
    return payload


def _get_signing_key_from_jwks(id_token: str, jwks_uri: str, verify: bool | str):
    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as exc:
        raise OidcAuthError("OIDC id_token header is invalid") from exc

    kid = str(header.get("kid") or "").strip()
    jwks_response = requests.get(jwks_uri, timeout=10, verify=verify)
    if jwks_response.status_code >= 400:
        raise OidcAuthError(f"OIDC JWKS fetch failed with status {jwks_response.status_code}")
    jwks = jwks_response.json()
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list) or not keys:
        raise OidcAuthError("OIDC JWKS payload is invalid")

    selected_key = None
    if kid:
        for key in keys:
            if str(key.get("kid") or "") == kid:
                selected_key = key
                break
    if selected_key is None:
        selected_key = keys[0]
    try:
        return RSAAlgorithm.from_jwk(json.dumps(selected_key))
    except Exception as exc:
        raise OidcAuthError("OIDC JWKS signing key is invalid") from exc


def _make_signed_state(request, provider: str, nonce: str, redirect_uri: str, organization_id: str | None = None) -> str:
    user_agent = ""
    try:
        user_agent = request.META.get("HTTP_USER_AGENT", "")
    except Exception:
        user_agent = ""
    source_ip = extract_client_ip(request) or ""
    payload = {
        "provider": _provider_slug(provider),
        "nonce": nonce,
        "ua": _hash_optional(user_agent),
        "ip": _hash_optional(source_ip),
        "redirect_uri": redirect_uri,
        "organization_id": str(organization_id) if organization_id else "",
        "iat": int(time()),
    }
    return signing.dumps(payload, salt="identity.oidc.state")


def _verify_signed_state(request, state: str, max_age_seconds: int = 600) -> dict[str, Any]:
    try:
        payload = signing.loads(state, salt="identity.oidc.state", max_age=max_age_seconds)
    except Exception as exc:
        raise OidcAuthError("Invalid or expired OIDC state") from exc

    user_agent = ""
    try:
        user_agent = request.META.get("HTTP_USER_AGENT", "")
    except Exception:
        user_agent = ""
    source_ip = extract_client_ip(request) or ""
    expected_ua = _hash_optional(user_agent)
    expected_ip = _hash_optional(source_ip)

    payload_ua = str(payload.get("ua") or "")
    payload_ip = str(payload.get("ip") or "")
    if payload_ua and expected_ua and payload_ua != expected_ua:
        raise OidcAuthError("OIDC state validation failed")
    if payload_ip and expected_ip and payload_ip != expected_ip:
        raise OidcAuthError("OIDC state validation failed")
    return payload


def build_authorization_url(request, settings_obj, provider: str, organization_id: str | None = None) -> tuple[str, str]:
    if not _is_provider_enabled(settings_obj, provider):
        raise OidcAuthError("Requested OIDC provider is disabled")

    config = build_provider_config(settings_obj, provider)
    verify = _oidc_verify_value(settings_obj)
    metadata = _get_discovery_document(config.discovery_url, verify=verify)
    authorization_endpoint = metadata.get("authorization_endpoint")
    if not authorization_endpoint:
        raise OidcAuthError("OIDC discovery does not contain authorization_endpoint")

    nonce = secrets.token_urlsafe(24)
    state = _make_signed_state(
        request=request,
        provider=config.provider,
        nonce=nonce,
        redirect_uri=config.redirect_uri,
        organization_id=organization_id,
    )
    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "scope": config.scopes,
        "state": state,
        "nonce": nonce,
    }
    if config.provider == "entra":
        params["response_mode"] = "query"

    return f"{authorization_endpoint}?{urlencode(params)}", config.provider


def complete_code_exchange(request, code: str, state: str) -> tuple[str, OidcProviderConfig, dict[str, Any], str | None]:
    if not code:
        raise OidcAuthError("Missing OIDC authorization code")
    if not state:
        raise OidcAuthError("Missing OIDC state")

    state_payload = _verify_signed_state(request=request, state=state)
    provider = _provider_slug(state_payload.get("provider"))
    organization_id = (state_payload.get("organization_id") or "").strip() or None

    from identity.models import AuthProviderSettings
    settings_obj = AuthProviderSettings.resolve_for_org_id(organization_id) if organization_id else AuthProviderSettings.get_solo()
    if settings_obj is None:
        raise OidcAuthError("Organization authentication settings not found")
    if not _is_provider_enabled(settings_obj, provider):
        raise OidcAuthError("Requested OIDC provider is disabled")

    config = build_provider_config(settings_obj, provider)
    verify = _oidc_verify_value(settings_obj)
    metadata = _get_discovery_document(config.discovery_url, verify=verify)
    token_endpoint = metadata.get("token_endpoint")
    jwks_uri = metadata.get("jwks_uri")
    issuer = metadata.get("issuer")
    if not token_endpoint or not jwks_uri or not issuer:
        raise OidcAuthError("OIDC discovery response missing required endpoints")

    token_response = requests.post(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
        verify=verify,
    )
    if token_response.status_code >= 400:
        raise OidcAuthError(f"OIDC token exchange failed with status {token_response.status_code}")

    token_payload = token_response.json()
    id_token = token_payload.get("id_token")
    if not id_token:
        raise OidcAuthError("OIDC token exchange did not return id_token")

    signing_key = _get_signing_key_from_jwks(id_token=id_token, jwks_uri=jwks_uri, verify=verify)
    claims = jwt.decode(
        id_token,
        signing_key,
        algorithms=["RS256", "RS384", "RS512"],
        audience=config.client_id,
        issuer=issuer,
        leeway=_OIDC_TOKEN_CLOCK_SKEW_SECONDS,
        options={"verify_at_hash": False},
    )
    if str(claims.get("nonce") or "") != str(state_payload.get("nonce") or ""):
        raise OidcAuthError("OIDC nonce validation failed")

    now_ts = int(timezone.now().timestamp())
    if int(claims.get("exp") or 0) and int(claims["exp"]) < now_ts:
        raise OidcAuthError("OIDC ID token is expired")

    return provider, config, claims, organization_id
