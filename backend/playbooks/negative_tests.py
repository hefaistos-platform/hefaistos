"""Negative tests of a Workbench: how to check that the rule does NOT fire on something the engineer accepted.

A negative test is a written procedure plus a recorded outcome. HEFAISTOS does not run the rule against
telemetry, so the result is what the person who ran the test reports. Nothing here changes the Workbench
test status, version or Blind Spots; the result is only stored and shown next to the test.

Pure functions only (no ORM), so they are cheap to test.
"""
import hashlib
import re
import uuid
from datetime import datetime, timezone

NOT_RUN = 'NOT_RUN'
NOT_DETECTED = 'NOT_DETECTED'   # the rule stayed silent, as the engineer accepted
DETECTED = 'DETECTED'           # the rule fired, so it covers more than the engineer said
RESULTS = (NOT_RUN, NOT_DETECTED, DETECTED)

STEPS_USER = 'USER'
STEPS_TEMPLATE = 'TEMPLATE'

EXPECTED = 'No alert is raised.'
MAX_TESTS = 50
LIMITS = {'steps': 4000, 'notes': 2000, 'limitation': 500, 'accepted_as': 1000, 'source_ref': 40}


def _line(value, limit):
    """Single-line text: whitespace collapsed."""
    return ' '.join(str(value or '').split())[:limit]


def _block(value, limit):
    """Multi-line text: line breaks kept (steps and notes are written as paragraphs or numbered lists)."""
    return str(value or '').replace('\r\n', '\n').strip()[:limit]


def fingerprint(rule_text):
    """Short hash of the rule, ignoring whitespace, so a recorded result can be told apart from a changed rule."""
    normalised = re.sub(r'\s+', ' ', str(rule_text or '')).strip()
    return hashlib.sha256(normalised.encode('utf-8')).hexdigest()[:16] if normalised else ''


def template_steps(limitation, accepted_as):
    """Deterministic starting text for a test the engineer did not write. No AI: nothing here is invented."""
    lines = ['Reproduce the behaviour you accepted as a limitation:']
    if limitation:
        lines.append(f'- Question: {limitation}')
    if accepted_as:
        lines.append(f'- Your answer: {accepted_as}')
    lines += ['',
              '1. On a test host that sends the rule\'s telemetry, run the behaviour described above.',
              '2. Wait for the rule schedule or run the query manually over the test window.',
              f'3. Expected: {EXPECTED[:-1].lower()}. If an alert appears, the rule covers more than you accepted.']
    return '\n'.join(lines)


def new_item(source_ref, limitation, accepted_as, steps=''):
    written = _block(steps, LIMITS['steps'])
    limitation, accepted_as = _line(limitation, LIMITS['limitation']), _line(accepted_as, LIMITS['accepted_as'])
    return {
        'id': str(uuid.uuid4()),
        'source_ref': _line(source_ref, LIMITS['source_ref']),
        'limitation': limitation,
        'accepted_as': accepted_as,
        'steps': written or template_steps(limitation, accepted_as),
        'steps_source': STEPS_USER if written else STEPS_TEMPLATE,
        'expected': EXPECTED,
        'result': NOT_RUN,
        'notes': '',
        'tested_at': None,
        'rule_fingerprint': '',
    }


def normalize(raw):
    """Defensive copy of whatever is stored or imported. Unknown keys are dropped, bad values reset."""
    items = []
    seen = set()
    for entry in (raw if isinstance(raw, list) else [])[:MAX_TESTS]:
        if not isinstance(entry, dict):
            continue
        ident = str(entry.get('id') or '')
        try:
            ident = str(uuid.UUID(ident))
        except ValueError:
            ident = str(uuid.uuid4())
        if ident in seen:
            continue
        seen.add(ident)
        result = entry.get('result') if entry.get('result') in RESULTS else NOT_RUN
        items.append({
            'id': ident,
            'source_ref': _line(entry.get('source_ref'), LIMITS['source_ref']),
            'limitation': _line(entry.get('limitation'), LIMITS['limitation']),
            'accepted_as': _line(entry.get('accepted_as'), LIMITS['accepted_as']),
            'steps': _block(entry.get('steps'), LIMITS['steps']),
            'steps_source': STEPS_USER if entry.get('steps_source') == STEPS_USER else STEPS_TEMPLATE,
            'expected': EXPECTED,
            'result': result,
            'notes': _block(entry.get('notes'), LIMITS['notes']),
            'tested_at': str(entry.get('tested_at'))[:40] if result != NOT_RUN and entry.get('tested_at') else None,
            'rule_fingerprint': str(entry.get('rule_fingerprint') or '')[:16] if result != NOT_RUN else '',
        })
    return items


def present(items, rule_text):
    """What the API returns: each item plus `stale`, true when a result was recorded for a different rule text."""
    current = fingerprint(rule_text)
    out = []
    for item in normalize(items):
        recorded = item['result'] != NOT_RUN
        out.append({**item, 'stale': bool(recorded and item['rule_fingerprint'] != current)})
    return out


def apply_update(items, test_id, *, rule_text, steps=None, result=None, notes=None, now=None):
    """Return a new list with one test changed. Raises ValueError for an unknown test or invalid result.

    Editing the steps clears a recorded result, because that result belongs to the old procedure.
    """
    if result is not None and result not in RESULTS:
        raise ValueError('Unknown test result.')
    items = normalize(items)
    target = next((i for i in items if i['id'] == str(test_id)), None)
    if target is None:
        raise ValueError('Negative test not found.')
    if steps is not None:
        text = _block(steps, LIMITS['steps'])
        if not text:
            raise ValueError('The steps cannot be empty.')
        if text != target['steps']:
            target.update(steps=text, steps_source=STEPS_USER)
            if result is None:
                result = NOT_RUN
    if notes is not None:
        target['notes'] = _block(notes, LIMITS['notes'])
    if result is not None:
        target['result'] = result
        if result == NOT_RUN:
            target.update(tested_at=None, rule_fingerprint='')
        else:
            stamp = now or datetime.now(timezone.utc)
            target.update(tested_at=stamp.isoformat(), rule_fingerprint=fingerprint(rule_text))
    return items


def summary(items):
    """Counts shown above the list. NOT_RUN is a state of the list, never a finding."""
    counts = {NOT_RUN: 0, NOT_DETECTED: 0, DETECTED: 0, 'stale': 0}
    for item in items or []:
        counts[item['result']] = counts.get(item['result'], 0) + 1
        if item.get('stale'):
            counts['stale'] += 1
    return counts
