"""Create a Workbench from a Maieutic session, queue rule generation, and store the results.

See Docs/README_MAIEUTIC.md, Finishing a session. Rule generation reuses the normal
AIGenerationTask pipeline (reference retrieval, validation gate, repair), so a rule made
from a session is held to the same standard as any other generated rule.

Deliberate deviations from spec section 8 (see Docs/README_MAIEUTIC.md):
- telemetry_requirements is NOT written. It is a reviewed tag list produced by a separate AI
  step; log sources and fields travel in technical_context as plain text instead.
- robustness_level / data_source_robustness are not set: the Workbench evaluates robustness itself
  (VALUATION). The Capability Library entries and the focus layer the user picked in the design stage are
  copied as chosen, after checking them (see capability_selection); nothing is filled in for the user.
"""

import logging
import uuid

from django.db import transaction

from . import maieutic_lifecycle as lifecycle
from .maieutic_models import MaieuticDraft

logger = logging.getLogger(__name__)

EXIT_WITH_RULE = 'CREATE_AND_GENERATE'
EXIT_WITHOUT_RULE = 'CREATE_WITHOUT_RULE'
KNOWN_FORMATS = ('KQL', 'SPL', 'EQL', 'WAZUH', 'AQL')
SEVERITIES = ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
# format -> (where it lives in opentide_yaml['platforms'], key holding the text, configured_platforms name)
PLATFORM_SLOTS = {
    'SPL': ('spl', 'query', 'spl'),
    'EQL': ('elastic', 'query', 'elastic'),
    'AQL': ('qradar', 'query', 'qradar'),
    'WAZUH': ('wazuh', 'rule', 'wazuh'),
}
MAX_CAPABILITY_REFS = 20
FOCUS_LAYERS = ('TOOL', 'API_EXPORT', 'COM_IPC', 'REGISTRY_OBJECT', 'PROTOCOL', 'PROCESS_BEHAVIOR', 'NETWORK_BEHAVIOR')
# 'Not known yet' is deliberately absent: not knowing is not a blind spot or a coverage gap, and the
# rule must not be told to list it as one.
LIMITATION_DISPOSITIONS = ('ACCEPTED_LIMITATION', 'COVERED_BY_OTHER_RULE')


def _s(value):
    return value.strip() if isinstance(value, str) else ''


def _list(value):
    return [v for v in (value or []) if v not in (None, '')]


def _text_of(item):
    if isinstance(item, dict):
        return _s(item.get('description') or item.get('text') or item.get('what') or item.get('value'))
    return _s(item)


# Playbook lists as PlaybookGraph stores them: field -> (key that must be filled, text keys, boolean keys).
STEP_LISTS = {
    'enrichment_steps': ('action', ('action', 'input', 'output', 'description'), ()),
    'containment_steps': ('action', ('action', 'description'), ('critical',)),
    'notification_steps': ('channel', ('channel', 'recipient', 'template'), ()),
}
MAX_STEPS = 30


def clean_steps(items, field):
    """Keep only well-formed steps of the shape PlaybookGraph expects. Entries without their key are dropped."""
    required, text_keys, bool_keys = STEP_LISTS[field]
    out = []
    for item in _list(items):
        if not isinstance(item, dict) or not _s(item.get(required)):
            continue
        row = {k: _s(item.get(k))[:2000] for k in text_keys}
        for k in bool_keys:
            row[k] = item.get(k) is True
        out.append(row)
    return out[:MAX_STEPS]


def negative_tests_from_spec(spec):
    """One negative test per ACCEPTED limitation. Not for 'covered by another rule' and never for unknown answers.

    The steps are the user's own when written in stage 5, otherwise a neutral template built from the question
    and the user's answer (no AI, nothing invented).
    """
    from playbooks import negative_tests as nt
    written = {}
    for entry in _list(((spec or {}).get('playbook_tests') or {}).get('negative_tests')):
        if isinstance(entry, dict) and _s(entry.get('from_ade_id')):
            written[_s(entry['from_ade_id'])] = _s(entry.get('steps'))
    return [nt.new_item(e.get('ade_id'), _s(e.get('question_text')), _s(e.get('answer_text')),
                        steps=written.get(_s(e.get('ade_id')), ''))
            for e in _ledger(spec) if e.get('disposition') == 'ACCEPTED_LIMITATION']


