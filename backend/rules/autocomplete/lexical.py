"""Quote- and parenthesis-aware scanning shared by the query-language validators.

The old validators counted raw quote characters, so an apostrophe in a comment
(``// the attacker's LSASS dump``) or inside a double-quoted string (``"*don't*"``) was
reported as "Unbalanced single quotes". This scanner walks the text once, skipping comments and
the bodies of strings, and reports the position of the offending token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class LexicalRules:
    string_quotes: Tuple[str, ...] = ("'", '"')
    line_comments: Tuple[str, ...] = ("//",)
    block_comments: bool = False          # /* ... */
    backslash_escape: bool = True         # \" inside a string
    doubled_quote_escape: bool = False    # SQL style '' inside a single-quoted string
    verbatim_prefix: str = ""             # KQL @"..." / @'...' (no backslash escapes)
    triple_quote: bool = False            # EQL """raw""" strings
    triple_backtick: bool = False         # KQL ```multi-line``` strings


_QUOTE_NAMES = {"'": "single", '"': "double"}


def _position(text: str, index: int) -> Tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    last_nl = text.rfind("\n", 0, index)
    return line, index - last_nl


def scan(text: str, rules: LexicalRules) -> List[Dict]:
    """Return Monaco-style issues for unbalanced parentheses and unterminated strings."""
    issues: List[Dict] = []
    text = text or ""
    n = len(text)
    i = 0
    parens: List[int] = []

    def issue(index: int, message: str) -> None:
        line, column = _position(text, index)
        issues.append({"line": line, "column": column, "message": message, "severity": "error"})

    while i < n:
        ch = text[i]

        if any(text.startswith(prefix, i) for prefix in rules.line_comments):
            nl = text.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if rules.block_comments and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue

        if rules.triple_backtick and text.startswith("```", i):
            end = text.find("```", i + 3)
            if end == -1:
                issue(i, "Unbalanced backticks")
                return issues
            i = end + 3
            continue
        if rules.triple_quote and text.startswith('"""', i):
            end = text.find('"""', i + 3)
            if end == -1:
                issue(i, "Unbalanced double quotes")
                return issues
            i = end + 3
            continue

        if ch in rules.string_quotes:
            start = i
            verbatim = bool(rules.verbatim_prefix) and i > 0 and text[i - 1] == rules.verbatim_prefix
            i += 1
            closed = False
            while i < n:
                c = text[i]
                if c == "\\" and rules.backslash_escape and not verbatim:
                    i += 2
                    continue
                if c == ch:
                    if (verbatim or rules.doubled_quote_escape) and i + 1 < n and text[i + 1] == ch:
                        i += 2
                        continue
                    closed = True
                    i += 1
                    break
                i += 1
            if not closed:
                issue(start, f"Unbalanced {_QUOTE_NAMES.get(ch, 'string')} quotes")
                return issues
            continue

        if ch == "(":
            parens.append(i)
        elif ch == ")":
            if parens:
                parens.pop()
            else:
                issue(i, "Unbalanced parentheses")
        i += 1

    for index in parens:
        issue(index, "Unbalanced parentheses")
    issues.sort(key=lambda item: (item["line"], item["column"]))
    return issues
