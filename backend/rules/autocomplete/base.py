"""
Base autocomplete engine - abstract class for format-specific implementations
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import re
from .suggestions import Suggestion, AutocompleteResult, SuggestionKind


class AutocompleteEngine(ABC):
    """
    Abstract base class for autocomplete engines.
    Subclasses implement format-specific logic (SIGMA, KQL, etc.)
    """
    
    def __init__(self):
        self.max_suggestions = 20
        self.min_prefix_length = 1
    
    @abstractmethod
    def analyze_context(self, text: str, position: int) -> Dict:
        """
        Analyze the context at cursor position.
        
        Returns dict with keys like:
        - 'section': What section of the rule (e.g., 'detection', 'logsource')
        - 'line': Current line content
        - 'prefix': Text being typed
        - 'previous_token': Previous meaningful token
        """
        pass
    
    @abstractmethod
    def get_suggestions(
        self,
        prefix: str,
        context: Dict,
        data_source_id: Optional[str] = None
    ) -> List[Suggestion]:
        """
        Return suggestions based on prefix and context.
        
        Args:
            prefix: Text user has typed so far
            context: Analysis of cursor position from analyze_context()
            data_source_id: Optional filter by selected data source
            
        Returns:
            List of Suggestion objects
        """
        pass
    
    @abstractmethod
    def validate_syntax(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Validate syntax of the rule.
        
        Returns:
            (is_valid, error_message)
        """
        pass
    
    def rank_suggestions(
        self,
        suggestions: List[Suggestion],
        prefix: str
    ) -> List[Suggestion]:
        """
        Rank suggestions by relevance.
        
        Factors:
        1. Exact prefix match (highest priority)
        2. Starts with prefix
        3. Contains prefix
        4. Alphabetical order
        """
        def score(suggestion: Suggestion) -> Tuple[int, str]:
            label = suggestion.label.lower()
            prefix_lower = prefix.lower()
            
            # Exact match
            if label == prefix_lower:
                return (0, label)
            # Starts with prefix
            elif label.startswith(prefix_lower):
                return (1, label)
            # Contains prefix
            elif prefix_lower in label:
                return (2, label)
            # Doesn't match (shouldn't happen due to filtering)
            else:
                return (3, label)
        
        return sorted(suggestions, key=score)
    
    def filter_suggestions(
        self,
        suggestions: List[Suggestion],
        prefix: str
    ) -> List[Suggestion]:
        """
        Filter suggestions by prefix (case-insensitive).
        """
        if not prefix:
            return suggestions
        
        prefix_lower = prefix.lower()
        return [
            s for s in suggestions
            if prefix_lower in s.label.lower()
        ]
    
    def get_autocomplete(
        self,
        text: str,
        position: int,
        data_source_id: Optional[str] = None
    ) -> AutocompleteResult:
        """
        Main entry point for autocomplete.
        
        Args:
            text: Full rule content
            position: Cursor position in text
            data_source_id: Optional selected data source
            
        Returns:
            AutocompleteResult with suggestions
        """
        # Analyze context at cursor
        context = self.analyze_context(text, position)
        
        # Extract prefix (word being typed)
        prefix = self._extract_prefix(text, position)
        
        # Don't suggest if prefix too short (unless in special cases)
        if len(prefix) < self.min_prefix_length and prefix != '':
            # For empty prefix, return nothing (user not typing yet)
            if not prefix:
                return AutocompleteResult(suggestions=[])
        
        # Get raw suggestions
        raw_suggestions = self.get_suggestions(
            prefix=prefix,
            context=context,
            data_source_id=data_source_id
        )
        
        # Filter by prefix match
        filtered = self.filter_suggestions(raw_suggestions, prefix)
        
        # Rank by relevance
        ranked = self.rank_suggestions(filtered, prefix)
        
        # Limit to max
        limited = ranked[:self.max_suggestions]
        
        # Check if we have more
        is_complete = len(ranked) <= self.max_suggestions
        
        return AutocompleteResult(
            suggestions=limited,
            isComplete=is_complete
        )
    
    @staticmethod
    def _extract_prefix(text: str, position: int) -> str:
        """
        Extract the word/prefix being typed at cursor position.
        
        Stops at whitespace, brackets, quotes, operators, etc.
        """
        if position > len(text):
            position = len(text)
        
        # Go backwards from cursor to find word boundary
        start = position - 1
        while start >= 0:
            char = text[start]
            # Stop at whitespace or special characters
            if char.isspace() or char in ':{}[](),"\'=<>!|&':
                break
            start -= 1
        
        start += 1  # Move to first character of word
        return text[start:position]
    
    @staticmethod
    def _get_line_at_position(text: str, position: int) -> str:
        """Get the full current line content at cursor position.

        Returns the entire line (from the previous newline to the next newline),
        not just the substring up to the cursor.
        """
        if position < 0:
            position = 0
        if position > len(text):
            position = len(text)

        # If cursor is at start of a new (empty) line because text ends with a newline,
        # step back one character to get the prior line content.
        if position > 0 and position == len(text) and text[position - 1] == '\n':
            position -= 1

        # Find start of current line
        start_idx = text.rfind('\n', 0, position)
        start_line = start_idx + 1 if start_idx != -1 else 0

        # Find end of current line
        end_idx = text.find('\n', position)
        end_line = end_idx if end_idx != -1 else len(text)

        line = text[start_line:end_line]

        # If the resolved line is empty, try the previous non-empty line
        if not line and start_line > 0:
            prev_end = start_idx
            prev_start_idx = text.rfind('\n', 0, prev_end)
            prev_start = prev_start_idx + 1 if prev_start_idx != -1 else 0
            line = text[prev_start:prev_end]

        return line
    
    @staticmethod
    def _get_previous_token(text: str, position: int) -> str:
        """Get the meaningful token immediately preceding the cursor.

        Skips trailing whitespace and punctuation (e.g., ':'), then captures the
        contiguous alphanumeric token. Useful for contexts like 'selection:'
        where the previous token should be 'selection'.
        """
        if position <= 0:
            return ''

        i = position - 1

        # Define punctuation/symbols that are not part of tokens
        punct = set(':{}[](),"\'=<>!|&-')

        # Skip trailing whitespace
        while i >= 0 and text[i].isspace():
            i -= 1

        # Skip trailing punctuation (e.g., colon after a key)
        while i >= 0 and text[i] in punct:
            i -= 1

        if i < 0:
            return ''

        # Collect token characters backwards until boundary
        token_end = i
        while i >= 0 and (not text[i].isspace()) and (text[i] not in punct):
            i -= 1

        token_start = i + 1
        return text[token_start:token_end + 1]
