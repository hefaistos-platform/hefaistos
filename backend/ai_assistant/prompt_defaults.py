"""Code-owned baselines; approved deployment overrides live only in the database."""

PROMPT_DEFAULTS = {
    'rule_generation.generate': {
        'title': 'Rule generation',
        'component': 'rule_generation',
        'version': '2026.10.30.1',
        'instructions': (
            'You are a Principal Detection Engineer. Generate layered detection outputs '
            'grounded in the supplied capability abstractions.\n\n'
            'Use the structured capability abstractions as authoritative grounding data. '
            'Do not ignore them. The PRIMARY-RULE must prioritize the requested detection '
            'focus layer when one is provided.'
        ),
    },
}

PROMPT_LANGUAGES = ('*', 'KQL', 'EQL', 'SPL', 'WAZUH', 'AQL', 'OTHER')
