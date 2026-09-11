import re
from typing import Any

import requests

from organizations.models import MISPInstance


def _extract_ttps(event_obj: dict[str, Any]) -> list[str]:
    combined = []
    tags = event_obj.get('Tag') or []
    for tag in tags:
        if isinstance(tag, dict):
            combined.append(str(tag.get('name') or ''))

    galaxy = event_obj.get('Galaxy') or []
    for gal in galaxy:
        clusters = (gal or {}).get('GalaxyCluster') or []
        for cluster in clusters:
            if isinstance(cluster, dict):
                combined.append(str(cluster.get('value') or ''))
                combined.extend(str(t.get('name') or '') for t in (cluster.get('Tag') or []) if isinstance(t, dict))

    text = ' '.join(combined).upper()
    ttps = re.findall(r'T\d{4}(?:\.\d{3})?', text)
    seen = set()
    result = []
    for item in ttps:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


CAPABILITY_ABSTRACTION_OBJECT_NAME = 'capability-abstraction'


def _find_object(event_obj: dict[str, Any], object_name: str) -> dict[str, Any] | None:
    objects = event_obj.get('Object') or []
    if not isinstance(objects, list):
        return None
    for obj in objects:
        if isinstance(obj, dict) and str(obj.get('name') or '').strip() == object_name:
            return obj
    return None


def _object_attribute_values(misp_object: dict[str, Any], object_relation: str) -> list[str]:
    values = []
    for attr in misp_object.get('Attribute') or []:
        if not isinstance(attr, dict):
            continue
        if str(attr.get('object_relation') or '').strip() != object_relation:
            continue
        value = str(attr.get('value') or '').strip()
        if value:
            values.append(value)
    return values


def _object_attribute_value(misp_object: dict[str, Any], object_relation: str) -> str:
    values = _object_attribute_values(misp_object, object_relation)
    return values[0] if values else ''


def normalize_capability_abstraction_object(
    event_obj: dict[str, Any], misp_object: dict[str, Any]
) -> dict[str, Any]:
    """Map a `capability-abstraction` MISP Object's attributes onto WaitingCase fields.

    Field-name choices deliberately mirror the HEFAISTOS Partner Integration API
    vocabulary (title, short_description, detection_objective, mapped_ttps,
    estimated_detection_complexity) for round-trip compatibility, per the object's
    own design doc. ATT&CK IDs come from `attack-technique-id` (methodology places
    ATT&CK mapping last/optional, so this may be empty).
    """
    event_id = str(event_obj.get('id') or '').strip()

    title = _object_attribute_value(misp_object, 'title')
    if not title:
        hypothesis = _object_attribute_value(misp_object, 'hypothesis')
        title = hypothesis or str(event_obj.get('info') or '').strip() or f'MISP Event {event_id or "unknown"}'

    short_description = _object_attribute_value(misp_object, 'short-description')
    if not short_description:
        chokepoint = _object_attribute_value(misp_object, 'chokepoint')
        residue_desc = _object_attribute_value(misp_object, 'residue-description')
        parts = [p for p in (chokepoint, residue_desc) if p]
        short_description = ' | '.join(parts) or str(event_obj.get('info') or '').strip()

    detection_objective = _object_attribute_value(misp_object, 'detection-objective')

    complexity_raw = _object_attribute_value(misp_object, 'estimated-detection-complexity')
    complexity = complexity_raw.strip().upper() if complexity_raw else 'MEDIUM'

    mapped_ttps = [
        v.strip().upper()
        for v in _object_attribute_values(misp_object, 'attack-technique-id')
        if v.strip()
    ]
    if not mapped_ttps:
        mapped_ttps = _extract_ttps(event_obj)

    return {
        'event_id': event_id,
        'title': title,
        'short_description': short_description,
        'detection_objective': detection_objective,
        'mapped_ttps': mapped_ttps,
        'estimated_detection_complexity': complexity,
        'raw_payload': event_obj,
    }


def normalize_misp_event(event_obj: dict[str, Any]) -> dict[str, Any]:
    capability_object = _find_object(event_obj, CAPABILITY_ABSTRACTION_OBJECT_NAME)
    if capability_object is not None:
        return normalize_capability_abstraction_object(event_obj, capability_object)

    event_id = str(event_obj.get('id') or '').strip()
    title = str(event_obj.get('info') or '').strip() or f'MISP Event {event_id or "unknown"}'

    attrs = event_obj.get('Attribute') or []
    ioc_values = []
    for attr in attrs[:15]:
        if not isinstance(attr, dict):
            continue
        value = str(attr.get('value') or '').strip()
        if value:
            ioc_values.append(value)

    short_description = (
        f"MISP event {event_id}: " + ', '.join(ioc_values[:8])
    ).strip()
    if not short_description or short_description == f'MISP event {event_id}:':
        short_description = str(event_obj.get('info') or '').strip()

    detection_objective = (
        f"Detect indicators and behaviours related to MISP event {event_id}."
    )

    return {
        'event_id': event_id,
        'title': title,
        'short_description': short_description,
        'detection_objective': detection_objective,
        'mapped_ttps': _extract_ttps(event_obj),
        'estimated_detection_complexity': 'MEDIUM',
        'raw_payload': event_obj,
    }


