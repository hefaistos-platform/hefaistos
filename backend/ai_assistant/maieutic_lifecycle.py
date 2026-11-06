"""Lifecycle, visibility and locking rules for MaieuticDraft.

Every write path goes through this module so the FINISHED lock cannot be bypassed by one
mutation forgetting a check. Rules: Docs/MAIEUTIC_3_SPEC.md sections 9, 9b, 9c.
"""

from django.db import transaction
from django.utils import timezone

from playbooks.utils.tlp import normalize_tlp

from . import maieutic_planner, maieutic_questioner, maieutic_questions
from .maieutic_models import MaieuticDraft

STAGE_COUNT = 6
CHALLENGE_LEVELS = ('LIGHT', 'STANDARD', 'EXPERT')
SPEC_SECTIONS = ('meta', 'hypothesis', 'interrogation', 'design', 'robustness', 'playbook_tests', 'review')
SPEC_VERSION = 1
MAX_SPEC_BYTES = 512 * 1024


class MaieuticError(Exception):
    """Raised for rule violations; the message is safe to show to the user."""


def _is_platform_admin(user) -> bool:
    return bool(getattr(user, 'is_superuser', False))


def _is_org_admin(user) -> bool:
    return str(getattr(user, 'role', '') or '') == 'ADMIN'


def get_visible_draft(user, draft_id):
    """Author-only visibility. Admins and superusers do NOT see other users' sessions."""
    return MaieuticDraft.objects.filter(
        id=draft_id, organization=user.organization, author=user,
    ).first()


def list_visible_drafts(user):
    return MaieuticDraft.objects.filter(organization=user.organization, author=user)


def can_delete(user, draft: MaieuticDraft) -> bool:
    if draft.author_id is not None and draft.author_id == user.id:
        return True
    if _is_platform_admin(user):
        return True
    return _is_org_admin(user) and draft.organization_id == user.organization_id


def admin_index(user):
    """Metadata only (spec 9b). Never returns spec, name content beyond the title, or answers."""
    if _is_platform_admin(user):
        qs = MaieuticDraft.objects.all()
    elif _is_org_admin(user):
        qs = MaieuticDraft.objects.filter(organization=user.organization)
    else:
        raise MaieuticError('Administrator access required.')
    return qs.select_related('author', 'organization').only(
        'id', 'name', 'status', 'outcome', 'current_stage', 'created_at', 'updated_at',
        'finished_at', 'allow_remote_pull', 'tlp_classification',
        'author__username', 'organization__name',
    )


def get_deletable_draft(user, draft_id):
    qs = MaieuticDraft.objects.all() if _is_platform_admin(user) else MaieuticDraft.objects.filter(
        organization=user.organization,
    )
    draft = qs.filter(id=draft_id).first()
    if draft is None or not can_delete(user, draft):
        return None
    return draft


def create_draft(user, *, name=None, tlp=None) -> MaieuticDraft:
    given = (name or '').strip()
    clean = given or 'New Maieutic session'
    tlp_value = normalize_tlp(tlp)
    spec = {'meta': {'spec_version': SPEC_VERSION, 'tlp': tlp_value, 'current_stage': 1}}
    if given:
        # The title the user typed when starting is also the stage 1 title. Without this the
        # required stage 1 field looked empty even though the user had already named the idea.
        spec['hypothesis'] = {'title': clean[:200]}
    return MaieuticDraft.objects.create(
        organization=user.organization,
        author=user,
        name=clean[:255],
        tlp_classification=tlp_value,
        spec=spec,
    )


def _assert_editable(draft: MaieuticDraft):
    if draft.status == MaieuticDraft.Status.FINISHED:
        raise MaieuticError('This Maieutic session is finished and locked. Edit the Workbench instead.')


