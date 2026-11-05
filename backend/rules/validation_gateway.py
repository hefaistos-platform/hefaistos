import logging
from typing import Any

from rules.utils import detect_rule_format

logger = logging.getLogger(__name__)


def _normalize_severity(raw: str | None) -> str:
    value = str(raw or '').strip().lower()
    if value in {'warning', 'warn'}:
        return 'warning'
    if value in {'info', 'information'}:
        return 'info'
    if value in {'hint', 'note'}:
        return 'hint'
    return 'error'


def _normalize_issue(issue: dict[str, Any], *, default_code: str) -> dict[str, Any]:
    line = issue.get('line', 1)
    column = issue.get('column')
    return {
        'severity': _normalize_severity(issue.get('severity')),
        'code': str(issue.get('code') or default_code),
        'message': str(issue.get('message') or 'Invalid rule content'),
        'line': max(1, int(line or 1)),
        'column': int(column or 1) if column is not None else None,
        'fix_hint': str(issue.get('fix_hint') or issue.get('fixHint') or '').strip() or None,
        'source': str(issue.get('source') or 'engine'),
    }


def _engine_validate(format_name: str, context: str, *, data_source_id: str | None = None) -> list[dict[str, Any]]:
    del data_source_id
    from rules.autocomplete import (
        AQLAutocompleteEngine,
        EQLAutocompleteEngine,
        KQLAutocompleteEngine,
        SPLAutocompleteEngine,
        WazuhAutocompleteEngine,
    )

    fmt = (format_name or '').upper()
    engine_map = {
        'KQL': KQLAutocompleteEngine,
        'WAZUH': WazuhAutocompleteEngine,
        'SPL': SPLAutocompleteEngine,
        'AQL': AQLAutocompleteEngine,
        'EQL': EQLAutocompleteEngine,
    }

    engine_cls = engine_map.get(fmt)
    if engine_cls is None:
        return []

    engine = engine_cls()
    validator = getattr(engine, 'validate_content', None)
    if callable(validator):
        raw = validator(context or '')
        return [_normalize_issue(issue if isinstance(issue, dict) else {}, default_code='SYNTAX') for issue in (raw or [])]

    is_valid, error = engine.validate_syntax(context or '')
    if is_valid:
        return []

    return [_normalize_issue({
        'line': 1,
        'column': 1,
        'message': error or 'Invalid rule content',
        'severity': 'error',
        'source': 'engine',
    }, default_code='SYNTAX')]


def _custom_hefaistos_checks(format_name: str, context: str) -> list[dict[str, Any]]:
    fmt = (format_name or '').upper()
    text = str(context or '')
    issues: list[dict[str, Any]] = []

    if not text.strip():
        issues.append(_normalize_issue({
            'severity': 'error',
            'code': 'EMPTY_RULE',
            'message': 'Rule content is empty.',
            'line': 1,
            'column': 1,
            'fix_hint': 'Provide rule logic before saving or accepting this rule.',
            'source': 'hefaistos',
        }, default_code='EMPTY_RULE'))
        return issues

    if fmt in {'KQL', 'EQL', 'WAZUH', 'SPL', 'AQL'}:
        detected = detect_rule_format(text)
        if detected != 'OTHER' and detected != fmt:
            issues.append(_normalize_issue({
                'severity': 'warning',
                'code': 'FORMAT_MISMATCH',
                'message': f'Content appears to be {detected}, but editor format is {fmt}.',
                'line': 1,
                'column': 1,
                'fix_hint': f'Switch editor format to {detected} or rewrite content as {fmt}.',
                'source': 'hefaistos',
            }, default_code='FORMAT_MISMATCH'))

    return issues


def _lsp_diagnostics(format_name: str, context: str) -> list[dict[str, Any]]:
    del context
    language_map = {
        'KQL': 'kql',
        'SPL': 'spl',
        'WAZUH': 'wazuh',
        'AQL': 'aql',
    }
    language = language_map.get((format_name or '').upper())
    if not language:
        return []

    try:
        from lsp_server.manager import get_lsp_manager
        status = get_lsp_manager().get_status().get(language) or {}
    except Exception as exc:
        logger.debug("LSP diagnostics unavailable for %s: %s", language, exc)
        return []

    if not status.get('running'):
        return []

    # LSP diagnostics are currently streamed through the WebSocket bridge to Monaco.
    # Backend gateway includes this hook so API/editor and AI generation share one orchestrator.
    return []


def validate_rule_content(
    *,
    format_name: str,
    context: str,
    position: int | None = None,
    data_source_id: str | None = None,
) -> dict[str, Any]:
    del position
    fmt = (format_name or '').upper()
    issues: list[dict[str, Any]] = []
    issues.extend(_engine_validate(fmt, context or '', data_source_id=data_source_id))
    issues.extend(_lsp_diagnostics(fmt, context or ''))
    issues.extend(_custom_hefaistos_checks(fmt, context or ''))

    syntax_blocking = [
        issue for issue in issues
        if issue.get('severity') == 'error' and str(issue.get('code') or '').upper() != 'FORMAT_MISMATCH'
    ]
    return {
        'format': fmt,
        'issues': issues,
        'is_valid': len(syntax_blocking) == 0,
        'has_warnings': any(issue.get('severity') == 'warning' for issue in issues),
    }
