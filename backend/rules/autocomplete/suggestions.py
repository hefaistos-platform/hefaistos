"""
Data models for autocomplete suggestions
"""

from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class SuggestionKind(str, Enum):
    """Type of suggestion - used by Monaco Editor for icons and sorting"""
    KEYWORD = "keyword"
    FIELD = "field"
    VALUE = "value"
    OPERATOR = "operator"
    FUNCTION = "function"
    SNIPPET = "snippet"
    TEXT = "text"


@dataclass
class Suggestion:
    """
    Represents a single autocomplete suggestion
    
    Attributes:
        label: What to display in the suggestion list
        kind: Type of suggestion (for Monaco icon/sorting)
        insertText: What to actually insert when selected
        detail: Type/category info (displayed in suggestion list)
        documentation: Detailed help text
        sortText: Controls sort order (prefix matching priority)
        filterText: Text used for filtering suggestions (defaults to label)
    """
    label: str
    kind: SuggestionKind
    insertText: str
    detail: Optional[str] = None
    documentation: Optional[str] = None
    sortText: Optional[str] = None
    filterText: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GraphQL response"""
        return {
            'label': self.label,
            'kind': self.kind.value,
            'insertText': self.insertText,
            'detail': self.detail,
            'documentation': self.documentation,
            'sortText': self.sortText or self.label,
            'filterText': self.filterText or self.label,
        }


@dataclass
class AutocompleteResult:
    """Result of autocomplete query"""
    suggestions: List[Suggestion]
    isComplete: bool = True  # Whether all matching suggestions are returned
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GraphQL response"""
        return {
            'suggestions': [s.to_dict() for s in self.suggestions],
            'isComplete': self.isComplete,
        }
