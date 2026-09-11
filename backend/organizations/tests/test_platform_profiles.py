"""Tests for profile-aware platform credential selection."""

from django.test import TestCase

from organizations.models import Organization, PlatformCredential


class TestPlatformCredentialProfiles(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Org Profiles Test')

    def _mk(self, platform: str, profile: str, *, enabled: bool = True, is_default: bool = False):
        row = PlatformCredential.objects.create(
            organization=self.org,
            platform=platform,
            profile_name=profile,
            enabled=enabled,
            is_default=is_default,
        )
        row.credentials = {'token': f'{platform}-{profile}'}
        row.save()
        return row

    def test_get_preferred_respects_explicit_profile(self):
        self._mk('defender', 'default', is_default=True)
        specific = self._mk('defender', 'prod-eu')

        resolved = PlatformCredential.get_preferred_for_platform(
            organization=self.org,
            platform='defender',
            profile_name='prod-eu',
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, specific.pk)

    def test_get_preferred_falls_back_to_default_flag(self):
        flagged = self._mk('sentinel', 'soc-primary', is_default=True)
        self._mk('sentinel', 'soc-secondary')

        resolved = PlatformCredential.get_preferred_for_platform(
            organization=self.org,
            platform='sentinel',
        )

        self.assertEqual(resolved.pk, flagged.pk)

    def test_get_preferred_falls_back_to_default_profile_name(self):
        named_default = self._mk('splunk', 'default')
        self._mk('splunk', 'dev')

        resolved = PlatformCredential.get_preferred_for_platform(
            organization=self.org,
            platform='splunk',
        )

        self.assertEqual(resolved.pk, named_default.pk)

    def test_preferred_map_returns_one_entry_per_platform(self):
        self._mk('qradar', 'default', is_default=True)
        self._mk('qradar', 'backup')
        self._mk('wazuh', 'lab', is_default=True)

        cred_map = PlatformCredential.preferred_credentials_map(
            organization=self.org,
            platforms=['qradar', 'wazuh', 'qradar'],
        )

        self.assertEqual(set(cred_map.keys()), {'qradar', 'wazuh'})
        self.assertEqual(cred_map['qradar']['token'], 'qradar-default')
        self.assertEqual(cred_map['wazuh']['token'], 'wazuh-lab')
