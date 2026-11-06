"""Records of positive test runs of a Workbench rule: was the test executed, and did the rule fire.

HEFAISTOS does not run the rule against telemetry. A record is what the person who ran the test reported,
with who and when. Records are only added, never edited, so the trail stays honest. Nothing here changes
test_validation_status (that belongs to the CI/CD pipeline), the Workbench version or Blind Spots.

Pure functions only (no ORM), so they are cheap to test.
"""
import re
import uuid
from datetime import datetime, timezone

from playbooks.negative_tests import fingerprint

MAX_RUNS = 20
LIMITS = {'notes': 2000, 'by': 150}


def _block(value, limit):
    return str(value or '').replace('\r\n', '\n').strip()[:limit]


def _line(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _fingerprint(value):
    """Exactly a fingerprint as made by negative_tests.fingerprint, otherwise nothing."""
    text = str(value or '')
    return text if re.fullmatch(r'[0-9a-f]{16}', text) else ''


def _flag(value):
    return value is True


def normalize(raw):
    """Defensive copy of whatever is stored or imported. Unknown keys are dropped; fired without executed is reset."""
    runs, seen = [], set()
    for entry in (raw if isinstance(raw, list) else [])[-MAX_RUNS:]:
        if not isinstance(entry, dict):
            continue
        try:
            ident = str(uuid.UUID(str(entry.get('id') or '')))
        except ValueError:
            ident = str(uuid.uuid4())
        if ident in seen:
            continue
        seen.add(ident)
        executed = _flag(entry.get('executed'))
        runs.append({
            'id': ident,
            'executed': executed,
            'fired': executed and _flag(entry.get('fired')),
            'notes': _block(entry.get('notes'), LIMITS['notes']),
            'recorded_at': str(entry.get('recorded_at'))[:40] if entry.get('recorded_at') else None,
            'recorded_by': _line(entry.get('recorded_by'), LIMITS['by']),
            'rule_fingerprint': _fingerprint(entry.get('rule_fingerprint')),
        })
    return runs


def for_export(runs):
    """What leaves the instance in a Workbench file: the outcome, not the person's username."""
    return [{**r, 'recorded_by': ''} for r in normalize(runs)]


def add_run(runs, *, executed, fired, notes, rule_text, user_name, now=None):
    """Return a new list with one record appended (oldest dropped past MAX_RUNS). Raises ValueError for nonsense."""
    if executed is not True and executed is not False or fired is not True and fired is not False:
        raise ValueError('Executed and fired must be true or false.')
    if not executed:
        raise ValueError('Tick "Test executed" first: a run that did not happen is not recorded.')
    runs = normalize(runs)
    stamp = now or datetime.now(timezone.utc)
    runs.append({
        'id': str(uuid.uuid4()),
        'executed': True,
        'fired': fired,
        'notes': _block(notes, LIMITS['notes']),
        'recorded_at': stamp.isoformat(),
        'recorded_by': _line(user_name, LIMITS['by']),
        'rule_fingerprint': fingerprint(rule_text),
    })
    return runs[-MAX_RUNS:]


def present(runs, rule_text):
    """What the API returns: newest first, each with `stale` (the rule text changed after the run)."""
    current = fingerprint(rule_text)
    out = [{**r, 'stale': r['rule_fingerprint'] != current} for r in normalize(runs)]
    return list(reversed(out))


def summary(presented):
    """Latest state for the header line. None when nothing was ever recorded."""
    if not presented:
        return None
    latest = presented[0]
    return {'runs': len(presented), 'latest_fired': latest['fired'], 'latest_stale': latest['stale']}