def _bullets(lines):
    return '\n'.join(f'- {line}' for line in lines if line)


def focus_layer_from_spec(spec):
    value = _s(((spec or {}).get('design') or {}).get('focus_layer')).upper()
    return value if value in FOCUS_LAYERS else ''


def capability_ids_from_spec(spec):
    """Ids the user picked, as unique UUID strings in the order picked. Anything else is dropped."""
    out = []
    refs = ((spec or {}).get('design') or {}).get('capability_refs')
    for raw in (refs if isinstance(refs, list) else []):
        try:
            value = str(uuid.UUID(str(raw)))
        except (ValueError, AttributeError, TypeError):
            continue
        if value not in out:
            out.append(value)
    return out[:MAX_CAPABILITY_REFS]


def capability_selection(spec, user, mitre):
    """Library entries to attach: only entries the user may see, for the chosen technique.

    Returns (entries, ignored_count). The picker only offers such entries, so anything else means the
    technique changed after picking, an entry was deleted, or the request was tampered with.
    """
    from playbooks.models import CapabilityAbstraction
    ids = capability_ids_from_spec(spec)
    if not ids or mitre is None:
        return [], len(ids)
    from django.db.models import Q
    found = {str(c.id): c for c in CapabilityAbstraction.objects.filter(
        id__in=ids, technique=mitre).filter(Q(organization=user.organization) | Q(organization__isnull=True))}
    entries = [found[i] for i in ids if i in found]
    return entries, len(ids) - len(entries)


def selected_formats(spec):
    chosen = [f for f in _list(((spec or {}).get('review') or {}).get('output_formats')) if f in KNOWN_FORMATS]
    ordered = ['KQL'] + [f for f in KNOWN_FORMATS[1:] if f in chosen]  # KQL is always first
    return ordered


def _ledger(spec):
    return list((((spec or {}).get('robustness') or {}).get('ade_ledger')) or [])


def _design_label(spec, ref):
    """Human wording for a design reference, from the user's own design."""
    if not ref:
        return ''
    kind, _, ident = str(ref).partition(':')
    design = (spec or {}).get('design') or {}
    if kind == 'match_element':
        for e in _list(design.get('match_elements')):
            if isinstance(e, dict) and e.get('id') == ident:
                return _text_of(e)
    if kind == 'exclusion':
        for i, x in enumerate(_list(design.get('exclusions'))):
            if isinstance(x, dict) and (x.get('id') == ident or str(i) == ident):
                return _text_of(x)
    if kind == 'correlation':
        items = _list(design.get('correlations'))
        if ident.isdigit() and int(ident) < len(items):
            return _text_of(items[int(ident)])
    return ''


def build_constraints(spec):
    """The three constraint groups of spec section 4, computed from the session (never typed by the user)."""
    spec = spec or {}
    hyp, design = spec.get('hypothesis') or {}, spec.get('design') or {}
    inter = spec.get('interrogation') or {}
    wt = design.get('windows_thresholds') or {}

    must_implement = []
    if _s(hyp.get('goal')):
        must_implement.append(f"Detect: {_s(hyp['goal'])}")
    for e in _list(design.get('match_elements')):
        line = _text_of(e)
        if line:
            changeable = e.get('attacker_changeable') if isinstance(e, dict) else None
            must_implement.append(f"Match on: {line}" + (f" (attacker can change it: {changeable})" if changeable else ''))
    for x in _list(design.get('exclusions')):
        if isinstance(x, dict) and _s(x.get('what')):
            must_implement.append(f"Exclude: {_s(x['what'])}" + (f" because {_s(x['why'])}" if _s(x.get('why')) else ''))
    window_bits = [f"{k.replace('_', ' ')}: {wt[k]}" for k in
                   ('time_window', 'alert_threshold', 'aggregation_field', 'suppression_window') if wt.get(k) not in (None, '')]
    if window_bits:
        must_implement.append('Window and threshold: ' + '; '.join(window_bits))
    for c in _list(design.get('correlations')):
        if _text_of(c):
            must_implement.append(f"Relate events: {_text_of(c)}")
    sources = [s.get('name') for s in _list(inter.get('log_sources')) if isinstance(s, dict) and s.get('name')]
    if sources:
        must_implement.append('Use these log sources: ' + ', '.join(str(x) for x in sources))
    for f in _list(inter.get('fields')):
        if isinstance(f, dict) and (f.get('siem_field_name') or f.get('standard_name')):
            must_implement.append(f"Field {f.get('standard_name') or ''} maps to {f.get('siem_field_name') or '(unmapped)'}")

    must_handle, limitations = [], []
    for entry in _ledger(spec):
        disposition = entry.get('disposition')
        topic = _s(entry.get('question_text'))
        answer = _s(entry.get('answer_text'))
        if disposition == 'HANDLED_IN_DESIGN':
            must_handle.append({'topic': topic, 'engineer_says': answer,
                                'applies_to': _design_label(spec, entry.get('design_ref'))})
        elif disposition in LIMITATION_DISPOSITIONS:
            limitations.append({'topic': topic, 'status': disposition, 'engineer_says': answer,
                                'covered_by': _s(entry.get('reference'))})
    return {'must_implement': must_implement, 'must_handle': must_handle, 'accepted_limitations': limitations}


