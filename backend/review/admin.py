from django.contrib import admin
from .models import ReviewRequest, ReviewComment

@admin.register(ReviewRequest)
class ReviewRequestAdmin(admin.ModelAdmin):
    list_display = ('playbook', 'author', 'organization', 'status', 'created_at')
    list_filter = ('status', 'organization')
    search_fields = ('playbook__title', 'author__username')
    filter_horizontal = ('reviewers',)

@admin.register(ReviewComment)
class ReviewCommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'review_request', 'created_at')
    list_filter = ('author',)
    search_fields = ('text', 'author__username')
