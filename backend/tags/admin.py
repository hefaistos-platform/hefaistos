from django.contrib import admin
from.models import TenantTag
from taggit.models import Tag

# Unregister the default Tag admin provided by taggit
admin.site.unregister(Tag)

# Register our custom, tenant-aware Tag model
@admin.register(TenantTag)
class TenantTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "organization")
    list_filter = ("organization",)
