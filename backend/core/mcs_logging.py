"""
MCS security logging helpers.

This module centralizes:
1) Building MCS-compliant security events.
2) Emitting structured JSON logs.
3) Persisting security logs to Elasticsearch.
4) Querying security logs for the admin UI.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

MCS_VERSION = "1.1.0"
DEFAULT_INDEX_PREFIX = "mcs-security"
DEFAULT_RETENTION_DAYS = 3
DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_ELASTIC_TIMEOUT_SECONDS = 1.5

_SENSITIVE_KEY_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "session",
    "jwt",
    "credential",
)

_INDEX_DATE_PATTERN = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime | None = None) -> str:
    dt = value or _now_utc()
    return dt.isoformat().replace("+00:00", "Z")


def _mcs_level(level: str | None) -> str:
    lvl = (level or "informational").strip().lower()
    if lvl in {"info", "informational"}:
        return "informational"
    if lvl in {"warn", "warning"}:
        return "warning"
    if lvl in {"error"}:
        return "error"
    if lvl in {"critical", "fatal"}:
        return "critical"
    return "informational"


def _python_level(level: str | None) -> int:
    normalized = _mcs_level(level)
    if normalized == "warning":
        return logging.WARNING
    if normalized == "error":
        return logging.ERROR
    if normalized == "critical":
        return logging.CRITICAL
    return logging.INFO


def _is_sensitive_key(key: str) -> bool:
    lowered = (key or "").lower()
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def _sanitize_value(value: Any, key_hint: str = "") -> Any:
    if value is None:
        return None

    if _is_sensitive_key(key_hint):
        return "[REDACTED]"

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, nested in value.items():
            out[key] = _sanitize_value(nested, key_hint=str(key))
        return out

    if isinstance(value, list):
        return [_sanitize_value(item, key_hint=key_hint) for item in value]

    if isinstance(value, tuple):
        return [_sanitize_value(item, key_hint=key_hint) for item in value]

    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.lower()
        if lowered.startswith("bearer "):
            return "Bearer [REDACTED]"
        if lowered.startswith("basic "):
            return "Basic [REDACTED]"
        if len(value) > 8000:
            return value[:8000] + "...[TRUNCATED]"
        return value

    return value


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, nested in value.items():
            compacted = _compact(nested)
            if compacted in (None, "", [], {}):
                continue
            cleaned[key] = compacted
        return cleaned

    if isinstance(value, list):
        cleaned_list = [_compact(item) for item in value]
        return [item for item in cleaned_list if item not in (None, "", [], {})]

    return value


def _default_event_type(outcome: str) -> list[str]:
    normalized = (outcome or "unknown").lower()
    if normalized == "success":
        return ["end", "success"]
    if normalized == "failure":
        return ["denied", "failure"]
    return ["info"]


def extract_client_ip(request: Any) -> str:
    if not request:
        return "unknown"

    request_obj = request.get("request") if isinstance(request, dict) else request
    meta = getattr(request_obj, "META", {}) or {}

    x_real_ip = meta.get("HTTP_X_REAL_IP")
    if x_real_ip:
        return x_real_ip.strip()

    x_forwarded_for = meta.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    remote_addr = meta.get("REMOTE_ADDR")
    if remote_addr:
        return remote_addr

    return "unknown"


def _request_context(request: Any) -> dict[str, Any]:
    if not request:
        return {}

    request_obj = request.get("request") if isinstance(request, dict) else request
    meta = getattr(request_obj, "META", {}) or {}

    ctx: dict[str, Any] = {
        "source_ip": extract_client_ip(request_obj),
        "method": getattr(request_obj, "method", None),
    }

    path = getattr(request_obj, "path", None)
    if path:
        ctx["path"] = path

    query_string = meta.get("QUERY_STRING")
    if query_string:
        ctx["query"] = query_string

    return ctx


def _resolve_service_name(logger_name: str | None = None) -> str:
    return (
        os.environ.get("HEFAISTOS_SERVICE_NAME")
        or os.environ.get("SERVICE_NAME")
        or logger_name
        or "hefaistos-backend"
    )


def _resolve_elastic_url() -> str:
    explicit = os.environ.get("MCS_ELASTIC_URL") or os.environ.get("ELASTICSEARCH_URL")
    if explicit:
        return explicit.rstrip("/")

    try:
        from django.conf import settings

        hosts = settings.ELASTICSEARCH_DSL.get("default", {}).get("hosts")
        if isinstance(hosts, str) and hosts:
            return hosts.rstrip("/")
        if isinstance(hosts, (list, tuple)) and hosts:
            return str(hosts[0]).rstrip("/")
    except Exception:
        pass

    return "http://elasticsearch:9200"


def _resolve_index_prefix() -> str:
    return (os.environ.get("MCS_ELASTIC_INDEX_PREFIX") or DEFAULT_INDEX_PREFIX).strip() or DEFAULT_INDEX_PREFIX


def _resolve_retention_days() -> int:
    try:
        parsed = int(os.environ.get("MCS_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS)))
        return max(1, parsed)
    except Exception:
        return DEFAULT_RETENTION_DAYS


def _resolve_timeout_seconds() -> float:
    try:
        parsed = float(os.environ.get("MCS_ELASTIC_TIMEOUT_SECONDS", str(DEFAULT_ELASTIC_TIMEOUT_SECONDS)))
        return max(0.2, parsed)
    except Exception:
        return DEFAULT_ELASTIC_TIMEOUT_SECONDS


def _elastic_enabled() -> bool:
    raw = (os.environ.get("MCS_ELASTIC_ENABLED", "true") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def build_mcs_event(
    *,
    level: str,
    logger_name: str,
    message: str,
    event_action: str,
    event_outcome: str,
    asvs_event_code: str,
    event_reason: str | None = None,
    event_category: list[str] | None = None,
    event_type: list[str] | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    source_ip: str | None = None,
    request: Any = None,
    http_status_code: int | None = None,
    asvs_details: dict[str, Any] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req_ctx = _request_context(request)

    event: dict[str, Any] = {
        "@timestamp": _iso_utc(),
        "log": {
            "level": _mcs_level(level),
            "logger": logger_name,
        },
        "message": message,
        "mcs": {
            "version": MCS_VERSION,
        },
        "event": {
            "category": event_category or ["intrusion_detection"],
            "type": event_type or _default_event_type(event_outcome),
            "action": event_action,
            "outcome": (event_outcome or "unknown").lower(),
            "reason": event_reason,
        },
        "user": {
            "id": user_id or "anonymous",
            "name": user_name,
        },
        "source": {
            "ip": source_ip or req_ctx.get("source_ip") or "unknown",
        },
        "http": {
            "request": {
                "method": req_ctx.get("method"),
            },
            "response": {
                "status_code": http_status_code,
            },
        },
        "url": {
            "path": req_ctx.get("path"),
            "query": req_ctx.get("query"),
        },
        "asvs": {
            "event_code": asvs_event_code,
        },
        "service": {
            "name": _resolve_service_name(logger_name),
        },
    }

    if asvs_details:
        event["asvs"].update(asvs_details)
    if extra_context:
        event["context"] = extra_context

    sanitized = _sanitize_value(event)
    return _compact(sanitized)


def emit_security_event(
    *,
    level: str,
    logger_name: str,
    message: str,
    event_action: str,
    event_outcome: str,
    asvs_event_code: str,
    event_reason: str | None = None,
    event_category: list[str] | None = None,
    event_type: list[str] | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    source_ip: str | None = None,
    request: Any = None,
    http_status_code: int | None = None,
    asvs_details: dict[str, Any] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = build_mcs_event(
        level=level,
        logger_name=logger_name,
        message=message,
        event_action=event_action,
        event_outcome=event_outcome,
        asvs_event_code=asvs_event_code,
        event_reason=event_reason,
        event_category=event_category,
        event_type=event_type,
        user_id=user_id,
        user_name=user_name,
        source_ip=source_ip,
        request=request,
        http_status_code=http_status_code,
        asvs_details=asvs_details,
        extra_context=extra_context,
    )
    logging.getLogger("security.mcs").log(
        _python_level(level),
        message,
        extra={"mcs_event": event},
    )
    return event


class MCSJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "mcs_event", None)
        if not isinstance(payload, dict):
            payload = build_mcs_event(
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
                event_action="application_log",
                event_outcome="unknown",
                asvs_event_code="ERROR-APP-EXCEPTION-01" if record.levelno >= logging.ERROR else "BIZLOGIC-FAIL-WORKFLOW-01",
            )
        return json.dumps(payload, ensure_ascii=True)


class ElasticsearchMCSHandler(logging.Handler):
    _cleanup_lock = threading.Lock()
    _last_cleanup_at: datetime | None = None

    def __init__(self) -> None:
        super().__init__()
        self.elastic_url = _resolve_elastic_url()
        self.index_prefix = _resolve_index_prefix()
        self.retention_days = _resolve_retention_days()
        self.timeout_seconds = _resolve_timeout_seconds()
        self.enabled = _elastic_enabled()
        self.session = requests.Session()

    def _index_name(self, timestamp: str | None) -> str:
        dt = _now_utc()
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except Exception:
                dt = _now_utc()
        return f"{self.index_prefix}-{dt.strftime('%Y.%m.%d')}"

    def emit(self, record: logging.LogRecord) -> None:
        if not self.enabled:
            return

        payload = getattr(record, "mcs_event", None)
        if not isinstance(payload, dict):
            return

        try:
            index_name = self._index_name(payload.get("@timestamp"))
            self.session.post(
                f"{self.elastic_url}/{index_name}/_doc",
                json=payload,
                timeout=self.timeout_seconds,
            )
            self._cleanup_old_indices()
        except Exception:
            # Never break application flow on logging transport failures.
            return

    def _cleanup_old_indices(self) -> None:
        now = _now_utc()
        with self._cleanup_lock:
            if self._last_cleanup_at and (now - self._last_cleanup_at) < timedelta(hours=6):
                return
            self._last_cleanup_at = now

        cutoff_date = (now - timedelta(days=self.retention_days)).date()
        try:
            response = self.session.get(
                f"{self.elastic_url}/_cat/indices/{self.index_prefix}-*",
                params={"h": "index", "format": "json"},
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 300:
                return
            indices = response.json()
        except Exception:
            return

        for item in indices:
            index_name = item.get("index", "")
            suffix = index_name.replace(f"{self.index_prefix}-", "", 1)
            match = _INDEX_DATE_PATTERN.match(suffix)
            if not match:
                continue
            try:
                year, month, day = map(int, match.groups())
                index_date = datetime(year=year, month=month, day=day, tzinfo=timezone.utc).date()
            except Exception:
                continue
            if index_date < cutoff_date:
                try:
                    self.session.delete(f"{self.elastic_url}/{index_name}", timeout=self.timeout_seconds)
                except Exception:
                    continue


def _normalize_search_hit(hit: dict[str, Any]) -> dict[str, Any]:
    src = hit.get("_source", {}) if isinstance(hit, dict) else {}
    log_obj = src.get("log", {}) if isinstance(src, dict) else {}
    event_obj = src.get("event", {}) if isinstance(src, dict) else {}
    asvs_obj = src.get("asvs", {}) if isinstance(src, dict) else {}
    user_obj = src.get("user", {}) if isinstance(src, dict) else {}
    source_obj = src.get("source", {}) if isinstance(src, dict) else {}
    service_obj = src.get("service", {}) if isinstance(src, dict) else {}
    request_obj = src.get("http", {}).get("request", {}) if isinstance(src, dict) else {}
    url_obj = src.get("url", {}) if isinstance(src, dict) else {}

    service_name = service_obj.get("name") if isinstance(service_obj, dict) else service_obj

    return {
        "id": hit.get("_id"),
        "timestamp": src.get("@timestamp"),
        "level": log_obj.get("level"),
        "logger": log_obj.get("logger"),
        "message": src.get("message"),
        "action": event_obj.get("action"),
        "outcome": event_obj.get("outcome"),
        "reason": event_obj.get("reason"),
        "event_code": asvs_obj.get("event_code"),
        "user_id": user_obj.get("id"),
        "user_name": user_obj.get("name"),
        "source_ip": source_obj.get("ip"),
        "request_method": request_obj.get("method"),
        "url_path": url_obj.get("path"),
        "service_name": service_name,
    }


def search_security_logs(
    *,
    limit: int = 100,
    offset: int = 0,
    level: str | None = None,
    action: str | None = None,
    search: str | None = None,
    user: str | None = None,
) -> dict[str, Any]:
    if not _elastic_enabled():
        return {"total": 0, "logs": []}

    page_size = min(max(int(limit or 100), 1), 500)
    page_offset = max(int(offset or 0), 0)

    lookback_hours = DEFAULT_LOOKBACK_HOURS
    index_prefix = _resolve_index_prefix()
    elastic_url = _resolve_elastic_url()
    timeout_seconds = _resolve_timeout_seconds()

    bool_query: dict[str, Any] = {
        "filter": [
            {
                "range": {
                    "@timestamp": {
                        "gte": f"now-{lookback_hours}h",
                        "lte": "now",
                    }
                }
            }
        ],
        "must": [],
    }

    if level:
        bool_query["filter"].append({"term": {"log.level": _mcs_level(level)}})
    if action:
        bool_query["filter"].append({"term": {"event.action": action}})

    if search:
        bool_query["must"].append(
            {
                "multi_match": {
                    "query": search,
                    "fields": [
                        "message",
                        "event.action",
                        "event.reason",
                        "asvs.event_code",
                        "user.id",
                        "user.name",
                        "source.ip",
                        "log.logger",
                        "service.name",
                    ],
                }
            }
        )

    if user:
        bool_query["filter"].append(
            {
                "bool": {
                    "should": [
                        {"term": {"user.id": user}},
                        {"term": {"user.name": user}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    body = {
        "query": {"bool": bool_query},
        "sort": [
            {"@timestamp": {"order": "desc", "unmapped_type": "date"}},
        ],
        "from": page_offset,
        "size": page_size,
    }

    response = requests.post(
        f"{elastic_url}/{index_prefix}-*/_search",
        json=body,
        timeout=timeout_seconds,
    )
    if response.status_code == 404:
        return {"total": 0, "logs": []}
    if response.status_code >= 300:
        raise RuntimeError(f"Failed to query security logs (HTTP {response.status_code})")

    payload = response.json()
    hits_section = payload.get("hits", {})
    hits = hits_section.get("hits", [])

    total_raw = hits_section.get("total", 0)
    if isinstance(total_raw, dict):
        total = int(total_raw.get("value", 0))
    else:
        total = int(total_raw or 0)

    return {
        "total": total,
        "logs": [_normalize_search_hit(hit) for hit in hits],
    }
