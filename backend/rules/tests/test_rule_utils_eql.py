from django.test import SimpleTestCase

from rules.utils import detect_rule_format, parse_rule_by_format


class RuleUtilsEqlTests(SimpleTestCase):
    def test_detect_rule_format_identifies_eql(self):
        query = 'process where process.name == "powershell.exe"'
        self.assertEqual(detect_rule_format(query), "EQL")

    def test_parse_rule_by_format_parses_eql(self):
        content = '// title: PowerShell execution\nprocess where process.name == "powershell.exe"'
        parsed = parse_rule_by_format(content, "EQL", fallback_author="tester")
        self.assertEqual(parsed["title"], "PowerShell execution")
        self.assertEqual(parsed["raw_content"], content)