@transaction.atomic
def update_draft(draft_id, user, *, name=None, current_stage=None, spec_patch=None, tlp=None,
                 challenge_level=None) -> MaieuticDraft:
    """Autosave. spec_patch replaces whole top-level sections it names (no deep merge)."""
    draft = MaieuticDraft.objects.select_for_update().filter(
        id=draft_id, organization=user.organization, author=user,
    ).first()
    if draft is None:
        raise MaieuticError('Maieutic session not found.')
    _assert_editable(draft)

    if spec_patch is not None:
        if not isinstance(spec_patch, dict):
            raise MaieuticError('spec_patch must be an object.')
        unknown = sorted(set(spec_patch) - set(SPEC_SECTIONS))
        if unknown:
            raise MaieuticError(f'Unknown spec sections: {", ".join(unknown)}.')
        if 'meta' in spec_patch:
            raise MaieuticError('meta is managed by the server and cannot be patched.')
        merged = dict(draft.spec or {})
        merged.update(spec_patch)
        import json
        if len(json.dumps(merged, default=str)) > MAX_SPEC_BYTES:
            raise MaieuticError('Session is too large to save.')
        draft.spec = merged

    if current_stage is not None:
        if not 1 <= int(current_stage) <= STAGE_COUNT:
            raise MaieuticError(f'current_stage must be between 1 and {STAGE_COUNT}.')
        draft.current_stage = int(current_stage)

    if name is not None:
        clean = name.strip()
        if not clean:
            raise MaieuticError('Name cannot be empty.')
        previous = draft.name
        draft.name = clean[:255]
        # Keep the stage 1 title in step with a rename, unless it was edited on its own.
        if not (spec_patch and 'hypothesis' in spec_patch):
            hyp = dict((draft.spec or {}).get('hypothesis') or {})
            if str(hyp.get('title') or '').strip() in ('', previous.strip()):
                hyp['title'] = clean[:200]
                draft.spec = {**(draft.spec or {}), 'hypothesis': hyp}

    if tlp is not None:
        draft.tlp_classification = normalize_tlp(tlp)

    meta = dict((draft.spec or {}).get('meta') or {})
    if challenge_level is not None:
        level = str(challenge_level).upper()
        if level not in CHALLENGE_LEVELS:
            raise MaieuticError(f'challenge_level must be one of {", ".join(CHALLENGE_LEVELS)}.')
        meta['challenge_level'] = level
    meta.update({'spec_version': SPEC_VERSION, 'tlp': draft.tlp_classification, 'current_stage': draft.current_stage})
    draft.spec = {**(draft.spec or {}), 'meta': meta}
    draft.save()
    return draft


def missing_for_workbench(spec: dict) -> list[str]:
    """Minimum set to create a Workbench (spec section 7)."""
    hyp = (spec or {}).get('hypothesis') or {}
    missing = []
    if not str(hyp.get('title') or '').strip():
        missing.append('hypothesis.title')
    technique = hyp.get('technique')
    technique_state = technique.get('state') if isinstance(technique, dict) else technique
    if technique_state not in ('SET', 'NONE_CHOSEN'):
        missing.append('hypothesis.technique')
    if not str(hyp.get('goal') or '').strip():
        missing.append('hypothesis.goal')
    return missing


@transaction.atomic
def finish_draft(draft_id, user, *, workbench, outcome) -> MaieuticDraft:
    """Lock the session. Called by the create-Workbench flow once the Workbench exists."""
    draft = MaieuticDraft.objects.select_for_update().filter(
        id=draft_id, organization=user.organization, author=user,
    ).first()
    if draft is None:
        raise MaieuticError('Maieutic session not found.')
    _assert_editable(draft)
    if outcome not in MaieuticDraft.Outcome.values:
        raise MaieuticError('Unknown outcome.')
    if workbench is None or workbench.organization_id != draft.organization_id:
        raise MaieuticError('A Workbench from the same organization is required to finish.')
    missing = missing_for_workbench(draft.spec)
    if missing:
        raise MaieuticError(f'Missing required answers: {", ".join(missing)}.')
    draft.status = MaieuticDraft.Status.FINISHED
    draft.outcome = outcome
    draft.created_workbench = workbench
    draft.finished_at = timezone.now()
    draft.save()
    return draft


@transaction.atomic
def set_sharing(draft_id, user, *, allow: bool) -> MaieuticDraft:
    """Only the author, only once FINISHED, and never for imported copies."""
    draft = MaieuticDraft.objects.select_for_update().filter(
        id=draft_id, organization=user.organization, author=user,
    ).first()
    if draft is None:
        raise MaieuticError('Maieutic session not found.')
    if draft.status != MaieuticDraft.Status.FINISHED:
        raise MaieuticError('Only finished sessions can be shared.')
    if draft.imported_from:
        raise MaieuticError('Imported sessions cannot be shared again.')
    draft.allow_remote_pull = bool(allow)
    draft.save(update_fields=['allow_remote_pull', 'updated_at'])
    return draft


def delete_draft(draft_id, user) -> None:
    draft = get_deletable_draft(user, draft_id)
    if draft is None:
        raise MaieuticError('Maieutic session not found.')
    draft.delete()


