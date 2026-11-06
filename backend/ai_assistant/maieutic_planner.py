"""Deterministic planner for the Maieutic ADE questions. No AI is involved here.

Input is the user's own structured design (see Docs/MAIEUTIC_ADE_QUESTIONS.md):
``spec['design']`` and ``spec['hypothesis']``. Output is which ADE questions to ask and why.

Principle: bias toward asking. Asking one question too many costs the user a NOT_APPLICABLE
answer; asking one too few silently hides a gap. Every flag records the design items that
triggered it, so an answer can point back to ``design_ref``.
"""

from . import maieutic_questions as mq

TEXT_ANCHORS = {'COMMAND_LINE_TEXT', 'FILE_OR_PROCESS_NAME', 'REGISTRY'}
TOOL_ANCHORS = {'FILE_OR_PROCESS_NAME', 'COMMAND_LINE_TEXT', 'API_OR_SYSCALL'}
LOCATION_ANCHORS = {'REGISTRY', 'FILE_OR_PROCESS_NAME', 'NETWORK'}
PLATFORM_ANCHORS = {'REGISTRY', 'API_OR_SYSCALL', 'FILE_OR_PROCESS_NAME'}
SETTABLE = {'FREELY', 'WITH_EFFORT', 'UNKNOWN'}
SETTABLE_FIELD = {'YES', 'PARTIAL', 'UNKNOWN'}
PARENT_WORDS = ('parent', 'child', 'spawn', 'launched by', 'started by')


def _items(value):
    return [v for v in (value or []) if isinstance(v, dict)]


def _text(item):
    if isinstance(item, dict):
        return str(item.get('description') or item.get('text') or item.get('value') or '')
    return str(item or '')


def _ref(kind, item, index):
    ident = item.get('id') if isinstance(item, dict) else None
    return f'{kind}:{ident}' if ident else f'{kind}:{index}'


def derive_design_flags(spec):
    """Return {flag: [design_ref, ...]} for the flags the design triggers."""
    spec = spec or {}
    design = spec.get('design') or {}
    interrogation = spec.get('interrogation') or {}
    elements = _items(design.get('match_elements'))
    exclusions = _items(design.get('exclusions'))
    correlations = design.get('correlations') or []
    thresholds = design.get('windows_thresholds') or {}
    fields = _items(interrogation.get('fields'))
    sources = _items(interrogation.get('log_sources'))

    flags = {}

    def hit(flag, ref):
        flags.setdefault(flag, [])
        if ref not in flags[flag]:
            flags[flag].append(ref)

    anchored = [(i, e, str(e.get('anchor_type') or '')) for i, e in enumerate(elements)]
    for i, e, anchor in anchored:
        ref = _ref('match_element', e, i)
        changeable = str(e.get('attacker_changeable') or '')
        if anchor in TOOL_ANCHORS:
            hit('names_specific_tool', ref)
        if anchor == 'FILE_OR_PROCESS_NAME':
            hit('matches_process_name', ref)
            hit('names_file_types', ref)
        if anchor in TEXT_ANCHORS and changeable != 'NO':
            hit('matches_attacker_controlled_string', ref)
        if anchor in LOCATION_ANCHORS:
            hit('names_specific_location', ref)
        if anchor in PLATFORM_ANCHORS:
            hit('version_or_platform_specific', ref)
        if any(w in _text(e).lower() for w in PARENT_WORDS):
            hit('relies_on_parent_process', ref)

    command_line = [(i, e) for i, e, a in anchored if a == 'COMMAND_LINE_TEXT']
    if len(command_line) >= 2:
        for i, e in command_line:
            hit('multi_condition_single_event', _ref('match_element', e, i))

    for n, c in enumerate(correlations):
        ref = f'correlation:{n}'
        hit('correlates_events_or_fields', ref)
        hit('relies_on_join_or_grouping', ref)
        if any(w in _text(c).lower() for w in PARENT_WORDS):
            hit('relies_on_parent_process', ref)
    if len(sources) >= 2:
        for i, s in enumerate(sources):
            hit('correlates_events_or_fields', _ref('log_source', s, i))

    if thresholds.get('alert_threshold') not in (None, '', 0) or thresholds.get('aggregation_function'):
        hit('uses_threshold_or_baseline', 'windows_thresholds')
    if thresholds.get('aggregation_field'):
        hit('relies_on_join_or_grouping', 'windows_thresholds')
    if thresholds.get('time_window') or thresholds.get('suppression_window'):
        hit('uses_time_window', 'windows_thresholds')

    for i, x in enumerate(exclusions):
        hit('plans_exclusions', _ref('exclusion', x, i))

    settable = [(i, e) for i, e, _ in anchored if str(e.get('attacker_changeable') or '') in SETTABLE]
    settable_fields = [(i, f) for i, f in enumerate(fields) if str(f.get('attacker_controlled') or '') in SETTABLE_FIELD]
    if exclusions and (settable or settable_fields):
        for i, e in settable:
            hit('uses_attacker_settable_value', _ref('match_element', e, i))
        for i, f in settable_fields:
            hit('uses_attacker_settable_value', _ref('field', f, i))

    if len(elements) + len(exclusions) >= 2:
        for i, e in enumerate(elements):
            hit('combines_multiple_conditions', _ref('match_element', e, i))
        for i, x in enumerate(exclusions):
            hit('combines_multiple_conditions', _ref('exclusion', x, i))

    return flags


