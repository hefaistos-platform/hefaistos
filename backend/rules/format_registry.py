from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class RuleFormatSpec:
    id: str
    display_name: str
    file_extension: str
    comment_syntax: str


FORMAT_REGISTRY: Dict[str, RuleFormatSpec] = {
    'KQL': RuleFormatSpec(id='kql', display_name='KQL', file_extension='kql', comment_syntax='//'),
    'EQL': RuleFormatSpec(id='eql', display_name='Elastic EQL', file_extension='eql', comment_syntax='//'),
    'SPL': RuleFormatSpec(id='spl', display_name='SPL', file_extension='spl', comment_syntax='#'),
    'WAZUH': RuleFormatSpec(id='wazuh', display_name='WAZUH', file_extension='xml', comment_syntax='xml'),
    'AQL': RuleFormatSpec(id='qradar', display_name='QRadar', file_extension='aql', comment_syntax='--'),
    'OTHER': RuleFormatSpec(id='other', display_name='OTHER', file_extension='txt', comment_syntax='#'),
}


def normalize_rule_format(fmt: Optional[str]) -> str:
    value = (fmt or '').strip().upper()
    if value == 'QRADAR':
        value = 'AQL'
    elif value == 'ELASTIC':
        value = 'EQL'
    return value if value in FORMAT_REGISTRY else 'OTHER'


def get_format_spec(fmt: Optional[str]) -> RuleFormatSpec:
    return FORMAT_REGISTRY[normalize_rule_format(fmt)]