# --- ADE questions: hints and answers (spec 3.5) -------------------------------------------

HINT_RUNGS = {1: 'where_to_look', 2: 'how_to_look', 3: 'worked_example'}


def is_expert(spec) -> bool:
    return str(((spec or {}).get('meta') or {}).get('challenge_level') or '').upper() == 'EXPERT'


def _active_ade_snapshot():
    from platform_data.models import AdeSnapshot
    return AdeSnapshot.objects.filter(status=AdeSnapshot.Status.ACTIVE).first()


def _planned_item(draft, ade_id):
    for item in maieutic_planner.plan(draft.spec, expert_all=is_expert(draft.spec)):
        if item['ade_id'] == ade_id:
            return item
    return None


def _lock_own(draft_id, user):
    draft = MaieuticDraft.objects.select_for_update().filter(
        id=draft_id, organization=user.organization, author=user,
    ).first()
    if draft is None:
        raise MaieuticError('Maieutic session not found.')
    _assert_editable(draft)
    return draft


def _save_robustness(draft, **changes):
    spec = dict(draft.spec or {})
    robustness = dict(spec.get('robustness') or {})
    robustness.update(changes)
    spec['robustness'] = robustness
    draft.spec = spec
    draft.save(update_fields=['spec', 'ade_snapshot', 'updated_at'])


@transaction.atomic
def reveal_hint(draft_id, user, *, ade_id, rung):
    """Hint ladder: one rung at a time, in order. Hints are fixed content and never use the answer."""
    draft = _lock_own(draft_id, user)
    item = _planned_item(draft, ade_id)
    if item is None:
        raise MaieuticError('That question is not part of this session.')
    if rung not in HINT_RUNGS:
        raise MaieuticError('rung must be 1, 2 or 3.')
    help_used = dict((draft.spec.get('robustness') or {}).get('ade_help') or {})
    used = int(help_used.get(ade_id, 0))
    if rung > used + 1:
        raise MaieuticError(f'Open hint {used + 1} first.')
    help_used[ade_id] = max(used, rung)
    _save_robustness(draft, ade_help=help_used)
    hint = item['question']['hints'][HINT_RUNGS[rung]]
    if isinstance(hint, dict):
        hint = f"Example from {hint['technique']}: {hint['text']}"
    return maieutic_questions.render_text(hint, item['question'], item['values'])


@transaction.atomic
def record_ade_answer(draft_id, user, *, ade_id, answer_text, disposition, reference=None,
                      design_ref=None, evaluation=None):
    """Store the user's own answer in the ledger. `evaluation` is advisory and never blocks."""
    draft = _lock_own(draft_id, user)
    item = _planned_item(draft, ade_id)
    if item is None:
        raise MaieuticError('That question is not part of this session.')
    try:
        disposition, text, reference = maieutic_questioner.validate_disposition(
            disposition, answer_text, reference)
    except ValueError as exc:
        raise MaieuticError(str(exc))
    if design_ref is not None and design_ref not in item['design_refs']:
        design_ref = None  # never store a reference the planner did not issue

    snapshot = draft.ade_snapshot or _active_ade_snapshot()
    draft.ade_snapshot = snapshot
    q = item['question']
    robustness = dict((draft.spec or {}).get('robustness') or {})
    ledger = [e for e in (robustness.get('ade_ledger') or []) if e.get('ade_id') != ade_id]
    previous = next((e for e in (robustness.get('ade_ledger') or []) if e.get('ade_id') == ade_id), None)
    evaluation = evaluation or {}
    ledger.append({
        'ade_id': ade_id,
        'snapshot_id': str(snapshot.id) if snapshot else None,
        'overlay_version': None,
        'question_id': q['id'],
        'question_version': q['version'],
        'trigger_reason': item['trigger_reason'],
        'question_text': maieutic_questions.render_text(q['question'], q, item['values']),
        'answer_text': text,
        'disposition': disposition,
        'reference': reference,
        'design_ref': design_ref,
        'help_rungs_used': list(range(1, int((robustness.get('ade_help') or {}).get(ade_id, 0)) + 1)),
        'evaluator_flag': evaluation.get('flag'),
        'evaluator_source': evaluation.get('source', 'NOT_EVALUATED'),
        'revision': (previous.get('revision', 1) + 1) if previous else 1,
        'answered_at': timezone.now().isoformat(),
    })
    ledger.sort(key=lambda e: e['ade_id'])
    _save_robustness(draft, ade_ledger=ledger)
    return draft
