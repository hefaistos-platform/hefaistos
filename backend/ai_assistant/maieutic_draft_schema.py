"""GraphQL for Maieutic 3.0 sessions. Visibility and locking live in maieutic_lifecycle."""

import graphene
from graphene.types.generic import GenericScalar
from graphql import GraphQLError

from identity.decorators import Roles, role_required

from . import maieutic_lifecycle as lifecycle
from . import maieutic_planner, maieutic_questioner, maieutic_questions
from .maieutic_lifecycle import MaieuticError
from .maieutic_models import MaieuticDraft


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except MaieuticError as exc:
        raise GraphQLError(str(exc))


def _user(info):
    user = info.context.user
    if user.is_anonymous:
        raise GraphQLError('Authentication required')
    return user


class MaieuticDraftType(graphene.ObjectType):
    """Author view. Includes the spec. Never returned to anyone but the author."""
    id = graphene.UUID()
    name = graphene.String()
    status = graphene.String()
    current_stage = graphene.Int()
    spec = GenericScalar()
    outcome = graphene.String()
    created_workbench_id = graphene.UUID()
    finished_at = graphene.DateTime()
    allow_remote_pull = graphene.Boolean()
    tlp_classification = graphene.String()
    imported_from = graphene.String()
    is_locked = graphene.Boolean()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    def resolve_created_workbench_id(self, info):
        return self.created_workbench_id

    def resolve_is_locked(self, info):
        return self.status == MaieuticDraft.Status.FINISHED


class MaieuticAdminRowType(graphene.ObjectType):
    """Metadata only (spec 9b). Deliberately has no spec, answers or transcript field."""
    id = graphene.UUID()
    name = graphene.String()
    author_username = graphene.String()
    organization_name = graphene.String()
    status = graphene.String()
    outcome = graphene.String()
    current_stage = graphene.Int()
    tlp_classification = graphene.String()
    allow_remote_pull = graphene.Boolean()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()
    finished_at = graphene.DateTime()

    def resolve_author_username(self, info):
        return self.author.username if self.author else None

    def resolve_organization_name(self, info):
        return self.organization.name


class AdeQuestionType(graphene.ObjectType):
    """One planned ADE question for a session, rendered with the user's own design wording."""
    ade_id = graphene.String()
    question_id = graphene.String()
    version = graphene.Int()
    trigger_reason = graphene.String()
    design_refs = graphene.List(graphene.String)
    question_text = graphene.String()
    why_we_ask = graphene.String()
    weak_answer = graphene.String()
    strong_answer = graphene.String()
    glossary = GenericScalar()
    hint_rungs_used = graphene.Int()
    hint_rungs_total = graphene.Int()
    state = graphene.String(description='OPEN, ANSWERED or STALE (answered against an older question version)')
    ledger_entry = GenericScalar()


class MaieuticAdePlanType(graphene.ObjectType):
    items = graphene.List(AdeQuestionType)
    needs_question = graphene.List(graphene.String, description='Upstream ADE subcategories with no question file yet')
    ade_snapshot_id = graphene.UUID()
    open_count = graphene.Int()


def _build_plan(draft):
    spec = draft.spec or {}
    answered = maieutic_planner.ledger_by_ade(spec)
    help_used = (spec.get('robustness') or {}).get('ade_help') or {}
    items = []
    for item in maieutic_planner.plan(spec, expert_all=lifecycle.is_expert(spec)):
        q = item['question']
        entry = answered.get(item['ade_id'])
        if entry is None or not entry.get('disposition'):
            state = 'OPEN'
        elif entry.get('question_version') != q['version']:
            state = 'STALE'
        else:
            state = 'ANSWERED'
        items.append(AdeQuestionType(
            ade_id=item['ade_id'], question_id=q['id'], version=q['version'],
            trigger_reason=item['trigger_reason'], design_refs=item['design_refs'],
            question_text=maieutic_questions.render_text(q['question'], q, item['values']),
            why_we_ask=maieutic_questions.render_text(q['why_we_ask'], q, item['values']),
            weak_answer=q['weak_answer'], strong_answer=q['strong_answer'],
            glossary=q.get('glossary') or [],
            hint_rungs_used=int(help_used.get(item['ade_id'], 0)), hint_rungs_total=3,
            state=state, ledger_entry=entry,
        ))
    snapshot = draft.ade_snapshot or lifecycle._active_ade_snapshot()
    return MaieuticAdePlanType(
        items=items,
        needs_question=maieutic_planner.questions_missing_for_snapshot(snapshot),
        ade_snapshot_id=snapshot.id if snapshot else None,
        open_count=sum(1 for i in items if i.state != 'ANSWERED'),
    )


