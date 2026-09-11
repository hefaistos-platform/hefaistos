# playbooks/forms.py (Simplified)
from django import forms
from .models import DetectionPlaybook

class DetectionPlaybookAdminForm(forms.ModelForm):
    # Keep the form simple, save_model handles the messy tag logic
    class Meta:
        model = DetectionPlaybook
        fields = '__all__'
    
    # We explicitly remove save_m2m override as save_model now handles everything.
    # DELETE the save_m2m method from this file.
