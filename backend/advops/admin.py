from django.contrib import admin
from .models import ADVOPSReport


@admin.register(ADVOPSReport)
class ADVOPSReportAdmin(admin.ModelAdmin):
    list_display = (
        "hunt_id",
        "status",
        "priority",
        "author",
        "organization",
        "updated_at",
    )
    list_filter = ("status", "priority", "organization")
    search_fields = ("hunt_id", "hypothesis", "author__username")
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        ("Metadata", {
            "fields": ("hunt_id", "status", "priority", "author", "organization", "created_at", "updated_at"),
        }),
        ("Content", {
            "fields": (
                "hypothesis",
                "verification_summary",
                "infrastructure_summary",
                "pivot_summary",
                "false_positive_summary",
                "mitre_summary",
                "detection_logic_summary",
            ),
        }),
    )
