from django.contrib import admin
from .models import RuleRepository, DetectionRule, KQLTable, KQLField, FieldMapping

admin.site.register(RuleRepository)
admin.site.register(DetectionRule)
admin.site.register(KQLTable)
admin.site.register(KQLField)
admin.site.register(FieldMapping)
