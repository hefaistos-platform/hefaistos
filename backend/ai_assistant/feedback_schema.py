"""Organization-scoped correction submission and admin review APIs."""
import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError

from .models import AIRuleFeedback, AIFeedbackAuditEvent
from .prompt_registry import require_prompt_admin
from .rule_feedback import (SUPPORTED_FORMATS, dismiss_feedback, feedback_payload, require_writer,
                            review_feedback, submit_feedback)


class AIRuleAttributionInput(graphene.InputObjectType):
    output_format = graphene.String(required=True)
    generation_artifact_id = graphene.UUID()
    detach = graphene.Boolean(default_value=False)


class AICorrectionIssueInput(graphene.InputObjectType):
    category = graphene.String(required=True)
    explanation = graphene.String(required=True)
    resolution = graphene.String(required=True)
    before = graphene.String()
    after = graphene.String()


class FeedbackAuditType(DjangoObjectType):
    class Meta:
        model = AIFeedbackAuditEvent
        fields = ('id', 'actor_username', 'action', 'reason', 'created_at')


class RuleFeedbackType(DjangoObjectType):
    rule_title = graphene.String()
    output_format = graphene.String()
    revision_number = graphene.Int()
    correction_author = graphene.String()
    variant = graphene.String()
    before = graphene.String()
    after = graphene.String()
    diff = graphene.String()
    prompt_provenance = graphene.JSONString()
    machine_readable = graphene.JSONString()
    events = graphene.List(FeedbackAuditType)

    class Meta:
        model = AIRuleFeedback
        fields = ('id', 'status', 'issues', 'verification', 'verification_evidence', 'created_at',
                  'submitted_username', 'submitted_at', 'reviewed_username', 'reviewed_at', 'review_note', 'root_cause')
        convert_choices_to_enum = False

    def resolve_rule_title(self, info):
        return self.revision.rule_title

    def resolve_output_format(self, info):
        return self.revision.output_format

    def resolve_revision_number(self, info):
        return self.revision.number

    def resolve_correction_author(self, info):
        return self.revision.author_username

    def resolve_variant(self, info):
        return self.revision.generation_artifact.variant

    def resolve_before(self, info):
        return self.revision.generation_artifact.content

    def resolve_after(self, info):
        return self.revision.editor_content

    def resolve_diff(self, info):
        return feedback_payload(self)['correction']['diff']

    def resolve_prompt_provenance(self, info):
        return self.revision.generation_artifact.prompt_provenance

    def resolve_machine_readable(self, info):
        return feedback_payload(self)

    def resolve_events(self, info):
        return self.events.all()


def _feedback_queryset():
    return AIRuleFeedback.objects.select_related('revision__generation_artifact').prefetch_related('events')


class Query(graphene.ObjectType):
    ai_rule_correction_candidates = graphene.List(RuleFeedbackType, playbook_id=graphene.UUID(),
                                                  rule_id=graphene.ID(), limit=graphene.Int(default_value=50))
    ai_quality_feedback = graphene.List(RuleFeedbackType, organization_id=graphene.UUID(),
        all_organizations=graphene.Boolean(default_value=False), status=graphene.String(default_value='SUBMITTED'),
        output_format=graphene.String(), limit=graphene.Int(default_value=100))

    def resolve_ai_rule_correction_candidates(self, info, playbook_id=None, rule_id=None, limit=50):
        user = info.context.user
        require_writer(user)
        if not rule_id and not playbook_id:
            return []
        qs = _feedback_queryset().filter(organization_id=user.organization_id, status='CANDIDATE')
        if not (user.is_superuser or user.role == 'ADMIN'):
            qs = qs.filter(revision__created_by=user)
        if rule_id:
            qs = qs.filter(revision__rule_id=rule_id)
        if playbook_id:
            qs = qs.filter(revision__workbench_id=str(playbook_id))
        return list(qs[:max(1, min(limit or 50, 100))])

    def resolve_ai_quality_feedback(self, info, organization_id=None, all_organizations=False,
                                   status='SUBMITTED', output_format=None, limit=100):
        user = info.context.user
        scope = None if all_organizations else (organization_id or getattr(user, 'organization_id', None))
        require_prompt_admin(user, scope)
        if scope is None and not all_organizations:
            raise GraphQLError('Select an organization or all organizations.')
        qs = _feedback_queryset()
        if scope is not None:
            qs = qs.filter(organization_id=scope)
        if status:
            if status not in AIRuleFeedback.Status.values:
                raise GraphQLError('Unknown feedback status.')
            qs = qs.filter(status=status)
        if output_format and output_format != '*':
            if output_format not in SUPPORTED_FORMATS:
                raise GraphQLError('Unsupported feedback format.')
            qs = qs.filter(revision__output_format=output_format)
        return list(qs[:max(1, min(limit or 100, 200))])


class SubmitRuleCorrectionFeedback(graphene.Mutation):
    class Arguments:
        feedback_id = graphene.UUID(required=True)
        issues = graphene.List(graphene.NonNull(AICorrectionIssueInput), required=True)
        verification = graphene.String(required=True)
        verification_evidence = graphene.String(default_value='')
    feedback = graphene.Field(RuleFeedbackType)

    @staticmethod
    def mutate(root, info, feedback_id, issues, verification, verification_evidence=''):
        feedback = submit_feedback(info.context.user, feedback_id, [dict(issue) for issue in issues],
                                   verification, verification_evidence)
        return SubmitRuleCorrectionFeedback(feedback=feedback)


class DismissRuleCorrectionFeedback(graphene.Mutation):
    class Arguments:
        feedback_id = graphene.UUID(required=True)
        reason = graphene.String(required=True)
    feedback = graphene.Field(RuleFeedbackType)

    @staticmethod
    def mutate(root, info, feedback_id, reason):
        return DismissRuleCorrectionFeedback(feedback=dismiss_feedback(info.context.user, feedback_id, reason))


class ReviewRuleCorrectionFeedback(graphene.Mutation):
    class Arguments:
        feedback_id = graphene.UUID(required=True)
        accept = graphene.Boolean(required=True)
        root_cause = graphene.String(required=True)
        review_note = graphene.String(required=True)
    feedback = graphene.Field(RuleFeedbackType)

    @staticmethod
    def mutate(root, info, feedback_id, accept, root_cause, review_note):
        return ReviewRuleCorrectionFeedback(feedback=review_feedback(info.context.user, feedback_id,
                                            accept, root_cause, review_note))


class Mutation(graphene.ObjectType):
    submit_rule_correction_feedback = SubmitRuleCorrectionFeedback.Field()
    dismiss_rule_correction_feedback = DismissRuleCorrectionFeedback.Field()
    review_rule_correction_feedback = ReviewRuleCorrectionFeedback.Field()
