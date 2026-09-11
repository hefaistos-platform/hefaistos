"""
Utility for injecting rule metadata as comments into detection rule content.

Supported formats: KQL, SPL, WAZUH, OTHER
"""


def inject_metadata(
    rule_content: str,
    rule_format: str,
    author: str,
    rule_name: str,
    severity: str,
    status: str,
    mitre_technique: str,
    rule_id: str = '',
    description: str = '',
    tags: list[str] | None = None,
) -> str:
    """
    Prepend metadata as comments to detection rule content.

    Args:
        rule_content: The raw rule text.
        rule_format: One of 'KQL', 'SPL', 'WAZUH', 'OTHER'.
        author: Author username.
        rule_name: Name/title of the rule.
        severity: Severity level (e.g. 'HIGH') or 'NA'.
        status: Rule status (e.g. 'DRAFT') or 'NA'.
        mitre_technique: MITRE ATT&CK technique ID (e.g. 'T1059.001') or 'NA'.
        rule_id: The rule's unique ID. No new UUID is generated.

    Returns:
        Rule content with metadata comment block prepended.
    """
    fmt = (rule_format or '').upper()

    if fmt == 'WAZUH':
        block = _build_xml_block(author, rule_name, description, tags, rule_id, severity, status, mitre_technique)
    elif fmt == 'KQL':
        block = _build_line_block('//', author, rule_name, description, tags, rule_id, severity, status, mitre_technique)
    elif fmt == 'AQL':
        block = _build_line_block('--', author, rule_name, description, tags, rule_id, severity, status, mitre_technique)
    else:
        # SPL, OTHER all use '#' line comments
        block = _build_line_block('#', author, rule_name, description, tags, rule_id, severity, status, mitre_technique)

    return block + rule_content


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_line_block(prefix: str, author: str, rule_name: str, description: str, tags: list[str] | None, rule_id: str,
                      severity: str, status: str, mitre_technique: str) -> str:
    sep = f"{prefix} ============================================\n"
    normalized_tags = ", ".join([str(t).strip() for t in (tags or []) if str(t).strip()])
    lines = [
        sep,
        f"{prefix} Rule Metadata\n",
        sep,
        f"{prefix} Author: {author}\n",
        f"{prefix} Rule name: {rule_name}\n",
        f"{prefix} Description: {description or 'NA'}\n",
        f"{prefix} Tags: {normalized_tags or 'NA'}\n",
        f"{prefix} ID: {rule_id}\n",
        f"{prefix} Severity: {severity}\n",
        f"{prefix} Status: {status}\n",
        f"{prefix} MITRE technique: {mitre_technique}\n",
        sep,
        "\n",
    ]
    return "".join(lines)


def _build_xml_block(author: str, rule_name: str, description: str, tags: list[str] | None, rule_id: str,
                     severity: str, status: str, mitre_technique: str) -> str:
    sep = "============================================\n"
    normalized_tags = ", ".join([str(t).strip() for t in (tags or []) if str(t).strip()])
    lines = [
        "<!--\n",
        sep,
        "Rule Metadata\n",
        sep,
        f"Author: {author}\n",
        f"Rule name: {rule_name}\n",
        f"Description: {description or 'NA'}\n",
        f"Tags: {normalized_tags or 'NA'}\n",
        f"ID: {rule_id}\n",
        f"Severity: {severity}\n",
        f"Status: {status}\n",
        f"MITRE technique: {mitre_technique}\n",
        sep,
        "-->\n",
        "\n",
    ]
    return "".join(lines)
