"""Traceability of a generated rule back to the engineer's design decisions (spec section 10).

The generator is asked, only for Maieutic Workbenches, to report for every decision whether and
where the rule realises it. This module numbers the decisions, parses that report defensively and
adds the one check that does not need to trust the model: a rule must not claim to cover an
accepted limitation.

The result is an AI-assisted check, never a guarantee, and the UI says so.
"""
import json
import re

IMPLEMENTED = ('yes', 'no', 'partial')
GROUP_LABELS = {'M': 'MUST_IMPLEMENT', 'H': 'MUST_HANDLE', 'L': 'ACCEPTED_LIMITATION'}
MAX_TEXT = 300

STATUS_OK = 'REPORTED'
STATUS_MISSING = 'NOT_REPORTED'
STATUS_CONFLICT = 'CONTRADICTS_LIMITATION'

TRACEABILITY_CONTRACT = (
    '---TRACEABILITY-START---\n'
    '<a JSON array with exactly one object per decision reference in the DESIGN DECISIONS block '
    '(M1, H1, L1 and so on): {"decision_ref": "M1", "implemented": "yes" or "no" or "partial", '
    '"where": "<the clause or line of the PRIMARY-RULE that realises it, empty if none>", '
    '"note": "<one short sentence>"}. For an ACCEPTED LIMITATION the value of "implemented" must be '
    '"no", because the rule must not claim to cover it. Plain JSON only, no markdown fences.>\n'
    '---TRACEABILITY-END---\n'
)


def _s(value):
    return ' '.join(str(value or '').split())


def _clip(value):
    text = _s(value)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 1] + '\u2026'


def decision_refs(constraints):
    """Number the decisions in the same order the prompt lists them: M1.., H1.., L1.."""
    constraints = constraints if isinstance(constraints, dict) else {}
    refs = []
    for i, item in enumerate(constraints.get('must_implement') or [], 1):
        refs.append({'ref': f'M{i}', 'group': GROUP_LABELS['M'], 'text': _clip(item)})
    for i, item in enumerate(constraints.get('must_handle') or [], 1):
        text = f"{_s(item.get('topic'))} Engineer: {_s(item.get('engineer_says'))}"
        refs.append({'ref': f'H{i}', 'group': GROUP_LABELS['H'], 'text': _clip(text)})
    for i, item in enumerate(constraints.get('accepted_limitations') or [], 1):
        text = f"{_s(item.get('topic'))} Engineer: {_s(item.get('engineer_says'))}"
        refs.append({'ref': f'L{i}', 'group': GROUP_LABELS['L'], 'text': _clip(text)})
    return refs


def has_decisions(constraints):
    return bool(decision_refs(constraints))


def _load_json_array(raw):
    text = (raw or '').strip()
    if not text:
        return None
    text = re.sub(r'^```[a-zA-Z]*\s*|\s*```$', '', text).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def build(raw, constraints):
    """One row per decision, in prompt order. Never raises; unusable model output yields NOT_REPORTED rows.

    Rows the model skipped are kept and marked, so a missing answer is visible instead of looking
    like a pass. Unknown references the model invented are dropped.
    """
    reported = {}
    for entry in _load_json_array(raw) or []:
        if isinstance(entry, dict) and isinstance(entry.get('decision_ref'), str):
            reported.setdefault(entry['decision_ref'].strip().upper(), entry)

    rows = []
    for decision in decision_refs(constraints):
        entry = reported.get(decision['ref'])
        row = {**decision, 'implemented': None, 'where': '', 'note': '', 'status': STATUS_MISSING}
        if entry is not None:
            implemented = _s(entry.get('implemented')).lower()
            row.update({
                'implemented': implemented if implemented in IMPLEMENTED else None,
                'where': _clip(entry.get('where')),
                'note': _clip(entry.get('note')),
                'status': STATUS_OK,
            })
            if row['implemented'] is None:
                row['status'] = STATUS_MISSING
        # The rule must never claim to cover something the engineer accepted as a limitation.
        if row['group'] == GROUP_LABELS['L'] and row['implemented'] in ('yes', 'partial'):
            row['status'] = STATUS_CONFLICT
        rows.append(row)
    return rows
