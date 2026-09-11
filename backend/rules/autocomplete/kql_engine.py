"""
KQL format autocomplete engine
"""
from typing import Dict, List, Optional, Tuple
from django.db.models import Prefetch
from .base import AutocompleteEngine
from .suggestions import Suggestion, SuggestionKind
from rules.models import KQLTable, KQLField, FieldMapping


class KQLAutocompleteEngine(AutocompleteEngine):
    """Autocomplete for KQL (Kusto Query Language)."""

    KEYWORDS = [
        "let", "where", "project", "project-away", "summarize", "extend",
        "join", "union", "mv-expand", "take", "limit", "order by",
        "sort", "top", "datatable", "count", "distinct", "render",
    ]

    OPERATORS = [
        "and", "or", "not", "in", "contains", "contains_cs", "startswith",
        "startswith_cs", "endswith", "endswith_cs", "matches", "between",
        "has", "has_cs", "hasprefix", "hassuffix", "!in", "!contains",
    ]

    FUNCTIONS = [
        "tolower", "toupper", "tostring", "datetime_add", "format_datetime",
        "ago", "bin", "parse_json", "substring", "trim", "strlen", "coalesce",
    ]

    def __init__(self):
        super().__init__()
        self.min_prefix_length = 0  # allow suggestions even with empty prefix
        self.max_suggestions = 40   # keep fields plus operators/functions

    def analyze_context(self, text: str, position: int) -> Dict:
        """Lightweight context detection for KQL."""
        line = self._get_line_at_position(text, position)
        previous_token = self._get_previous_token(text, position)

        before_cursor = text[:position]
        after_pipe = before_cursor.rfind("|")
        after_project = before_cursor.rfind("project")
        after_where = before_cursor.rfind("where")

        section = "root"
        if after_pipe != -1 and after_pipe > after_project and after_pipe > after_where:
            section = "pipe"
        elif after_project != -1 and after_project > after_where:
            section = "project"
        elif after_where != -1:
            section = "where"

        return {
            "section": section,
            "line": line,
            "previous_token": previous_token,
        }

    def get_suggestions(
        self,
        prefix: str,
        context: Dict,
        data_source_id: Optional[str] = None
    ) -> List[Suggestion]:
        section = context.get("section", "root")
        suggestions: List[Suggestion] = []

        allowed_fields = self._allowed_fields_for_data_source(data_source_id)

        if section in ("root", "pipe"):
            suggestions.extend(self._suggest_tables(prefix, allowed_fields))
            suggestions.extend(self._keyword_suggestions())

        if section in ("project", "where", "pipe"):
            suggestions.extend(self._suggest_fields(prefix, allowed_fields))
            suggestions.extend(self._operator_suggestions())
            suggestions.extend(self._function_suggestions())

        return suggestions

    def rank_suggestions(self, suggestions: List[Suggestion], prefix: str) -> List[Suggestion]:
        """Prioritize fields > keywords > operators > functions > others."""
        kind_weight = {
            SuggestionKind.FIELD: 0,
            SuggestionKind.KEYWORD: 1,
            SuggestionKind.OPERATOR: 2,
            SuggestionKind.FUNCTION: 3,
            SuggestionKind.SNIPPET: 4,
            SuggestionKind.VALUE: 5,
            SuggestionKind.TEXT: 6,
        }

        def score(s: Suggestion):
            return (kind_weight.get(s.kind, 10), s.label.lower())

        return sorted(suggestions, key=score)

    def validate_syntax(self, text: str) -> Tuple[bool, Optional[str]]:
        if text.count("(") != text.count(")"):
            return False, "Unbalanced parentheses"

        if text.count('"') % 2 != 0:
            return False, "Unbalanced double quotes"

        if text.count("'") % 2 != 0:
            return False, "Unbalanced single quotes"

        stripped = text.rstrip()
        if stripped.endswith("|"):
            return False, "Query cannot end with a pipe operator"

        return True, None

    def validate_content(self, text: str) -> List[Dict]:
        """Return Monaco-friendly validation issues for KQL text."""
        is_valid, error = self.validate_syntax(text)
        if is_valid:
            return []

        line = self._get_line_at_position(text, len(text))
        return [
            {
                "line": max(1, text.count("\n") + 1),
                "column": max(1, len(line) + 1),
                "message": error or "Invalid KQL syntax",
                "severity": "error",
            }
        ]

    def _keyword_suggestions(self) -> List[Suggestion]:
        return [
            Suggestion(label=kw, kind=SuggestionKind.KEYWORD, insertText=kw + " ")
            for kw in self.KEYWORDS
        ]

    def _operator_suggestions(self) -> List[Suggestion]:
        return [
            Suggestion(label=op, kind=SuggestionKind.OPERATOR, insertText=op + " ")
            for op in self.OPERATORS
        ]

    def _function_suggestions(self) -> List[Suggestion]:
        return [
            Suggestion(label=fn + "()", kind=SuggestionKind.FUNCTION, insertText=fn + "()", detail="function")
            for fn in self.FUNCTIONS
        ]

    def _suggest_tables(self, prefix: str, allowed_fields: Optional[set]) -> List[Suggestion]:
        qs = KQLTable.objects.all().prefetch_related(
            Prefetch("fields", queryset=KQLField.objects.all())
        )
        tables = list(qs)
        if not tables:
            tables = [
                KQLTable(table_name="SecurityEvent"),
                KQLTable(table_name="DeviceInfo"),
                KQLTable(table_name="DeviceNetworkEvents"),
                KQLTable(table_name="IdentityLogonEvents"),
            ]

        filtered_tables = []
        for t in tables:
            if allowed_fields is not None:
                try:
                    related = getattr(t, "fields", None)
                    field_list = list(related.all()) if related is not None else []
                except Exception:
                    field_list = []
                if not any((f.field_name in allowed_fields) for f in field_list):
                    continue
            if prefix and prefix.lower() not in t.table_name.lower():
                continue
            filtered_tables.append(t)

        return [
            Suggestion(
                label=t.table_name,
                kind=SuggestionKind.FIELD,
                insertText=t.table_name + " ",
                detail="table",
            )
            for t in filtered_tables
        ]

    def _suggest_fields(self, prefix: str, allowed_fields: Optional[set]) -> List[Suggestion]:
        try:
            fields = list(KQLField.objects.select_related("table"))
        except Exception:
            fields = []

        if allowed_fields is not None:
            fields = [f for f in fields if f.field_name in allowed_fields]

        if not fields:
            fallback = [
                ("SecurityEvent", "AccountName"),
                ("SecurityEvent", "Computer"),
                ("SecurityEvent", "EventID"),
                ("DeviceNetworkEvents", "RemoteUrl"),
                ("DeviceNetworkEvents", "ActionType"),
            ]
            return [
                Suggestion(
                    label=f"{tbl}.{fld}",
                    kind=SuggestionKind.FIELD,
                    insertText=fld,
                    detail=tbl,
                )
                for tbl, fld in fallback
                if (allowed_fields is None or fld in allowed_fields)
                if not prefix or prefix.lower() in fld.lower()
            ]

        return [
            Suggestion(
                label=f"{f.table.table_name}.{f.field_name}",
                kind=SuggestionKind.FIELD,
                insertText=f.field_name,
                detail=f.table.table_name,
            )
            for f in fields
            if not prefix or prefix.lower() in f.field_name.lower()
        ]

    def _allowed_fields_for_data_source(self, data_source_id: Optional[str]) -> Optional[set]:
        if not data_source_id:
            return None
        try:
            field_names = list(
                FieldMapping.objects.filter(data_source_id=data_source_id)
                .exclude(kql_field__isnull=True)
                .values_list("kql_field", flat=True)
            )
            return set(field_names) if field_names else None
        except Exception:
            return None


__all__ = ["KQLAutocompleteEngine"]
