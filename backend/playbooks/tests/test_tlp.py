from unittest import TestCase

from playbooks.utils.tlp import TLP_VALUES, map_tlp_text, normalize_tlp


class TlpNormalizationTests(TestCase):
    def test_all_classifications_survive_prefixed_lowercase_imports(self):
        for value in TLP_VALUES:
            with self.subTest(value=value):
                self.assertEqual(normalize_tlp(f' tlp:{value.lower()} '), value)

    def test_unknown_or_missing_classifications_are_unclear(self):
        for value in (None, '', 'Unknown', 'not used', 'unrecognized', 'TLP:UNCLEAR'):
            with self.subTest(value=value):
                self.assertEqual(normalize_tlp(value), 'UNCLEAR')

    def test_ai_unknown_text_never_becomes_clear(self):
        for value in ('TLP:UNCLEAR', 'unknown source', 'sharing is not clear', 'not used', 'unavailable'):
            with self.subTest(value=value):
                self.assertEqual(map_tlp_text(value, default='CLEAR'), 'UNCLEAR')

    def test_ai_preserves_official_levels_and_strict_suffix(self):
        for value in TLP_VALUES:
            with self.subTest(value=value):
                self.assertEqual(map_tlp_text(f'TLP:{value}'), value)

    def test_absent_ai_field_retains_existing_classification(self):
        self.assertEqual(map_tlp_text('', default='RED'), 'RED')
