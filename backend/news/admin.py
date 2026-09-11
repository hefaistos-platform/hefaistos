from django.contrib import admin
from .models import NewsPost, UserNewsRead
from .models import NewsSettings


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ('title_display', 'category', 'priority', 'is_published', 'is_pinned', 'published_at', 'expires_at', 'author')
    list_filter = ('is_published', 'is_pinned', 'category', 'priority', 'published_at')
    search_fields = ('title', 'content', 'author__username')
    readonly_fields = ('id', 'created_at', 'updated_at', 'published_at')
    
    fieldsets = (
        ('Content', {
            'fields': ('title', 'content', 'category', 'priority')
        }),
        ('Publishing', {
            'fields': ('is_published', 'is_pinned', 'published_at', 'expires_at')
        }),
        ('Metadata', {
            'fields': ('id', 'author', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def title_display(self, obj):
        return obj.title or f"{obj.content[:50]}..."
    title_display.short_description = 'Title/Content'
    
    def save_model(self, request, obj, form, change):
        if not obj.author:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(UserNewsRead)
class UserNewsReadAdmin(admin.ModelAdmin):
    list_display = ('user', 'news_post', 'read_at')
    list_filter = ('read_at', 'user')
    search_fields = ('user__username', 'news_post__title')
    readonly_fields = ('id', 'read_at')


@admin.register(NewsSettings)
class NewsSettingsAdmin(admin.ModelAdmin):
    list_display = ('digest_enabled', 'digest_day', 'digest_hour', 'updated_at')
    fields = ('digest_enabled', 'digest_day', 'digest_hour')
    readonly_fields = ()
