from django.test import TestCase
from organizations.models import Organization
from data_catalog.models import DataSource
from rules.autocomplete.kql_engine import KQLAutocompleteEngine
from rules.models import KQLTable, KQLField, FieldMapping


class KQLAutocompleteTests(TestCase):
    def setUp(self):
        se = KQLTable.objects.create(table_name="SecurityEvent")
        KQLField.objects.create(table=se, field_name="Account")
        KQLField.objects.create(table=se, field_name="Computer")
        dne = KQLTable.objects.create(table_name="DeviceNetworkEvents")
        KQLField.objects.create(table=dne, field_name="RemoteUrl")

    def test_table_suggestions_at_root(self):
        engine = KQLAutocompleteEngine()
        res = engine.get_autocomplete(text="", position=0)
        labels = [s.label for s in res.suggestions]
        self.assertIn("SecurityEvent", labels)
        self.assertIn("DeviceNetworkEvents", labels)

    def test_field_suggestions_after_project(self):
        engine = KQLAutocompleteEngine()
        text = "SecurityEvent | project "
        pos = len(text)
        res = engine.get_autocomplete(text=text, position=pos)
        labels = [s.label for s in res.suggestions]
        self.assertIn("SecurityEvent.Account", labels)
        self.assertIn("SecurityEvent.Computer", labels)
        self.assertIn("DeviceNetworkEvents.RemoteUrl", labels)

    def test_operator_and_function_present(self):
        engine = KQLAutocompleteEngine()
        text = "SecurityEvent | where "
        res = engine.get_autocomplete(text=text, position=len(text))
        labels = [s.label for s in res.suggestions]
        self.assertIn("and", labels)
        self.assertTrue(any(label.endswith("()") for label in labels))

    def test_data_source_filters_fields_and_tables(self):
        org = Organization.objects.create(name="Test Org")
        ds = DataSource.objects.create(name="DS1", organization=org)

        extra_table = KQLTable.objects.create(table_name="ExtraTable")
        KQLField.objects.create(table=extra_table, field_name="ExtraField")

        FieldMapping.objects.create(data_source=ds, kql_field="Account")
        FieldMapping.objects.create(data_source=ds, kql_field="RemoteUrl")

        engine = KQLAutocompleteEngine()

        root_res = engine.get_autocomplete(text="", position=0, data_source_id=str(ds.id))
        root_labels = [s.label for s in root_res.suggestions]
        self.assertIn("SecurityEvent", root_labels)
        self.assertIn("DeviceNetworkEvents", root_labels)
        self.assertNotIn("ExtraTable", root_labels)

        project_text = "SecurityEvent | project "
        project_res = engine.get_autocomplete(text=project_text, position=len(project_text), data_source_id=str(ds.id))
        project_labels = [s.label for s in project_res.suggestions]
        self.assertIn("SecurityEvent.Account", project_labels)
        self.assertIn("DeviceNetworkEvents.RemoteUrl", project_labels)
        self.assertNotIn("SecurityEvent.Computer", project_labels)
        self.assertNotIn("ExtraTable.ExtraField", project_labels)

    def test_validate_content_reports_basic_syntax_errors(self):
        engine = KQLAutocompleteEngine()

        issues = engine.validate_content('SecurityEvent | where ProcessName == "powershell')

        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "quotes" in issues[0]["message"].lower()
