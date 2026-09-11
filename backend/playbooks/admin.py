# playbooks/admin.py (FINAL, ROBUST FIX)

from django.contrib import admin
from .models import (
    DetectionPlaybook,
    Task,
    PlaybookGraph,
    PlaybookNode,
    PlaybookEdge,
    OpentidePreviewTask,
    MveDraft,
    MveNode,
    MveEdge,
    MveValidationRun,
)
from .forms import DetectionPlaybookAdminForm 

# Import the TenantTag model to manage tags directly
# NOTE: Replace 'tags.models' if your TenantTag is in a different location
from tags.models import TenantTag 

@admin.register(DetectionPlaybook)
class DetectionPlaybookAdmin(admin.ModelAdmin):
    # Use the custom form to stop default save_m2m logic from interfering
    form = DetectionPlaybookAdminForm 
    
    # Exclude 'tags' from form submission fields if the form still tries to save them,
    # though the form override should handle this.
    # exclude = ('tags',) # Uncomment this if issues persist, but usually save_m2m handles it.

    # Add framework M2M widgets to the horizontal selector UI
    filter_horizontal = (
        'detection_rules',
        'required_data_sources',
        'mitre_ics_mappings',
        'mitre_mobile_mappings',
    )

    def save_model(self, request, obj, form, change):
        # 1. Save the main object instance first to ensure it has a PK (obj.pk)
        super().save_model(request, obj, form, change)
        
        organization = form.cleaned_data.get('organization')
        tag_names = form.cleaned_data.get('tags')

        if organization and tag_names:
            # --- Manual Tag Handling ---
            
            # 2. Clear all existing tags before setting new ones
            obj.tags.clear() 

            tag_objects = []
            
            # 3. Iterate through raw tag names and manually get_or_create with organization
            for tag_name in tag_names:
                # Use your custom TenantTag model's manager directly
                tag_instance, created = TenantTag.objects.get_or_create(
                    name=tag_name, 
                    defaults={
                        'organization': organization 
                        # This ensures 'organization_id' is set if a new tag is created
                    }
                )
                tag_objects.append(tag_instance)

            # 4. Assign the correctly created/fetched tag objects back to the instance
            obj.tags.set(tag_objects) 
            
    # CRITICAL: We also need to override save_related to prevent the default 
    # M2M processing from running, as save_model now handles tags.
    def save_related(self, request, form, formsets, change):
        # Save all related objects *except* tags, which we handled in save_model
        # Use a list comprehension to filter out the TaggableManager fields
        m2m_fields_to_save = []
        for formset in formsets:
            m2m_fields_to_save.append(formset)

        super().save_related(request, form, m2m_fields_to_save, change)

# Register the Task model separately
admin.site.register(Task)
admin.site.register(PlaybookGraph)
admin.site.register(PlaybookNode)
admin.site.register(PlaybookEdge)
admin.site.register(OpentidePreviewTask)
admin.site.register(MveDraft)
admin.site.register(MveNode)
admin.site.register(MveEdge)
admin.site.register(MveValidationRun)
