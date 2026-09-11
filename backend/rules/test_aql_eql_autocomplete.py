from django.test import SimpleTestCase

from rules.autocomplete import AQLAutocompleteEngine, EQLAutocompleteEngine


class AQLAutocompleteTests(SimpleTestCase):
    def test_aql_keyword_suggestions_available(self):
        engine = AQLAutocompleteEngine()
        result = engine.get_autocomplete(text="SEL", position=3)
        labels = [s.label for s in result.suggestions]
        self.assertIn("SELECT", labels)

    def test_aql_validation_reports_missing_from(self):
        engine = AQLAutocompleteEngine()
        issues = engine.validate_content("SELECT sourceip WHERE sourceip IS NOT NULL")
        self.assertEqual(len(issues), 1)
        self.assertIn("SELECT and FROM", issues[0]["message"])


class EQLAutocompleteTests(SimpleTestCase):
    def test_eql_event_category_suggestions_available(self):
        engine = EQLAutocompleteEngine()
        result = engine.get_autocomplete(text="pro", position=3)
        labels = [s.label for s in result.suggestions]
        self.assertIn("process", labels)

    def test_eql_validation_reports_unbalanced_quotes(self):
        engine = EQLAutocompleteEngine()
        issues = engine.validate_content('process where process.name == "powershell.exe')
        self.assertEqual(len(issues), 1)
        self.assertIn("quotes", issues[0]["message"].lower())

