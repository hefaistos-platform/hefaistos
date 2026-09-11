"""
WAZUH XML format autocomplete engine
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from .base import AutocompleteEngine
from .suggestions import Suggestion, SuggestionKind


class WazuhAutocompleteEngine(AutocompleteEngine):
    """
    Autocomplete for WAZUH detection rules (XML format)

    WAZUH Rule Structure:
    <group name="...">
      <rule id="..." level="...">
        <if_sid>...</if_sid>
        <if_group>...</if_group>
        <match>...</match>
        <regex>...</regex>
        <decoded_as>...</decoded_as>
        <category>...</category>
        <field name="...">...</field>
        <description>...</description>
        <options>...</options>
        <info>...</info>
        <mitre>
          <id>...</id>
        </mitre>
      </rule>
    </group>
    """

    # Top-level WAZUH rule tags
    WAZUH_TAGS = [
        'group', 'rule', 'if_sid', 'if_group', 'if_matched_sid', 'if_matched_group',
        'match', 'regex', 'decoded_as', 'category', 'field', 'srcip', 'dstip',
        'srcport', 'dstport', 'user', 'url', 'id', 'status', 'hostname',
        'program_name', 'protocol', 'action', 'description', 'info', 'options',
        'check_diff', 'group_name', 'mitre', 'cve', 'list', 'var'
    ]

    # Common attributes
    RULE_ATTRIBUTES = ['id', 'level', 'maxsize', 'frequency', 'timeframe', 'ignore']
    GROUP_ATTRIBUTES = ['name']
    FIELD_ATTRIBUTES = ['name', 'type']

    # Common WAZUH levels
    WAZUH_LEVELS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15']

    # Common categories
    WAZUH_CATEGORIES = [
        'authentication_success', 'authentication_failed', 'authentication_failures',
        'invalid_login', 'web-log', 'web', 'access-denied', 'access-allowed',
        'firewall', 'ids', 'syslog', 'errors', 'network', 'spam', 'worm',
        'exploit', 'policy_violation', 'denial_of_service', 'attack', 'malware'
    ]

    # Common decoders
    WAZUH_DECODERS = [
        'windows', 'syslog', 'ssh', 'apache', 'nginx', 'firewall', 'cisco',
        'fortigate', 'paloalto', 'checkpoint', 'juniper', 'linux', 'macos',
        'eventchannel', 'json', 'web-accesslog', 'web-log', 'ossec'
    ]

    # Options
    WAZUH_OPTIONS = [
        'no_email_alert', 'no_log', 'no_full_log', 'alert_by_email',
        'no_counter', 'no_ar', 'no_full_log', 'no_pre_match'
    ]

    # Maximum look-ahead distance for checking closing tags
    LOOKAHEAD_DISTANCE = 100

    def analyze_context(self, text: str, position: int) -> Dict:
        """Analyze XML context at cursor position."""
        line = self._get_line_at_position(text, position)
        before_cursor = text[:position]

        # Check if we're inside a tag
        last_open = before_cursor.rfind('<')
        last_close = before_cursor.rfind('>')

        section = "text"
        in_tag = last_open > last_close

        if in_tag:
            # Inside a tag - suggest tag names or attributes
            tag_content = before_cursor[last_open + 1:]
            if ' ' in tag_content:
                section = "attribute"
            else:
                section = "tag"

        # Check if we're in specific sections (use lookahead constant)
        if '<rule' in before_cursor:
            if '</rule>' not in text[position:position + self.LOOKAHEAD_DISTANCE]:
                section = "rule_content"

        if '<group' in before_cursor:
            if '</group>' not in text[position:position + self.LOOKAHEAD_DISTANCE]:
                section = "group_content"

        return {
            "section": section,
            "line": line,
            "in_tag": in_tag,
        }

    def get_suggestions(
        self,
        prefix: str,
        context: Dict,
        data_source_id: Optional[str] = None
    ) -> List[Suggestion]:
        """Generate WAZUH XML suggestions based on context."""
        section = context.get("section", "text")
        suggestions: List[Suggestion] = []

        if section == "tag":
            # Suggest tag names
            for tag in self.WAZUH_TAGS:
                suggestions.append(
                    Suggestion(
                        label=tag,
                        kind=SuggestionKind.KEYWORD,
                        insertText=tag,
                        detail=f"WAZUH XML tag",
                        documentation=f"<{tag}>...</{tag}>"
                    )
                )

        elif section == "attribute":
            # Suggest common attributes
            for attr in self.RULE_ATTRIBUTES + self.GROUP_ATTRIBUTES + self.FIELD_ATTRIBUTES:
                suggestions.append(
                    Suggestion(
                        label=attr,
                        kind=SuggestionKind.FIELD,
                        insertText=f'{attr}=""',
                        detail="Attribute"
                    )
                )

        elif section in ("rule_content", "text"):
            # Suggest rule elements
            for tag in ['if_sid', 'if_group', 'match', 'regex', 'decoded_as',
                       'category', 'field', 'description', 'info', 'options', 'mitre']:
                suggestions.append(
                    Suggestion(
                        label=tag,
                        kind=SuggestionKind.KEYWORD,
                        insertText=f"<{tag}></{tag}>",
                        detail=f"WAZUH rule element",
                        documentation=f"Add {tag} element to rule"
                    )
                )

            # Suggest categories
            for cat in self.WAZUH_CATEGORIES:
                suggestions.append(
                    Suggestion(
                        label=cat,
                        kind=SuggestionKind.VALUE,
                        insertText=cat,
                        detail="Category"
                    )
                )

            # Suggest decoders
            for decoder in self.WAZUH_DECODERS:
                suggestions.append(
                    Suggestion(
                        label=decoder,
                        kind=SuggestionKind.VALUE,
                        insertText=decoder,
                        detail="Decoder"
                    )
                )

        return suggestions

    def validate_syntax(self, text: str) -> Tuple[bool, Optional[str]]:
        """Basic XML validation for WAZUH rules.

        Note: This is lenient to allow editing incomplete rules during development.
        Only checks for major structural issues.
        """
        # Check for matching opening/closing tags
        open_tags = text.count('<')
        close_tags = text.count('>')

        if open_tags != close_tags:
            return False, "Mismatched XML tags"

        # Allow incomplete XML during editing - don't require specific structure
        # Users may be creating group definitions, rule definitions, or other valid WAZUH XML

        return True, None

    def validate_content(self, text: str) -> List[Dict]:
        """Return Monaco-friendly validation issues for WAZUH XML rules."""
        issues: List[Dict] = []
        if not text or not text.strip():
            return issues

        try:
            ET.fromstring(text)
        except ET.ParseError as exc:
            line, column = getattr(exc, "position", (1, 1))
            issues.append({
                "line": line or 1,
                "column": column or 1,
                "message": f"Syntax Error: {exc}",
                "severity": "error",
            })
            return issues

        for rule_match in re.finditer(r"<rule\b[^>]*>.*?</rule>", text, re.DOTALL | re.IGNORECASE):
            rule_block = rule_match.group(0)
            opening_tag_end = rule_block.find(">")
            opening_tag = rule_block[: opening_tag_end + 1] if opening_tag_end != -1 else rule_block
            rule_start_offset = rule_match.start()

            def offset_to_line_column(offset: int) -> Tuple[int, int]:
                absolute_offset = rule_start_offset + offset
                line = text.count("\n", 0, absolute_offset) + 1
                last_newline = text.rfind("\n", 0, absolute_offset)
                column = absolute_offset - last_newline
                return line, column

            rule_id_match = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', opening_tag, re.IGNORECASE)
            if not rule_id_match:
                line, column = offset_to_line_column(max(0, opening_tag.find("<rule")))
                issues.append({
                    "line": line,
                    "column": column,
                    "message": "Rule must contain an 'id' attribute.",
                    "severity": "error",
                })

            level_match = re.search(r'\blevel\s*=\s*["\']([^"\']+)["\']', opening_tag, re.IGNORECASE)
            if not level_match:
                line, column = offset_to_line_column(max(0, opening_tag.find("<rule")))
                issues.append({
                    "line": line,
                    "column": column,
                    "message": "Rule must contain a 'level' attribute.",
                    "severity": "error",
                })
            else:
                try:
                    level_value = int(level_match.group(1))
                    if level_value < 0 or level_value > 16:
                        line, column = offset_to_line_column(level_match.start(1))
                        issues.append({
                            "line": line,
                            "column": column,
                            "message": "Rule level must be between 0 and 16.",
                            "severity": "error",
                        })
                except ValueError:
                    line, column = offset_to_line_column(level_match.start(1))
                    issues.append({
                        "line": line,
                        "column": column,
                        "message": "Rule level must be numeric.",
                        "severity": "error",
                    })

            for framework_tag, prefix, message in (
                ("mitre", "T", "Always use exact ATT&CK codes such as T1078."),
                ("engage", "EAC", "Always use exact Engage codes such as EAC0002."),
                ("vulnerability", "CVE-", "Always use exact CVE identifiers such as CVE-2023-23397."),
            ):
                for match in re.finditer(rf"<{framework_tag}\b.*?<id>(.*?)</id>.*?</{framework_tag}>", rule_block, re.DOTALL | re.IGNORECASE):
                    value = (match.group(1) or "").strip()
                    if not value:
                        line, column = offset_to_line_column(match.start())
                        issues.append({
                            "line": line,
                            "column": column,
                            "message": f"<{framework_tag}> requires a non-empty <id> value.",
                            "severity": "error",
                        })
                    elif not value.startswith(prefix):
                        line, column = offset_to_line_column(match.start(1))
                        issues.append({
                            "line": line,
                            "column": column,
                            "message": message,
                            "severity": "error",
                        })

        return issues

    def rank_suggestions(self, suggestions: List[Suggestion], prefix: str) -> List[Suggestion]:
        """Prioritize keywords > fields > values > others."""
        kind_weight = {
            SuggestionKind.KEYWORD: 0,
            SuggestionKind.FIELD: 1,
            SuggestionKind.VALUE: 2,
            SuggestionKind.OPERATOR: 3,
            SuggestionKind.FUNCTION: 4,
            SuggestionKind.SNIPPET: 5,
            SuggestionKind.TEXT: 6,
        }

        def score(s: Suggestion):
            return (kind_weight.get(s.kind, 10), s.label.lower())

        return sorted(suggestions, key=score)
