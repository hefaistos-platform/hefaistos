"""
Tests for WAZUH autocomplete engine
"""

from django.test import TestCase
from rules.autocomplete.wazuh_engine import WazuhAutocompleteEngine
from rules.autocomplete.suggestions import SuggestionKind, AutocompleteResult


class WazuhAutocompleteEngineTest(TestCase):
    """Test WAZUH autocomplete functionality"""

    def setUp(self):
        """Initialize the engine"""
        self.engine = WazuhAutocompleteEngine()

    def test_wazuh_tag_suggestions(self):
        """Test that WAZUH tags are suggested"""
        # Test with empty rule
        text = "<"
        position = 1

        result = self.engine.get_autocomplete(text, position)

        assert isinstance(result, AutocompleteResult)
        assert len(result.suggestions) > 0

        # Check for common tags
        labels = [s.label for s in result.suggestions]
        assert 'rule' in labels
        assert 'group' in labels

    def test_extract_prefix(self):
        """Test prefix extraction at cursor position"""
        # Test extracting "match" at position 6
        text = "<match"
        prefix = self.engine._extract_prefix(text, 6)
        assert prefix == "match", f"Expected 'match', got '{prefix}'"

        # Test extracting "" after opening tag
        text = "<"
        prefix = self.engine._extract_prefix(text, 1)
        assert prefix == "", f"Expected '', got '{prefix}'"

    def test_get_line_at_position(self):
        """Test getting current line at position"""
        text = "<group name=\"test\">\n  <rule id=\"100001\" level=\"5\">\n    <match>test</match>"

        # Position in first line
        line = self.engine._get_line_at_position(text, 10)
        assert "group" in line, f"Got: {line}"

        # Position in second line
        line = self.engine._get_line_at_position(text, 30)
        assert "rule" in line, f"Got: {line}"

    def test_analyze_context_in_tag(self):
        """Test context analysis when inside a tag"""
        text = "<rule"
        position = 5

        context = self.engine.analyze_context(text, position)
        assert context["section"] == "tag"
        assert context["in_tag"] == True

    def test_analyze_context_attribute(self):
        """Test context analysis when inside tag with attributes"""
        text = "<rule id="
        position = 9

        context = self.engine.analyze_context(text, position)
        assert context["section"] == "attribute"
        assert context["in_tag"] == True

    def test_validate_syntax_valid(self):
        """Test syntax validation with valid XML"""
        text = '<rule id="100001"><match>test</match></rule>'

        is_valid, error = self.engine.validate_syntax(text)
        assert is_valid == True
        assert error is None

    def test_validate_syntax_invalid(self):
        """Test syntax validation with invalid XML"""
        text = '<rule id="100001"><match>test'

        is_valid, error = self.engine.validate_syntax(text)
        assert is_valid == False
        assert error is not None

    def test_suggestions_filtering(self):
        """Test that suggestions are filtered by prefix"""
        text = "<mat"
        position = 4

        result = self.engine.get_autocomplete(text, position)

        # Should only get suggestions containing 'mat'
        for suggestion in result.suggestions:
            assert 'mat' in suggestion.label.lower()

    def test_rule_content_context(self):
        """Test suggestions inside a rule element"""
        text = "<rule id=\"100001\">\n  "
        position = len(text)

        result = self.engine.get_autocomplete(text, position)

        # Should suggest rule elements
        labels = [s.label for s in result.suggestions]
        assert 'match' in labels or 'regex' in labels or any('match' in l or 'regex' in l for l in labels)

    def test_validate_content_reports_semantic_wazuh_errors(self):
        text = (
            '<group name="test">\n'
            '  <rule level="20">\n'
            '    <mitre><id>1078</id></mitre>\n'
            '    <engage><id>Lure</id></engage>\n'
            '    <vulnerability><id>123</id></vulnerability>\n'
            '  </rule>\n'
            '</group>'
        )

        issues = self.engine.validate_content(text)

        messages = [issue["message"] for issue in issues]
        assert any("id" in message.lower() for message in messages)
        assert any("level" in message.lower() for message in messages)
        assert any("ATT&CK" in message for message in messages)
        assert any("Engage" in message for message in messages)
        assert any("CVE" in message for message in messages)

    def test_validate_content_reports_xml_syntax_error(self):
        issues = self.engine.validate_content('<rule id="100001"><match>test')

        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "Syntax Error" in issues[0]["message"]
