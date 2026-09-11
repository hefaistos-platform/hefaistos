from django.test import TestCase
from .opentide_schemas import (
    OpenTideRule,
    OpenTideMetadata,
    OpenTidePlatforms,
    KQLPlatform,
    SPLPlatform,
    SigmaPlatform,
    SigmaDetection,
    SigmaLogSource,
    WazuhPlatform,
    QRadarPlatform,
    Severity,
    Status,
)


VALID_RULE = {
    'metadata': {
        'title': 'Suspicious PowerShell Execution',
        'description': 'Detects suspicious PowerShell base64 encoded command execution',
        'author': 'Security Team',
        'severity': 'HIGH',
        'mitre_technique': 'T1059.001',
        'uuid': '12345678-1234-4234-a234-123456789abc',
        'status': 'experimental',
    },
    'platforms': {
        'kql': {
            'query': 'DeviceProcessEvents | where ProcessCommandLine has "powershell"',
        },
    },
}


class OpenTideSchemaValidationTests(TestCase):
    """Unit tests for CoreTide OpenTide Pydantic schema validation."""

    def test_valid_rule_passes(self):
        rule = OpenTideRule(**VALID_RULE)
        self.assertEqual(rule.metadata.title, 'Suspicious PowerShell Execution')
        self.assertEqual(rule.metadata.severity, Severity.HIGH)
        self.assertEqual(rule.metadata.mitre_technique, 'T1059.001')
        self.assertIsNotNone(rule.platforms.kql)

    def test_invalid_mitre_technique_id_rejected(self):
        from pydantic import ValidationError
        bad = {**VALID_RULE, 'metadata': {**VALID_RULE['metadata'], 'mitre_technique': 'T999999'}}
        with self.assertRaises(ValidationError) as ctx:
            OpenTideRule(**bad)
        errors = ctx.exception.errors()
        self.assertTrue(any('mitre_technique' in str(e['loc']) for e in errors))

    def test_valid_base_technique_id(self):
        """T1059 (without sub-technique) should also be valid."""
        data = {**VALID_RULE, 'metadata': {**VALID_RULE['metadata'], 'mitre_technique': 'T1059'}}
        rule = OpenTideRule(**data)
        self.assertEqual(rule.metadata.mitre_technique, 'T1059')

    def test_missing_title_rejected(self):
        from pydantic import ValidationError
        meta = {k: v for k, v in VALID_RULE['metadata'].items() if k != 'title'}
        bad = {**VALID_RULE, 'metadata': meta}
        with self.assertRaises(ValidationError) as ctx:
            OpenTideRule(**bad)
        errors = ctx.exception.errors()
        self.assertTrue(any('title' in str(e['loc']) for e in errors))

    def test_invalid_uuid_rejected(self):
        from pydantic import ValidationError
        bad = {**VALID_RULE, 'metadata': {**VALID_RULE['metadata'], 'uuid': 'not-a-uuid'}}
        with self.assertRaises(ValidationError):
            OpenTideRule(**bad)

    def test_no_platforms_configured_rejected(self):
        from pydantic import ValidationError
        bad = {**VALID_RULE, 'platforms': {}}
        with self.assertRaises(ValidationError) as ctx:
            OpenTideRule(**bad)
        self.assertIn('At least one platform', str(ctx.exception))

    def test_extra_fields_forbidden(self):
        from pydantic import ValidationError
        bad = {**VALID_RULE, 'unknown_field': 'value'}
        with self.assertRaises(ValidationError):
            OpenTideRule(**bad)

    def test_severity_enum_validation(self):
        from pydantic import ValidationError
        bad = {**VALID_RULE, 'metadata': {**VALID_RULE['metadata'], 'severity': 'EXTREME'}}
        with self.assertRaises(ValidationError):
            OpenTideRule(**bad)

    def test_to_yaml_dict_export(self):
        rule = OpenTideRule(**VALID_RULE)
        d = rule.to_yaml_dict()
        self.assertIn('metadata', d)
        self.assertIn('platforms', d)
        self.assertIn('kql', d['platforms'])

    def test_multiple_platforms_valid(self):
        data = {
            **VALID_RULE,
            'platforms': {
                'kql': {'query': 'DeviceProcessEvents'},
                'spl': {'query': 'index=main sourcetype=WinEventLog'},
            }
        }
        rule = OpenTideRule(**data)
        self.assertIsNotNone(rule.platforms.kql)
        self.assertIsNotNone(rule.platforms.spl)

    def test_qradar_scope_validation(self):
        from pydantic import ValidationError
        bad_platforms = {
            'qradar': {'query': 'SELECT * FROM events', 'scope': 'invalid_scope'},
        }
        with self.assertRaises(ValidationError):
            OpenTideRule(**{**VALID_RULE, 'platforms': bad_platforms})

    def test_wazuh_level_validation(self):
        from pydantic import ValidationError
        bad_platforms = {
            'wazuh': {'rule': '<rule/>', 'level': 20},  # level must be 0-16
        }
        with self.assertRaises(ValidationError):
            OpenTideRule(**{**VALID_RULE, 'platforms': bad_platforms})


class SanitizeFilenameAndMitreFolderTests(TestCase):
    """Test MITRE technique ID folder extraction in git_client."""

    def test_base_technique_extracted_from_subtechnique(self):
        from playbooks.git_client import sanitize_filename
        # The folder logic: mitre_technique_id.split('.')[0]
        mitre_id = 'T1059.001'
        base = mitre_id.split('.')[0]
        self.assertEqual(base, 'T1059')

    def test_base_technique_with_no_subtechnique(self):
        mitre_id = 'T1053'
        base = mitre_id.split('.')[0]
        self.assertEqual(base, 'T1053')

    def test_sanitize_filename_spaces(self):
        from playbooks.git_client import sanitize_filename
        self.assertEqual(sanitize_filename('Suspicious PowerShell Execution'), 'suspicious_powershell_execution')

    def test_sanitize_filename_special_chars(self):
        from playbooks.git_client import sanitize_filename
        self.assertEqual(sanitize_filename('Rule: Test/Case'), 'rule_test_case')

    def test_sanitize_workbench_title_preserves_case_and_brackets(self):
        from playbooks.git_client import sanitize_workbench_title_for_filename
        self.assertEqual(
            sanitize_workbench_title_for_filename('[Prod][JPH][eSeL] Kriticka manipulace s AUDIT'),
            '[Prod][JPH][eSeL]_Kriticka_manipulace_s_AUDIT',
        )

    def test_sanitize_workbench_title_removes_path_delimiters(self):
        from playbooks.git_client import sanitize_workbench_title_for_filename
        self.assertEqual(
            sanitize_workbench_title_for_filename('Blue Team / Tier\\2: Rule'),
            'Blue_Team_Tier_2_Rule',
        )
