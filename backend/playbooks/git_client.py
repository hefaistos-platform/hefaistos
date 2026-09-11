"""Helpers for GitHub-based OpenTIDE publishing."""

import re


def sanitize_filename(title: str) -> str:
    """
    Convert a detection rule title to a safe filename.

    Converts to lowercase, replaces spaces and special characters with underscores,
    strips leading/trailing underscores, and truncates to 80 characters.
    """
    name = title.lower()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    name = name.strip('_')
    return name[:80] or 'detection_rule'


def sanitize_workbench_title_for_filename(title: str) -> str:
    """
    Convert a workbench title to a readable and safe filename stem.

    Keeps casing and markers like ``[Prod]`` for readability while:
    - replacing whitespace with underscores,
    - removing path separators/control chars and Windows-reserved chars,
    - collapsing repeated underscores,
    - trimming unsafe leading/trailing punctuation.
    """
    value = (title or '').strip()
    if not value:
        return 'detection_rule'

    # Strip control characters and any path separator to avoid nested paths.
    value = re.sub(r'[\x00-\x1f]+', '', value)
    value = value.replace('/', '_').replace('\\', '_')

    # Normalize spacing and characters problematic across common filesystems.
    value = re.sub(r'\s+', '_', value)
    value = re.sub(r'[<>:"|?*]+', '_', value)
    value = re.sub(r'_+', '_', value).strip('._ ')

    return value[:120] or 'detection_rule'
