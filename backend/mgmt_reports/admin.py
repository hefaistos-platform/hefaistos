from django.contrib import admin

from .models import AIPrompt, MonthlyReportSnapshot, ReportMailingList


@admin.register(AIPrompt)
class AIPromptAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'required_role', 'is_active', 'is_system', 'order')
    list_filter = ('category', 'required_role', 'is_active', 'is_system')
    search_fields = ('title', 'description', 'prompt_template')
    readonly_fields = ('id', 'created_at', 'updated_at')

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'category', 'order')
        }),
        ('Prompt Configuration', {
            'fields': ('prompt_template',)
        }),
        ('Permissions & Status', {
            'fields': ('required_role', 'is_active', 'is_system')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MonthlyReportSnapshot)
class MonthlyReportSnapshotAdmin(admin.ModelAdmin):
    list_display = ('organization', 'year', 'month', 'captured_at')
    list_filter = ('organization', 'year')
    readonly_fields = ('id', 'captured_at')
    ordering = ('-year', '-month')


@admin.register(ReportMailingList)
class ReportMailingListAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'is_subscribed', 'subscribed_at', 'unsubscribed_at')
    list_filter = ('organization', 'is_subscribed')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('id', 'subscribed_at')
