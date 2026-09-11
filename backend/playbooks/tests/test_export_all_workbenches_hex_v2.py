import base64
import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from identity.decorators import Roles
from playbooks.schema import ExportAllWorkbenchesHexV2


class TestExportAllWorkbenchesHexV2(SimpleTestCase):
    def _make_info(self):
        user = SimpleNamespace(
            id='user-1',
            username='admin',
            is_anonymous=False,
            role=Roles.ADMIN,
            is_superuser=False,
            is_staff=False,
            organization=SimpleNamespace(id='org-1', name='Acme Org'),
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    @patch('playbooks.schema.serialize_playbook_graph_hex_v2')
    @patch('playbooks.schema.PlaybookGraph.objects')
    def test_exports_zip_manifest_using_hex_v2_serializer(
        self,
        mock_graph_objects,
        mock_serialize,
    ):
        graph = SimpleNamespace(id='graph-1', title='Alpha Workbench', version=3, minor_version=1)
        mock_graph_objects.filter.return_value.select_related.return_value.prefetch_related.return_value = [graph]
        mock_serialize.return_value = {'hex_format': '2.0', 'metadata': {'name': 'Alpha Workbench'}}

        result = ExportAllWorkbenchesHexV2.mutate(None, self._make_info())

        self.assertTrue(result.success)
        self.assertEqual(result.content_type, 'application/zip')
        self.assertIn('workbenches_hex_v2_', result.filename)

        archive_bytes = base64.b64decode(result.file_data)
        with zipfile.ZipFile(io.BytesIO(archive_bytes), 'r') as archive:
            names = set(archive.namelist())
            self.assertIn('Alpha_Workbench__graph-1.hex.json', names)
            self.assertIn('manifest.json', names)

            exported_graph = json.loads(archive.read('Alpha_Workbench__graph-1.hex.json').decode('utf-8'))
            self.assertEqual(exported_graph['hex_format'], '2.0')

            manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
            self.assertEqual(manifest['hex_format'], '2.0')
            self.assertEqual(manifest['organization'], 'Acme Org')
            self.assertEqual(manifest['count'], 1)
            self.assertEqual(manifest['entries'][0]['filename'], 'Alpha_Workbench__graph-1.hex.json')
            self.assertEqual(manifest['entries'][0]['version'], 3)
            self.assertEqual(manifest['entries'][0]['minor_version'], 1)