def event_has_tag(event_obj: dict[str, Any], required_tag: str) -> bool:
    target = str(required_tag or '').strip().lower()
    if not target:
        return True

    candidates = []
    for key in ('Tag', 'EventTag'):
        for tag in event_obj.get(key) or []:
            if isinstance(tag, dict):
                candidates.append(str(tag.get('name') or '').strip().lower())
            else:
                candidates.append(str(tag).strip().lower())
    return target in {candidate for candidate in candidates if candidate}


def _filter_events_by_tag(events: list[dict[str, Any]], required_tag: str) -> list[dict[str, Any]]:
    return [event for event in events if event_has_tag(event, required_tag)]


def fetch_misp_events(
    instance: MISPInstance,
    limit: int = 25,
    event_id: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        'returnFormat': 'json',
        'limit': max(1, min(int(limit or 25), 100)),
    }
    if event_id:
        body['eventid'] = str(event_id)
    normalized_tag = str(tag or '').strip()
    if normalized_tag:
        body['tags'] = [normalized_tag]

    response = requests.post(
        f"{instance.url.rstrip('/')}/events/restSearch",
        headers={
            'Authorization': instance.auth_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        json=body,
        timeout=30,
        verify=instance.verify_ssl,
    )
    response.raise_for_status()

    data = response.json()
    events_container = data.get('response', data)
    events: list[dict[str, Any]] = []

    if isinstance(events_container, list):
        for item in events_container:
            if isinstance(item, dict) and isinstance(item.get('Event'), dict):
                events.append(item['Event'])
            elif isinstance(item, dict):
                events.append(item)
    elif isinstance(events_container, dict):
        if isinstance(events_container.get('Event'), list):
            for item in events_container.get('Event') or []:
                if isinstance(item, dict):
                    events.append(item)
        elif isinstance(events_container.get('Event'), dict):
            events.append(events_container['Event'])

    if normalized_tag:
        return _filter_events_by_tag(events, normalized_tag)
    return events


def import_waiting_cases_from_misp(
    *,
    instance,
    user,
    event_id: str | None = None,
    tag: str | None = None,
    limit: int = 25,
    run_ai_enrichment: bool = False,
):
    """Shared import logic used by both the GraphQL mutation and scheduled auto-pull.

    Ledger-gated: an event already recorded in MISPImportLedger for this instance is
    never re-imported, even if its WaitingCase was since deleted from the Waiting Room.
    """
    from .models import MISPImportLedger, WaitingCase, queue_waiting_case_enrichment

    events = fetch_misp_events(instance=instance, limit=limit, event_id=event_id, tag=tag)

    imported = 0
    skipped = 0
    created_cases = []
    normalized_tag = (tag or '').strip()

    already_ledgered = set(
        MISPImportLedger.objects.filter(misp_instance=instance).values_list('misp_event_id', flat=True)
    )

    for event_obj in events:
        if normalized_tag and not event_has_tag(event_obj, normalized_tag):
            skipped += 1
            continue
        normalized = normalize_misp_event(event_obj)
        event_pk = str(normalized.get('event_id') or '').strip()
        if not event_pk:
            skipped += 1
            continue

        if event_pk in already_ledgered:
            skipped += 1
            continue

        defaults = {
            'organization': user.organization,
            'created_by': user,
            'source_type': WaitingCase.SourceType.MISP,
            'title': normalized.get('title') or f'MISP Event {event_pk}',
            'short_description': normalized.get('short_description') or '',
            'detection_objective': normalized.get('detection_objective') or '',
            'mapped_ttps': normalized.get('mapped_ttps') or [],
            'estimated_detection_complexity': normalized.get('estimated_detection_complexity') or '',
            'raw_payload': normalized.get('raw_payload') or {},
            'status': WaitingCase.LifecycleStatus.NEW,
        }
        waiting_case, created = WaitingCase.objects.get_or_create(
            misp_instance=instance,
            misp_event_id=event_pk,
            defaults=defaults,
        )
        if created:
            imported += 1
            created_cases.append(waiting_case)
            MISPImportLedger.objects.get_or_create(
                misp_instance=instance,
                misp_event_id=event_pk,
                defaults={
                    'organization': user.organization,
                    'misp_event_uuid': str(event_obj.get('uuid') or '').strip(),
                    'waiting_case': waiting_case,
                },
            )
            already_ledgered.add(event_pk)
            if run_ai_enrichment:
                queue_waiting_case_enrichment(waiting_case, user)
        else:
            skipped += 1

    return {
        'imported_count': imported,
        'skipped_count': skipped,
        'waiting_cases': created_cases,
    }
