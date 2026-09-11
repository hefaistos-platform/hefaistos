from django.contrib import admin
from .models import (
	RuleRepository,
	RuleRepositoryRAGFileStatus,
	DetectionRule,
	KQLTable,
	KQLField,
	FieldMapping,
    AutocompleteEvent,
)

admin.site.register(RuleRepository)
admin.site.register(RuleRepositoryRAGFileStatus)
admin.site.register(DetectionRule)
admin.site.register(KQLTable)
admin.site.register(KQLField)
admin.site.register(FieldMapping)
admin.site.register(AutocompleteEvent)
