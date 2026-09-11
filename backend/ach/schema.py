import graphene
from graphene_django import DjangoObjectType
from django.utils import timezone
from identity.decorators import role_required, Roles, is_bot_auditor_user
from .models import ACHAnalysis, Hypothesis, Evidence, MatrixCell, ACHTemplate
from .engine import ACHScoringEngine
from .ai import ACHGenerator
from ai_assistant.models import UserAISettings
from ai_assistant.schema import UserAISettingsType as AIUserSettingsType
from data_catalog.models import DataSource
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph
from playbooks.schema import PlaybookGraphType


def generate_copy_title(base_title: str, existing_titles) -> str:
    """Return a unique COPY title with numbered suffixes."""
    suffix_base = f"{base_title} - COPY"
    if suffix_base not in existing_titles:
        return suffix_base
    counter = 1
    while True:
        candidate = f"{suffix_base}{counter}"
        if candidate not in existing_titles:
            return candidate
        counter += 1

class ACHTemplateType(DjangoObjectType):
    class Meta:
        model = ACHTemplate
        fields = "__all__"

class MitreAttackTechniqueType(DjangoObjectType):
    id = graphene.UUID(source='pk')
    
    class Meta:
        model = MitreAttackTechnique
        fields = "__all__"

class BiasCheckResultType(graphene.ObjectType):
    is_biased = graphene.Boolean()
    warning_message = graphene.String()
    reasoning = graphene.String()

class GeneratedEvidenceType(graphene.ObjectType):
    content = graphene.String()
    credibility = graphene.String()

class GeneratedACHContentType(graphene.ObjectType):
    hypotheses = graphene.List(graphene.String)
    evidence = graphene.List(GeneratedEvidenceType)

class EvidenceInput(graphene.InputObjectType):
    content = graphene.String(required=True)
    credibility = graphene.String()

class ACHAnalysisType(DjangoObjectType):
    class Meta:
        model = ACHAnalysis
        fields = "__all__"
    
    scores = graphene.JSONString()
    matrix_cells = graphene.List(lambda: MatrixCellType)

    def resolve_scores(self, info):
        return ACHScoringEngine.calculate_scores(self)
    
    def resolve_matrix_cells(self, info):
        # Get all matrix cells for this analysis through hypotheses and evidence
        return MatrixCell.objects.filter(
            hypothesis__analysis=self
        ).select_related('hypothesis', 'evidence')

class HypothesisType(DjangoObjectType):
    category = graphene.String()
    visual_bar = graphene.String()
    score = graphene.Int()
    similar_workbench_count = graphene.Int()
    similar_workbenches = graphene.List(PlaybookGraphType)
    
    class Meta:
        model = Hypothesis
        fields = "__all__"
    
    def _get_all_scores(self):
        """Return cached scores dict for the parent analysis, computing once per analysis instance."""
        if not hasattr(self.analysis, '_all_scores_cache'):
            self.analysis._all_scores_cache = ACHScoringEngine.calculate_scores(self.analysis)
        return self.analysis._all_scores_cache

    def resolve_score(self, info):
        """Calculate the score for this hypothesis"""
        if not hasattr(self, '_score_cache'):
            self._score_cache = self._get_all_scores().get(str(self.id), 0)
        return self._score_cache
    
    def resolve_category(self, info):
        """Determine category: MOST_LIKELY, PLAUSIBLE, or ELIMINATED"""
        score = self.resolve_score(info)
        return ACHScoringEngine.get_category(score)
    
    def resolve_visual_bar(self, info):
        """Generate visual bar representation of score"""
        score = self.resolve_score(info)
        # Get max score from all hypotheses in analysis for proportion
        all_scores = self._get_all_scores()
        max_score = max(all_scores.values()) if all_scores else 30
        return ACHScoringEngine.get_visual_bar(score, max_score)

    def resolve_similar_workbench_count(self, info):
        user = info.context.user
        if user.is_anonymous or self.analysis.owner_id != getattr(user, 'id', None):
            return 0
        if not self.mitre_technique_id:
            return 0
        return PlaybookGraph.objects.filter(
            organization=user.organization,
            mitre_technique_id=self.mitre_technique_id,
        ).count()

    def resolve_similar_workbenches(self, info):
        user = info.context.user
        if user.is_anonymous or self.analysis.owner_id != getattr(user, 'id', None):
            return []
        if not self.mitre_technique_id:
            return []
        return PlaybookGraph.objects.filter(
            organization=user.organization,
            mitre_technique_id=self.mitre_technique_id,
        ).order_by('-updated_at')[:25]

