from django.test import SimpleTestCase

from rules.validation_gateway import validate_rule_content


class ValidationGatewayTests(SimpleTestCase):
    def test_kql_syntax_error_returns_blocking_issue(self):
        result = validate_rule_content(
            format_name='KQL',
            context='DeviceProcessEvents |',
            position=21,
        )
        self.assertFalse(result['is_valid'])
        self.assertTrue(any(issue.get('code') == 'SYNTAX' for issue in result['issues']))

    def test_format_mismatch_is_warning(self):
        result = validate_rule_content(
            format_name='KQL',
            context='index=main | stats count by host',
            position=32,
        )
        self.assertTrue(any(issue.get('code') == 'FORMAT_MISMATCH' for issue in result['issues']))
        self.assertTrue(any(issue.get('severity') == 'warning' for issue in result['issues']))

    def test_empty_content_is_invalid(self):
        result = validate_rule_content(
            format_name='SPL',
            context='   ',
            position=3,
        )
        self.assertFalse(result['is_valid'])
        self.assertTrue(any(issue.get('code') == 'EMPTY_RULE' for issue in result['issues']))
