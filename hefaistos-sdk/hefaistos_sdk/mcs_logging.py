"""Lightweight MCS security logging for HEFAISTOS connectors."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

MCS_VERSION = "1.1.0"
DEFAULT_INDEX_PREFIX = "mcs-security"
DEFAULT_RETENTION_DAYS = 3

_logger = logging.getLogger("security.mcs")
_session = requests.Session()
_last_cleanup: datetime | None = None
_index_date_pattern = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$")


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mcs_level(level: str | None) -> str:
    normalized = (level or "informational").lower()
    if normalized in {"warn", "warning"}:
        return "warning"
    if normalized in {"error"}:
        return "error"
    if normalized in {"critical", "fatal"}:
        return "critical"
    return "informational"


def _elastic_url() -> str:
    return (os.environ.get("MCS_ELASTIC_URL") or os.environ.get("ELASTICSEARCH_URL") or "http://elasticsearch:9200").rstrip("/")


def _index_prefix() -> str:
    return (os.environ.get("MCS_ELASTIC_INDEX_PREFIX") or DEFAULT_INDEX_PREFIX).strip() or DEFAULT_INDEX_PREFIX


def _retention_days() -> int:
    try:
        return max(1, int(os.environ.get("MCS_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))))
    except Exception:
        return DEFAULT_RETENTION_DAYS


def _enabled() -> bool:
    raw = (os.environ.get("MCS_ELASTIC_ENABLED", "true") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _service_name(logger_name: str | None = None) -> str:
    return os.environ.get("HEFAISTOS_SERVICE_NAME") or os.environ.get("SERVICE_NAME") or logger_name or "hefaistos-connector"


def _cleanup_indices() -> None:
    global _last_cleanup

    if not _enabled():
        return

    now = datetime.now(timezone.utc)
    if _last_cleanup and (now - _last_cleanup) < timedelta(hours=6):
        return
    _last_cleanup = now

    prefix = _index_prefix()
    cutoff = (now - timedelta(days=_retention_days())).date()
    try:
        response = _session.get(
            f"{_elastic_url()}/_cat/indices/{prefix}-*",
            params={"h": "index", "format": "json"},
            timeout=1.5,
        )
        if response.status_code >= 300:
            return
        for item in response.json():
            index_name = item.get("index", "")
            suffix = index_name.replace(f"{prefix}-", "", 1)
            match = _index_date_pattern.match(suffix)
            if not match:
                continue
            year, month, day = map(int, match.groups())
            index_date = datetime(year, month, day, tzinfo=timezone.utc).date()
            if index_date < cutoff:
                try:
                    _session.delete(f"{_elastic_url()}/{index_name}", timeout=1.5)
                except Exception:
                    continue
    except Exception:
        return


def emit_security_event(
    *,
    level: str,
    logger_name: str,
    message: str,
    event_action: str,
    event_outcome: str,
    asvs_event_code: str,
    event_reason: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    source_ip: str | None = None,
    asvs_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
            "category": ["authentication"],
            "type": ["failure"] if event_outcome == "failure" else ["info"],
            "action": event_action,
            "outcome": event_outcome,
            "reason": event_reason,
        },
        "user": {
            "id": user_id or "connector_svc",
            "name": user_name,
        },
        "source": {
            "ip": source_ip or "unknown",
        },
        "asvs": {
            "event_code": asvs_event_code,
        },
        "service": {
            "name": _service_name(logger_name),
        },
    }
    if asvs_details:
        event["asvs"].update(asvs_details)

    payload = json.dumps(event, ensure_ascii=True)
    _logger.info(payload)

    if _enabled():
        try:
            now = datetime.now(timezone.utc)
            index_name = f"{_index_prefix()}-{now.strftime('%Y.%m.%d')}"
            _session.post(
                f"{_elastic_url()}/{index_name}/_doc",
                json=event,
                timeout=1.5,
            )
            _cleanup_indices()
        except Exception:
            pass

    return event
