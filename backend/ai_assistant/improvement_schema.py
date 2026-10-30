"""Scoped proposal/evaluation APIs reuse the existing explicit prompt activation workflow."""
import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError

from .models import (AIImprovementProposal, AIImprovementEvaluation, AIImprovementAssessment,
                     AIGenerationTask)
from .quality_schema import _scope, PromptVersionType
from .improvements import (create_proposal, start_suggestion, start_evaluation,
                           assess_evaluation, evaluation_ready)
from .prompt_registry import require_prompt_admin


class ImprovementCaseInput(graphene.InputObjectType):
    feedback_id = graphene.UUID(required=True)
    purpose = graphene.String(default_value='CORRECTION')
    required_text = graphene.List(graphene.NonNull(graphene.String), default_value=[])
    forbidden_text = graphene.List(graphene.NonNull(graphene.String), default_value=[])
    review_criteria = graphene.String(required=True)


class ImprovementAssessmentInput(graphene.InputObjectType):
    case_id = graphene.UUID(required=True)
    passed = graphene.Boolean(required=True)
    note = graphene.String(required=True)


class ImprovementAssessmentType(DjangoObjectType):
    class Meta:
        model = AIImprovementAssessment
        fields = ('id', 'cases', 'reviewer_username', 'created_at')


class ImprovementEvaluationType(DjangoObjectType):
    status = graphene.String()
    result_data = graphene.JSONString()
    prepared_evidence = graphene.JSONString()
    error_message = graphene.String()
    assessment = graphene.Field(ImprovementAssessmentType)

    class Meta:
        model = AIImprovementEvaluation
        fields = ('id', 'content_hash', 'base_fingerprint', 'created_at')

    def resolve_status(self, info):
        return self.task.status if self.task else ('COMPLETED' if hasattr(self, 'result') and hasattr(self, 'assessment') else 'UNAVAILABLE')

    def resolve_result_data(self, info):
        return self.result.data if hasattr(self, 'result') else None

    def resolve_prepared_evidence(self, info):
        return self.task.prompt_provenance if self.task else None

    def resolve_error_message(self, info):
        return self.task.error_message if self.task else ''

    def resolve_assessment(self, info):
        return self.assessment if hasattr(self, 'assessment') else None


class ImprovementProposalType(DjangoObjectType):
    version = graphene.Field(PromptVersionType)
    evaluations = graphene.List(ImprovementEvaluationType)
    evaluation_ready = graphene.Boolean()

    class Meta:
        model = AIImprovementProposal
        fields = ('id', 'evidence', 'cases', 'created_at')

    def resolve_version(self, info):
        return self.version

    def resolve_evaluations(self, info):
        return list(self.evaluations.select_related('task', 'result', 'assessment')[:20])

    def resolve_evaluation_ready(self, info):
        return evaluation_ready(self)


class ImprovementDraftTaskType(graphene.ObjectType):
    id = graphene.UUID()
    status = graphene.String()
    result_data = graphene.JSONString()
    error_message = graphene.String()


class Query(graphene.ObjectType):
    ai_improvement_proposals = graphene.List(ImprovementProposalType, organization_id=graphene.UUID(),
        installation=graphene.Boolean(default_value=False), language=graphene.String(default_value='*'))
    ai_improvement_draft_task = graphene.Field(ImprovementDraftTaskType, task_id=graphene.UUID(required=True))

    def resolve_ai_improvement_proposals(self, info, organization_id=None, installation=False, language='*'):
        scope = _scope(info.context.user, organization_id, installation)
        return list(AIImprovementProposal.objects.select_related('version__configuration', 'version__created_by', 'version__reviewed_by')
            .filter(version__configuration__organization_id=scope, version__configuration__language=language)[:50])

    def resolve_ai_improvement_draft_task(self, info, task_id):
        user = info.context.user
        task = AIGenerationTask.objects.filter(pk=task_id, task_type='DRAFT_PROMPT_IMPROVEMENT', user=user).first() if user.is_authenticated else None
        if not task or task.organization_id != user.organization_id:
            raise GraphQLError('AI improvement draft job not found.')
        require_prompt_admin(user, task.input_data.get('scope_id'))
        return ImprovementDraftTaskType(id=task.id, status=task.status, result_data=task.result_data, error_message=task.error_message)


class StartAIImprovementDraft(graphene.Mutation):
    class Arguments:
        organization_id = graphene.UUID()
        installation = graphene.Boolean(default_value=False)
        language = graphene.String(default_value='*')
        feedback_ids = graphene.List(graphene.NonNull(graphene.UUID), required=True)
        base_fingerprint = graphene.String(required=True)
    task_id = graphene.UUID()

    @staticmethod
    def mutate(root, info, feedback_ids, base_fingerprint, organization_id=None, installation=False, language='*'):
        scope = _scope(info.context.user, organization_id, installation)
        task = start_suggestion(info.context.user, organization_id=scope, language=language,
                                feedback_ids=feedback_ids, base_fingerprint=base_fingerprint)
        return StartAIImprovementDraft(task_id=task.id)


class CreateAIImprovementProposal(graphene.Mutation):
    class Arguments:
        organization_id = graphene.UUID()
        installation = graphene.Boolean(default_value=False)
        language = graphene.String(default_value='*')
        instructions = graphene.String(required=True)
        change_reason = graphene.String(required=True)
        base_fingerprint = graphene.String(required=True)
        cases = graphene.List(graphene.NonNull(ImprovementCaseInput), required=True)
    proposal = graphene.Field(ImprovementProposalType)

    @staticmethod
    def mutate(root, info, instructions, change_reason, base_fingerprint, cases, organization_id=None, installation=False, language='*'):
        scope = _scope(info.context.user, organization_id, installation)
        proposal = create_proposal(info.context.user, organization_id=scope, language=language, instructions=instructions,
            change_reason=change_reason, base_fingerprint=base_fingerprint, cases=[dict(item) for item in cases])
        return CreateAIImprovementProposal(proposal=proposal)


class StartAIImprovementEvaluation(graphene.Mutation):
    class Arguments:
        proposal_id = graphene.UUID(required=True)
    evaluation = graphene.Field(ImprovementEvaluationType)

    @staticmethod
    def mutate(root, info, proposal_id):
        return StartAIImprovementEvaluation(evaluation=start_evaluation(info.context.user, proposal_id))


class AssessAIImprovementEvaluation(graphene.Mutation):
    class Arguments:
        evaluation_id = graphene.UUID(required=True)
        cases = graphene.List(graphene.NonNull(ImprovementAssessmentInput), required=True)
    evaluation = graphene.Field(ImprovementEvaluationType)

    @staticmethod
    def mutate(root, info, evaluation_id, cases):
        return AssessAIImprovementEvaluation(evaluation=assess_evaluation(info.context.user, evaluation_id, [dict(item) for item in cases]))


class Mutation(graphene.ObjectType):
    start_ai_improvement_draft = StartAIImprovementDraft.Field()
    create_ai_improvement_proposal = CreateAIImprovementProposal.Field()
    start_ai_improvement_evaluation = StartAIImprovementEvaluation.Field()
    assess_ai_improvement_evaluation = AssessAIImprovementEvaluation.Field()
