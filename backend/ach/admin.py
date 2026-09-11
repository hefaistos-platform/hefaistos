from django.contrib import admin
from .models import ACHAnalysis, Hypothesis, Evidence, MatrixCell, ACHTemplate

class HypothesisInline(admin.TabularInline):
    model = Hypothesis
    extra = 1

class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 1

@admin.register(ACHAnalysis)
class ACHAnalysisAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'created_at')
    inlines = [HypothesisInline, EvidenceInline]

@admin.register(Hypothesis)
class HypothesisAdmin(admin.ModelAdmin):
    list_display = ('content', 'analysis', 'is_proven')

@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('content', 'analysis', 'credibility')

@admin.register(MatrixCell)
class MatrixCellAdmin(admin.ModelAdmin):
    list_display = ('hypothesis', 'evidence', 'score')
    list_filter = ('score',)

@admin.register(ACHTemplate)
class ACHTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    search_fields = ('title',)
