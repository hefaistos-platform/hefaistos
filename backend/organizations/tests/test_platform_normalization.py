"""Tests for HEF deployment platform normalization."""

from django.test import SimpleTestCase

from organizations.schema import normalize_deployment_platforms


class TestNormalizeDeploymentPlatforms(SimpleTestCase):
    def test_maps_format_keys_to_deployment_targets(self):
        mapped, dropped = normalize_deployment_platforms(['kql', 'spl', 'wazuh'])
        self.assertEqual(mapped, ['defender', 'splunk', 'wazuh'])
        self.assertEqual(dropped, [])

    def test_drops_unmapped_values(self):
        mapped, dropped = normalize_deployment_platforms(['elastic', 'foo'])
        self.assertEqual(mapped, [])
        self.assertEqual(dropped, ['elastic', 'foo'])

    def test_deduplicates_mapped_values(self):
        mapped, dropped = normalize_deployment_platforms(['kql', 'defender', 'KQL'])
        self.assertEqual(mapped, ['defender'])
        self.assertEqual(dropped, [])

    def test_maps_kql_to_sentinel_when_policy_is_sentinel(self):
        mapped, dropped = normalize_deployment_platforms(
            ['kql', 'spl'],
            kql_target_policy='sentinel',
        )
        self.assertEqual(mapped, ['sentinel', 'splunk'])
        self.assertEqual(dropped, [])

    def test_maps_kql_to_both_when_policy_is_both(self):
        mapped, dropped = normalize_deployment_platforms(
            ['kql', 'defender', 'sentinel'],
            kql_target_policy='both',
        )
        self.assertEqual(mapped, ['defender', 'sentinel'])
        self.assertEqual(dropped, [])
