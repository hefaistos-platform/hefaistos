from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from organizations.models import Organization
from playbooks.models import PlaybookGraph
from playbooks.schema import (
    serialize_playbook_graph,
    serialize_playbook_graph_hex_v2,
    update_playbook_graph_from_hex_v2,
    update_playbook_graph_from_v1,
)

FREE_RULE = {"content": "rule demo { condition: true }", "format": "yara"}
# "metadata" is regenerated from the Workbench fields on every save (PlaybookGraph.save ->
# auto_update_opentide_yaml), so only platforms, freeRule and MVE chains are carried over.
EXISTING_DOC = {
    "platforms": {"kql": {"query": "DeviceProcessEvents | take 10"}},
    "mve_velocity_detections": [{"id": "mve-1", "chain": ["a", "b"]}],
}


class HexImportFreeRuleMergeTests(TestCase):
    """Importing a file that carries a FREE rule must not wipe the Workbench's OpenTIDE data."""

    def setUp(self):
        user_model = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.user = user_model.objects.create_user(username='free_admin', organization=self.org, role='ADMIN')
        self.graph = PlaybookGraph.objects.create(
            organization=self.org,
            author=self.user,
            title='wb',
            status='IDEA',
            detection_rule='DeviceProcessEvents | take 1',
            opentide_yaml=dict(EXISTING_DOC, freeRule="old free rule"),
        )
        patcher = patch('playbooks.l1_portal.upsert_l1_portal_snapshot')
        patcher.start()
        self.addCleanup(patcher.stop)

    def stored(self):
        return PlaybookGraph.objects.get(pk=self.graph.pk)

    def _assert_merged(self):
        doc = self.stored().opentide_yaml
        self.assertEqual(doc["freeRule"], FREE_RULE)
        self.assertEqual(doc["platforms"], EXISTING_DOC["platforms"])
        self.assertIn("metadata", doc)  # regenerated, not carried over
        self.assertEqual(doc["mve_velocity_detections"], EXISTING_DOC["mve_velocity_detections"])

    def test_v1_update_with_free_rule_keeps_platforms_and_mve_chains(self):
        data = serialize_playbook_graph(self.graph)
        data['playbook']['free_rule'] = FREE_RULE
        update_playbook_graph_from_v1(data, self.graph, self.user)
        self._assert_merged()

    def test_hex_v2_update_with_free_rule_keeps_platforms_and_mve_chains(self):
        data = serialize_playbook_graph_hex_v2(self.graph)
        data['detection_logic']['free_rule'] = FREE_RULE
        update_playbook_graph_from_hex_v2(data, self.graph, self.user)
        self._assert_merged()

    def test_update_without_free_rule_leaves_document_untouched(self):
        for dump, key, update in (
            (serialize_playbook_graph, 'playbook', update_playbook_graph_from_v1),
            (serialize_playbook_graph_hex_v2, 'detection_logic', update_playbook_graph_from_hex_v2),
        ):
            PlaybookGraph.objects.filter(pk=self.graph.pk).update(
                opentide_yaml=dict(EXISTING_DOC, freeRule="old free rule")
            )
            graph = self.stored()
            data = dump(graph)
            data[key].pop('free_rule', None)
            update(data, graph, self.user)
            self.assertEqual(self.stored().opentide_yaml["platforms"], EXISTING_DOC["platforms"])
            self.assertEqual(self.stored().opentide_yaml["freeRule"], "old free rule")

    def test_free_rule_import_onto_empty_document_still_works(self):
        PlaybookGraph.objects.filter(pk=self.graph.pk).update(opentide_yaml={})
        graph = self.stored()
        data = serialize_playbook_graph_hex_v2(graph)
        data['detection_logic']['free_rule'] = FREE_RULE
        update_playbook_graph_from_hex_v2(data, graph, self.user)
        doc = self.stored().opentide_yaml
        self.assertEqual(doc["freeRule"], FREE_RULE)
        self.assertEqual(doc["platforms"], {})
