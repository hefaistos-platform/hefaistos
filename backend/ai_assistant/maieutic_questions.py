"""Maieutic ADE question bank: loader, validator and renderer.

Questions are versioned YAML files in ``maieutic_content/ade_questions/`` and are reviewed like
code. There is no runtime approval workflow and no user-facing approval gate: the user answers
every question themselves. The AI may rephrase a question or challenge a vague answer; it never
writes an answer. See Docs/MAIEUTIC_ADE_QUESTIONS.md.

Guardrails enforced here (so a bad file fails the tests, not a user):
- the question is about the user's hypothesis and planned design, never about "your rule"
  (the rule is the final product, not the starting point);
- the question is open-ended (no yes/no openers);
- three ordered hint rungs, the last being a worked example from a different technique;
- every {placeholder} is declared and has a plain-language fallback.
"""

import re
from functools import lru_cache
from pathlib import Path

import yaml

CONTENT_DIR = Path(__file__).resolve().parent / 'maieutic_content' / 'ade_questions'

ADE_ID_RE = re.compile(r'^ADE[1-4]-\d{2}$')
QUESTION_ID_RE = re.compile(r'^ade-q-ade[1-4]-\d{2}$')
PLACEHOLDER_RE = re.compile(r'\{([a-z_]+)\}')

# Facts the planner can derive from the design answers. A question lists the ones that trigger it.
DESIGN_FLAGS = frozenset({
    'names_specific_tool',            # design names a tool, binary, command or API
    'matches_process_name',           # design identifies behaviour by process / binary name
    'multi_condition_single_event',   # several text conditions expected inside one event
    'version_or_platform_specific',   # design assumes an OS, software or API version
})
APPLIES_TYPES = frozenset({'always', 'design_flags_any'})

# Yes/no openers are not Socratic: they invite a one-word answer.
YES_NO_OPENERS = (
    'is', 'are', 'was', 'were', 'do', 'does', 'did', 'can', 'could', 'would', 'will',
    'should', 'has', 'have', 'had', 'may', 'might',
)
FORBIDDEN_PHRASES = re.compile(r'\b(your|the|this) (existing )?(rule|query|detection rule)\b', re.I)
USER_FACING_TEXT_FIELDS = ('question', 'why_we_ask', 'weak_answer', 'strong_answer')
HINT_KEYS = ('where_to_look', 'how_to_look', 'worked_example')


class QuestionContentError(ValueError):
    """Raised when a question file breaks a rule above."""


def _require(cond, path, msg):
    if not cond:
        raise QuestionContentError(f'{path}: {msg}')


def _texts(q):
    out = [(f, q.get(f)) for f in USER_FACING_TEXT_FIELDS]
    hints = q.get('hints') or {}
    out += [(f'hints.{k}', hints.get(k)) for k in ('where_to_look', 'how_to_look')]
    example = hints.get('worked_example') or {}
    out += [('hints.worked_example.text', example.get('text'))]
    return out


