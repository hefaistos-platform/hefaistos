from django.contrib import admin
from .models import (OrgAISettings, SharedAIProfile, AIGenerationTask,
                     AIPromptConfiguration, AIPromptVersion, AIPromptAuditEvent,
                     AIRuleGenerationArtifact, AIRuleRevision, AIRuleLineage,
                     AIRuleFeedback, AIFeedbackAuditEvent)
from .models import (AIImprovementProposal, AIImprovementEvaluation,
                     AIImprovementAssessment, AIImprovementEvaluationResult)


@admin.register(OrgAISettings)
class OrgAISettingsAdmin(admin.ModelAdmin):
    list_display = ('organization', 'shared_profile', 'shared_profile_locked', 'ollama_base_url', 'ollama_model', 'updated_at')
    search_fields = ('organization__name', 'ollama_model')


@admin.register(SharedAIProfile)
class SharedAIProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'updated_at')
    search_fields = ('name',)


@admin.register(AIGenerationTask)
class AIGenerationTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'task_type', 'status', 'created_at', 'completed_at')
    list_filter = ('task_type', 'status')
    search_fields = ('user__username',)
    readonly_fields = ('id', 'user', 'organization', 'task_type', 'input_data', 'result_data', 'prompt_provenance',
                       'error_message', 'created_at', 'started_at', 'completed_at')


class ReadOnlyPromptAdmin(admin.ModelAdmin):
    """All writes go through the audited approval service."""
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(AIPromptConfiguration, ReadOnlyPromptAdmin)
admin.site.register(AIPromptVersion, ReadOnlyPromptAdmin)
admin.site.register(AIPromptAuditEvent, ReadOnlyPromptAdmin)
admin.site.register(AIRuleGenerationArtifact, ReadOnlyPromptAdmin)
admin.site.register(AIRuleRevision, ReadOnlyPromptAdmin)
admin.site.register(AIRuleLineage, ReadOnlyPromptAdmin)
admin.site.register(AIRuleFeedback, ReadOnlyPromptAdmin)
admin.site.register(AIFeedbackAuditEvent, ReadOnlyPromptAdmin)
admin.site.register(AIImprovementProposal, ReadOnlyPromptAdmin)
admin.site.register(AIImprovementEvaluation, ReadOnlyPromptAdmin)
admin.site.register(AIImprovementAssessment, ReadOnlyPromptAdmin)
admin.site.register(AIImprovementEvaluationResult, ReadOnlyPromptAdmin)
