from django.contrib import admin
from .models import KnowledgeBaseCategory, KnowledgeBaseArticle

@admin.register(KnowledgeBaseCategory)
class KnowledgeBaseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'description')
    list_filter = ('organization',)
    search_fields = ('name',)

@admin.register(KnowledgeBaseArticle)
class KnowledgeBaseArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'organization', 'author', 'updated_at')
    list_filter = ('organization', 'category', 'author')
    search_fields = ('title', 'content')
