import os
from typing import List
from urllib.parse import urlparse

from django.utils.html import escape

_PLACEHOLDER_HOSTS = {
    "app.example.com",
    "example.com",
    "www.example.com",
    "your.domain.com",
}

def _normalize_base_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _is_placeholder_base_url(value: str) -> bool:
    try:
        host = (urlparse(value).hostname or "").lower()
    except Exception:
        return True
    if not host:
        return True
    return host in _PLACEHOLDER_HOSTS or host.endswith(".example.com")


def _frontend_base_from_request(request: object | None) -> str:
    if not request:
        return ""
    request_obj = request.get("request") if isinstance(request, dict) else request
    try:
        return (request_obj.build_absolute_uri("/") or "").rstrip("/")
    except Exception:
        return ""


def get_frontend_base_url(request: object | None = None) -> str:
    """Resolve canonical frontend base URL with placeholder-safe fallbacks."""
    try:
        from django.conf import settings
        public_base = getattr(settings, "PUBLIC_BASE_URL", None) or os.environ.get("PUBLIC_BASE_URL")
        frontend_base = getattr(settings, "FRONTEND_URL", None) or os.environ.get("FRONTEND_URL")
        server_domain = getattr(settings, "SERVER_DOMAIN", None) or os.environ.get("SERVER_DOMAIN")
    except Exception:
        public_base = os.environ.get("PUBLIC_BASE_URL")
        frontend_base = os.environ.get("FRONTEND_URL")
        server_domain = os.environ.get("SERVER_DOMAIN")

    for candidate in (
        _normalize_base_url(public_base),
        _normalize_base_url(frontend_base),
        _normalize_base_url(server_domain),
        _normalize_base_url(_frontend_base_from_request(request)),
    ):
        if candidate and not _is_placeholder_base_url(candidate):
            return candidate

    # Last-resort fallback preserves backward behavior in local/dev setups.
    fallback = _normalize_base_url(_frontend_base_from_request(request)) or "https://localhost"
    return fallback


def get_login_url(request: object | None = None) -> str:
    """Return the configured frontend login URL."""
    return get_frontend_base_url(request=request) + "/login"


def login_link_text(request: object | None = None) -> str:
    """Return a plain-text login footer line."""
    return f"Login to HEFAISTOS platform: {get_login_url(request=request)}"


def login_link_html(request: object | None = None) -> str:
    """Return an HTML login footer line."""
    url = get_login_url(request=request)
    return (
        f'<p style="margin-top:16px">Login to HEFAISTOS platform: '
        f'<a href="{url}" style="color:#2563eb;text-decoration:underline">{url}</a></p>'
    )


def render_news_item_html(title: str, content_md: str, category_label: str, priority: str, author_username: str, published_at_iso: str) -> str:
    # Minimal HTML (no markdown conversion to avoid new deps); escape and wrap
    content_html = "<p>{}</p>".format(escape(content_md).replace('\n', '<br/>'))
    return f"""
    <div style="border:1px solid #eaeaea;border-radius:8px;padding:16px;margin-bottom:12px;font-family:Arial,sans-serif">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="font-size:18px">{escape(category_label)}</span>
        <strong style="font-size:16px">{escape(title or 'News Update')}</strong>
        <span style="font-size:12px;color:#555">Priority: {escape(priority)}</span>
      </div>
      {content_html}
      <div style="font-size:12px;color:#777;margin-top:8px">By {escape(author_username)} • {escape(published_at_iso)}</div>
    </div>
    """.strip()


def render_digest_html(items: List[str]) -> str:
    items_html = "\n".join(items)
    login_url = get_login_url()
    return f"""
    <html>
    <body style="background:#f6f8fb;padding:24px">
      <div style="max-width:720px;margin:0 auto;background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);padding:24px">
        <h2 style="font-family:Arial,sans-serif;color:#1f2937;margin-top:0">Hefaistos News Digest</h2>
        {items_html}
        <hr style="border:none;border-top:1px solid #eee;margin:16px 0"/>
        <p style="font-size:13px;font-family:Arial,sans-serif">Login to HEFAISTOS platform: <a href="{login_url}" style="color:#2563eb;text-decoration:underline">{login_url}</a></p>
        <div style="font-size:12px;color:#777">You are receiving this because you have an account on Hefaistos.</div>
      </div>
    </body>
    </html>
    """.strip()


def render_simple_text(subject: str, lines: List[str]) -> str:
    return f"{subject}\n\n" + "\n".join(lines) + f"\n\n{login_link_text()}"
