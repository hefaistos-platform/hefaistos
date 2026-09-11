from django.contrib import admin

from .models import WaitingCase, WaitingCaseEnrichmentTask


@admin.register(WaitingCase)
class WaitingCaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'source_type', 'status', 'misp_event_id', 'updated_at')
    list_filter = ('status', 'source_type', 'organization')
    search_fields = ('title', 'misp_event_id')


@admin.register(WaitingCaseEnrichmentTask)
class WaitingCaseEnrichmentTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'waiting_case', 'status', 'requested_by', 'created_at', 'completed_at')
    list_filter = ('status',)
