from typing import Callable, Dict, Optional, Tuple


RuleConverter = Callable[[str], str]


def _passthrough_converter(rule_content: str) -> str:
    return rule_content


_DIRECT_CONVERTERS: Dict[Tuple[str, str], RuleConverter] = {
    ('KQL', 'AQL'): _passthrough_converter,
    ('AQL', 'KQL'): _passthrough_converter,
}


def convert_rule_content(source_format: str, target_format: str, rule_content: str) -> Optional[str]:
    converter = _DIRECT_CONVERTERS.get(((source_format or '').upper(), (target_format or '').upper()))
    if not converter:
        return None
    return converter(rule_content)

