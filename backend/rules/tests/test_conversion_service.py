from django.test import SimpleTestCase

from rules.conversion_service import convert_rule_content


class TestConversionService(SimpleTestCase):
    def test_direct_converter_is_used_when_available(self):
        source = "DeviceProcessEvents | where ProcessCommandLine has 'cmd.exe'"
        converted = convert_rule_content("KQL", "AQL", source)
        self.assertEqual(converted, source)

    def test_returns_none_when_no_converter_available(self):
        converted = convert_rule_content("SPL", "WAZUH", "index=* | stats count")
        self.assertIsNone(converted)