def workbench_fields(spec):
    """Pure mapping of the session to Workbench field values (spec section 8)."""
    spec = spec or {}
    hyp, inter = spec.get('hypothesis') or {}, spec.get('interrogation') or {}
    design, play = spec.get('design') or {}, spec.get('playbook_tests') or {}
    wt = design.get('windows_thresholds') or {}
    constraints = build_constraints(spec)

    goal = _s(hyp.get('goal'))
    methods = [_text_of(m) for m in _list(hyp.get('attacker_methods'))]
    if methods:
        goal += '\n\nWays an attacker could do this:\n' + _bullets(methods)

    context = []
    if _s(hyp.get('scope_notes')):
        context.append('Scope notes\n' + _s(hyp['scope_notes']))
    sources = [f"{s.get('name')}" + (f" ({s['coverage_status_at_pick']})" if s.get('coverage_status_at_pick') else '')
               for s in _list(inter.get('log_sources')) if isinstance(s, dict) and s.get('name')]
    if sources:
        context.append('Telemetry the engineer planned to use (not verified)\n' + _bullets(sources))
    fields = [f"{f.get('standard_name') or '?'} -> {f.get('siem_field_name') or '?'}; attacker can control it: {f.get('attacker_controlled') or 'UNKNOWN'}"
              + (f"; {f['note']}" if _s(f.get('note')) else '')
              for f in _list(inter.get('fields')) if isinstance(f, dict)]
    if fields:
        context.append('Fields relied on\n' + _bullets(fields))
    if _s(design.get('blueprint_text')):
        context.append('Design in the engineer\'s words\n' + _s(design['blueprint_text']))
    if constraints['must_implement']:
        context.append('Design elements\n' + _bullets(constraints['must_implement']))

    false_positives = [_text_of(b) for b in _list(inter.get('benign_lookalikes'))]
    false_positives += [f"{_s(x.get('what'))}" + (f" ({_s(x['why'])})" if _s(x.get('why')) else '')
                        for x in _list(design.get('exclusions')) if isinstance(x, dict) and _s(x.get('what'))]

    # Only what the engineer established. Unanswered questions are remaining Maieutic work, not findings,
    # so they are never written into the Workbench.
    blind = []
    for lim in constraints['accepted_limitations']:
        label = {'ACCEPTED_LIMITATION': 'Accepted limitation', 'COVERED_BY_OTHER_RULE': 'Covered elsewhere'}[lim['status']]
        said = lim['engineer_says'] or 'no answer given'
        extra = f" (covered by: {lim['covered_by']})" if lim['covered_by'] else ''
        blind.append(f"{label}: {lim['topic']} {said}{extra}")

    fields_out: dict = {
        'title': _s(hyp.get('title')),
        'goal': goal,
        'technical_context': '\n\n'.join(context),
        'false_positives': '\n'.join(f'- {x}' for x in false_positives if x),
        'blind_spots': '\n'.join(f'- {x}' for x in blind if x),
        'triage_guidance': _s(play.get('triage_guidance')),
        'response_playbook': _s(play.get('response_playbook')),
        'test_scenario': _s(play.get('test_scenario')),
        'test_expected_output': _s(play.get('test_expected_output')),
        'time_window': _s(wt.get('time_window'))[:20],
        'aggregation_field': _s(wt.get('aggregation_field'))[:100],
        'suppression_window': _s(wt.get('suppression_window'))[:20],
    }
    for field in STEP_LISTS:
        steps = clean_steps(play.get(field), field)
        if steps:
            fields_out[field] = steps
    negative = negative_tests_from_spec(spec)
    if negative:
        fields_out['negative_tests'] = negative
    focus = focus_layer_from_spec(spec)
    if focus:
        fields_out['detection_focus_layer'] = focus
    if _s(play.get('alert_trigger')):
        fields_out['alert_trigger'] = _s(play['alert_trigger'])
    if play.get('default_severity') in SEVERITIES:
        fields_out['default_severity'] = play['default_severity']
    threshold = wt.get('alert_threshold')
    if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and threshold >= 0:
        fields_out['alert_threshold'] = int(threshold)
    correlations = [_text_of(c) for c in _list(design.get('correlations')) if _text_of(c)]
    if correlations:
        fields_out['downstream_correlation_requirements'] = {'correlationScope': '; '.join(correlations)}
    return fields_out