def validate_question(q, path='question'):
    _require(isinstance(q, dict), path, 'must be a mapping')
    _require(QUESTION_ID_RE.match(str(q.get('id', ''))), path, "id must look like 'ade-q-ade2-01'")
    _require(ADE_ID_RE.match(str(q.get('ade_id', ''))), path, "ade_id must look like 'ADE2-01'")
    _require(q['id'] == f"ade-q-{q['ade_id'].lower()}", path, 'id must match ade_id')
    _require(isinstance(q.get('version'), int) and q['version'] >= 1, path, 'version must be an integer >= 1')

    for field in USER_FACING_TEXT_FIELDS:
        value = q.get(field)
        _require(isinstance(value, str) and value.strip(), path, f'{field} is required')

    first_word = re.split(r'\W+', q['question'].strip().lower(), maxsplit=1)[0]
    _require(first_word not in YES_NO_OPENERS, path,
             f"question must be open-ended; it starts with '{first_word}'")
    _require(q['question'].strip().endswith('?'), path, 'question must end with a question mark')

    hints = q.get('hints')
    _require(isinstance(hints, dict) and set(hints) == set(HINT_KEYS), path,
             f'hints must have exactly {", ".join(HINT_KEYS)} (in that order of use)')
    for key in ('where_to_look', 'how_to_look'):
        _require(isinstance(hints[key], str) and hints[key].strip(), path, f'hints.{key} is required')
    example = hints['worked_example']
    _require(isinstance(example, dict) and example.get('technique') and example.get('text'), path,
             'hints.worked_example needs technique and text (use a technique other than the user\'s)')

    for field, value in _texts(q):
        _require(not FORBIDDEN_PHRASES.search(str(value or '')), path,
                 f"{field} refers to 'the/your rule'; ask about the hypothesis or design instead")

    glossary = q.get('glossary') or []
    _require(isinstance(glossary, list), path, 'glossary must be a list')
    for item in glossary:
        _require(isinstance(item, dict) and item.get('term') and item.get('meaning'), path,
                 'each glossary item needs term and meaning')

    applies = q.get('applies_when')
    _require(isinstance(applies, dict) and applies.get('type') in APPLIES_TYPES, path,
             f'applies_when.type must be one of {sorted(APPLIES_TYPES)}')
    if applies['type'] == 'design_flags_any':
        flags = applies.get('flags')
        _require(isinstance(flags, list) and flags, path, 'design_flags_any needs a non-empty flags list')
        unknown = sorted(set(flags) - DESIGN_FLAGS)
        _require(not unknown, path, f'unknown design flags: {", ".join(unknown)}')

    checklist = q.get('checklist')
    _require(isinstance(checklist, list) and len(checklist) >= 2 and all(isinstance(c, str) and c.strip() for c in checklist),
             path, 'checklist needs at least two non-empty items')

    placeholders = q.get('placeholders') or {}
    _require(isinstance(placeholders, dict), path, 'placeholders must be a mapping name -> fallback phrase')
    used = set()
    for _, value in _texts(q):
        used |= set(PLACEHOLDER_RE.findall(str(value or '')))
    undeclared = sorted(used - set(placeholders))
    _require(not undeclared, path, f'placeholders used but not declared: {", ".join(undeclared)}')
    for name, fallback in placeholders.items():
        _require(isinstance(fallback, str) and fallback.strip(), path, f'placeholder {name} needs a fallback phrase')
    return q


@lru_cache(maxsize=1)
def load_questions(directory=None):
    """Return {ade_id: question}. Fails loudly on any invalid or duplicate file."""
    base = Path(directory) if directory else CONTENT_DIR
    questions = {}
    for file in sorted(base.glob('*.yaml')):
        data = yaml.safe_load(file.read_text(encoding='utf-8'))
        validate_question(data, path=file.name)
        _require(data['ade_id'] not in questions, file.name, f"duplicate question for {data['ade_id']}")
        questions[data['ade_id']] = data
    return questions


def questions_for_design(design_flags, *, expert_all=False, questions=None):
    """Deterministic selection (no AI). Returns [(question, trigger_reason)] ordered by ADE id."""
    pool = questions if questions is not None else load_questions()
    flags = set(design_flags or ())
    selected = []
    for ade_id in sorted(pool):
        q = pool[ade_id]
        applies = q['applies_when']
        if applies['type'] == 'always':
            reason = 'always'
        else:
            hit = sorted(flags & set(applies['flags']))
            reason = f"design:{hit[0]}" if hit else None
            if reason is None and expert_all:
                reason = 'expert_all'
        if reason:
            selected.append((q, reason))
    return selected


def render_text(text, q, values=None):
    """Fill {placeholders} from the user's own design wording; fall back to a plain phrase."""
    values = values or {}
    fallbacks = q.get('placeholders') or {}
    return PLACEHOLDER_RE.sub(
        lambda m: (str(values.get(m.group(1)) or '').strip() or fallbacks.get(m.group(1), '')), str(text))
