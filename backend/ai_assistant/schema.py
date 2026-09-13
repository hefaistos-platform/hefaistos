import json
import logging
import os
import re
import threading
import time
from datetime import datetime

import graphene
from django.db import close_old_connections, transaction, models
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from .models import UserAISettings, OrgAISettings, SharedAIProfile, AIGenerationTask
from organizations.models import Organization
from .engine import (
    generate_rule,
    run_logic_deconstruction,
    suggest_rule_improvements,
    generate_similar_rules,
    recommend_reusable_rule,
    run_custom_prompt,
    run_maieutic_questioning,
    run_strain_extraction,
    fetch_and_extract_from_url,
    generate_response_playbook,
    extract_threat_report_workbench_payload,
)
import requests
from requests.exceptions import RequestException
from playbooks.models import PlaybookGraph, CapabilityAbstraction
from platform_data.models import MitreAttackTechnique, ChokepointSnapshot, ChokepointEntry
from identity.decorators import role_required, Roles

logger = logging.getLogger(__name__)


SUPPORTED_RESPONSE_PLAYBOOK_TRANSLATIONS = {
    'CZ': 'Czech',
    'DE': 'German',
    'SP': 'Spanish',
    'FR': 'French',
}

RESPONSE_PLAYBOOK_TRANSLATION_PATTERN = re.compile(
    r'^\s*\[Translation:\s*(CZ|DE|SP|FR)\]\s*\n'
    r'(?P<translated>.*?)'
    r'\n\s*---\s*\n'
    r'\s*\[Original\]\s*\n'
    r'(?P<original>.*?)\s*$',
    re.DOTALL | re.IGNORECASE,
)

VALID_USER_PREFERRED_MODELS = [
    'GPT-5.5',
    'GPT-5.4',
    'GPT-5.4-MINI',
    'GEMINI-3.1-PRO-PREVIEW',
    'GEMINI-3.5-FLASH',
    'GEMINI-3-FLASH-PREVIEW',
    'GEMINI-3.1-FLASH-LITE',
    'GEMINI-3.1-FLASH-LITE-PREVIEW',
    'CLAUDE-OPUS-4.7',
    'CLAUDE-SONNET-4.6',
    'CLAUDE-HAIKU-4.5-20251001',
]

_PREFERRED_MODEL_ALIASES = {
    model.upper(): model
    for model in VALID_USER_PREFERRED_MODELS
}


def _get_effective_ai_settings(user_settings):
    """Return OrgAISettings if the user has opted in and the org has any AI provider configured."""
    if getattr(user_settings, 'use_org_ai', False):
        org = getattr(user_settings.user, 'organization', None)
        if org:
            try:
                org_settings = OrgAISettings.objects.select_related('shared_profile').get(organization=org)
                effective_settings = org_settings.get_effective_settings()
                if getattr(effective_settings, 'has_any_provider', False):
                    return effective_settings
            except OrgAISettings.DoesNotExist:
                pass
    return user_settings