def conversation_log(spec):
    """Audit trail for PlaybookGraph.conversation_history: the questions asked and the user's own answers."""
    log = []
    for e in _list(((spec or {}).get('interrogation') or {}).get('qa_log')):
        if isinstance(e, dict):
            log.append({'role': 'assistant', 'content': _s(e.get('question'))})
            log.append({'role': 'user', 'content': _s(e.get('answer'))})
    for e in _ledger(spec):
        log.append({'role': 'assistant', 'content': _s(e.get('question_text'))})
        log.append({'role': 'user', 'content': _s(e.get('answer_text')) or '(not known yet)'})
    return log


def generation_context(workbench, spec):
    """Workbench generation context plus the frozen constraint groups."""
    from .schema import _build_playbook_generation_context
    context = _build_playbook_generation_context(workbench)
    context['maieutic_constraints'] = build_constraints(spec)
    return context


@transaction.atomic
def create_workbench_from_draft(draft_id, user, *, exit_mode):
    """Create the Workbench, lock the session, and (optionally) queue generation. Returns (workbench, tasks)."""
    from ai_assistant.models import AIGenerationTask, UserAISettings
    from playbooks.models import ActivityLog, MitreAttackTechnique, PlaybookGraph, PlaybookNode
    from playbooks.schema import _normalize_workbench_title, _resolve_user_organization_for_create

    if exit_mode not in (EXIT_WITH_RULE, EXIT_WITHOUT_RULE):
        raise lifecycle.MaieuticError('exit must be CREATE_AND_GENERATE or CREATE_WITHOUT_RULE.')
    draft = MaieuticDraft.objects.select_for_update().filter(
        id=draft_id, organization=user.organization, author=user).first()
    if draft is None:
        raise lifecycle.MaieuticError('Maieutic session not found.')
    lifecycle._assert_editable(draft)
    missing = lifecycle.missing_for_workbench(draft.spec)
    if missing:
        raise lifecycle.MaieuticError(f'Missing required answers: {", ".join(missing)}.')
    if exit_mode == EXIT_WITH_RULE and not UserAISettings.objects.filter(user=user).exists():
        raise lifecycle.MaieuticError(
            'Rule generation needs an AI provider. Configure AI Settings in your profile, '
            'or choose "Create Workbench without a rule".')

    spec = draft.spec or {}
    values = workbench_fields(spec)
    technique = (spec.get('hypothesis') or {}).get('technique') or {}
    mitre = None
    if technique.get('state') == 'SET' and technique.get('id'):
        mitre = MitreAttackTechnique.objects.filter(technique_id=technique['id']).first()

    organization = _resolve_user_organization_for_create(user)
    workbench = PlaybookGraph.objects.create(
        organization=organization, author=user, status='IDEA', mitre_technique=mitre,
        tlp_classification=draft.tlp_classification,
        conversation_history=conversation_log(spec), **values)
    workbench.title = _normalize_workbench_title(workbench.title, workbench)
    workbench.save(update_fields=['title', 'updated_at'])
    capabilities, ignored = capability_selection(spec, user, mitre)
    if capabilities:
        workbench.selected_capability_abstractions.set(capabilities)
    if ignored:
        logger.info('Maieutic session %s: %s capability entr(ies) not attached (other technique, not visible or gone)',
                    draft.id, ignored)
    ActivityLog.objects.create(playbook=workbench, user=user, action='Created',
                               details=f'Created from Maieutic session "{draft.name}"')
    PlaybookNode.objects.create(graph=workbench, layer_name='Incident Start', position_x=100, position_y=100)

    tasks = []
    outcome = MaieuticDraft.Outcome.WORKBENCH_WITHOUT_RULE
    if exit_mode == EXIT_WITH_RULE:
        outcome = MaieuticDraft.Outcome.WORKBENCH_WITH_RULE
        context = generation_context(workbench, spec)
        for fmt in selected_formats(spec):
            tasks.append(AIGenerationTask.objects.create(
                user=user, organization=user.organization, task_type=AIGenerationTask.TaskType.GENERATE_RULE,
                input_data={'playbook_id': str(workbench.id), 'output_format': fmt, 'playbook_context': context,
                            'maieutic_workbench_id': str(workbench.id), 'maieutic_draft_id': str(draft.id)}))

    lifecycle.finish_draft(draft.id, user, workbench=workbench, outcome=outcome)

    if tasks:
        from core.rabbitmq import publish_event

        def publish():
            for t in tasks:
                if not publish_event('ai.generation.requested', {
                        'task_id': str(t.id), 'task_type': t.task_type, 'user_id': str(user.id)}):
                    logger.warning('Could not publish generation task %s', t.id)
        transaction.on_commit(publish)
    return workbench, tasks