class EvidenceType(DjangoObjectType):
    class Meta:
        model = Evidence
        fields = "__all__"

class MatrixCellType(DjangoObjectType):
    class Meta:
        model = MatrixCell
        fields = "__all__"

class CreateACHAnalysis(graphene.Mutation):
    class Arguments:
        title = graphene.String(required=True)
        description = graphene.String()

    analysis = graphene.Field(ACHAnalysisType)

    def mutate(self, info, title, description=""):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        analysis = ACHAnalysis.objects.create(
            title=title,
            description=description,
            owner=user
        )
        return CreateACHAnalysis(analysis=analysis)

class AddHypothesis(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)
        content = graphene.String(required=True)
        mitre_technique_id = graphene.UUID()

    hypothesis = graphene.Field(HypothesisType)

    def mutate(self, info, analysis_id, content, mitre_technique_id=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            analysis = ACHAnalysis.objects.get(id=analysis_id, owner=user)
        except ACHAnalysis.DoesNotExist:
            raise Exception("Analysis not found")

        ttp = None
        if mitre_technique_id:
            try:
                ttp = MitreAttackTechnique.objects.get(id=mitre_technique_id)
            except MitreAttackTechnique.DoesNotExist:
                raise Exception("MITRE ATT&CK Technique not found")

        hypothesis = Hypothesis.objects.create(analysis=analysis, content=content, mitre_technique=ttp)
        return AddHypothesis(hypothesis=hypothesis)

class AddEvidence(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)
        content = graphene.String(required=True)
        credibility = graphene.String()
        data_source_id = graphene.ID()
        log_reference = graphene.String()

    evidence = graphene.Field(EvidenceType)

    def mutate(self, info, analysis_id, content, credibility='MEDIUM', data_source_id=None, log_reference=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            analysis = ACHAnalysis.objects.get(id=analysis_id, owner=user)
        except ACHAnalysis.DoesNotExist:
            raise Exception("Analysis not found")

        ds = None
        if data_source_id:
            try:
                ds = DataSource.objects.get(id=data_source_id)
            except DataSource.DoesNotExist:
                pass

        evidence = Evidence.objects.create(
            analysis=analysis, 
            content=content, 
            credibility=credibility,
            data_source=ds,
            log_reference=log_reference or ""
        )
        return AddEvidence(evidence=evidence)

class UpdateHypothesis(graphene.Mutation):
    class Arguments:
        hypothesis_id = graphene.ID(required=True)
        content = graphene.String(required=True)
        mitre_technique_id = graphene.UUID(required=False)

    hypothesis = graphene.Field(HypothesisType)

    def mutate(self, info, hypothesis_id, content, mitre_technique_id=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            hypothesis = Hypothesis.objects.get(id=hypothesis_id, analysis__owner=user)
        except Hypothesis.DoesNotExist:
            raise Exception("Hypothesis not found or access denied")

        hypothesis.content = content
        if mitre_technique_id is not None:
            if mitre_technique_id == "":
                hypothesis.mitre_technique = None
            else:
                try:
                    mt = MitreAttackTechnique.objects.get(id=mitre_technique_id)
                except MitreAttackTechnique.DoesNotExist:
                    raise Exception("MITRE technique not found")
                hypothesis.mitre_technique = mt
        hypothesis.save()
        return UpdateHypothesis(hypothesis=hypothesis)

class DeleteHypothesis(graphene.Mutation):
    class Arguments:
        hypothesis_id = graphene.ID(required=True)

    ok = graphene.Boolean()

    def mutate(self, info, hypothesis_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            hypothesis_filters = {"id": hypothesis_id}
            if not user.is_superuser:
                hypothesis_filters["analysis__owner"] = user
            hypothesis = Hypothesis.objects.get(**hypothesis_filters)
        except Hypothesis.DoesNotExist:
            raise Exception("Hypothesis not found or access denied")

        hypothesis.delete()
        return DeleteHypothesis(ok=True)

class UpdateEvidence(graphene.Mutation):
    class Arguments:
        evidence_id = graphene.ID(required=True)
        content = graphene.String(required=True)
        credibility = graphene.String()
        data_source_id = graphene.ID()
        log_reference = graphene.String()

    evidence = graphene.Field(EvidenceType)

    def mutate(self, info, evidence_id, content, credibility=None, data_source_id=None, log_reference=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            evidence = Evidence.objects.get(id=evidence_id, analysis__owner=user)
        except Evidence.DoesNotExist:
            raise Exception("Evidence not found or access denied")

        evidence.content = content
        if credibility is not None:
            evidence.credibility = credibility
        if log_reference is not None:
            evidence.log_reference = log_reference
        
        if data_source_id:
            try:
                evidence.data_source = DataSource.objects.get(id=data_source_id)
            except DataSource.DoesNotExist:
                pass
        elif data_source_id == "":
            evidence.data_source = None
        
        evidence.save()
        return UpdateEvidence(evidence=evidence)

class DeleteEvidence(graphene.Mutation):
    class Arguments:
        evidence_id = graphene.ID(required=True)

    ok = graphene.Boolean()

    def mutate(self, info, evidence_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            evidence_filters = {"id": evidence_id}
            if not user.is_superuser:
                evidence_filters["analysis__owner"] = user
            evidence = Evidence.objects.get(**evidence_filters)
        except Evidence.DoesNotExist:
            raise Exception("Evidence not found or access denied")

        evidence.delete()
        return DeleteEvidence(ok=True)

class ApplyACHTemplate(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)
        template_id = graphene.ID(required=True)

    analysis = graphene.Field(ACHAnalysisType)

    def mutate(self, info, analysis_id, template_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            analysis = ACHAnalysis.objects.get(id=analysis_id, owner=user)
            template = ACHTemplate.objects.get(id=template_id)
        except (ACHAnalysis.DoesNotExist, ACHTemplate.DoesNotExist):
            raise Exception("Analysis or Template not found")

        # Apply Hypotheses
        for h_str in template.hypotheses:
            Hypothesis.objects.create(analysis=analysis, content=h_str)
        
        # Apply Evidence
        for e_obj in template.evidence:
            Evidence.objects.create(
                analysis=analysis, 
                content=e_obj.get('content'), 
                credibility=e_obj.get('credibility', 'MEDIUM')
            )
            
        return ApplyACHTemplate(analysis=analysis)

class CreateACHTemplate(graphene.Mutation):
    class Arguments:
        title = graphene.String(required=True)
        description = graphene.String()
        hypotheses = graphene.List(graphene.String)
        evidence = graphene.List(EvidenceInput)

    template = graphene.Field(ACHTemplateType)

    def mutate(self, info, title, description="", hypotheses=None, evidence=None):
        # Optional: gate on admin role
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        tpl = ACHTemplate.objects.create(
            title=title,
            description=description or "",
            hypotheses=hypotheses or [],
            evidence=[
                {
                    'content': e.get('content'),
                    'credibility': e.get('credibility') or 'MEDIUM'
                } for e in (evidence or [])
            ]
        )
        return CreateACHTemplate(template=tpl)

class SaveACHAsTemplate(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)
        title = graphene.String(required=True)
        description = graphene.String()

    template = graphene.Field(ACHTemplateType)

    def mutate(self, info, analysis_id, title, description=""):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        # Ensure the analysis belongs to the user
        try:
            analysis = ACHAnalysis.objects.get(id=analysis_id, owner=user)
        except ACHAnalysis.DoesNotExist:
            raise Exception("Analysis not found or access denied")

        # Snapshot hypotheses and evidence
        hyp_list = list(Hypothesis.objects.filter(analysis=analysis).order_by('sequence').values_list('content', flat=True))
        ev_rows = Evidence.objects.filter(analysis=analysis).order_by('sequence').values('content', 'credibility')
        ev_list = [{ 'content': r['content'], 'credibility': r.get('credibility') or 'MEDIUM' } for r in ev_rows]

        tpl = ACHTemplate.objects.create(
            title=title,
            description=description or "",
            hypotheses=hyp_list,
            evidence=ev_list
        )

        # Mark the analysis as saved as template
        analysis.saved_as_template = True
        analysis.save(update_fields=['saved_as_template', 'updated_at'])

        return SaveACHAsTemplate(template=tpl)

class CheckACHBias(graphene.Mutation):
    class Arguments:
        hypothesis_content = graphene.String(required=True)
        evidence_content = graphene.String(required=True)
        score = graphene.String(required=True)
        other_hypotheses = graphene.List(graphene.String, required=True)

    result = graphene.Field(BiasCheckResultType)

    def mutate(self, info, hypothesis_content, evidence_content, score, other_hypotheses):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        generator = ACHGenerator()
        res = generator.check_bias(user, hypothesis_content, evidence_content, score, other_hypotheses)
        
        if not res:
            return CheckACHBias(result=None)
            
        return CheckACHBias(result=BiasCheckResultType(
            is_biased=res.get('is_biased', False),
            warning_message=res.get('warning_message'),
            reasoning=res.get('reasoning')
        ))

class UpdateMatrixCell(graphene.Mutation):
    class Arguments:
        hypothesis_id = graphene.ID(required=True)
        evidence_id = graphene.ID(required=True)
        score = graphene.String(required=True)

    cell = graphene.Field(MatrixCellType)

    def mutate(self, info, hypothesis_id, evidence_id, score):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        # Verify ownership through hypothesis -> analysis -> owner
        try:
            hypothesis = Hypothesis.objects.get(id=hypothesis_id, analysis__owner=user)
            evidence = Evidence.objects.get(id=evidence_id, analysis__owner=user)
        except (Hypothesis.DoesNotExist, Evidence.DoesNotExist):
            raise Exception("Hypothesis or Evidence not found or access denied")

        cell, created = MatrixCell.objects.update_or_create(
            hypothesis=hypothesis,
            evidence=evidence,
            defaults={'score': score}
        )
        return UpdateMatrixCell(cell=cell)

class UpdateACHStatus(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)
        status = graphene.String(required=True)

    analysis = graphene.Field(ACHAnalysisType)

    def mutate(self, info, analysis_id, status):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        status = status.upper()
        if status not in ['RESEARCH', 'FINISHED']:
            raise Exception("Invalid status")

        try:
            analysis = ACHAnalysis.objects.get(id=analysis_id, owner=user)
        except ACHAnalysis.DoesNotExist:
            raise Exception("Analysis not found or access denied")

        analysis.status = status
        analysis.approved_by = None
        analysis.approved_at = None
        analysis.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        return UpdateACHStatus(analysis=analysis)


class SetACHRemotePull(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)
        enabled = graphene.Boolean(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    analysis = graphene.Field(ACHAnalysisType)

    def mutate(self, info, analysis_id, enabled):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        analysis = ACHAnalysis.objects.select_related('owner').filter(id=analysis_id).first()
        if analysis is None:
            raise Exception("Analysis not found")

        is_admin = bool(
            user.role in [Roles.ADMIN, Roles.REVIEWER]
            or getattr(user, 'is_superuser', False)
            or getattr(user, 'is_staff', False)
        )
        same_org = bool(
            getattr(user, 'organization_id', None)
            and getattr(analysis.owner, 'organization_id', None) == user.organization_id
        )

        if not same_org and not is_admin:
            raise Exception("Access denied")
        if not is_admin and analysis.owner_id != user.id:
            raise Exception("Only owner or admin can change remote pull access")

        analysis.allow_remote_pull = bool(enabled)
        analysis.save(update_fields=['allow_remote_pull', 'updated_at'])
        return SetACHRemotePull(
            success=True,
            message='Remote pull enabled for this ACH analysis' if analysis.allow_remote_pull else 'Remote pull disabled for this ACH analysis',
            analysis=analysis,
        )


class ApproveACHAnalysis(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)

    analysis = graphene.Field(ACHAnalysisType)

    @role_required([Roles.ADMIN, Roles.REVIEWER])
    def mutate(self, info, analysis_id):
        user = info.context.user

        if not user.organization_id:
            raise Exception("User must belong to an organization")

        try:
            analysis = ACHAnalysis.objects.get(
                id=analysis_id,
                owner__organization=user.organization,
            )
        except ACHAnalysis.DoesNotExist:
            raise Exception("Analysis not found or access denied")

        analysis.status = 'APPROVED'
        analysis.approved_by = user
        analysis.approved_at = timezone.now()
        analysis.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        return ApproveACHAnalysis(analysis=analysis)

class GenerateACHContent(graphene.Mutation):
    class Arguments:
        description = graphene.String(required=True)

    result = graphene.Field(GeneratedACHContentType)

    def mutate(self, info, description):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        generator = ACHGenerator()
        data = generator.generate(user, description)
        
        evidence_list = [
            GeneratedEvidenceType(content=e['content'], credibility=e['credibility']) 
            for e in data.get('evidence', [])
        ]
        
        result = GeneratedACHContentType(
            hypotheses=data.get('hypotheses', []),
            evidence=evidence_list
        )
        
        return GenerateACHContent(result=result)

class DeleteACHAnalysis(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)

    ok = graphene.Boolean()

    def mutate(self, info, analysis_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        try:
            analysis_filters = {"id": analysis_id}
            if not user.is_superuser:
                analysis_filters["owner"] = user
            analysis = ACHAnalysis.objects.get(**analysis_filters)
        except ACHAnalysis.DoesNotExist:
            raise Exception("Analysis not found or access denied")

        # Deleting the analysis cascades to hypotheses, evidence, and matrix cells (on_delete=CASCADE)
        analysis.delete()
        return DeleteACHAnalysis(ok=True)


class CloneACHAnalysis(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.UUID(required=True)

    analysis = graphene.Field(ACHAnalysisType)

    def mutate(self, info, analysis_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        try:
            analysis = ACHAnalysis.objects.get(id=analysis_id, owner=user)
        except ACHAnalysis.DoesNotExist:
            raise Exception("Analysis not found or access denied")

        existing_titles = set(ACHAnalysis.objects.filter(owner=user).values_list('title', flat=True))
        new_title = generate_copy_title(analysis.title, existing_titles)

        new_analysis = ACHAnalysis.objects.create(
            title=new_title,
            description=analysis.description,
            owner=user,
            status='RESEARCH'
        )

        hypothesis_map = {}
        for hypothesis in analysis.hypotheses.all():
            clone_h = Hypothesis.objects.create(
                analysis=new_analysis,
                content=hypothesis.content,
                is_proven=hypothesis.is_proven,
                sequence=hypothesis.sequence,
                mitre_technique=hypothesis.mitre_technique,
            )
            hypothesis_map[hypothesis.id] = clone_h

        evidence_map = {}
        for evidence in analysis.evidence_items.all():
            clone_e = Evidence.objects.create(
                analysis=new_analysis,
                content=evidence.content,
                credibility=evidence.credibility,
                relevance=evidence.relevance,
                sequence=evidence.sequence,
                data_source=evidence.data_source,
                log_reference=evidence.log_reference,
            )
            evidence_map[evidence.id] = clone_e

        for cell in MatrixCell.objects.filter(hypothesis__analysis=analysis):
            new_h = hypothesis_map.get(cell.hypothesis_id)
            new_e = evidence_map.get(cell.evidence_id)
            if new_h and new_e:
                MatrixCell.objects.create(
                    hypothesis=new_h,
                    evidence=new_e,
                    score=cell.score,
                    notes=cell.notes,
                )

        return CloneACHAnalysis(analysis=new_analysis)

class CreatePlaybookGraphFromHypothesis(graphene.Mutation):
    class Arguments:
        hypothesis_id = graphene.ID(required=True)

    playbook_graph = graphene.Field(lambda: PlaybookGraphType)
    ok = graphene.Boolean()

    def mutate(self, info, hypothesis_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        
        try:
            hypothesis = Hypothesis.objects.get(id=hypothesis_id, analysis__owner=user)
        except Hypothesis.DoesNotExist:
            raise Exception("Hypothesis not found or access denied")

        # Get user's organization
        if not user.organization:
            raise Exception("User must belong to an organization")

        # Create a new PlaybookGraph with the hypothesis as the title
        graph = PlaybookGraph.objects.create(
            title=hypothesis.content,
            organization=user.organization,
            author=user,
            status='IDEA',
            mitre_technique=hypothesis.mitre_technique,
            goal=f"Investigate and detect: {hypothesis.content}"
        )
        graph.title = PlaybookGraph.compose_title_with_custom_id(hypothesis.content, graph.custom_id)
        graph.save(update_fields=["title", "updated_at"])

        return CreatePlaybookGraphFromHypothesis(playbook_graph=graph, ok=True)

class Mutation(graphene.ObjectType):
    create_ach_analysis = CreateACHAnalysis.Field()
    add_hypothesis = AddHypothesis.Field()
    add_evidence = AddEvidence.Field()
    update_hypothesis = UpdateHypothesis.Field()
    delete_hypothesis = DeleteHypothesis.Field()
    update_evidence = UpdateEvidence.Field()
    delete_evidence = DeleteEvidence.Field()
    update_matrix_cell = UpdateMatrixCell.Field()
    generate_ach_content = GenerateACHContent.Field()
    apply_ach_template = ApplyACHTemplate.Field()
    check_ach_bias = CheckACHBias.Field()
    create_ach_template = CreateACHTemplate.Field()
    save_ach_as_template = SaveACHAsTemplate.Field()
    update_ach_status = UpdateACHStatus.Field()
    set_ach_remote_pull = SetACHRemotePull.Field()
    approve_ach_analysis = ApproveACHAnalysis.Field()
    delete_ach_analysis = DeleteACHAnalysis.Field()
    clone_ach_analysis = CloneACHAnalysis.Field()
    create_playbook_graph_from_hypothesis = CreatePlaybookGraphFromHypothesis.Field()

class Query(graphene.ObjectType):
    ach_analyses = graphene.List(ACHAnalysisType)
    ach_analysis = graphene.Field(ACHAnalysisType, id=graphene.UUID(required=True))
    ach_templates = graphene.List(ACHTemplateType)
    mitre_attack_techniques = graphene.List(MitreAttackTechniqueType)
    myAiSettings = graphene.Field(AIUserSettingsType)

    def resolve_ach_analyses(self, info):
        if info.context.user.is_anonymous:
            return ACHAnalysis.objects.none()
        user = info.context.user
        if is_bot_auditor_user(user):
            return ACHAnalysis.objects.all()
        if user.role in [Roles.ADMIN, Roles.REVIEWER] and user.organization_id:
            return ACHAnalysis.objects.filter(owner__organization=user.organization)
        return ACHAnalysis.objects.filter(owner=user)

    def resolve_ach_analysis(self, info, id):
        if info.context.user.is_anonymous:
            return None
        try:
            user = info.context.user
            if is_bot_auditor_user(user):
                return ACHAnalysis.objects.get(id=id)
            if user.role in [Roles.ADMIN, Roles.REVIEWER] and user.organization_id:
                return ACHAnalysis.objects.get(id=id, owner__organization=user.organization)
            return ACHAnalysis.objects.get(id=id, owner=user)
        except ACHAnalysis.DoesNotExist:
            return None

    def resolve_ach_templates(self, info):
        return ACHTemplate.objects.all()

    def resolve_mitre_attack_techniques(self, info):
        return MitreAttackTechnique.objects.all()

    def resolve_myAiSettings(self, info):
        user = info.context.user
        if user.is_anonymous:
            return None
        try:
            return UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            return None
