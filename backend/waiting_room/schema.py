import uuid

import graphene
from django.db import transaction
from django.utils import timezone
from graphene_django import DjangoObjectType
from graphql import GraphQLError

from identity.decorators import Roles, role_required
from organizations.models import MISPInstance
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph

from .misp import import_waiting_cases_from_misp
from .models import WaitingCase, queue_waiting_case_enrichment


def _normalized_ttp_list(raw_values) -> list[str]:
    return [str(t).strip().upper() for t in (raw_values or []) if str(t).strip()]


class WaitingCaseType(DjangoObjectType):
    mapped_ttps = graphene.List(graphene.String)

    class Meta:
        model = WaitingCase
        fields = (
            'id',
            'organization',
            'created_by',
            'source_type',
            'misp_instance',
            'misp_event_id',
            'title',
            'short_description',
            'detection_objective',
            'mapped_ttps',
            'estimated_detection_complexity',
            'raw_payload',
            'status',
            'enrichment_error',
            'promoted_graph',
            'promoted_at',
            'created_at',
            'updated_at',
        )

    def resolve_mapped_ttps(self, info):
        return self.mapped_ttps or []


class WaitingCaseInput(graphene.InputObjectType):
    title = graphene.String(required=True)
    short_description = graphene.String(required=True)
    detection_objective = graphene.String(required=False)
    mapped_ttps = graphene.List(graphene.String, required=False)
    estimated_detection_complexity = graphene.String(required=False)


