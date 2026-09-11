from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from.models import DetectionRule
from organizations.models import Organization

@registry.register_document
class DetectionRuleDocument(Document):
    # CRITICAL: We explicitly define the organization field to ensure
    # we can filter by it in our search queries.
    organization = fields.ObjectField(properties={
        'id': fields.KeywordField(),
    })

    class Index:
        # Name of the Elasticsearch index
        name = 'detection_rules'
        # See Elasticsearch Indices API reference for available settings
        settings = {'number_of_shards': 1,
                    'number_of_replicas': 0}

    class Django:
        model = DetectionRule # The model associated with this document

        # The fields of the model you want to be indexed in Elasticsearch
        fields = [
            'title',
            'status',
            'description',
            'author',
        ]

        # This is required to access the related organization object
        related_models = ['organization']

        def get_instances_from_related(self, related_instance):
            """If the related model is changed, update the DetectionRule index."""
            if isinstance(related_instance, Organization):
                return related_instance.detection_rules.all()