class MaieuticLogFieldType(graphene.ObjectType):
    log_source_id = graphene.UUID()
    standard_name = graphene.String()
    siem_field_name = graphene.String()


def _log_fields(log_source_ids):
    from log_catalog.models import LogField
    ids = list(log_source_ids or [])[:50]
    rows = LogField.objects.filter(log_source_id__in=ids).order_by('log_source_id', 'standard_name')
    return [MaieuticLogFieldType(log_source_id=r.log_source_id, standard_name=r.standard_name,
                                 siem_field_name=r.siem_field_name) for r in rows]


class Query(graphene.ObjectType):
    maieutic_drafts = graphene.List(MaieuticDraftType, status=graphene.String())
    maieutic_draft = graphene.Field(MaieuticDraftType, id=graphene.UUID(required=True))
    maieutic_admin_index = graphene.List(MaieuticAdminRowType)
    maieutic_log_source_fields = graphene.List(
        MaieuticLogFieldType, log_source_ids=graphene.List(graphene.UUID, required=True))
    maieutic_ade_plan = graphene.Field(MaieuticAdePlanType, draft_id=graphene.UUID(required=True))

    @role_required([Roles.ADMIN, Roles.ANALYST])
    def resolve_maieutic_drafts(self, info, status=None):
        qs = lifecycle.list_visible_drafts(_user(info))
        if status:
            qs = qs.filter(status=status)
        return qs

    @role_required([Roles.ADMIN, Roles.ANALYST])
    def resolve_maieutic_draft(self, info, id):
        return lifecycle.get_visible_draft(_user(info), id)

    @role_required([Roles.ADMIN, Roles.ANALYST])
    def resolve_maieutic_log_source_fields(self, info, log_source_ids):
        return _log_fields(log_source_ids)

    @role_required([Roles.ADMIN, Roles.ANALYST])
    def resolve_maieutic_ade_plan(self, info, draft_id):
        draft = lifecycle.get_visible_draft(_user(info), draft_id)
        return _build_plan(draft) if draft else None

    @role_required([Roles.ADMIN])
    def resolve_maieutic_admin_index(self, info):
        return _guard(lifecycle.admin_index, _user(info))


class CreateMaieuticDraft(graphene.Mutation):
    class Arguments:
        name = graphene.String()
        tlp_classification = graphene.String()

    draft = graphene.Field(MaieuticDraftType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, name=None, tlp_classification=None):
        return CreateMaieuticDraft(draft=lifecycle.create_draft(
            _user(info), name=name, tlp=tlp_classification))


class UpdateMaieuticDraft(graphene.Mutation):
    class Arguments:
        draft_id = graphene.UUID(required=True)
        name = graphene.String()
        current_stage = graphene.Int()
        spec_patch = GenericScalar()
        tlp_classification = graphene.String()
        challenge_level = graphene.String()

    draft = graphene.Field(MaieuticDraftType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id, name=None, current_stage=None, spec_patch=None, tlp_classification=None,
               challenge_level=None):
        return UpdateMaieuticDraft(draft=_guard(
            lifecycle.update_draft, draft_id, _user(info), name=name, current_stage=current_stage,
            spec_patch=spec_patch, tlp=tlp_classification, challenge_level=challenge_level))


