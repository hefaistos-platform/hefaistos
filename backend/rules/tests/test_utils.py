import yaml
from django.test import SimpleTestCase

from rules.utils import extract_platform_rules_from_opentide


class TestExtractPlatformRulesFromOpenTide(SimpleTestCase):
    def test_extract_platform_rules_kql_only(self):
        mdr_data = {
            'name': 'mdr_test_rule',
            'platforms': {
                'kql': {'query': 'DeviceProcessEvents | where FileName =~ "powershell.exe"'},
            },
        }
        files = extract_platform_rules_from_opentide(mdr_data, sanitized_title='test_rule')
        self.assertEqual(set(files.keys()), {'kql/test_rule.kql'})
        self.assertEqual(files['kql/test_rule.kql'], 'DeviceProcessEvents | where FileName =~ "powershell.exe"')

    def test_extract_platform_rules_multi_platform(self):
        mdr_data = {
            'name': 'mdr_multi',
            'platforms': {
                'kql': {'query': 'kql query'},
                'spl': {'query': 'spl query'},
                'sigma': {'detection': {'selection': {'Image|endswith': 'cmd.exe'}, 'condition': 'selection'}},
            },
        }
        files = extract_platform_rules_from_opentide(mdr_data, sanitized_title='multi')
        self.assertEqual(set(files.keys()), {
            'kql/multi.kql',
            'splunk/multi.spl',
            'sigma/multi.yml',
        })

    def test_extract_platform_rules_empty_platforms(self):
        files = extract_platform_rules_from_opentide({'name': 'mdr_empty', 'platforms': {}})
        self.assertEqual(files, {})

    def test_extract_platform_rules_with_base_folder(self):
        mdr_data = {
            'name': 'mdr_rule',
            'configurations': {
                'splunk': {'query': 'index=main'},
            },
        }
        files = extract_platform_rules_from_opentide(
            mdr_data,
            base_folder='content/hef',
            sanitized_title='rule_one',
        )
        self.assertEqual(set(files.keys()), {'content/hef/splunk/rule_one.spl'})

    def test_extract_platform_rules_reads_sentinel_kql_configuration(self):
        mdr_data = {
            'name': 'mdr_rule',
            'configurations': {
                'microsoft_sentinel': {'query': 'SecurityEvent | take 10'},
            },
        }
        files = extract_platform_rules_from_opentide(mdr_data, sanitized_title='rule_one')
        self.assertEqual(set(files.keys()), {'kql/rule_one.kql'})
        self.assertEqual(files['kql/rule_one.kql'], 'SecurityEvent | take 10')

    def test_extract_platform_rules_sigma_is_yaml(self):
        mdr_data = {
            'name': 'mdr_sigma',
            'configurations': {
                'sigma': {
                    'rule': (
                        'title: Suspicious PowerShell\n'
                        'detection:\n'
                        '  selection:\n'
                        '    EventID: 4688\n'
                        '  condition: selection\n'
                    ),
                },
            },
        }
        files = extract_platform_rules_from_opentide(mdr_data, sanitized_title='sigma_rule')
        # Filename comes from sanitized_title (MDR title), NOT from embedded sigma title
        self.assertIn('sigma/sigma_rule.yml', files)
        parsed = yaml.safe_load(files['sigma/sigma_rule.yml'])
        self.assertEqual(parsed['title'], 'Suspicious PowerShell')
        self.assertEqual(parsed['detection']['condition'], 'selection')

    def test_extract_platform_rules_sigma_without_title_falls_back_to_sanitized_title(self):
        mdr_data = {
            'name': 'mdr_sigma',
            'configurations': {
                'sigma': {
                    'rule': (
                        'detection:\n'
                        '  selection:\n'
                        '    EventID: 4688\n'
                        '  condition: selection\n'
                    ),
                },
            },
        }
        files = extract_platform_rules_from_opentide(mdr_data, sanitized_title='sigma_rule')
        self.assertIn('sigma/sigma_rule.yml', files)
        parsed = yaml.safe_load(files['sigma/sigma_rule.yml'])
        self.assertEqual(parsed['detection']['condition'], 'selection')
