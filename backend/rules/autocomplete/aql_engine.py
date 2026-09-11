"""
AQL (QRadar Ariel Query Language) autocomplete engine
"""

from typing import Dict, List, Optional, Tuple
from .base import AutocompleteEngine
from .suggestions import Suggestion, SuggestionKind


class AQLAutocompleteEngine(AutocompleteEngine):
    KEYWORDS = [
        "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "LIKE", "IN",
        "BETWEEN", "ORDER BY", "GROUP BY", "HAVING", "LIMIT", "DISTINCT",
        "JOIN", "LEFT JOIN", "INNER JOIN",
    ]

    FUNCTIONS = [
        "COUNT()", "SUM()", "AVG()", "MIN()", "MAX()", "LOWER()", "UPPER()",
        "DATEFORMAT()", "LOGSOURCENAME()", "ASSETHOSTNAME()",
    ]

    SNIPPETS = [
        "SELECT * FROM events WHERE ",
        "SELECT sourceip, destinationip FROM events WHERE ",
    ]

    def __init__(self):
        super().__init__()
        self.min_prefix_length = 0
        self.max_suggestions = 40

    def analyze_context(self, text: str, position: int) -> Dict:
        return {
            "line": self._get_line_at_position(text, position),
            "previous_token": self._get_previous_token(text, position),
        }

    def get_suggestions(
        self,
        prefix: str,
        context: Dict,
        data_source_id: Optional[str] = None,
    ) -> List[Suggestion]:
        suggestions: List[Suggestion] = []

        suggestions.extend(
            Suggestion(label=kw, kind=SuggestionKind.KEYWORD, insertText=f"{kw} ", detail="AQL keyword")
            for kw in self.KEYWORDS
        )
        suggestions.extend(
            Suggestion(label=fn, kind=SuggestionKind.FUNCTION, insertText=fn, detail="AQL function")
            for fn in self.FUNCTIONS
        )
        suggestions.extend(
            Suggestion(label=snippet, kind=SuggestionKind.SNIPPET, insertText=snippet, detail="AQL snippet")
            for snippet in self.SNIPPETS
        )
        return suggestions

    def validate_syntax(self, text: str) -> Tuple[bool, Optional[str]]:
        stripped = (text or "").strip()
        if not stripped:
            return False, "Empty AQL query"

        if text.count("(") != text.count(")"):
            return False, "Unbalanced parentheses"
        if text.count('"') % 2 != 0:
            return False, "Unbalanced double quotes"
        if text.count("'") % 2 != 0:
            return False, "Unbalanced single quotes"

        lowered = stripped.lower()
        if "select" not in lowered or " from " not in f" {lowered} ":
            return False, "AQL query should include SELECT and FROM"
        if lowered.endswith(("where", "and", "or")):
            return False, "AQL query ends with an incomplete clause"

        return True, None

    def validate_content(self, text: str) -> List[Dict]:
        is_valid, error = self.validate_syntax(text)
        if is_valid:
            return []
        return [{
            "line": max(1, text.count("\n") + 1),
            "column": max(1, len(self._get_line_at_position(text, len(text))) + 1),
            "message": error or "Invalid AQL syntax",
            "severity": "error",
        }]

