from types import SimpleNamespace
from django.test import TestCase
from rules.schema import GetAutocompleteOptions


class SupportedFormatAutocompleteTests(TestCase):
    def test_supported_languages_return_suggestions_through_graphql(self):
        import graphene
        from rules.schema import Mutation
        schema = graphene.Schema(query=type('Query', (graphene.ObjectType,), {'ok': graphene.Boolean()}), mutation=Mutation)
        query = '''mutation($format: String!, $context: String!, $position: Int!) {
          getAutocompleteOptions(format: $format, context: $context, position: $position) {
            result { suggestions { label kind insertText } isComplete }
          }
        }'''
        for fmt, text, expected in [('KQL', 'SecurityEvent | wh', 'where'), ('EQL', 'seq', 'sequence'),
                                    ('SPL', 'index=main | st', 'stats'), ('WAZUH', '<ru', 'rule'),
                                    ('AQL', 'SEL', 'SELECT')]:
            with self.subTest(format=fmt):
                result = schema.execute(query, variable_values={'format': fmt, 'context': text, 'position': len(text)},
                                        context_value=SimpleNamespace(user=SimpleNamespace(organization=None)))
                self.assertIsNone(result.errors)
                suggestions = result.data['getAutocompleteOptions']['result']['suggestions']
                self.assertIn(expected, [item['label'] for item in suggestions])
