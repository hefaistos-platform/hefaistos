from django.contrib import admin
from .models import PainPoint, PainPointComment


@admin.register(PainPoint)
class PainPointAdmin(admin.ModelAdmin):
    list_display = ('subject', 'author', 'priority', 'status', 'created_at', 'resolved_by')
    list_filter = ('status', 'priority', 'organization', 'created_at')
    search_fields = ('subject', 'description', 'author__username')
    readonly_fields = ('id', 'created_at', 'updated_at', 'resolved_at')
    
    fieldsets = (
        ('Pain Point Info', {
            'fields': ('id', 'subject', 'description', 'author', 'organization')
        }),
        ('Priority & Status', {
            'fields': ('priority', 'status')
        }),
        ('Resolution', {
            'fields': ('resolved_by', 'resolved_at', 'resolution_notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Auto-populate organization from user if not set"""
        if not obj.organization and obj.author:
            obj.organization = obj.author.organization
        super().save_model(request, obj, form, change)


@admin.register(PainPointComment)
class PainPointCommentAdmin(admin.ModelAdmin):
    list_display = ('pain_point', 'author', 'created_at')
    list_filter = ('created_at', 'pain_point')
    search_fields = ('content', 'author__username', 'pain_point__subject')
    readonly_fields = ('id', 'created_at', 'updated_at')
