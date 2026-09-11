from django.test import SimpleTestCase

from rules.format_registry import get_format_spec, normalize_rule_format


class FormatRegistryTests(SimpleTestCase):
    def test_eql_is_normalized_and_registered(self):
        self.assertEqual(normalize_rule_format("eql"), "EQL")
        spec = get_format_spec("EQL")
        self.assertEqual(spec.file_extension, "eql")
        self.assertEqual(spec.id, "eql")