def _observable(question, flag_refs, spec):
    """Wording for {design_observable}: the user's own description of the first triggering item."""
    design = (spec or {}).get('design') or {}
    elements = {(_ref('match_element', e, i)): e for i, e in enumerate(_items(design.get('match_elements')))}
    exclusions = {(_ref('exclusion', x, i)): x for i, x in enumerate(_items(design.get('exclusions')))}
    for ref in flag_refs:
        item = elements.get(ref) or exclusions.get(ref)
        if item:
            text = _text(item) or str(item.get('what') or '')
            if text.strip():
                return text.strip()[:140]
    return ''


def plan(spec, *, expert_all=False, questions=None):
    """Planned ADE questions, deterministic and ordered by ADE id.

    Each item: {ade_id, question, trigger_reason, design_refs, values}.
    """
    pool = questions if questions is not None else mq.load_questions()
    flag_refs = derive_design_flags(spec)
    out = []
    for q, reason in mq.questions_for_design(set(flag_refs), expert_all=expert_all, questions=pool):
        refs = []
        if q['applies_when']['type'] == 'design_flags_any':
            for flag in q['applies_when']['flags']:
                for ref in flag_refs.get(flag, []):
                    if ref not in refs:
                        refs.append(ref)
        out.append({
            'ade_id': q['ade_id'],
            'question': q,
            'trigger_reason': reason,
            'design_refs': refs,
            'values': {'design_observable': _observable(q, refs, spec)},
        })
    return out


def ledger_by_ade(spec):
    ledger = ((spec or {}).get('robustness') or {}).get('ade_ledger') or []
    return {e.get('ade_id'): e for e in ledger if isinstance(e, dict)}


def open_items(spec, *, expert_all=False):
    """Planned questions with no disposition yet, or answered against an older question version."""
    answered = ledger_by_ade(spec)
    result = []
    for item in plan(spec, expert_all=expert_all):
        entry = answered.get(item['ade_id'])
        stale = entry is not None and entry.get('question_version') != item['question']['version']
        if entry is None or not entry.get('disposition') or stale:
            result.append(item)
    return result


def snapshot_label(snapshot):
    """Short human label of an imported ADE snapshot: the commit when known, else the ref."""
    return (snapshot.source_sha[:12] if snapshot.source_sha else snapshot.source_ref) or 'unknown'


def framework_drift(pinned, active, relevant_ids):
    """What changed upstream, for this session, since it started answering against `pinned`.

    Only a note for the user: nothing is reopened or hidden because of it. A question reopens when
    its own text version changes (see open_items), not when the upstream definition changes, and
    answers already given are kept. `relevant_ids` are the ADE ids the session plans or answered.
    Returns None when there is nothing to tell (no pinned or active snapshot, the same snapshot, or
    no relevant topic removed or changed).
    """
    if pinned is None or active is None or pinned.id == active.id:
        return None

    def hashes(snapshot):
        return {e.ade_id: e.source_hash for e in snapshot.entries.filter(kind='SUBCATEGORY') if e.ade_id}

    old, new, relevant = hashes(pinned), hashes(active), set(relevant_ids)
    removed = sorted(i for i in old if i not in new and i in relevant)
    changed = sorted(i for i in old if i in new and old[i] != new[i] and i in relevant)
    if not removed and not changed:
        return None
    return {
        'pinned_snapshot_id': pinned.id, 'active_snapshot_id': active.id,
        'pinned_label': snapshot_label(pinned), 'active_label': snapshot_label(active),
        'removed': removed, 'changed': changed,
    }


def questions_missing_for_snapshot(snapshot, questions=None):
    """Upstream subcategories in a promoted ADE snapshot that have no question file yet."""
    if snapshot is None:
        return []
    pool = questions if questions is not None else mq.load_questions()
    return sorted(
        e.ade_id for e in snapshot.entries.filter(kind='SUBCATEGORY') if e.ade_id and e.ade_id not in pool
    )
