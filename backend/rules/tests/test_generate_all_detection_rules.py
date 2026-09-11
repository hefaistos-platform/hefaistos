from types import SimpleNamespace

from django.test import SimpleTestCase

from identity.decorators import Roles
from rules.schema import GenerateAllDetectionRules


class TestGenerateAllDetectionRules(SimpleTestCase):
    def test_prefers_direct_converter_over_ai(self):
        user = SimpleNamespace(
            is_anonymous=False,
            role=Roles.ADMIN,
            username='tester',
            is_superuser=False,
            is_staff=False,
        )
        info = SimpleNamespace(context=SimpleNamespace(user=user))
        result = GenerateAllDetectionRules.mutate(
            None,
            info,
            source_format='KQL',
            source_content='DeviceProcessEvents | where ProcessCommandLine has "cmd.exe"',
            target_formats=['AQL'],
            playbook_id=None,
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0].status, 'converted')
        self.assertEqual(result.results[0].method, 'converter')