def _normalize_preferred_model_choice(value: str | None) -> str | None:
    """Map user-supplied model labels to canonical enum values."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return ''
    upper = raw.upper()
    canonical = _PREFERRED_MODEL_ALIASES.get(upper)
    if canonical:
        return canonical
    relaxed = re.sub(r'[\s_]+', '-', upper)
    return _PREFERRED_MODEL_ALIASES.get(relaxed)


def _resolve_rag_language(language_hint: str | None, *, rule_content: str | None = None) -> str | None:
    from .rag_templates import normalize_rag_language

    normalized = normalize_rag_language(language_hint, fallback='')
    if normalized:
        return normalized

    if rule_content and str(rule_content).strip():
        try:
            from rules.utils import detect_rule_format

            detected_format = detect_rule_format(str(rule_content))
            return normalize_rag_language(detected_format, fallback='')
        except Exception:
            return None

    return None


def _resolve_target_org(user, organization_id=None):
    if organization_id is None:
        return getattr(user, 'organization', None)

    if not (getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)):
        raise GraphQLError("Only superusers can target another organization.")

    try:
        return Organization.objects.get(pk=organization_id)
    except Organization.DoesNotExist:
        raise GraphQLError("Organization not found.")


def _serialize_capability_abstractions(playbook):
    return [
        {
            'id': str(cap.id),
            'layer': cap.abstraction_layer,
            'component_artifact': cap.component_artifact,
            'adversary_purpose': cap.adversary_purpose or '',
            'common_evasions': cap.common_evasions or '',
            'expected_observables': cap.expected_observables or '',
            'applicable_telemetry': cap.applicable_telemetry or '',
            'detection_value': cap.detection_value or '',
            'robustness_level': cap.robustness_level or 0,
            'source_kind': cap.source_kind,
            'review_status': cap.review_status,
            'is_baseline': cap.is_baseline,
        }
        for cap in playbook.selected_capability_abstractions.all()
    ]


def _build_playbook_generation_context(playbook) -> dict:
    raw_strategy = playbook.selected_strategy
    if isinstance(raw_strategy, str):
        try:
            raw_strategy = json.loads(raw_strategy)
        except (json.JSONDecodeError, ValueError):
            raw_strategy = {}
    strategy_obj = raw_strategy if isinstance(raw_strategy, dict) else {}

    return {
        'title': playbook.title,
        'technique_id': playbook.mitre_technique.technique_id if playbook.mitre_technique else 'Unknown',
        'technique_name': playbook.mitre_technique.name if playbook.mitre_technique else 'Unknown',
        'strategy_name': strategy_obj.get('name', 'Custom'),
        'technical_context': playbook.technical_context,
        'goal': playbook.goal,
        'data_sources': "See Data Catalog",
        'false_positives': playbook.false_positives or '',
        'blind_spots': playbook.blind_spots or '',
        'test_scenario': playbook.test_scenario or '',
        'test_expected_output': playbook.test_expected_output or '',
        'existing_logic': playbook.detection_rule or '',
        'detection_focus_layer': playbook.detection_focus_layer or '',
        'capability_abstractions': _serialize_capability_abstractions(playbook),
    }


def _enrich_with_rag_reference_context(
    user,
    base_context: dict | None,
    *,
    rule_content: str | None = None,
    additional_text: str | None = None,
    language: str = 'KQL',
    limit: int = 6,
) -> tuple[dict, list[dict]]:
    context = dict(base_context) if isinstance(base_context, dict) else {}
    normalized_language = _resolve_rag_language(language, rule_content=rule_content)
    if not normalized_language:
        return context, []

    org = getattr(user, 'organization', None)
    org_id = str(getattr(org, 'id', '')).strip() or None

    try:
        from .rag_templates import build_reference_context_prompt, retrieve_reference_context

        reference_context = retrieve_reference_context(
            playbook_context=context,
            rule_content=rule_content,
            additional_text=additional_text,
            language=normalized_language,
            organization_id=org_id,
            limit=limit,
        )
        if reference_context:
            context['reference_context_prompt'] = build_reference_context_prompt(reference_context)
        return context, reference_context
    except Exception as exc:
        logger.warning("RAG context enrichment failed: %s", exc)
        return context, []


def _record_rag_usage(reference_context: list[dict]):
    if not reference_context:
        return

    try:
        from .rag_templates import mark_reference_files_used

        mark_reference_files_used(reference_context)
    except Exception as exc:
        logger.warning("Failed to record RAG file usage: %s", exc)


def _split_translated_response_playbook(value: str | None) -> dict:
    raw = (value or '').strip()
    if not raw:
        return {'language': None, 'translated': '', 'original': ''}

    match = RESPONSE_PLAYBOOK_TRANSLATION_PATTERN.match(raw)
    if not match:
        return {'language': None, 'translated': '', 'original': raw}

    return {
        'language': (match.group(1) or '').upper() or None,
        'translated': (match.group('translated') or '').strip(),
        'original': (match.group('original') or '').strip(),
    }


def _compose_translated_response_playbook(original: str, translated: str, language_code: str) -> str:
    return (
        f"[Translation: {language_code}]\n"
        f"{(translated or '').strip()}\n\n"
        f"---\n\n"
        f"[Original]\n"
        f"{(original or '').strip()}"
    )


def _normalize_lookup_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


def _lookup_value(source: dict | None, *aliases: str, default=None):
    if not isinstance(source, dict):
        return default
    lookup = {_normalize_lookup_key(str(k)): v for k, v in source.items()}
    for alias in aliases:
        key = _normalize_lookup_key(alias)
        if key in lookup:
            return lookup[key]
        for actual_key, value in lookup.items():
            if key and (actual_key.startswith(key) or key in actual_key):
                return value
    return default


def _coerce_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _coerce_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _is_empty_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def _humanize_key(raw_key: str) -> str:
    text = str(raw_key or '')
    text = re.sub(r'[_\-]+', ' ', text)
    text = re.sub(r'(?<=[a-z0-9])([A-Z])', r' \1', text)
    text = ' '.join(text.split()).strip()
    if not text:
        return ''
    return text.title()


def _summarize_structured_item(item: dict) -> str:
    code = _coerce_text(_lookup_value(item, 'code', 'id', default=''))
    name = _coerce_text(_lookup_value(item, 'name', 'title', default=''))
    role = _coerce_text(_lookup_value(item, 'role', 'description', 'purpose', default=''))

    if code and name and role:
        return f"**{code} {name}:** {role}"
    if code and name:
        return f"**{code} {name}**"
    if code and role:
        return f"**{code}:** {role}"
    if name and role:
        return f"**{name}:** {role}"
    if name:
        return f"**{name}**"
    if code:
        return f"**{code}**"
    return ''


def _format_markdown_lines(value, indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = '  ' * indent

    if isinstance(value, dict):
        for raw_key, raw_val in value.items():
            if _is_empty_value(raw_val):
                continue
            label = _humanize_key(raw_key)
            if isinstance(raw_val, (dict, list)):
                lines.append(f"{prefix}- **{label}:**")
                lines.extend(_format_markdown_lines(raw_val, indent + 1))
            else:
                lines.append(f"{prefix}- **{label}:** {_coerce_text(raw_val)}")
        return lines

    if isinstance(value, list):
        for item in value:
            if _is_empty_value(item):
                continue
            if isinstance(item, dict):
                summary = _summarize_structured_item(item)
                if summary:
                    lines.append(f"{prefix}- {summary}")
                    detail = {
                        k: v for k, v in item.items()
                        if _normalize_lookup_key(str(k)) not in {
                            'code',
                            'id',
                            'name',
                            'title',
                            'role',
                            'description',
                            'purpose',
                        }
                    }
                    if detail:
                        lines.extend(_format_markdown_lines(detail, indent + 1))
                    continue
                lines.append(f"{prefix}-")
                lines.extend(_format_markdown_lines(item, indent + 1))
                continue
            if isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(_format_markdown_lines(item, indent + 1))
                continue
            lines.append(f"{prefix}- {_coerce_text(item)}")
        return lines

    text = _coerce_text(value)
    if text:
        lines.append(f"{prefix}- {text}")
    return lines


def _coerce_markdown_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        lines = _format_markdown_lines(value)
        return '\n'.join(lines).strip()
    return str(value).strip()


def _coerce_string_list(value) -> list[str]:
    items = []
    for raw in _coerce_list(value):
        if raw is None:
            continue
        if isinstance(raw, dict):
            text = _coerce_text(
                _lookup_value(raw, 'name', 'title', 'description', 'value', default=raw)
            )
        else:
            text = _coerce_text(raw)
        if text:
            items.append(text)
    deduped = []
    for text in items:
        if text not in deduped:
            deduped.append(text)
    return deduped


def _extract_codes(value, pattern: str) -> list[str]:
    regex = re.compile(pattern, flags=re.IGNORECASE)
    found: list[str] = []

    def walk(node):
        if node is None:
            return
        if isinstance(node, str):
            for match in regex.findall(node):
                token = match[0] if isinstance(match, tuple) else match
                token = token.upper()
                if token not in found:
                    found.append(token)
            return
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if isinstance(node, dict):
            for child in node.values():
                walk(child)

    walk(value)
    return found


def _extract_first_code(value, pattern: str) -> str:
    codes = _extract_codes(value, pattern)
    return codes[0] if codes else ''


def _merge_text(current: str, incoming: str, mode: str) -> str:
    current_norm = (current or '').strip()
    incoming_norm = (incoming or '').strip()
    if not incoming_norm:
        return current or ''
    if mode == 'OVERWRITE' or not current_norm:
        return incoming_norm
    if incoming_norm in current_norm:
        return current_norm
    return f"{current_norm}\n\n{incoming_norm}"


def _merge_list(current: list, incoming: list, mode: str) -> list:
    merged = [] if mode == 'OVERWRITE' else list(current or [])
    for item in incoming or []:
        if item not in merged:
            merged.append(item)
    return merged


def _map_layer_name(raw: str) -> str | None:
    key = _normalize_lookup_key(raw)
    mapping = {
        'tool': CapabilityAbstraction.AbstractionLayer.TOOL,
        'binary': CapabilityAbstraction.AbstractionLayer.TOOL,
        'toolbinary': CapabilityAbstraction.AbstractionLayer.TOOL,
        'apiexport': CapabilityAbstraction.AbstractionLayer.API_EXPORT,
        'api': CapabilityAbstraction.AbstractionLayer.API_EXPORT,
        'export': CapabilityAbstraction.AbstractionLayer.API_EXPORT,
        'comipc': CapabilityAbstraction.AbstractionLayer.COM_IPC,
        'com': CapabilityAbstraction.AbstractionLayer.COM_IPC,
        'ipc': CapabilityAbstraction.AbstractionLayer.COM_IPC,
        'registryobject': CapabilityAbstraction.AbstractionLayer.REGISTRY_OBJECT,
        'registry': CapabilityAbstraction.AbstractionLayer.REGISTRY_OBJECT,
        'protocol': CapabilityAbstraction.AbstractionLayer.PROTOCOL,
        'processbehavior': CapabilityAbstraction.AbstractionLayer.PROCESS_BEHAVIOR,
        'networkbehavior': CapabilityAbstraction.AbstractionLayer.NETWORK_BEHAVIOR,
    }
    return mapping.get(key)


def _map_robustness_level(raw) -> int:
    if raw is None:
        return 0
    if isinstance(raw, int):
        return max(0, min(raw, 5))
    text = _normalize_lookup_key(_coerce_text(raw))
    if not text:
        return 0
    if 'invariant' in text or 'technique' in text:
        return 5
    if 'strongbehavior' in text or 'strong' in text:
        return 4
    if 'moderate' in text:
        return 3
    if 'toolartifact' in text or 'tool' in text or 'artifact' in text:
        return 2
    if 'ephemeral' in text:
        return 1
    return 0


def _map_severity(raw: str, default: str = 'MEDIUM') -> str:
    text = (raw or '').upper()
    for value in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'):
        if value in text:
            return value
    return default


def _map_tlp(raw: str, default: str = 'AMBER') -> str:
    text = (raw or '').upper()
    for value in ('CLEAR', 'GREEN', 'AMBER+STRICT', 'AMBER', 'RED'):
        if value in text:
            return value
    return default


def _resolve_mitre_technique(technique_codes: list[str]):
    for code in technique_codes:
        try:
            return MitreAttackTechnique.objects.get(technique_id=code)
        except MitreAttackTechnique.DoesNotExist:
            if '.' in code:
                parent = code.split('.', 1)[0]
                try:
                    return MitreAttackTechnique.objects.get(technique_id=parent)
                except MitreAttackTechnique.DoesNotExist:
                    continue
    return None


def _build_active_chokepoint_context_lines(technique_codes: list[str], limit: int = 5) -> list[str]:
    """
    Return short markdown lines with active chokepoint guidance for ATT&CK codes.
    """
    codes = []
    for code in technique_codes or []:
        normalized = (code or "").upper().strip()
        if not normalized:
            continue
        codes.append(normalized)
        if '.' in normalized:
            codes.append(normalized.split('.', 1)[0])
    deduped = []
    for code in codes:
        if code not in deduped:
            deduped.append(code)
    if not deduped:
        return []

    snapshot = ChokepointSnapshot.objects.filter(status=ChokepointSnapshot.Status.ACTIVE).first()
    if not snapshot:
        return []

    entries = list(
        ChokepointEntry.objects.filter(snapshot=snapshot)
        .filter(
            models.Q(primary_technique_id__in=deduped) |
            models.Q(sub_technique_id__in=deduped)
        )
        .order_by('sub_technique_id', 'title')[:limit]
    )
    if not entries:
        return []

    revision = (snapshot.source_sha or snapshot.source_ref or '')[:12]
    lines = [f"Active chokepoint guidance ({revision}):"]
    for entry in entries:
        technique = entry.sub_technique_id or entry.primary_technique_id or 'Unknown'
        line = f"- {technique} [{entry.title}]"
        details = []
        telemetry = (entry.telemetry_prerequisites or '').strip()
        if telemetry:
            details.append(f"telemetry: {telemetry[:140]}")
        hints = entry.native_rule_hints if isinstance(entry.native_rule_hints, dict) else {}
        hint_chunks = []
        for key in ('kql', 'spl', 'wazuh_xml'):
            values = hints.get(key) or []
            if isinstance(values, list) and values:
                hint_chunks.append(f"{key}: {str(values[0])[:100]}")
        if hint_chunks:
            details.append("hints: " + " | ".join(hint_chunks))
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        known_bypasses = metadata.get("known_bypasses") or []
        if isinstance(known_bypasses, list) and known_bypasses:
            first_bypass = known_bypasses[0]
            if isinstance(first_bypass, dict):
                bypass = str(first_bypass.get("Bypass") or first_bypass.get("bypass") or "").strip()
                mitigation = str(first_bypass.get("Mitigation") or first_bypass.get("mitigation") or "").strip()
                if bypass:
                    details.append(f"bypass: {bypass[:110]}")
                if mitigation:
                    details.append(f"mitigation: {mitigation[:110]}")
            else:
                details.append(f"bypass: {str(first_bypass)[:110]}")
        if details:
            line += f" ({'; '.join(details)})"
        lines.append(line)
    return lines


def _to_strategy_dict(raw_strategy):
    if isinstance(raw_strategy, dict):
        return dict(raw_strategy)
    if isinstance(raw_strategy, str):
        try:
            parsed = json.loads(raw_strategy)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _parse_capability_entries(part1: dict, fallback_technique_codes: list[str]) -> list[dict]:
    library = _lookup_value(
        part1,
        'capability_abstraction_library',
        'capability abstraction library',
        default=[],
    )
    candidates = _coerce_list(library)
    if len(candidates) == 1 and isinstance(candidates[0], dict):
        maybe_entries = _lookup_value(
            candidates[0],
            'entries',
            'items',
            'capabilities',
            'capability_abstractions',
            default=None,
        )
        if maybe_entries is not None:
            candidates = _coerce_list(maybe_entries)

    parsed = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        raw_technique_code = _coerce_text(
            _lookup_value(row, 'attack technique code', 'att&ck technique code', 'technique code')
        )
        technique_code = _extract_first_code(raw_technique_code, r'\bT\d{4}(?:\.\d{3})?\b')
        if not technique_code:
            technique_code = raw_technique_code.upper()
        if not technique_code and fallback_technique_codes:
            technique_code = fallback_technique_codes[0]
        layer = _map_layer_name(_coerce_text(_lookup_value(row, 'abstraction layer')))
        component_artifact = _coerce_text(_lookup_value(row, 'component / artifact', 'component artifact'))
        if not layer or not component_artifact:
            continue
        parsed.append({
            'technique_code': technique_code.upper() if technique_code else '',
            'abstraction_layer': layer,
            'component_artifact': component_artifact[:255],
            'adversary_purpose': _coerce_text(_lookup_value(row, 'adversary purpose')),
            'common_evasions': _coerce_text(_lookup_value(row, 'common evasion / variations', 'common evasion', 'common evasions')),
            'expected_observables': _coerce_text(_lookup_value(row, 'expected observables')),
            'applicable_telemetry': _coerce_text(_lookup_value(row, 'applicable telemetry')),
            'detection_value': _coerce_text(_lookup_value(row, 'detection value')),
            'robustness_level': _map_robustness_level(_lookup_value(row, 'robustness level')),
        })
    return parsed


def _parse_containment_steps(raw_value) -> list[dict]:
    parsed = []
    for item in _coerce_list(raw_value):
        if isinstance(item, dict):
            description = _coerce_text(_lookup_value(item, 'description', 'action', 'step', 'text'))
            critical = bool(_lookup_value(item, 'critical', 'manual_approval', default=False))
        else:
            description = _coerce_text(item)
            critical = False
        if description:
            parsed.append({'description': description, 'critical': critical})
    return parsed


def _parse_notifications(raw_value) -> list[dict]:
    parsed = []
    for item in _coerce_list(raw_value):
        channel = ''
        target = ''
        if isinstance(item, dict):
            channel = _coerce_text(_lookup_value(item, 'channel', 'type', 'route'))
            target = _coerce_text(_lookup_value(item, 'target', 'destination', 'value', 'queue'))
        else:
            text = _coerce_text(item)
            if ':' in text:
                channel, target = [part.strip() for part in text.split(':', 1)]
            else:
                channel, target = text, ''
        ch_upper = channel.upper()
        if 'JIRA' in ch_upper:
            channel = 'Jira'
        elif 'SERVICE' in ch_upper:
            channel = 'ServiceNow'
        elif 'EMAIL' in ch_upper:
            channel = 'Email'
        elif 'TEAMS' in ch_upper or 'SLACK' in ch_upper:
            channel = 'Slack/Teams'
        if channel:
            parsed.append({'channel': channel, 'target': target})
    return parsed


def _parse_threat_actors(raw_value) -> list[dict]:
    parsed = []
    for item in _coerce_list(raw_value):
        if isinstance(item, dict):
            name = _coerce_text(_lookup_value(item, 'name', 'actor', 'threat actor'))
            aliases = _coerce_string_list(_lookup_value(item, 'aliases', 'alias'))
            sighting = _coerce_text(_lookup_value(item, 'sightings / campaigns mentioned', 'sightings', 'campaigns', 'sighting'))
            references = _coerce_string_list(_lookup_value(item, 'actor-specific references', 'references', 'refs'))
        else:
            name = _coerce_text(item)
            aliases = []
            sighting = ''
            references = []
        if not name:
            continue
        actor = {'name': name}
        if aliases:
            actor['aliases'] = aliases
        if sighting:
            actor['sighting'] = sighting
        if references:
            actor['references'] = references
        parsed.append(actor)
    return parsed


def _parse_downstream_correlation(raw_value) -> dict:
    if isinstance(raw_value, str):
        if not raw_value.strip():
            return {}
        return {
            'correlationScope': [],
            'temporalLogic': {'windowSize': '', 'windowUnit': 'seconds', 'sequenceType': 'strict'},
            'joinKeys': {'requiredFields': [], 'joinLogic': ''},
            'stateManagement': {'ttl': '', 'expiryCondition': ''},
            'falsePositiveMitigation': {'exclusionRules': raw_value.strip()},
        }
    if not isinstance(raw_value, dict):
        return {}

    scope_raw = _lookup_value(raw_value, 'correlation scope', default=[])
    scopes = []
    for scope in _coerce_string_list(scope_raw):
        norm = scope.lower()
        if 'host' in norm:
            scopes.append('Host-Based')
        elif 'network' in norm:
            scopes.append('Network-Wide')
        elif 'account' in norm:
            scopes.append('Account-Based')

    temporal = _lookup_value(raw_value, 'temporal logic', default={}) or {}
    temporal_window = _coerce_text(_lookup_value(temporal, 'window size', 'window'))
    temporal_unit = _coerce_text(_lookup_value(temporal, 'window unit', default='seconds')).lower()
    if temporal_unit not in ('seconds', 'minutes', 'hours'):
        temporal_unit = 'seconds'
    sequence_text = _coerce_text(_lookup_value(temporal, 'order', 'sequence type', default='strict')).lower()
    sequence_type = 'strict' if 'strict' in sequence_text else 'loose'

    join_keys = _lookup_value(raw_value, 'join keys', default={}) or {}
    join_fields = _coerce_string_list(_lookup_value(join_keys, 'required fields', 'fields', 'join keys'))
    join_logic = _coerce_text(_lookup_value(join_keys, 'join logic'))

    state = _lookup_value(raw_value, 'state management', default={}) or {}
    ttl = _coerce_text(_lookup_value(state, 'ttl', 'time-to-live'))
    expiry = _coerce_text(_lookup_value(state, 'expiry condition', 'expiry'))

    fp = _lookup_value(raw_value, 'false positive mitigation', default={}) or {}
    exclusions = _coerce_text(_lookup_value(fp, 'exclusion rules', 'exclusions'))

    return {
        'correlationScope': list(dict.fromkeys(scopes)),
        'temporalLogic': {
            'windowSize': temporal_window,
            'windowUnit': temporal_unit,
            'sequenceType': sequence_type,
        },
        'joinKeys': {
            'requiredFields': join_fields,
            'joinLogic': join_logic,
        },
        'stateManagement': {
            'ttl': ttl,
            'expiryCondition': expiry,
        },
        'falsePositiveMitigation': {
            'exclusionRules': exclusions,
        },
    }


def _extract_threat_report_parts(payload: dict):
    part1 = _lookup_value(payload, 'part1', 'part 1', 'detection strategy', 'part_1', default={}) or {}
    part2 = _lookup_value(payload, 'part2', 'part 2', 'deep dive', 'part_2', default={}) or {}
    part4 = _lookup_value(payload, 'part4', 'part 4', 'soar configuration', 'part_4', default={}) or {}
    part5 = _lookup_value(payload, 'part5', 'part 5', 'testing & validation', 'testing and validation', 'part_5', default={}) or {}
    return (
        part1 if isinstance(part1, dict) else {},
        part2 if isinstance(part2, dict) else {},
        part4 if isinstance(part4, dict) else {},
        part5 if isinstance(part5, dict) else {},
    )


def _merge_downstream_correlation(existing, incoming, mode: str):
    if mode == 'OVERWRITE' or not isinstance(existing, dict):
        return incoming or {}
    if not isinstance(incoming, dict):
        return existing

    merged = dict(existing)
    merged_scope = _merge_list(existing.get('correlationScope') or [], incoming.get('correlationScope') or [], 'APPEND')
    merged_temporal = dict(existing.get('temporalLogic') or {})
    merged_temporal.update({k: v for k, v in (incoming.get('temporalLogic') or {}).items() if v})
    merged_join = dict(existing.get('joinKeys') or {})
    merged_join['requiredFields'] = _merge_list(
        (existing.get('joinKeys') or {}).get('requiredFields') or [],
        (incoming.get('joinKeys') or {}).get('requiredFields') or [],
        'APPEND',
    )
    incoming_join_logic = _coerce_text((incoming.get('joinKeys') or {}).get('joinLogic'))
    if incoming_join_logic:
        merged_join['joinLogic'] = _merge_text(
            _coerce_text((existing.get('joinKeys') or {}).get('joinLogic')),
            incoming_join_logic,
            'APPEND',
        )
    merged_state = dict(existing.get('stateManagement') or {})
    merged_state.update({k: v for k, v in (incoming.get('stateManagement') or {}).items() if v})
    merged_fp = dict(existing.get('falsePositiveMitigation') or {})
    merged_fp['exclusionRules'] = _merge_text(
        _coerce_text((existing.get('falsePositiveMitigation') or {}).get('exclusionRules')),
        _coerce_text((incoming.get('falsePositiveMitigation') or {}).get('exclusionRules')),
        'APPEND',
    )

    merged['correlationScope'] = merged_scope
    merged['temporalLogic'] = merged_temporal
    merged['joinKeys'] = merged_join
    merged['stateManagement'] = merged_state
    merged['falsePositiveMitigation'] = merged_fp
    return merged

class OrgAISettingsType(DjangoObjectType):
    class Meta:
        model = OrgAISettings
        fields = ('id', 'ollama_base_url', 'ollama_model', 'org_preferred_model',
                  'azure_openai_endpoint', 'azure_openai_deployment', 'created_at', 'updated_at',
                  'ollama_enabled', 'openai_enabled', 'gemini_enabled', 'claude_enabled', 'azure_openai_enabled',
                  'shared_profile_locked')

    has_ollama = graphene.Boolean()
    has_openai = graphene.Boolean()
    has_gemini = graphene.Boolean()
    has_claude = graphene.Boolean()
    has_azure_openai = graphene.Boolean()
    has_any_provider = graphene.Boolean()
    config_source = graphene.String()
    shared_profile_id = graphene.UUID()
    shared_profile_name = graphene.String()
    can_edit_custom_settings = graphene.Boolean()

    def resolve_has_ollama(self, info):
        return bool(getattr(_resolve_effective_org_ai_settings(self), 'has_ollama', False))

    def resolve_has_openai(self, info):
        return bool(getattr(_resolve_effective_org_ai_settings(self), 'has_openai', False))

    def resolve_has_gemini(self, info):
        return bool(getattr(_resolve_effective_org_ai_settings(self), 'has_gemini', False))

    def resolve_has_claude(self, info):
        return bool(getattr(_resolve_effective_org_ai_settings(self), 'has_claude', False))

    def resolve_has_azure_openai(self, info):
        return bool(getattr(_resolve_effective_org_ai_settings(self), 'has_azure_openai', False))

    def resolve_has_any_provider(self, info):
        return bool(getattr(_resolve_effective_org_ai_settings(self), 'has_any_provider', False))

    def resolve_config_source(self, info):
        return getattr(self, 'config_source', 'CUSTOM')

    def resolve_shared_profile_id(self, info):
        return getattr(self, 'shared_profile_id', None)

    def resolve_shared_profile_name(self, info):
        if getattr(self, 'shared_profile_id', None):
            return getattr(self.shared_profile, 'name', '') if getattr(self, 'shared_profile', None) else ''
        return ''

    def resolve_can_edit_custom_settings(self, info):
        return bool(getattr(self, 'can_edit_custom_settings', True))


def _resolve_effective_org_ai_settings(settings_obj):
    """Resolve effective Org AI settings from a GraphQL root object."""
    if hasattr(settings_obj, 'get_effective_settings'):
        return settings_obj.get_effective_settings()
    return settings_obj


class SharedAIProfileType(DjangoObjectType):
    class Meta:
        model = SharedAIProfile
        fields = (
            'id',
            'name',
            'ollama_base_url',
            'ollama_model',
            'org_preferred_model',
            'azure_openai_endpoint',
            'azure_openai_deployment',
            'created_at',
            'updated_at',
            'is_active',
            'ollama_enabled',
            'openai_enabled',
            'gemini_enabled',
            'claude_enabled',
            'azure_openai_enabled',
        )

    has_ollama = graphene.Boolean()
    has_openai = graphene.Boolean()
    has_gemini = graphene.Boolean()
    has_claude = graphene.Boolean()
    has_azure_openai = graphene.Boolean()
    has_any_provider = graphene.Boolean()

    def resolve_has_ollama(self, info):
        return self.has_ollama

    def resolve_has_openai(self, info):
        return self.has_openai

    def resolve_has_gemini(self, info):
        return self.has_gemini

    def resolve_has_claude(self, info):
        return self.has_claude

    def resolve_has_azure_openai(self, info):
        return self.has_azure_openai

    def resolve_has_any_provider(self, info):
        return self.has_any_provider


class UserAISettingsType(DjangoObjectType):
    class Meta:
        model = UserAISettings
        exclude_fields = ('openai_api_key', 'gemini_api_key', 'claude_api_key') # Never return raw keys to UI

    has_openai = graphene.Boolean()
    has_gemini = graphene.Boolean()
    has_claude = graphene.Boolean()
    has_ollama = graphene.Boolean()
    decrypted_openai = graphene.Boolean()
    decrypted_gemini = graphene.Boolean()
    decrypted_claude = graphene.Boolean()
    key_status = graphene.String()
    effective_preferred_model = graphene.String()

    def resolve_has_openai(self, info): return bool(self.openai_api_key)
    def resolve_has_gemini(self, info): return bool(self.gemini_api_key)
    def resolve_has_claude(self, info): return bool(self.claude_api_key)
    def resolve_has_ollama(self, info):
        if not self.use_org_ai:
            return False
        org = getattr(self.user, 'organization', None)
        if not org:
            return False
        try:
            org_settings = OrgAISettings.objects.select_related('shared_profile').get(organization=org)
            effective = org_settings.get_effective_settings()
            return bool(getattr(effective, 'has_ollama', False))
        except OrgAISettings.DoesNotExist:
            return False
    def resolve_decrypted_openai(self, info): return bool(self.get_openai_key())
    def resolve_decrypted_gemini(self, info): return bool(self.get_gemini_key())
    def resolve_decrypted_claude(self, info): return bool(self.get_claude_key())
    def resolve_effective_preferred_model(self, info):
        """Return the effective model name, resolving org AI settings when use_org_ai=True."""
        if self.use_org_ai:
            org = getattr(self.user, 'organization', None)
            if org:
                try:
                    org_settings = OrgAISettings.objects.select_related('shared_profile').get(organization=org)
                    effective = org_settings.get_effective_settings()
                    if getattr(effective, 'has_any_provider', False):
                        pm = effective.preferred_model
                        if pm == 'OLLAMA':
                            return effective.get_ollama_model() or 'OLLAMA'
                        return pm
                except OrgAISettings.DoesNotExist:
                    pass
        return self.preferred_model
    def resolve_key_status(self, info):
        parts = []
        for label, raw, dec in [
            ('OPENAI', self.openai_api_key, self.get_openai_key()),
            ('GEMINI', self.gemini_api_key, self.get_gemini_key()),
            ('CLAUDE', self.claude_api_key, self.get_claude_key()),
        ]:
            if raw and raw.startswith('enc:') and not dec:
                parts.append(f"{label}:ENCRYPTED_UNREADABLE")
            elif dec:
                parts.append(f"{label}:OK")
            elif raw:
                parts.append(f"{label}:PLAINTEXT")
            else:
                parts.append(f"{label}:MISSING")
        return ','.join(parts)

class UpdateAISettings(graphene.Mutation):
    class Arguments:
        openai_key = graphene.String()
        gemini_key = graphene.String()
        claude_key = graphene.String()
        preferred_model = graphene.String()
        use_org_ai = graphene.Boolean()

    settings = graphene.Field(UserAISettingsType)
    warning = graphene.String()

    def mutate(self, info, **kwargs):
        user = info.context.user
        settings, _ = UserAISettings.objects.get_or_create(user=user)

        # Apply updates (empty string removes the key)
        if 'openai_key' in kwargs:
            settings.openai_api_key = kwargs['openai_key'] or ''
        if 'gemini_key' in kwargs:
            settings.gemini_api_key = kwargs['gemini_key'] or ''
        if 'claude_key' in kwargs:
            settings.claude_api_key = kwargs['claude_key'] or ''
        # Accept both snake_case and camelCase from GraphQL client
        pm = kwargs.get('preferred_model') if 'preferred_model' in kwargs else kwargs.get('preferredModel')
        normalized_pm = _normalize_preferred_model_choice(pm)
        if pm is not None and pm != "":
            if normalized_pm:
                settings.preferred_model = normalized_pm
        if 'use_org_ai' in kwargs and kwargs['use_org_ai'] is not None:
            settings.use_org_ai = kwargs['use_org_ai']

        # Re-evaluate preferred_model if it points to a missing provider or wasn't supplied
        # Use decrypted values to build availability so broken encryption doesn't falsely mark providers available
        from .engine import build_available
        available = build_available(settings)

        original_preferred = pm if pm else settings.preferred_model
        warning = None
        if available and settings.preferred_model not in available:
            from .engine import FALLBACK_PRIORITY
            for p in FALLBACK_PRIORITY:
                if p in available:
                    settings.preferred_model = p
                    break
            if original_preferred and original_preferred != settings.preferred_model:
                warning = f"Preferred model '{original_preferred}' not available; switched to '{settings.preferred_model}'."
        if settings.preferred_model not in VALID_USER_PREFERRED_MODELS:
            settings.preferred_model = VALID_USER_PREFERRED_MODELS[0]
            if not warning and original_preferred and original_preferred != settings.preferred_model:
                warning = f"Preferred model '{original_preferred}' is invalid; switched to '{settings.preferred_model}'."
        if not available:
            warning = "No provider keys configured; add at least one to enable AI generation."

        settings.save()
        return UpdateAISettings(settings=settings, warning=warning)

class DeconstructRule(graphene.Mutation):
    class Arguments:
        rule_text = graphene.String()
        rule_url = graphene.String()

    report = graphene.String()
    provider_used = graphene.String()
    warning = graphene.String()

    def mutate(self, info, rule_text=None, rule_url=None):
        user = info.context.user
        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return DeconstructRule(report="Error: Please configure AI Settings in your profile first.", provider_used="NONE", warning=None)

        effective = _get_effective_ai_settings(settings)
        content = None
        warning = None
        if rule_url:
            try:
                resp = requests.get(rule_url, timeout=10)
                resp.raise_for_status()
                content = resp.text
            except RequestException as e:
                warning = f"Failed to fetch URL: {e}"
        if not content:
            content = rule_text or ""
        if not content.strip():
            return DeconstructRule(report="Error: No rule content provided.", provider_used="NONE", warning=warning)

        report_text, provider = run_logic_deconstruction(effective, content)
        return DeconstructRule(report=report_text, provider_used=provider, warning=warning)


class SuggestRuleImprovements(graphene.Mutation):
    """AI-powered analysis of detection rules with specific improvement suggestions."""
    class Arguments:
        rule_content = graphene.String(required=True, description="The detection rule content to analyze")
        rule_format = graphene.String(required=False, description="Format: KQL, EQL, WAZUH, or SPL (default: KQL)")

    suggestions = graphene.String(description="AI-generated improvement suggestions (analysis text)")
    improved_rule = graphene.String(description="Complete improved rule extracted from the AI response")
    provider_used = graphene.String(description="Which AI provider was used")

    def mutate(self, info, rule_content, rule_format=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return SuggestRuleImprovements(
                suggestions="Error: Please configure AI Settings in your profile first.",
                improved_rule=None,
                provider_used="NONE"
            )

        if not rule_content or not rule_content.strip():
            return SuggestRuleImprovements(
                suggestions="Error: No rule content provided to analyze.",
                improved_rule=None,
                provider_used="NONE"
            )

        effective = _get_effective_ai_settings(settings)
        fmt = rule_format or 'KQL'
        rag_context, reference_context = _enrich_with_rag_reference_context(
            user,
            {},
            rule_content=rule_content,
            language=fmt,
            limit=6,
        )
        suggestions_text, provider = suggest_rule_improvements(
            effective, 
            rule_content, 
            fmt,
            rag_context if rag_context else None,
        )
        _record_rag_usage(reference_context)

        # Extract the improved rule from between the delimiter markers.
        # Use flexible whitespace matching to tolerate leading spaces or \r\n line endings
        # that the AI may produce despite the prompt asking for no indentation.
        improved_rule = None
        marker_match = re.search(
            r'[ \t]*---IMPROVED-RULE-START---[ \t]*\r?\n(.*?)\r?\n[ \t]*---IMPROVED-RULE-END---',
            suggestions_text,
            re.DOTALL,
        )
        if marker_match:
            improved_rule = marker_match.group(1).strip()
            # Strip the raw delimiters from the displayed suggestions text so the
            # markdown view remains clean.
            suggestions_display = re.sub(
                r'\n?[ \t]*---IMPROVED-RULE-START---[ \t]*\r?\n.*?\r?\n[ \t]*---IMPROVED-RULE-END---[ \t]*\n?',
                '',
                suggestions_text,
                flags=re.DOTALL,
            ).strip()
        else:
            suggestions_display = suggestions_text

        return SuggestRuleImprovements(
            suggestions=suggestions_display,
            improved_rule=improved_rule,
            provider_used=provider,
        )


class GenerateSimilarRules(graphene.Mutation):
    """Generate similar detection rules based on an existing rule with various variation options."""
    class Arguments:
        rule_content = graphene.String(required=True, description="The source detection rule to base variations on")
        rule_format = graphene.String(required=False, description="Format of source rule: KQL, EQL, WAZUH, or SPL (default: KQL)")
        variation_type = graphene.String(required=False, description="Type: technique, evasion, platform, scope, custom (default: technique)")
        num_variations = graphene.Int(required=False, description="Number of variations to generate 1-5 (default: 3)")
        target_format = graphene.String(required=False, description="Output format (defaults to source format)")
        custom_instructions = graphene.String(required=False, description="Custom instructions for generation")

    generated_rules = graphene.String(description="AI-generated similar rules separated by ---RULE---")
    provider_used = graphene.String(description="Which AI provider was used")
    variation_type = graphene.String(description="The variation type that was used")
    num_generated = graphene.Int(description="Number of rules generated")

    def mutate(self, info, rule_content, rule_format=None, variation_type=None, 
               num_variations=None, target_format=None, custom_instructions=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return GenerateSimilarRules(
                generated_rules="Error: Please configure AI Settings in your profile first.",
                provider_used="NONE",
                variation_type=variation_type or 'technique',
                num_generated=0
            )

        if not rule_content or not rule_content.strip():
            return GenerateSimilarRules(
                generated_rules="Error: No rule content provided.",
                provider_used="NONE",
                variation_type=variation_type or 'technique',
                num_generated=0
            )

        # Validate variation_type
        valid_types = ['technique', 'evasion', 'platform', 'scope', 'custom']
        var_type = (variation_type or 'technique').lower()
        if var_type not in valid_types:
            var_type = 'technique'

        effective = _get_effective_ai_settings(settings)
        source_fmt = (rule_format or 'KQL').upper()
        target_fmt = (target_format or source_fmt).upper()
        rag_language = _resolve_rag_language(target_fmt) or _resolve_rag_language(source_fmt)

        rag_context = {}
        reference_context = []
        if rag_language:
            rag_context, reference_context = _enrich_with_rag_reference_context(
                user,
                {},
                rule_content=rule_content,
                additional_text=custom_instructions,
                language=rag_language,
                limit=6,
            )

        generated_text, provider = generate_similar_rules(
            effective,
            rule_content,
            rule_format or 'KQL',
            rag_context if rag_context else None,
            var_type,
            num_variations or 3,
            target_format,
            custom_instructions,
        )
        _record_rag_usage(reference_context)

        # Normalise common separator variants the AI might produce so the
        # frontend can reliably split on '---RULE---'.
        generated_text = re.sub(
            r'(?m)^\s*-{3,}\s*RULE\s*-{3,}\s*$',
            '---RULE---',
            generated_text,
            flags=re.IGNORECASE,
        )

        # Count rules generated (by counting delimiters + 1, or 1 if no delimiters)
        num_generated = generated_text.count('---RULE---') + 1 if '---RULE---' in generated_text else 1
        
        return GenerateSimilarRules(
            generated_rules=generated_text,
            provider_used=provider,
            variation_type=var_type,
            num_generated=num_generated
        )


class MaieuticQuestion(graphene.Mutation):
    """AI-powered Socratic questioning with full form context awareness."""
    class Arguments:
        user_input = graphene.String(required=True, description="User's current input/hypothesis")
        conversation_history = graphene.JSONString(required=False, description="Previous conversation turns")
        current_step = graphene.String(required=False, description="Current step in workflow: hypothesis, interrogation, robustness, playbook")
        challenge_level = graphene.String(
            required=False,
            description="Question depth: light, standard, expert",
        )
        synthesis_mode = graphene.Boolean(
            required=False,
            description="When true (typically in review), AI should propose autofill content for missing workbench sections.",
        )
        form_context = graphene.JSONString(
            required=False,
            description="Complete form state across all steps so the AI can reference what the user has already entered"
        )

    ai_response = graphene.JSONString(description="AI's Socratic response with reasoning and question")
    provider_used = graphene.String(description="Which AI provider was used")
    field_suggestions = graphene.JSONString(description="Field-specific hints based on form context")
    autofill_candidates = graphene.JSONString(description="AI-proposed field/value drafts for optional autofill")

    def mutate(
        self,
        info,
        user_input,
        conversation_history=None,
        current_step='hypothesis',
        challenge_level='standard',
        synthesis_mode=False,
        form_context=None,
    ):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            import json
            return MaieuticQuestion(
                ai_response=json.dumps({"error": "Please configure AI Settings in your profile first.", "socratic_question": "What detection hypothesis would you like to explore?"}),
                provider_used="NONE",
                field_suggestions=json.dumps({}),
                autofill_candidates=json.dumps({"target_fields": [], "proposed_text": {}}),
            )
        
        import json

        parsed_history = conversation_history
        if conversation_history and isinstance(conversation_history, str):
            try:
                parsed_history = json.loads(conversation_history)
            except (json.JSONDecodeError, TypeError):
                parsed_history = None

        # Parse form_context if provided as a JSON string
        parsed_form_context = None
        if form_context:
            try:
                parsed_form_context = json.loads(form_context) if isinstance(form_context, str) else form_context
            except (json.JSONDecodeError, TypeError):
                parsed_form_context = None

        effective = _get_effective_ai_settings(settings)
        response_text, provider, field_suggestions = run_maieutic_questioning(
            effective,
            user_input,
            parsed_history,
            current_step or 'hypothesis',
            parsed_form_context,
            challenge_level or 'standard',
            bool(synthesis_mode),
        )
        
        # Parse JSON response
        try:
            response_json = json.loads(response_text)
        except json.JSONDecodeError:
            response_json = {"error": "Invalid AI response", "socratic_question": response_text[:200]}
        autofill_candidates = response_json.get("autofill_candidates", {"target_fields": [], "proposed_text": {}})
        
        return MaieuticQuestion(
            ai_response=response_json,
            provider_used=provider,
            field_suggestions=json.dumps(field_suggestions) if field_suggestions else json.dumps({}),
            autofill_candidates=json.dumps(autofill_candidates),
        )


class StrainResult(graphene.ObjectType):
    hunt_id = graphene.String()
    hypothesis = graphene.String()
    status = graphene.String()
    priority = graphene.String()
    verification_summary = graphene.String()
    infrastructure_summary = graphene.String()
    pivot_summary = graphene.String()
    false_positive_summary = graphene.String()
    mitre_summary = graphene.String()
    detection_logic_summary = graphene.String()
    confidence = graphene.String()
    error = graphene.String()

class ExtractStrainData(graphene.Mutation):
    class Arguments:
        file_content = graphene.String(required=True)
        filename = graphene.String(required=True)

    result = graphene.Field(StrainResult)
    provider_used = graphene.String()

    def mutate(self, info, file_content, filename):
        print(f"[strAIn] Received request for file: {filename}") # LOGGING
        user = info.context.user
        if user.is_anonymous:
            print("[strAIn] User is anonymous") # LOGGING
            raise Exception("Authentication required")
        
        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            print("[strAIn] No AI Settings found") # LOGGING
            return ExtractStrainData(
                result=StrainResult(error="Please configure AI settings first. Go to your profile to add API keys."),
                provider_used="NONE"
            )

        try:
            print("[strAIn] Starting engine extraction...") # LOGGING
            effective = _get_effective_ai_settings(settings)
            json_str, provider = run_strain_extraction(effective, file_content, filename)
            print(f"[strAIn] Extraction complete. Provider: {provider}. Result len: {len(json_str)}") # LOGGING
            
            import json
            try:
                data = json.loads(json_str)
            except Exception as parse_error:
                print(f"[strAIn] JSON parse error: {parse_error}") # LOGGING
                data = {"error": f"Failed to parse AI response: {str(parse_error)}", "hypothesis": str(json_str)[:200]}
                
            return ExtractStrainData(
                result=StrainResult(
                    hunt_id=data.get('huntId') or data.get('hunt_id', ''),
                    hypothesis=data.get('hypothesis', ''),
                    status=data.get('status', 'IDEA'),
                    priority=data.get('priority', 'MEDIUM'),
                    verification_summary=data.get('verificationSummary') or data.get('verification_summary', ''),
                    infrastructure_summary=data.get('infrastructureSummary') or data.get('infrastructure_summary', ''),
                    pivot_summary=data.get('pivotSummary') or data.get('pivot_summary', ''),
                    false_positive_summary=data.get('falsePositiveSummary') or data.get('false_positive_summary', ''),
                    mitre_summary=data.get('mitreSummary') or data.get('mitre_summary', ''),
                    detection_logic_summary=data.get('detectionLogicSummary') or data.get('detection_logic_summary', ''),
                    confidence=data.get('confidence', 'Low'),
                    error=data.get('error', '')
                ),
                provider_used=provider
            )
        except Exception as e:
            # Catch all extraction errors and return them as structured error
            error_msg = f"Document processing failed: {str(e)}"
            print(f"[strAIn] Extraction error: {error_msg}") # LOGGING
            import traceback
            traceback.print_exc()
            return ExtractStrainData(
                result=StrainResult(
                    error=error_msg,
                    hypothesis='',
                    status='IDEA',
                    priority='MEDIUM'
                ),
                provider_used="ERROR"
            )


class ExtractStrainDataFromURL(graphene.Mutation):
    class Arguments:
        url = graphene.String(required=True)

    result = graphene.Field(StrainResult)
    provider_used = graphene.String()

    def mutate(self, info, url):
        print(f"[strAIn] Received URL request: {url}")  # LOGGING
        user = info.context.user
        if user.is_anonymous:
            print("[strAIn] User is anonymous")  # LOGGING
            raise Exception("Authentication required")

        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            print("[strAIn] No AI Settings found")  # LOGGING
            return ExtractStrainDataFromURL(
                result=StrainResult(error="Please configure AI settings first. Go to your profile to add API keys."),
                provider_used="NONE"
            )

        try:
            print("[strAIn] Starting URL engine extraction...")  # LOGGING
            effective = _get_effective_ai_settings(settings)
            json_str, provider = fetch_and_extract_from_url(effective, url)
            print(f"[strAIn] URL Extraction complete. Provider: {provider}. Result len: {len(json_str)}")  # LOGGING

            import json
            try:
                data = json.loads(json_str)
            except Exception as parse_error:
                print(f"[strAIn] JSON parse error: {parse_error}")  # LOGGING
                data = {"error": f"Failed to parse AI response: {str(parse_error)}", "hypothesis": str(json_str)[:200]}

            return ExtractStrainDataFromURL(
                result=StrainResult(
                    hunt_id=data.get('huntId') or data.get('hunt_id', ''),
                    hypothesis=data.get('hypothesis', ''),
                    status=data.get('status', 'IDEA'),
                    priority=data.get('priority', 'MEDIUM'),
                    verification_summary=data.get('verificationSummary') or data.get('verification_summary', ''),
                    infrastructure_summary=data.get('infrastructureSummary') or data.get('infrastructure_summary', ''),
                    pivot_summary=data.get('pivotSummary') or data.get('pivot_summary', ''),
                    false_positive_summary=data.get('falsePositiveSummary') or data.get('false_positive_summary', ''),
                    mitre_summary=data.get('mitreSummary') or data.get('mitre_summary', ''),
                    detection_logic_summary=data.get('detectionLogicSummary') or data.get('detection_logic_summary', ''),
                    confidence=data.get('confidence', 'Low'),
                    error=data.get('error', '')
                ),
                provider_used=provider
            )
        except Exception as e:
            error_msg = f"URL processing failed: {str(e)}"
            print(f"[strAIn] URL Extraction error: {error_msg}")  # LOGGING
            import traceback
            traceback.print_exc()
            return ExtractStrainDataFromURL(
                result=StrainResult(
                    error=error_msg,
                    hypothesis='',
                    status='IDEA',
                    priority='MEDIUM'
                ),
                provider_used="ERROR"
            )


class GenerateResponsePlaybook(graphene.Mutation):
    """Generate a structured incident response playbook using AI, based on Deep Dive context fields."""

    class Arguments:
        playbook_id = graphene.UUID(required=True)

    response_playbook = graphene.String()
    provider_used = graphene.String()

    def mutate(self, info, playbook_id):
        user = info.context.user
        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return GenerateResponsePlaybook(
                response_playbook="# Error: Please configure AI Settings in your profile first.",
                provider_used="NONE",
            )

        try:
            graph = PlaybookGraph.objects.get(pk=playbook_id)
        except PlaybookGraph.DoesNotExist:
            return GenerateResponsePlaybook(
                response_playbook="# Error: Playbook not found.",
                provider_used="NONE",
            )

        context = {
            'title': graph.title or 'Unknown',
            'goal': graph.goal or '',
            'technical_context': graph.technical_context or '',
            'false_positives': graph.false_positives or '',
            'blind_spots': graph.blind_spots or '',
            'technique_id': getattr(graph.mitre_technique, 'technique_id', '') or '',
            'technique_name': getattr(graph.mitre_technique, 'name', '') or '',
            'detection_rule': graph.detection_rule or '',
        }

        context, reference_context = _enrich_with_rag_reference_context(
            user,
            context,
            rule_content=graph.detection_rule or '',
            language=_resolve_rag_language(None, rule_content=graph.detection_rule or '') or 'KQL',
            limit=6,
        )

        playbook_text, provider = generate_response_playbook(_get_effective_ai_settings(settings), context)
        _record_rag_usage(reference_context)
        return GenerateResponsePlaybook(response_playbook=playbook_text, provider_used=provider)


class RecommendReusableRuleFromRag(graphene.Mutation):
    """Assess whether an existing retrieved template should be reused/adapted for this workbench."""

    class Arguments:
        playbook_id = graphene.UUID(required=True)
        output_format = graphene.String(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    provider_used = graphene.String()
    workbench_summary = graphene.String()
    decision = graphene.String()
    rationale = graphene.String()
    candidate_source = graphene.String()
    adapted_rule = graphene.String()
    reference_count = graphene.Int()

    def mutate(self, info, playbook_id, output_format=None):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        fmt = (output_format or 'KQL').upper()
        rag_language = _resolve_rag_language(fmt)
        if not rag_language:
            return RecommendReusableRuleFromRag(
                success=False,
                message="Reusable-template assessment currently supports KQL, EQL, SPL, and WAZUH.",
                provider_used="NONE",
                workbench_summary='',
                decision='CREATE_NEW',
                rationale='Output format is not supported for RAG template reuse.',
                candidate_source='NONE',
                adapted_rule='',
                reference_count=0,
            )

        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return RecommendReusableRuleFromRag(
                success=False,
                message="Please configure AI Settings in your profile first.",
                provider_used="NONE",
                workbench_summary='',
                decision='CREATE_NEW',
                rationale='AI settings are not configured.',
                candidate_source='NONE',
                adapted_rule='',
                reference_count=0,
            )

        try:
            graph = PlaybookGraph.objects.prefetch_related('selected_capability_abstractions').get(
                pk=playbook_id,
                organization=user.organization,
            )
        except PlaybookGraph.DoesNotExist:
            return RecommendReusableRuleFromRag(
                success=False,
                message="Playbook not found.",
                provider_used="NONE",
                workbench_summary='',
                decision='CREATE_NEW',
                rationale='Playbook does not exist or is not accessible.',
                candidate_source='NONE',
                adapted_rule='',
                reference_count=0,
            )

        base_context = _build_playbook_generation_context(graph)
        base_context['existing_logic'] = graph.detection_rule or base_context.get('existing_logic') or ''

        rag_context, reference_context = _enrich_with_rag_reference_context(
            user,
            base_context,
            rule_content=graph.detection_rule or '',
            language=rag_language,
            limit=8,
        )

        recommendation, provider = recommend_reusable_rule(
            _get_effective_ai_settings(settings),
            rag_context,
            output_format=fmt,
        )
        _record_rag_usage(reference_context)

        return RecommendReusableRuleFromRag(
            success=True,
            message=f"Assessed {len(reference_context)} retrieved template(s) for reuse.",
            provider_used=provider,
            workbench_summary=recommendation.get('workbench_summary') or '',
            decision=recommendation.get('decision') or 'CREATE_NEW',
            rationale=recommendation.get('rationale') or '',
            candidate_source=recommendation.get('candidate_source') or 'NONE',
            adapted_rule=recommendation.get('adapted_rule') or '',
            reference_count=len(reference_context),
        )


class TranslateResponsePlaybook(graphene.Mutation):
    """Translate response playbook text while preserving one original + one translation layout."""

    class Arguments:
        playbook_id = graphene.UUID(required=True)
        target_language = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    provider_used = graphene.String()
    target_language = graphene.String()
    translated_text = graphene.String()
    response_playbook = graphene.String()

    def mutate(self, info, playbook_id, target_language):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        lang_code = (target_language or '').strip().upper()
        if lang_code not in SUPPORTED_RESPONSE_PLAYBOOK_TRANSLATIONS:
            allowed = ', '.join(sorted(SUPPORTED_RESPONSE_PLAYBOOK_TRANSLATIONS.keys()))
            return TranslateResponsePlaybook(
                success=False,
                message=f"Unsupported target language. Allowed values: {allowed}.",
                provider_used='NONE',
                target_language=lang_code or None,
                translated_text='',
                response_playbook='',
            )

        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return TranslateResponsePlaybook(
                success=False,
                message="Please configure AI Settings in your profile first.",
                provider_used='NONE',
                target_language=lang_code,
                translated_text='',
                response_playbook='',
            )

        try:
            graph = PlaybookGraph.objects.get(pk=playbook_id, organization=user.organization)
        except PlaybookGraph.DoesNotExist:
            return TranslateResponsePlaybook(
                success=False,
                message="Playbook not found.",
                provider_used='NONE',
                target_language=lang_code,
                translated_text='',
                response_playbook='',
            )

        parsed = _split_translated_response_playbook(graph.response_playbook)
        original_text = (parsed.get('original') or '').strip()
        if not original_text:
            return TranslateResponsePlaybook(
                success=False,
                message="Response Playbook is empty. Add content before requesting translation.",
                provider_used='NONE',
                target_language=lang_code,
                translated_text='',
                response_playbook='',
            )

        target_label = SUPPORTED_RESPONSE_PLAYBOOK_TRANSLATIONS[lang_code]
        system_prompt = (
            "You are a cybersecurity localization specialist. "
            "Translate the provided response playbook into the requested target language. "
            "Preserve markdown structure, numbering, bullets, and line breaks. "
            "Do not add commentary, prefaces, or explanations. "
            "Do NOT translate proper names, product names, vendor names, MITRE ATT&CK IDs, "
            "IOC values (hashes, IPs, domains), query syntax, code snippets, commands, file paths, "
            "registry paths, API names, or specialized cybersecurity/IT terminology."
        )
        user_prompt = (
            f"Target language code: {lang_code}\n"
            f"Target language name: {target_label}\n\n"
            "Translate the text below:\n\n"
            f"{original_text}"
        )

        try:
            translated_text, provider = run_custom_prompt(
                _get_effective_ai_settings(settings),
                user_prompt=user_prompt,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            logger.exception(
                "translate_response_playbook_ai failed: playbook_id=%s user=%s language=%s",
                playbook_id,
                getattr(user, 'username', 'unknown'),
                lang_code,
            )
            return TranslateResponsePlaybook(
                success=False,
                message=f"Translation failed: {exc}",
                provider_used='ERROR',
                target_language=lang_code,
                translated_text='',
                response_playbook='',
            )

        translated = (translated_text or '').strip()
        translated = re.sub(r'^```[a-zA-Z]*\s*', '', translated).strip()
        translated = re.sub(r'\s*```$', '', translated).strip()
        if (not translated) or translated.lower().startswith('error:'):
            return TranslateResponsePlaybook(
                success=False,
                message=translated or "AI returned empty translation output.",
                provider_used=provider or 'NONE',
                target_language=lang_code,
                translated_text='',
                response_playbook='',
            )

        formatted_response = _compose_translated_response_playbook(
            original=original_text,
            translated=translated,
            language_code=lang_code,
        )
        graph.response_playbook = formatted_response
        graph.save(update_fields=['response_playbook'])

        return TranslateResponsePlaybook(
            success=True,
            message=f"Response Playbook translated to {target_label}.",
            provider_used=provider,
            target_language=lang_code,
            translated_text=translated,
            response_playbook=formatted_response,
        )


class UpdateOrgAISettings(graphene.Mutation):
    """Update organization-wide AI settings. Admin only."""
    class Arguments:
        organization_id = graphene.UUID()
        ollama_base_url = graphene.String()
        ollama_model = graphene.String()
        openai_key = graphene.String()
        gemini_key = graphene.String()
        claude_key = graphene.String()
        azure_openai_endpoint = graphene.String()
        azure_openai_key = graphene.String()
        azure_openai_deployment = graphene.String()
        org_preferred_model = graphene.String()
        ollama_enabled = graphene.Boolean()
        openai_enabled = graphene.Boolean()
        gemini_enabled = graphene.Boolean()
        claude_enabled = graphene.Boolean()
        azure_openai_enabled = graphene.Boolean()

    settings = graphene.Field(OrgAISettingsType)
    ok = graphene.Boolean()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, organization_id=None, ollama_base_url=None, ollama_model=None,
               openai_key=None, gemini_key=None, claude_key=None,
               azure_openai_endpoint=None, azure_openai_key=None, azure_openai_deployment=None,
               org_preferred_model=None,
               ollama_enabled=None, openai_enabled=None, gemini_enabled=None,
               claude_enabled=None, azure_openai_enabled=None):
        user = info.context.user
        org = _resolve_target_org(user, organization_id=organization_id)
        if org is None:
            raise Exception("User is not associated with an organization.")
        settings, _ = OrgAISettings.objects.select_related('shared_profile').get_or_create(organization=org)
        if settings.shared_profile_locked and not (user.is_superuser or user.is_staff):
            raise GraphQLError(
                "Organization AI settings are locked by superuser shared profile assignment."
            )
        if ollama_base_url is not None:
            settings.ollama_base_url = ollama_base_url.strip()
        if ollama_model is not None:
            settings.ollama_model = ollama_model.strip()
        if openai_key is not None:
            settings.openai_api_key = openai_key or ''
        if gemini_key is not None:
            settings.gemini_api_key = gemini_key or ''
        if claude_key is not None:
            settings.claude_api_key = claude_key or ''
        if azure_openai_endpoint is not None:
            settings.azure_openai_endpoint = azure_openai_endpoint.strip()
        if azure_openai_key is not None:
            settings.azure_openai_api_key = azure_openai_key or ''
        if azure_openai_deployment is not None:
            settings.azure_openai_deployment = azure_openai_deployment.strip()
        if org_preferred_model is not None:
            settings.org_preferred_model = org_preferred_model.strip()
        if ollama_enabled is not None:
            settings.ollama_enabled = ollama_enabled
        if openai_enabled is not None:
            settings.openai_enabled = openai_enabled
        if gemini_enabled is not None:
            settings.gemini_enabled = gemini_enabled
        if claude_enabled is not None:
            settings.claude_enabled = claude_enabled
        if azure_openai_enabled is not None:
            settings.azure_openai_enabled = azure_openai_enabled
        settings.save()
        return UpdateOrgAISettings(settings=settings, ok=True)


class SetSharedAIProfile(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=False)
        name = graphene.String(required=False)
        ollama_base_url = graphene.String()
        ollama_model = graphene.String()
        openai_key = graphene.String()
        gemini_key = graphene.String()
        claude_key = graphene.String()
        azure_openai_endpoint = graphene.String()
        azure_openai_key = graphene.String()
        azure_openai_deployment = graphene.String()
        org_preferred_model = graphene.String()
        ollama_enabled = graphene.Boolean()
        openai_enabled = graphene.Boolean()
        gemini_enabled = graphene.Boolean()
        claude_enabled = graphene.Boolean()
        azure_openai_enabled = graphene.Boolean()
        is_active = graphene.Boolean()

    profile = graphene.Field(SharedAIProfileType)
    ok = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        id=None,
        name=None,
        ollama_base_url=None,
        ollama_model=None,
        openai_key=None,
        gemini_key=None,
        claude_key=None,
        azure_openai_endpoint=None,
        azure_openai_key=None,
        azure_openai_deployment=None,
        org_preferred_model=None,
        ollama_enabled=None,
        openai_enabled=None,
        gemini_enabled=None,
        claude_enabled=None,
        azure_openai_enabled=None,
        is_active=None,
    ):
        user = info.context.user
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError("Permission denied. Superuser access required.")

        created = False
        if id is not None:
            profile = SharedAIProfile.objects.filter(pk=id).first()
            if profile is None:
                raise GraphQLError("Shared AI profile not found.")
        else:
            profile = SharedAIProfile(created_by=user)
            created = True

        if name is not None:
            profile.name = name.strip()
        elif created:
            raise GraphQLError("Profile name is required when creating a shared AI profile.")

        if ollama_base_url is not None:
            profile.ollama_base_url = ollama_base_url.strip()
        if ollama_model is not None:
            profile.ollama_model = ollama_model.strip()
        if openai_key is not None:
            profile.openai_api_key = openai_key or ''
        if gemini_key is not None:
            profile.gemini_api_key = gemini_key or ''
        if claude_key is not None:
            profile.claude_api_key = claude_key or ''
        if azure_openai_endpoint is not None:
            profile.azure_openai_endpoint = azure_openai_endpoint.strip()
        if azure_openai_key is not None:
            profile.azure_openai_api_key = azure_openai_key or ''
        if azure_openai_deployment is not None:
            profile.azure_openai_deployment = azure_openai_deployment.strip()
        if org_preferred_model is not None:
            profile.org_preferred_model = org_preferred_model.strip()
        if ollama_enabled is not None:
            profile.ollama_enabled = bool(ollama_enabled)
        if openai_enabled is not None:
            profile.openai_enabled = bool(openai_enabled)
        if gemini_enabled is not None:
            profile.gemini_enabled = bool(gemini_enabled)
        if claude_enabled is not None:
            profile.claude_enabled = bool(claude_enabled)
        if azure_openai_enabled is not None:
            profile.azure_openai_enabled = bool(azure_openai_enabled)
        if is_active is not None:
            profile.is_active = bool(is_active)

        profile.save()
        return SetSharedAIProfile(
            profile=profile,
            ok=True,
            message="Shared AI profile created." if created else "Shared AI profile updated.",
        )


class DeleteSharedAIProfile(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError("Permission denied. Superuser access required.")

        profile = SharedAIProfile.objects.filter(pk=id).first()
        if profile is None:
            return DeleteSharedAIProfile(ok=False, message="Shared AI profile not found.")

        profile.is_active = False
        profile.save(update_fields=['is_active', 'updated_at'])
        return DeleteSharedAIProfile(ok=True, message="Shared AI profile deactivated.")


class AssignSharedAIProfile(graphene.Mutation):
    class Arguments:
        organization_id = graphene.UUID(required=True)
        shared_profile_id = graphene.UUID(required=False)
        clear_assignment = graphene.Boolean(required=False, default_value=False)
        shared_profile_locked = graphene.Boolean(required=False)

    settings = graphene.Field(OrgAISettingsType)
    ok = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        organization_id,
        shared_profile_id=None,
        clear_assignment=False,
        shared_profile_locked=None,
    ):
        user = info.context.user
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError("Permission denied. Superuser access required.")

        target_org = _resolve_target_org(user, organization_id=organization_id)
        settings, _ = OrgAISettings.objects.get_or_create(organization=target_org)

        if clear_assignment:
            settings.shared_profile = None
            settings.shared_profile_locked = False
        elif shared_profile_id is not None:
            profile = SharedAIProfile.objects.filter(pk=shared_profile_id, is_active=True).first()
            if profile is None:
                raise GraphQLError("Shared AI profile not found or inactive.")
            settings.shared_profile = profile

        if shared_profile_locked is not None:
            settings.shared_profile_locked = bool(shared_profile_locked)
            if settings.shared_profile_locked and settings.shared_profile_id is None:
                raise GraphQLError("Cannot lock shared AI without an assigned shared profile.")

        settings.save()
        return AssignSharedAIProfile(
            settings=settings,
            ok=True,
            message="Shared AI assignment updated.",
        )


# ---------------------------------------------------------------------------
# Async AI generation task types and mutations
# ---------------------------------------------------------------------------

class AIGenerationTaskType(graphene.ObjectType):
    """Lightweight type returned by the polling query."""
    id = graphene.UUID()
    task_type = graphene.String()
    status = graphene.String()
    result_data = graphene.String(description="JSON string with the task result when COMPLETED")
    error_message = graphene.String()
    created_at = graphene.DateTime()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()


def _to_ai_generation_task_type(task: AIGenerationTask) -> AIGenerationTaskType:
    return AIGenerationTaskType(
        id=task.id,
        task_type=task.task_type,
        status=task.status,
        result_data=json.dumps(task.result_data) if task.result_data else None,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


def _create_ai_task(user, task_type: str, input_data: dict) -> 'AIGenerationTask':
    """Create an AIGenerationTask record and publish it to RabbitMQ."""
    from core.rabbitmq import publish_event

    task = AIGenerationTask.objects.create(
        user=user,
        task_type=task_type,
        input_data=input_data,
    )
    logger.warning(
        "AI task created: id=%s type=%s user=%s",
        task.id,
        task_type,
        getattr(user, 'username', 'unknown'),
    )

    published = publish_event('ai.generation.requested', {
        'task_id': str(task.id),
        'task_type': task_type,
        'user_id': str(user.id),
    })
    if not published:
        logger.warning(
            "Failed to publish ai.generation.requested for task %s; worker will not process.", task.id
        )
    else:
        logger.warning("AI task published to queue: id=%s type=%s", task.id, task_type)
    return task


def _start_inline_threat_report_fallback(task_id: str) -> None:
    """
    Fallback executor for threat-report tasks when worker queue processing is unavailable.

    If the task is still PENDING after a short delay, process it in a daemon thread
    within the backend process. This keeps the feature usable even when the worker
    service is down.
    """
    enabled = os.environ.get('HEFAISTOS_INLINE_AI_FALLBACK', 'true').lower() in {'1', 'true', 'yes', 'on'}
    if not enabled:
        return
    logger.debug("Inline threat-report fallback scheduled for task %s.", task_id)

    def _runner():
        close_old_connections()
        try:
            time.sleep(10)
            from django.utils import timezone as _tz

            claimed = AIGenerationTask.objects.filter(
                pk=task_id,
                task_type=AIGenerationTask.TaskType.POPULATE_THREAT_REPORT,
                status=AIGenerationTask.TaskStatus.PENDING,
            ).update(
                status=AIGenerationTask.TaskStatus.RUNNING,
                started_at=_tz.now(),
            )
            if claimed != 1:
                logger.debug(
                    "Inline fallback skipped task %s because it is no longer pending.",
                    task_id,
                )
                return

            try:
                task = AIGenerationTask.objects.select_related('user').get(pk=task_id)
            except AIGenerationTask.DoesNotExist:
                return

            logger.warning("Inline fallback claimed threat-report task %s after queue grace period.", task_id)

            settings = UserAISettings.objects.get(user=task.user)
            effective = _get_effective_ai_settings(settings)
            result, provider = extract_threat_report_workbench_payload(
                effective,
                task.input_data.get('file_content', ''),
                task.input_data.get('filename', 'threat-report.pdf'),
            )
            task.status = AIGenerationTask.TaskStatus.COMPLETED
            task.result_data = {
                'provider_used': provider,
                'filename': task.input_data.get('filename', 'threat-report.pdf'),
                'parsed_payload': result.get('parsed_payload', {}),
                'parse_warnings': result.get('parse_warnings', []),
                'raw_response': result.get('raw_response', ''),
            }
            task.completed_at = _tz.now()
            task.save(update_fields=['status', 'result_data', 'completed_at'])
            logger.warning("Inline fallback completed threat-report task %s.", task_id)
        except Exception as exc:
            logger.exception("Inline fallback failed for threat-report task %s: %s", task_id, exc)
            try:
                from django.utils import timezone as _tz
                task = AIGenerationTask.objects.get(pk=task_id)
                task.status = AIGenerationTask.TaskStatus.FAILED
                task.error_message = f"Inline fallback failed: {exc}"
                task.completed_at = _tz.now()
                task.save(update_fields=['status', 'error_message', 'completed_at'])
            except Exception:
                pass
        finally:
            close_old_connections()

    threading.Thread(
        target=_runner,
        name=f"threat-report-fallback-{task_id}",
        daemon=True,
    ).start()


class StartGenerateRuleTask(graphene.Mutation):
    """Start an async AI rule-generation task and return a task ID to poll."""

    class Arguments:
        playbook_id = graphene.UUID(required=True)
        output_format = graphene.String(required=False)

    task_id = graphene.UUID(description="Task ID – poll with aiGenerationTaskStatus")
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, playbook_id, output_format=None):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        try:
            playbook = PlaybookGraph.objects.prefetch_related('selected_capability_abstractions').get(
                pk=playbook_id,
                organization=user.organization,
            )
        except PlaybookGraph.DoesNotExist:
            return StartGenerateRuleTask(task_id=None, success=False, message="Playbook not found.")

        try:
            user_settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return StartGenerateRuleTask(
                task_id=None, success=False,
                message="Please configure AI Settings in your profile first."
            )

        input_data = {
            'playbook_id': str(playbook_id),
            'output_format': output_format or 'KQL',
            'playbook_context': _build_playbook_generation_context(playbook),
        }

        task = _create_ai_task(user, AIGenerationTask.TaskType.GENERATE_RULE, input_data)
        return StartGenerateRuleTask(
            task_id=task.id, success=True,
            message="AI generation task queued. Poll aiGenerationTaskStatus for the result."
        )


class StartSuggestImprovementsTask(graphene.Mutation):
    """Start an async AI rule-improvement suggestions task and return a task ID to poll."""

    class Arguments:
        rule_content = graphene.String(required=True)
        rule_format = graphene.String(required=False)
        playbook_id = graphene.UUID(required=False)

    task_id = graphene.UUID(description="Task ID – poll with aiGenerationTaskStatus")
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, rule_content, rule_format=None, playbook_id=None):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        if not rule_content or not rule_content.strip():
            return StartSuggestImprovementsTask(
                task_id=None, success=False, message="No rule content provided."
            )

        try:
            UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return StartSuggestImprovementsTask(
                task_id=None, success=False,
                message="Please configure AI Settings in your profile first."
            )

        input_data = {
            'rule_content': rule_content,
            'rule_format': rule_format or 'KQL',
        }
        if playbook_id:
            try:
                playbook = PlaybookGraph.objects.prefetch_related('selected_capability_abstractions').get(
                    pk=playbook_id,
                    organization=user.organization,
                )
                input_data['playbook_context'] = _build_playbook_generation_context(playbook)
            except PlaybookGraph.DoesNotExist:
                return StartSuggestImprovementsTask(
                    task_id=None, success=False, message="Playbook not found."
                )
        task = _create_ai_task(user, AIGenerationTask.TaskType.SUGGEST_IMPROVEMENTS, input_data)
        return StartSuggestImprovementsTask(
            task_id=task.id, success=True,
            message="AI suggestions task queued. Poll aiGenerationTaskStatus for the result."
        )


class StartGenerateSimilarRulesTask(graphene.Mutation):
    """Start an async AI similar-rules generation task and return a task ID to poll."""

    class Arguments:
        rule_content = graphene.String(required=True)
        rule_format = graphene.String(required=False)
        variation_type = graphene.String(required=False)
        num_variations = graphene.Int(required=False)
        target_format = graphene.String(required=False)
        custom_instructions = graphene.String(required=False)
        playbook_id = graphene.UUID(required=False)

    task_id = graphene.UUID(description="Task ID – poll with aiGenerationTaskStatus")
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, rule_content, rule_format=None, variation_type=None,
               num_variations=None, target_format=None, custom_instructions=None, playbook_id=None):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        if not rule_content or not rule_content.strip():
            return StartGenerateSimilarRulesTask(
                task_id=None, success=False, message="No rule content provided."
            )

        try:
            UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return StartGenerateSimilarRulesTask(
                task_id=None, success=False,
                message="Please configure AI Settings in your profile first."
            )

        valid_types = ['technique', 'evasion', 'platform', 'scope', 'custom']
        var_type = (variation_type or 'technique').lower()
        if var_type not in valid_types:
            var_type = 'technique'

        input_data = {
            'rule_content': rule_content,
            'rule_format': rule_format or 'KQL',
            'variation_type': var_type,
            'num_variations': num_variations or 3,
            'target_format': target_format,
            'custom_instructions': custom_instructions,
        }
        if playbook_id:
            try:
                playbook = PlaybookGraph.objects.prefetch_related('selected_capability_abstractions').get(
                    pk=playbook_id,
                    organization=user.organization,
                )
                input_data['playbook_context'] = _build_playbook_generation_context(playbook)
            except PlaybookGraph.DoesNotExist:
                return StartGenerateSimilarRulesTask(
                    task_id=None, success=False, message="Playbook not found."
                )
        task = _create_ai_task(user, AIGenerationTask.TaskType.GENERATE_SIMILAR, input_data)
        return StartGenerateSimilarRulesTask(
            task_id=task.id, success=True,
            message="AI similar-rules task queued. Poll aiGenerationTaskStatus for the result."
        )


class StartPopulateWorkbenchFromThreatReportTask(graphene.Mutation):
    """Start async threat-report extraction to produce staged workbench payload."""

    class Arguments:
        playbook_id = graphene.UUID(required=True)
        file_content = graphene.String(required=True)
        filename = graphene.String(required=True)

    task_id = graphene.UUID(description="Task ID – poll with aiGenerationTaskStatus")
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, playbook_id, file_content, filename):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        if not filename or not filename.lower().endswith('.pdf'):
            return StartPopulateWorkbenchFromThreatReportTask(
                task_id=None,
                success=False,
                message="Only PDF threat reports are supported.",
            )
        if not file_content:
            return StartPopulateWorkbenchFromThreatReportTask(
                task_id=None,
                success=False,
                message="No file content provided.",
            )
        if len(file_content) > 16 * 1024 * 1024:
            return StartPopulateWorkbenchFromThreatReportTask(
                task_id=None,
                success=False,
                message="Threat report payload is too large.",
            )

        try:
            PlaybookGraph.objects.get(pk=playbook_id, organization=user.organization)
        except PlaybookGraph.DoesNotExist:
            return StartPopulateWorkbenchFromThreatReportTask(
                task_id=None,
                success=False,
                message="Playbook not found.",
            )

        try:
            UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return StartPopulateWorkbenchFromThreatReportTask(
                task_id=None,
                success=False,
                message="Please configure AI Settings in your profile first.",
            )

        logger.warning(
            "Queueing threat-report populate task: playbook=%s user=%s filename=%s",
            playbook_id,
            getattr(user, 'username', 'unknown'),
            filename,
        )
        task = _create_ai_task(
            user,
            AIGenerationTask.TaskType.POPULATE_THREAT_REPORT,
            {
                'playbook_id': str(playbook_id),
                'file_content': file_content,
                'filename': filename,
            },
        )
        _start_inline_threat_report_fallback(str(task.id))
        return StartPopulateWorkbenchFromThreatReportTask(
            task_id=task.id,
            success=True,
            message="Threat report extraction queued. Poll aiGenerationTaskStatus for result.",
        )


class ApplyThreatReportPopulateResult(graphene.Mutation):
    """Apply a staged threat-report payload to a workbench in APPEND or OVERWRITE mode."""

    class Arguments:
        playbook_id = graphene.UUID(required=True)
        payload = graphene.JSONString(required=True)
        mode = graphene.String(required=True, description="OVERWRITE or APPEND")

    success = graphene.Boolean()
    message = graphene.String()
    applied_fields = graphene.List(graphene.String)
    capabilities_added = graphene.Int()

    @staticmethod
    def mutate(root, info, playbook_id, payload, mode):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        mode_value = (mode or '').upper().strip()
        if mode_value not in {'OVERWRITE', 'APPEND'}:
            return ApplyThreatReportPopulateResult(
                success=False,
                message="Invalid mode. Use OVERWRITE or APPEND.",
                applied_fields=[],
                capabilities_added=0,
            )

        try:
            graph = PlaybookGraph.objects.prefetch_related('selected_capability_abstractions').get(
                pk=playbook_id,
                organization=user.organization,
            )
        except PlaybookGraph.DoesNotExist:
            return ApplyThreatReportPopulateResult(
                success=False,
                message="Playbook not found.",
                applied_fields=[],
                capabilities_added=0,
            )

        payload_obj = payload
        if isinstance(payload_obj, str):
            try:
                payload_obj = json.loads(payload_obj)
            except (json.JSONDecodeError, ValueError):
                return ApplyThreatReportPopulateResult(
                    success=False,
                    message="Staged payload is not valid JSON.",
                    applied_fields=[],
                    capabilities_added=0,
                )
        if not isinstance(payload_obj, dict):
            return ApplyThreatReportPopulateResult(
                success=False,
                message="Staged payload must be a JSON object.",
                applied_fields=[],
                capabilities_added=0,
            )

        part1, part2, part4, part5 = _extract_threat_report_parts(payload_obj)
        technique_pattern = r'\bT\d{4}(?:\.\d{3})?\b'

        primary_choke_point_raw = _lookup_value(
            part1,
            'primary choke point (mitre att&ck technique)',
            'primary choke point',
            'primary choke point mitre attack technique',
            default='',
        )
        primary_choke_point_codes = _extract_codes(primary_choke_point_raw, technique_pattern)

        techniques_raw = _lookup_value(
            part1,
            'mitre att&ck techniques',
            'mitre attack techniques',
            'mitre techniques',
            default=[],
        )
        legacy_technique_codes = _extract_codes(techniques_raw, technique_pattern)
        technical_context = _coerce_markdown_text(_lookup_value(part2, 'technical context'))
        technical_context_codes = _extract_codes(technical_context, technique_pattern)
        all_payload_technique_codes = _extract_codes(payload_obj, technique_pattern)

        primary_choke_point_code = ''
        for candidates in (
            primary_choke_point_codes,
            legacy_technique_codes,
            technical_context_codes,
            all_payload_technique_codes,
        ):
            if candidates:
                primary_choke_point_code = candidates[0]
                break

        technique_codes = _merge_list([], legacy_technique_codes, 'APPEND')
        technique_codes = _merge_list(technique_codes, technical_context_codes, 'APPEND')
        if not technique_codes:
            technique_codes = all_payload_technique_codes
        if primary_choke_point_code:
            technique_codes = [primary_choke_point_code] + [
                code for code in technique_codes if code != primary_choke_point_code
            ]

        detection_strategy_raw = _lookup_value(
            part1,
            'recommended detection strategies',
            'detection strategies',
            default=[],
        )
        detection_strategy_codes = _extract_codes(detection_strategy_raw, r'\bDET\d{3,}\b')
        capability_entries = _parse_capability_entries(
            part1,
            [primary_choke_point_code] if primary_choke_point_code else technique_codes,
        )

        strategic_goal = _coerce_markdown_text(_lookup_value(part2, 'strategic goal'))
        response_playbook = _coerce_markdown_text(_lookup_value(part2, 'response playbook'))
        false_positives = _coerce_markdown_text(_lookup_value(part2, 'known false positives', 'false positives'))
        blind_spots = _coerce_markdown_text(_lookup_value(part2, 'blind spots & coverage gaps', 'blind spots'))

        trigger_block = _lookup_value(part4, 'trigger and severity', default={}) or {}
        trigger = _coerce_text(_lookup_value(trigger_block, 'trigger', 'trigger condition', default=''))
        if not trigger:
            trigger = _coerce_text(_lookup_value(part4, 'trigger', 'trigger condition'))
        severity = _coerce_text(_lookup_value(trigger_block, 'severity', default=''))
        if not severity:
            severity = _coerce_text(_lookup_value(part4, 'severity', 'initial severity'))
        containment_steps = _parse_containment_steps(_lookup_value(part4, 'containment', default=[]))
        notification_steps = _parse_notifications(_lookup_value(part4, 'notifications', default=[]))

        classification = _lookup_value(
            part4,
            'opentide classification & reference',
            'opentide classification and reference',
            'opentide classification',
            default={},
        ) or {}
        tlp_level = _coerce_text(_lookup_value(classification, 'tlp level', 'tlp', default=''))
        if not tlp_level:
            tlp_level = _coerce_text(_lookup_value(part4, 'tlp level', 'tlp classification'))
        public_references = _coerce_string_list(
            _lookup_value(
                classification,
                'url / external references',
                'external references',
                'public references',
                default=_lookup_value(part4, 'public references', 'external references', default=[]),
            )
        )
        internal_references = _coerce_string_list(
            _lookup_value(
                classification,
                'internal reference',
                'internal references',
                default=_lookup_value(part4, 'internal references', default=[]),
            )
        )
        threat_surface = _coerce_string_list(
            _lookup_value(
                classification,
                'threat surface taxonomy',
                'threat surface',
                default=_lookup_value(part4, 'threat surface taxonomy', 'threat surface', default=[]),
            )
        )

        threat_actors = _parse_threat_actors(
            _lookup_value(part4, 'threat actor', 'threat actors', default=[])
        )
        downstream = _parse_downstream_correlation(
            _lookup_value(part4, 'downstream correlation requirements', default={})
        )

        validation_strategy = _coerce_markdown_text(_lookup_value(part5, 'validation strategy'))
        choke_point_testing = _coerce_markdown_text(_lookup_value(part5, 'choke point testing'))

        applied_fields: list[str] = []
        capabilities_added = 0
        created_capability_ids: list[str] = []
        focus_layer_from_caps = ''

        with transaction.atomic():
            if technique_codes:
                technique_for_graph = [primary_choke_point_code] if primary_choke_point_code else technique_codes
                mapped_technique = _resolve_mitre_technique(technique_for_graph)
                if mapped_technique and (mode_value == 'OVERWRITE' or not graph.mitre_technique_id):
                    graph.mitre_technique = mapped_technique
                    applied_fields.append('mitreTechnique')

            selected_strategy = _to_strategy_dict(graph.selected_strategy)
            extraction_meta = {
                'appliedAt': datetime.utcnow().isoformat() + 'Z',
                'mode': mode_value,
                'primaryChokePointCode': primary_choke_point_code,
                'mitreTechniqueCodes': technique_codes,
                'detectionStrategyCodes': detection_strategy_codes,
            }
            if mode_value == 'OVERWRITE':
                selected_strategy['threatReportExtractions'] = [extraction_meta]
                if primary_choke_point_code:
                    selected_strategy['primaryChokePointCode'] = primary_choke_point_code
                else:
                    selected_strategy.pop('primaryChokePointCode', None)
                selected_strategy['mitreTechniqueCodes'] = technique_codes
                selected_strategy['detectionStrategyCodes'] = detection_strategy_codes
            else:
                selected_strategy['threatReportExtractions'] = list(
                    selected_strategy.get('threatReportExtractions') or []
                ) + [extraction_meta]
                if primary_choke_point_code:
                    selected_strategy['primaryChokePointCode'] = primary_choke_point_code
                selected_strategy['mitreTechniqueCodes'] = _merge_list(
                    selected_strategy.get('mitreTechniqueCodes') or [],
                    technique_codes,
                    'APPEND',
                )
                selected_strategy['detectionStrategyCodes'] = _merge_list(
                    selected_strategy.get('detectionStrategyCodes') or [],
                    detection_strategy_codes,
                    'APPEND',
                )
            graph.selected_strategy = selected_strategy
            applied_fields.append('selectedStrategy')

            context_lines = []
            if primary_choke_point_code:
                context_lines.append(f"Primary choke point: {primary_choke_point_code}")
            if technique_codes:
                related_techniques = [
                    code for code in technique_codes if code != primary_choke_point_code
                ] if primary_choke_point_code else technique_codes
                if related_techniques:
                    context_lines.append(f"Related ATT&CK techniques: {', '.join(related_techniques)}")
            if detection_strategy_codes:
                context_lines.append(f"Detection strategy codes: {', '.join(detection_strategy_codes)}")
            chokepoint_lines = _build_active_chokepoint_context_lines(
                [primary_choke_point_code] if primary_choke_point_code else technique_codes,
                limit=6,
            )
            if chokepoint_lines:
                context_lines.extend(chokepoint_lines)
            if capability_entries:
                context_lines.append("Capability abstractions extracted:")
                for row in capability_entries[:20]:
                    context_lines.append(
                        f"- [{row['abstraction_layer']}] {row['component_artifact']}"
                    )
            context_sections = []
            if technical_context:
                context_sections.append(technical_context)
            if context_lines:
                context_sections.append(
                    "### Threat Report Extraction Metadata\n" + '\n'.join(context_lines)
                )
            technical_context_block = '\n\n'.join(section for section in context_sections if section.strip())
            if technical_context_block:
                merged = _merge_text(graph.technical_context, technical_context_block, mode_value)
                if merged != (graph.technical_context or ''):
                    graph.technical_context = merged
                    applied_fields.append('technicalContext')

            if strategic_goal:
                merged = _merge_text(graph.goal, strategic_goal, mode_value)
                if merged != (graph.goal or ''):
                    graph.goal = merged
                    applied_fields.append('goal')
            if response_playbook:
                merged = _merge_text(graph.response_playbook, response_playbook, mode_value)
                if merged != (graph.response_playbook or ''):
                    graph.response_playbook = merged
                    applied_fields.append('responsePlaybook')
                merged_triage = _merge_text(graph.triage_guidance, response_playbook, mode_value)
                if merged_triage != (graph.triage_guidance or ''):
                    graph.triage_guidance = merged_triage
                    applied_fields.append('triageGuidance')
            if false_positives:
                merged = _merge_text(graph.false_positives, false_positives, mode_value)
                if merged != (graph.false_positives or ''):
                    graph.false_positives = merged
                    applied_fields.append('falsePositives')
            if blind_spots:
                merged = _merge_text(graph.blind_spots, blind_spots, mode_value)
                if merged != (graph.blind_spots or ''):
                    graph.blind_spots = merged
                    applied_fields.append('blindSpots')

            if trigger:
                merged = _merge_text(graph.alert_trigger, trigger, mode_value)
                if merged != (graph.alert_trigger or ''):
                    graph.alert_trigger = merged
                    applied_fields.append('alertTrigger')
            mapped_severity = _map_severity(severity, default=graph.default_severity or 'MEDIUM')
            if mode_value == 'OVERWRITE' or not graph.default_severity:
                if mapped_severity and mapped_severity != graph.default_severity:
                    graph.default_severity = mapped_severity
                    applied_fields.append('defaultSeverity')

            if containment_steps:
                merged_containment = _merge_list(graph.containment_steps or [], containment_steps, mode_value)
                if merged_containment != (graph.containment_steps or []):
                    graph.containment_steps = merged_containment
                    applied_fields.append('containmentSteps')

            if notification_steps:
                merged_notifications = _merge_list(graph.notification_steps or [], notification_steps, mode_value)
                if merged_notifications != (graph.notification_steps or []):
                    graph.notification_steps = merged_notifications
                    applied_fields.append('notificationSteps')

            if public_references:
                merged = _merge_list(graph.public_references or [], public_references, mode_value)
                if merged != (graph.public_references or []):
                    graph.public_references = merged
                    applied_fields.append('publicReferences')

            if internal_references:
                merged = _merge_list(graph.internal_references or [], internal_references, mode_value)
                if merged != (graph.internal_references or []):
                    graph.internal_references = merged
                    applied_fields.append('internalReferences')

            if threat_surface:
                merged = _merge_list(graph.threat_surface or [], threat_surface, mode_value)
                if merged != (graph.threat_surface or []):
                    graph.threat_surface = merged
                    applied_fields.append('threatSurface')

            if threat_actors:
                merged = _merge_list(graph.threat_actors or [], threat_actors, mode_value)
                if merged != (graph.threat_actors or []):
                    graph.threat_actors = merged
                    applied_fields.append('threatActors')

            if downstream:
                merged = _merge_downstream_correlation(
                    graph.downstream_correlation_requirements or {},
                    downstream,
                    mode_value,
                )
                if merged != (graph.downstream_correlation_requirements or {}):
                    graph.downstream_correlation_requirements = merged
                    applied_fields.append('downstreamCorrelationRequirements')

            mapped_tlp = _map_tlp(tlp_level, default=graph.tlp_classification or 'AMBER')
            if mode_value == 'OVERWRITE' or not graph.tlp_classification:
                if mapped_tlp and mapped_tlp != graph.tlp_classification:
                    graph.tlp_classification = mapped_tlp
                    applied_fields.append('tlpClassification')

            if validation_strategy:
                merged = _merge_text(graph.test_scenario, validation_strategy, mode_value)
                if merged != (graph.test_scenario or ''):
                    graph.test_scenario = merged
                    applied_fields.append('testScenario')
            if choke_point_testing:
                merged = _merge_text(graph.test_expected_output, choke_point_testing, mode_value)
                if merged != (graph.test_expected_output or ''):
                    graph.test_expected_output = merged
                    applied_fields.append('testExpectedOutput')

            for row in capability_entries:
                cap_technique = _resolve_mitre_technique(
                    [row['technique_code']] if row['technique_code'] else technique_codes
                )
                if not cap_technique:
                    continue
                capability, created = CapabilityAbstraction.objects.get_or_create(
                    technique=cap_technique,
                    organization=user.organization,
                    abstraction_layer=row['abstraction_layer'],
                    component_artifact=row['component_artifact'],
                    defaults={
                        'created_by': user,
                        'updated_by': user,
                        'adversary_purpose': row['adversary_purpose'],
                        'common_evasions': row['common_evasions'],
                        'expected_observables': row['expected_observables'],
                        'applicable_telemetry': row['applicable_telemetry'],
                        'detection_value': row['detection_value'],
                        'robustness_level': row['robustness_level'],
                        'review_status': CapabilityAbstraction.ReviewStatus.DRAFT,
                        'source_kind': CapabilityAbstraction.SourceKind.CUSTOM,
                        'is_baseline': False,
                    },
                )
                if created:
                    capabilities_added += 1
                else:
                    dirty = False
                    for field in (
                        'adversary_purpose',
                        'common_evasions',
                        'expected_observables',
                        'applicable_telemetry',
                        'detection_value',
                    ):
                        incoming = row.get(field, '')
                        if not incoming:
                            continue
                        if mode_value == 'OVERWRITE' and getattr(capability, field, '') != incoming:
                            setattr(capability, field, incoming)
                            dirty = True
                        elif mode_value == 'APPEND' and not getattr(capability, field, ''):
                            setattr(capability, field, incoming)
                            dirty = True
                    incoming_robustness = row.get('robustness_level', 0) or 0
                    if incoming_robustness:
                        if mode_value == 'OVERWRITE' and capability.robustness_level != incoming_robustness:
                            capability.robustness_level = incoming_robustness
                            dirty = True
                        elif mode_value == 'APPEND' and not capability.robustness_level:
                            capability.robustness_level = incoming_robustness
                            dirty = True
                    if capability.review_status != CapabilityAbstraction.ReviewStatus.DRAFT:
                        capability.review_status = CapabilityAbstraction.ReviewStatus.DRAFT
                        dirty = True
                    if dirty:
                        capability.updated_by = user
                        capability.version += 1
                        capability.save()
                created_capability_ids.append(str(capability.id))
                if not focus_layer_from_caps:
                    focus_layer_from_caps = row['abstraction_layer']

            graph.save()

            if created_capability_ids:
                existing_ids = [str(pk) for pk in graph.selected_capability_abstractions.values_list('id', flat=True)]
                if mode_value == 'OVERWRITE':
                    target_ids = created_capability_ids
                else:
                    target_ids = existing_ids + [pk for pk in created_capability_ids if pk not in existing_ids]
                graph.selected_capability_abstractions.set(target_ids)
                applied_fields.append('selectedCapabilityAbstractions')

            if focus_layer_from_caps and (mode_value == 'OVERWRITE' or not graph.detection_focus_layer):
                graph.detection_focus_layer = focus_layer_from_caps
                graph.save(update_fields=['detection_focus_layer'])
                applied_fields.append('detectionFocusLayer')

        deduped_fields = list(dict.fromkeys(applied_fields))
        return ApplyThreatReportPopulateResult(
            success=True,
            message=f"Threat report data applied in {mode_value} mode.",
            applied_fields=deduped_fields,
            capabilities_added=capabilities_added,
        )


class Mutation(graphene.ObjectType):
    update_ai_settings = UpdateAISettings.Field()
    update_org_ai_settings = UpdateOrgAISettings.Field()
    set_shared_ai_profile = SetSharedAIProfile.Field()
    delete_shared_ai_profile = DeleteSharedAIProfile.Field()
    assign_shared_ai_profile = AssignSharedAIProfile.Field()
    deconstruct_rule = DeconstructRule.Field()
    suggest_rule_improvements = SuggestRuleImprovements.Field()
    generate_similar_rules = GenerateSimilarRules.Field()
    maieutic_question = MaieuticQuestion.Field()
    extract_strain_data = ExtractStrainData.Field()
    extract_strain_data_from_url = ExtractStrainDataFromURL.Field()
    generate_response_playbook_ai = GenerateResponsePlaybook.Field()
    recommend_reusable_rule_from_rag = RecommendReusableRuleFromRag.Field()
    translate_response_playbook_ai = TranslateResponsePlaybook.Field()
    # Async (non-blocking) variants that avoid gateway timeouts
    start_generate_rule_task = StartGenerateRuleTask.Field()
    start_suggest_improvements_task = StartSuggestImprovementsTask.Field()
    start_generate_similar_rules_task = StartGenerateSimilarRulesTask.Field()
    start_populate_workbench_from_threat_report_task = StartPopulateWorkbenchFromThreatReportTask.Field()
    apply_threat_report_populate_result = ApplyThreatReportPopulateResult.Field()

class Query(graphene.ObjectType):
    my_ai_settings = graphene.Field(UserAISettingsType)
    org_ai_settings = graphene.Field(OrgAISettingsType, organization_id=graphene.UUID(required=False))
    shared_ai_profiles = graphene.List(
        SharedAIProfileType,
        include_inactive=graphene.Boolean(required=False, default_value=False),
    )
    ai_generation_task_status = graphene.Field(
        AIGenerationTaskType,
        task_id=graphene.UUID(required=True),
        description="Poll the status of an async AI generation task.",
    )
    latest_threat_report_task_for_playbook = graphene.Field(
        AIGenerationTaskType,
        playbook_id=graphene.UUID(required=True),
        description=(
            "Return the latest threat-report populate task for this playbook "
            "(owned by the current user)."
        ),
    )

    def resolve_ai_generation_task_status(self, info, task_id):
        """Return the current status (and result when COMPLETED) of an async AI generation task."""
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        try:
            task = AIGenerationTask.objects.get(pk=task_id, user=user)
        except AIGenerationTask.DoesNotExist:
            raise GraphQLError("Task not found")

        from django.utils import timezone as _tz
        pending_timeout = (
            600 if task.task_type == AIGenerationTask.TaskType.POPULATE_THREAT_REPORT else 180
        )
        if (
            task.status == AIGenerationTask.TaskStatus.PENDING
            and (_tz.now() - task.created_at).total_seconds() > pending_timeout
        ):
            task.status = AIGenerationTask.TaskStatus.FAILED
            task.error_message = (
                f'AI task stayed in queue too long ({pending_timeout // 60}+ minutes). '
                'The AI worker may be offline or queue publishing failed.'
            )
            task.completed_at = _tz.now()
            task.save(update_fields=['status', 'error_message', 'completed_at'])
            logger.warning("AIGenerationTask %s stuck in PENDING and was marked FAILED.", task_id)

        # Time-out tasks stuck in RUNNING.
        # Threat-report extraction is intentionally heavier and allowed extra time.
        task_timeout_seconds = (
            1800 if task.task_type == AIGenerationTask.TaskType.POPULATE_THREAT_REPORT else 600
        )
        if (
            task.status == AIGenerationTask.TaskStatus.RUNNING
            and task.started_at
            and (_tz.now() - task.started_at).total_seconds() > task_timeout_seconds
        ):
            task.status = AIGenerationTask.TaskStatus.FAILED
            task.error_message = (
                f'AI generation task timed out after {task_timeout_seconds // 60} minutes. '
                'The AI model may be unavailable or overloaded — please try again.'
            )
            task.completed_at = _tz.now()
            task.save(update_fields=['status', 'error_message', 'completed_at'])
            logger.warning("AIGenerationTask %s timed out and was marked FAILED.", task_id)

        return _to_ai_generation_task_type(task)

    def resolve_latest_threat_report_task_for_playbook(self, info, playbook_id):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        task = (
            AIGenerationTask.objects
            .filter(
                user=user,
                task_type=AIGenerationTask.TaskType.POPULATE_THREAT_REPORT,
                input_data__playbook_id=str(playbook_id),
            )
            .order_by('-created_at')
            .first()
        )
        if not task:
            return None
        return _to_ai_generation_task_type(task)

    def resolve_my_ai_settings(self, info):
        settings = UserAISettings.objects.filter(user=info.context.user).first()
        if settings is None:
            # Auto-enable org AI when the organisation already has a provider configured
            use_org_ai = False
            org = getattr(info.context.user, 'organization', None)
            if org:
                try:
                    org_settings = OrgAISettings.objects.select_related('shared_profile').get(organization=org)
                    effective = org_settings.get_effective_settings()
                    if getattr(effective, 'has_any_provider', False):
                        use_org_ai = True
                except OrgAISettings.DoesNotExist:
                    pass
            settings = UserAISettings.objects.create(user=info.context.user, use_org_ai=use_org_ai)
        # Ensure preferred_model is always canonical and GraphQL-enum-safe.
        # This also repairs legacy lowercase values (e.g. "gpt-5.4") on read.
        normalized_preferred = _normalize_preferred_model_choice(settings.preferred_model)
        if normalized_preferred and normalized_preferred != settings.preferred_model:
            settings.preferred_model = normalized_preferred
            settings.save(update_fields=['preferred_model'])
        elif not normalized_preferred or settings.preferred_model not in VALID_USER_PREFERRED_MODELS:
            from .engine import build_available, FALLBACK_PRIORITY
            available = build_available(settings)
            new_model = None
            for p in FALLBACK_PRIORITY:
                if p in available and p in VALID_USER_PREFERRED_MODELS:
                    new_model = p
                    break
            if new_model is None and VALID_USER_PREFERRED_MODELS:
                new_model = VALID_USER_PREFERRED_MODELS[0]
            if new_model:
                settings.preferred_model = new_model
                settings.save(update_fields=['preferred_model'])
        return settings

    def resolve_org_ai_settings(self, info, organization_id=None):
        user = info.context.user
        if user.is_anonymous:
            return None
        org = _resolve_target_org(user, organization_id=organization_id)
        if not org:
            return None
        settings, _ = OrgAISettings.objects.get_or_create(organization=org)
        return settings

    def resolve_shared_ai_profiles(self, info, include_inactive=False):
        user = info.context.user
        if user.is_anonymous:
            return []
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError("Permission denied. Superuser access required.")

        qs = SharedAIProfile.objects.all()
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return list(qs.order_by('name'))