class Query(graphene.ObjectType):
    waiting_cases = graphene.List(WaitingCaseType)
    waiting_case = graphene.Field(WaitingCaseType, id=graphene.UUID(required=True))

    def resolve_waiting_cases(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        return WaitingCase.objects.filter(organization=user.organization).select_related(
            'created_by', 'misp_instance', 'promoted_graph'
        )

    def resolve_waiting_case(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        try:
            return WaitingCase.objects.select_related(
                'created_by', 'misp_instance', 'promoted_graph'
            ).get(pk=id, organization=user.organization)
        except WaitingCase.DoesNotExist:
            raise GraphQLError('Waiting case not found')


class CreateWaitingCase(graphene.Mutation):
    class Arguments:
        input = WaitingCaseInput(required=True)
        auto_enrich = graphene.Boolean(required=False, default_value=False)

    waiting_case = graphene.Field(WaitingCaseType)

    @staticmethod
    @role_required([Roles.REVIEWER, Roles.ADMIN])
    @transaction.atomic
    def mutate(root, info, input, auto_enrich=False):
        user = info.context.user
        title = (input.title or '').strip()
        short_description = (input.short_description or '').strip()

        if not title:
            raise GraphQLError('title is required')
        if not short_description:
            raise GraphQLError('short description is required')

        waiting_case = WaitingCase.objects.create(
            organization=user.organization,
            created_by=user,
            source_type=WaitingCase.SourceType.MANUAL,
            title=title,
            short_description=short_description,
            detection_objective=(getattr(input, 'detection_objective', None) or '').strip(),
            mapped_ttps=_normalized_ttp_list(getattr(input, 'mapped_ttps', None)),
            estimated_detection_complexity=(getattr(input, 'estimated_detection_complexity', None) or '').strip(),
            status=WaitingCase.LifecycleStatus.NEW,
        )

        if auto_enrich:
            queue_waiting_case_enrichment(waiting_case, user)

        return CreateWaitingCase(waiting_case=waiting_case)


class UpdateWaitingCase(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)
        input = WaitingCaseInput(required=True)
        auto_enrich = graphene.Boolean(required=False, default_value=False)

    waiting_case = graphene.Field(WaitingCaseType)

    @staticmethod
    @role_required([Roles.REVIEWER, Roles.ADMIN])
    @transaction.atomic
    def mutate(root, info, id, input, auto_enrich=False):
        user = info.context.user
        try:
            waiting_case = WaitingCase.objects.get(pk=id, organization=user.organization)
        except WaitingCase.DoesNotExist:
            raise GraphQLError('Waiting case not found')

        title = (input.title or '').strip()
        short_description = (input.short_description or '').strip()
        if not title:
            raise GraphQLError('title is required')
        if not short_description:
            raise GraphQLError('short description is required')

        waiting_case.title = title
        waiting_case.short_description = short_description
        waiting_case.detection_objective = (getattr(input, 'detection_objective', None) or '').strip()
        waiting_case.mapped_ttps = _normalized_ttp_list(getattr(input, 'mapped_ttps', None))
        waiting_case.estimated_detection_complexity = (
            getattr(input, 'estimated_detection_complexity', None) or ''
        ).strip()
        if waiting_case.status == WaitingCase.LifecycleStatus.FAILED:
            waiting_case.status = WaitingCase.LifecycleStatus.NEW
            waiting_case.enrichment_error = ''
        waiting_case.save(
            update_fields=[
                'title',
                'short_description',
                'detection_objective',
                'mapped_ttps',
                'estimated_detection_complexity',
                'status',
                'enrichment_error',
                'updated_at',
            ]
        )

        if auto_enrich:
            queue_waiting_case_enrichment(waiting_case, user)

        return UpdateWaitingCase(waiting_case=waiting_case)


class ImportWaitingCasesFromMISP(graphene.Mutation):
    class Arguments:
        misp_instance_id = graphene.UUID(required=True)
        event_id = graphene.String(required=False)
        tag = graphene.String(required=False)
        limit = graphene.Int(required=False, default_value=25)
        run_ai_enrichment = graphene.Boolean(required=False, default_value=False)

    success = graphene.Boolean()
    message = graphene.String()
    imported_count = graphene.Int()
    skipped_count = graphene.Int()
    waiting_cases = graphene.List(WaitingCaseType)

    @staticmethod
    @role_required([Roles.REVIEWER, Roles.ADMIN])
    @transaction.atomic
    def mutate(root, info, misp_instance_id, event_id=None, tag=None, limit=25, run_ai_enrichment=False):
        user = info.context.user
        try:
            instance = MISPInstance.objects.get(pk=misp_instance_id, organization=user.organization)
        except MISPInstance.DoesNotExist:
            raise GraphQLError('MISP instance not found')

        try:
            result = import_waiting_cases_from_misp(
                instance=instance,
                user=user,
                event_id=event_id,
                tag=tag,
                limit=limit,
                run_ai_enrichment=run_ai_enrichment,
            )
        except Exception as exc:
            raise GraphQLError(f'Failed to import from MISP: {exc}')

        return ImportWaitingCasesFromMISP(
            success=True,
            message=f"Imported {result['imported_count']} waiting cases from MISP.",
            imported_count=result['imported_count'],
            skipped_count=result['skipped_count'],
            waiting_cases=result['waiting_cases'],
        )


class PromoteWaitingCaseToWorkbench(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)
        title = graphene.String(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    waiting_case = graphene.Field(WaitingCaseType)
    workbench = graphene.Field('playbooks.schema.PlaybookGraphType')
    graph = graphene.Field(
        'playbooks.schema.PlaybookGraphType',
        deprecation_reason='Use workbench field instead. graph will be removed in a future release.',
    )

    @staticmethod
    @role_required([Roles.ANALYST])
    @transaction.atomic
    def mutate(root, info, id, title=None):
        user = info.context.user
        try:
            waiting_case = WaitingCase.objects.select_for_update().get(pk=id, organization=user.organization)
        except WaitingCase.DoesNotExist:
            raise GraphQLError('Waiting case not found')

        if waiting_case.status == WaitingCase.LifecycleStatus.PROMOTED and waiting_case.promoted_graph_id:
            return PromoteWaitingCaseToWorkbench(
                success=True,
                message='Waiting case already promoted.',
                waiting_case=waiting_case,
                workbench=waiting_case.promoted_graph,
                graph=waiting_case.promoted_graph,
            )

        final_title = (title or waiting_case.title or '').strip()
        if not final_title:
            raise GraphQLError('title is required')

        if not (waiting_case.short_description or '').strip():
            raise GraphQLError('short description is required before promotion')

        workbench = PlaybookGraph.objects.create(
            organization=user.organization,
            author=user,
            title=final_title,
            goal=waiting_case.short_description,
            technical_context=waiting_case.detection_objective,
            blind_spots='',
            false_positives='',
            status='IDEA',
        )
        workbench.title = PlaybookGraph.compose_title_with_custom_id(final_title, workbench.custom_id)
        workbench.save(update_fields=['title', 'updated_at'])

        first_ttp = None
        for ttp in waiting_case.mapped_ttps or []:
            ttp = str(ttp).strip().upper()
            if ttp:
                first_ttp = ttp
                break

        if first_ttp:
            technique = MitreAttackTechnique.objects.filter(technique_id__iexact=first_ttp).first()
            if technique:
                workbench.mitre_technique = technique
                workbench.save(update_fields=['mitre_technique', 'updated_at'])

        waiting_case.promoted_graph = workbench
        waiting_case.promoted_at = timezone.now()
        waiting_case.status = WaitingCase.LifecycleStatus.PROMOTED
        waiting_case.save(update_fields=['promoted_graph', 'promoted_at', 'status', 'updated_at'])

        return PromoteWaitingCaseToWorkbench(
            success=True,
            message='Waiting case promoted to Workbench.',
            waiting_case=waiting_case,
            workbench=workbench,
            graph=workbench,
        )


class DeleteWaitingCase(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @transaction.atomic
    def mutate(root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')

        try:
            waiting_case = WaitingCase.objects.select_related('created_by').get(pk=id, organization=user.organization)
        except WaitingCase.DoesNotExist:
            raise GraphQLError('Waiting case not found')

        is_admin = user.role == Roles.ADMIN
        is_superuser = bool(user.is_superuser)
        is_author = waiting_case.created_by_id == user.id

        if not (is_author or is_admin or is_superuser):
            raise GraphQLError('Only the case author or an admin can delete this waiting case.')

        waiting_case.delete()
        return DeleteWaitingCase(success=True, message='Waiting case deleted.')


class Mutation(graphene.ObjectType):
    create_waiting_case = CreateWaitingCase.Field()
    update_waiting_case = UpdateWaitingCase.Field()
    import_waiting_cases_from_misp = ImportWaitingCasesFromMISP.Field()
    promote_waiting_case_to_workbench = PromoteWaitingCaseToWorkbench.Field()
    delete_waiting_case = DeleteWaitingCase.Field()
