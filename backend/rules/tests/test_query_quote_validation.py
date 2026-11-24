from django.test import SimpleTestCase

from rules.autocomplete import lexical
from rules.autocomplete.aql_engine import AQLAutocompleteEngine
from rules.autocomplete.eql_engine import EQLAutocompleteEngine
from rules.autocomplete.kql_engine import KQLAutocompleteEngine


class KqlQuoteValidationTests(SimpleTestCase):
    def setUp(self):
        self.engine = KQLAutocompleteEngine()

    def test_apostrophe_in_comment_is_valid(self):
        text = "// Detect the attacker's LSASS dump\nDeviceProcessEvents\n| where FileName =~ 'procdump.exe'"
        self.assertEqual(self.engine.validate_content(text), [])
        self.assertEqual(self.engine.validate_syntax(text), (True, None))

    def test_apostrophe_inside_double_quoted_string_is_valid(self):
        self.assertEqual(self.engine.validate_content('T | where Msg contains "don\'t"'), [])

    def test_double_quote_inside_single_quoted_string_is_valid(self):
        self.assertEqual(self.engine.validate_content("T | where Msg contains 'say \"hi\"'"), [])

    def test_escaped_quote_and_verbatim_strings(self):
        self.assertEqual(self.engine.validate_content(r'T | where Msg == "a \" b"'), [])
        self.assertEqual(self.engine.validate_content(r'T | where Path == @"C:\temp\"'), [])
        self.assertEqual(self.engine.validate_content("T | where Msg == @'it''s'"), [])

    def test_parentheses_inside_strings_and_comments_are_ignored(self):
        self.assertEqual(self.engine.validate_content('T | where Msg == ")" // ((('), [])

    def test_unterminated_string_reports_its_own_line(self):
        text = "// ok\nT\n| where A == 'x'\n| where B == 'oops\n| project A"
        issues = self.engine.validate_content(text)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["line"], 4)
        self.assertEqual(issues[0]["message"], "Unbalanced single quotes")

    def test_unbalanced_double_quote_still_reported(self):
        issues = self.engine.validate_content('SecurityEvent | where ProcessName == "powershell')
        self.assertIn("quotes", issues[0]["message"].lower())

    def test_unbalanced_parentheses_report_position(self):
        issues = self.engine.validate_content("T\n| where (A == 1")
        self.assertEqual(issues[0]["message"], "Unbalanced parentheses")
        self.assertEqual(issues[0]["line"], 2)
        issues = self.engine.validate_content("T | where A == 1)")
        self.assertEqual(issues[0]["message"], "Unbalanced parentheses")

    def test_trailing_pipe_still_rejected(self):
        self.assertFalse(self.engine.validate_syntax("T | where A == 1 |")[0])

    def test_triple_backtick_string(self):
        self.assertEqual(self.engine.validate_content("T | where M == ```it's\nmulti```"), [])


class EqlQuoteValidationTests(SimpleTestCase):
    def setUp(self):
        self.engine = EQLAutocompleteEngine()

    def test_apostrophe_inside_double_quoted_string_is_valid(self):
        text = 'process where process.command_line : "*don\'t*"'
        self.assertEqual(self.engine.validate_content(text), [])

    def test_apostrophe_in_comment_is_valid(self):
        text = "// attacker's tool\nprocess where process.name == \"x.exe\""
        self.assertEqual(self.engine.validate_content(text), [])

    def test_raw_triple_quote_string(self):
        self.assertEqual(self.engine.validate_content('process where process.args : """a "b" c"""'), [])

    def test_unterminated_string_still_reported(self):
        issues = self.engine.validate_content('process where process.name == "powershell.exe')
        self.assertIn("quotes", issues[0]["message"].lower())


class AqlQuoteValidationTests(SimpleTestCase):
    def setUp(self):
        self.engine = AQLAutocompleteEngine()

    def test_sql_doubled_quote_and_comment(self):
        text = "-- the attacker's host\nSELECT sourceip FROM events WHERE username = 'o''brien'"
        self.assertEqual(self.engine.validate_content(text), [])

    def test_unterminated_string_still_reported(self):
        issues = self.engine.validate_content("SELECT sourceip FROM events WHERE username = 'bob")
        self.assertIn("quotes", issues[0]["message"].lower())


class LexicalScanTests(SimpleTestCase):
    def test_empty_text(self):
        self.assertEqual(lexical.scan("", lexical.LexicalRules()), [])
        self.assertEqual(lexical.scan(None, lexical.LexicalRules()), [])