class SetMaieuticDraftSharing(graphene.Mutation):
    class Arguments:
        draft_id = graphene.UUID(required=True)
        allow_remote_pull = graphene.Boolean(required=True)

    draft = graphene.Field(MaieuticDraftType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id, allow_remote_pull):
        return SetMaieuticDraftSharing(draft=_guard(
            lifecycle.set_sharing, draft_id, _user(info), allow=allow_remote_pull))


class DeleteMaieuticDraft(graphene.Mutation):
    class Arguments:
        draft_id = graphene.UUID(required=True)

    ok = graphene.Boolean()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id):
        _guard(lifecycle.delete_draft, draft_id, _user(info))
        return DeleteMaieuticDraft(ok=True)


class RevealMaieuticHint(graphene.Mutation):
    class Arguments:
        draft_id = graphene.UUID(required=True)
        ade_id = graphene.String(required=True)
        rung = graphene.Int(required=True)

    hint = graphene.String()
    rung = graphene.Int()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id, ade_id, rung):
        text = _guard(lifecycle.reveal_hint, draft_id, _user(info), ade_id=ade_id, rung=rung)
        return RevealMaieuticHint(hint=text, rung=rung)


def _user_ai_settings(user):
    from .models import UserAISettings
    return UserAISettings.objects.filter(user=user).first()


class AnswerMaieuticAdeQuestion(graphene.Mutation):
    """Stores the user's own answer. The AI check is advisory: it can ask a follow-up, never blocks."""
    class Arguments:
        draft_id = graphene.UUID(required=True)
        ade_id = graphene.String(required=True)
        answer_text = graphene.String()
        disposition = graphene.String(required=True)
        reference = graphene.String()
        design_ref = graphene.String()

    ledger_entry = GenericScalar()
    evaluator_flag = graphene.String()
    evaluator_source = graphene.String()
    follow_up = graphene.String()
    open_count = graphene.Int()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id, ade_id, disposition, answer_text='', reference=None, design_ref=None):
        user = _user(info)
        draft = lifecycle.get_visible_draft(user, draft_id)
        if draft is None:
            raise GraphQLError('Maieutic session not found.')
        if draft.status == MaieuticDraft.Status.FINISHED:
            raise GraphQLError('This Maieutic session is finished and locked. Edit the Workbench instead.')
        try:
            disposition, answer_text, reference = maieutic_questioner.validate_disposition(
                disposition, answer_text, reference)
        except ValueError as exc:
            raise GraphQLError(str(exc))
        item = next((i for i in maieutic_planner.plan(draft.spec, expert_all=lifecycle.is_expert(draft.spec))
                     if i['ade_id'] == ade_id), None)
        if item is None:
            raise GraphQLError('That question is not part of this session.')
        q = item['question']
        evaluation = maieutic_questioner.evaluate_answer(
            question=q,
            question_text=maieutic_questions.render_text(q['question'], q, item['values']),
            answer_text=answer_text, disposition=disposition, spec=draft.spec,
            user_settings=_user_ai_settings(user), organization_id=user.organization_id,
        )
        updated = _guard(
            lifecycle.record_ade_answer, draft_id, user, ade_id=ade_id, answer_text=answer_text,
            disposition=disposition, reference=reference, design_ref=design_ref, evaluation=evaluation)
        entry = maieutic_planner.ledger_by_ade(updated.spec).get(ade_id)
        return AnswerMaieuticAdeQuestion(
            ledger_entry=entry, evaluator_flag=evaluation['flag'], evaluator_source=evaluation['source'],
            follow_up=evaluation['follow_up'], open_count=_build_plan(updated).open_count)


class Mutation(graphene.ObjectType):
    create_maieutic_draft = CreateMaieuticDraft.Field()
    update_maieutic_draft = UpdateMaieuticDraft.Field()
    set_maieutic_draft_sharing = SetMaieuticDraftSharing.Field()
    delete_maieutic_draft = DeleteMaieuticDraft.Field()
    reveal_maieutic_hint = RevealMaieuticHint.Field()
    answer_maieutic_ade_question = AnswerMaieuticAdeQuestion.Field()
