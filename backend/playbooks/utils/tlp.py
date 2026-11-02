"""TLP classifications, including the proposal from https://tlp-unclear.org/."""

import re

TLP_CHOICES = [
    ('CLEAR', 'TLP:CLEAR - Public disclosure'),
    ('GREEN', 'TLP:GREEN - Community sharing'),
    ('AMBER', 'TLP:AMBER - Limited disclosure'),
    ('AMBER+STRICT', 'TLP:AMBER+STRICT - Organization only'),
    ('RED', 'TLP:RED - Personal for named recipients'),
    ('UNCLEAR', 'TLP:UNCLEAR - Source or sharing model unknown, unclear, or not used (tlp-unclear.org)'),
]

TLP_VALUES = {value for value, _ in TLP_CHOICES}


def normalize_tlp(raw) -> str:
    """Accept bare or TLP-prefixed values; unknown classifications are UNCLEAR."""
    value = str(raw or '').strip().upper()
    if value.startswith('TLP:'):
        value = value[4:].strip()
    return value if value in TLP_VALUES else 'UNCLEAR'


def map_tlp_text(raw: str, default: str = 'UNCLEAR') -> str:
    """Map extracted report text without interpreting UNCLEAR as CLEAR."""
    text = (raw or '').strip().upper()
    if not text:
        return default
    if any(value in text for value in (
        'UNCLEAR', 'UNKNOWN', 'NOT CLEAR', 'NOT USED', 'NOT AVAILABLE', 'UNAVAILABLE', 'N/A',
    )):
        return 'UNCLEAR'
    for value in ('CLEAR', 'GREEN', 'AMBER+STRICT', 'AMBER', 'RED'):
        if re.search(rf'\b{re.escape(value)}\b', text):
            return value
    return 'UNCLEAR'
