"""
Elastic EQL autocomplete engine
"""

from typing import Dict, List, Optional, Tuple
from .base import AutocompleteEngine
from .suggestions import Suggestion, SuggestionKind


class EQLAutocompleteEngine(AutocompleteEngine):
    KEYWORDS = [
        "sequence", "where", "by", "with", "maxspan", "any", "until", "not",
        "in", "and", "or", "true", "false",
    ]

    EVENT_CATEGORIES = [
        "process", "file", "network", "registry", "library", "dns",
    ]

    SNIPPETS = [
        'process where process.name == "powershell.exe"',
        'sequence by host.id with maxspan=5m\n  [process where process.name == "cmd.exe"]\n  [network where destination.port == 4444]',
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
            Suggestion(label=kw, kind=SuggestionKind.KEYWORD, insertText=f"{kw} ", detail="EQL keyword")
            for kw in self.KEYWORDS
        )
        suggestions.extend(
            Suggestion(label=cat, kind=SuggestionKind.FIELD, insertText=f"{cat} where ", detail="event category")
            for cat in self.EVENT_CATEGORIES
        )
        suggestions.extend(
            Suggestion(label=snippet, kind=SuggestionKind.SNIPPET, insertText=snippet, detail="EQL snippet")
            for snippet in self.SNIPPETS
        )
        return suggestions

    def validate_syntax(self, text: str) -> Tuple[bool, Optional[str]]:
        stripped = (text or "").strip()
        if not stripped:
            return False, "Empty EQL query"

        if text.count("(") != text.count(")"):
            return False, "Unbalanced parentheses"
        if text.count('"') % 2 != 0:
            return False, "Unbalanced double quotes"
        if text.count("'") % 2 != 0:
            return False, "Unbalanced single quotes"

        lowered = stripped.lower()
        if lowered.endswith(("where", "and", "or", "by", "with")):
            return False, "EQL query ends with an incomplete clause"
        if lowered.startswith("sequence") and "[" not in stripped:
            return False, "EQL sequence query should include bracketed event clauses"

        return True, None

    def validate_content(self, text: str) -> List[Dict]:
        is_valid, error = self.validate_syntax(text)
        if is_valid:
            return []
        return [{
            "line": max(1, text.count("\n") + 1),
            "column": max(1, len(self._get_line_at_position(text, len(text))) + 1),
            "message": error or "Invalid EQL syntax",
            "severity": "error",
        }]