def apply_generation_result(task, result):
    """Write a finished task's rule into its Workbench. Never overwrites text the user has since entered."""
    from playbooks.models import ActivityLog, PlaybookGraph

    data = task.input_data or {}
    wb_id = data.get('maieutic_workbench_id')
    rule = _s((result or {}).get('rule'))
    if not wb_id or not rule:
        return False
    fmt = str(data.get('output_format') or 'KQL').upper()
    with transaction.atomic():
        wb = PlaybookGraph.objects.select_for_update().filter(pk=wb_id, organization_id=task.organization_id).first()
        if wb is None:
            return False
        if fmt == 'KQL':
            if _s(wb.detection_rule):
                return False
            wb.detection_rule, wb.detection_rule_format = rule, 'KQL'
            wb.save(update_fields=['detection_rule', 'detection_rule_format', 'updated_at'])
        else:
            slot, key, name = PLATFORM_SLOTS[fmt]
            doc = dict(wb.opentide_yaml) if isinstance(wb.opentide_yaml, dict) else {}
            platforms = dict(doc.get('platforms') or {})
            block = dict(platforms.get(slot) or {})
            if _s(block.get(key)):
                return False
            block[key] = rule
            platforms[slot] = block
            doc['platforms'] = platforms
            wb.opentide_yaml = doc
            configured = list(wb.configured_platforms or [])
            if name not in configured:
                configured.append(name)
            wb.configured_platforms = configured
            wb.save(update_fields=['opentide_yaml', 'configured_platforms', 'updated_at'])
        ActivityLog.objects.create(playbook=wb, user=task.user, action='Rule generated',
                                   details=f'{fmt} rule generated from the Maieutic session design '
                                           f'(validation: {(result or {}).get("validation_status", "unknown")})')
    return True


def generation_status(workbench_id, user):
    """Per-format state of the generation tasks queued for a Workbench, for the banner."""
    from ai_assistant.models import AIGenerationTask
    rows = AIGenerationTask.objects.filter(
        organization=user.organization, user=user, input_data__maieutic_workbench_id=str(workbench_id),
    ).order_by('created_at')
    out = []
    for t in rows:
        result = t.result_data or {}
        out.append({'task_id': t.id, 'output_format': (t.input_data or {}).get('output_format'),
                    'status': t.status, 'validation_status': result.get('validation_status'),
                    'has_rule': bool(_s(result.get('rule'))), 'error': t.error_message or '',
                    'traceability': result.get('traceability') or [],
                    'traceability_rule_repaired': bool(result.get('traceability_rule_repaired'))})
    return out
