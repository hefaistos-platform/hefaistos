import json

from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase

from organizations.models import Organization
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph, CapabilityAbstraction


class CapabilityAbstractionGraphQLTests(GraphQLTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.org = Organization.objects.create(name="Capability Org")
        self.other_org = Organization.objects.create(name="Other Capability Org")
        self.user = User.objects.create_user(
            username="capuser",
            password="password",
            organization=self.org,
            role="ANALYST",
        )
        self.admin_user = User.objects.create_user(
            username="capadmin",
            password="password",
            organization=self.org,
            role="ADMIN",
        )
        self.technique = MitreAttackTechnique.objects.create(
            technique_id="T1218.005",
            stix_id="attack-pattern--capability-test",
            name="Mshta",
            description="Signed binary proxy execution via Mshta",
            url="https://example.com/t1218.005",
        )
        self.technique_two = MitreAttackTechnique.objects.create(
            technique_id="T1059.001",
            stix_id="attack-pattern--capability-test-2",
            name="PowerShell",
            description="PowerShell execution",
            url="https://example.com/t1059.001",
        )
        self.graph = PlaybookGraph.objects.create(
            title="Capability Workbench",
            organization=self.org,
            author=self.user,
            mitre_technique=self.technique,
        )
        self.shared_entry = CapabilityAbstraction.objects.create(
            technique=self.technique,
            organization=None,
            abstraction_layer=CapabilityAbstraction.AbstractionLayer.TOOL,
            component_artifact="mshta.exe",
            detection_value="Quick win for signed binary proxy execution",
            source_kind=CapabilityAbstraction.SourceKind.SEEDED,
            is_baseline=True,
        )
        self.org_entry = CapabilityAbstraction.objects.create(
            technique=self.technique,
            organization=self.org,
            created_by=self.user,
            updated_by=self.user,
            abstraction_layer=CapabilityAbstraction.AbstractionLayer.PROCESS_BEHAVIOR,
            component_artifact="mshta child process chain",
            detection_value="Stronger process behavior anchor",
            source_kind=CapabilityAbstraction.SourceKind.CUSTOM,
            review_status=CapabilityAbstraction.ReviewStatus.REVIEWED,
        )
        self.hidden_entry = CapabilityAbstraction.objects.create(
            technique=self.technique,
            organization=self.other_org,
            abstraction_layer=CapabilityAbstraction.AbstractionLayer.NETWORK_BEHAVIOR,
            component_artifact="remote script retrieval",
            detection_value="Should not be visible to the current org",
            source_kind=CapabilityAbstraction.SourceKind.CUSTOM,
        )
        self.org_entry_other_technique = CapabilityAbstraction.objects.create(
            technique=self.technique_two,
            organization=self.org,
            created_by=self.user,
            updated_by=self.user,
            abstraction_layer=CapabilityAbstraction.AbstractionLayer.TOOL,
            component_artifact="powershell.exe",
            detection_value="Command interpreter behavior",
            source_kind=CapabilityAbstraction.SourceKind.CUSTOM,
        )
        self.client.force_login(self.user)

    def test_capability_abstractions_query_returns_baseline_and_org_scope(self):
        query = '''
            query CapabilityAbstractions($techniqueId: String!) {
                capabilityAbstractions(techniqueId: $techniqueId) {
                    id
                    componentArtifact
                    isSharedBaseline
                    organizationName
                }
            }
        '''
        response = self.query(query, variables={"techniqueId": self.technique.technique_id})
        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]["capabilityAbstractions"]
        component_names = {item["componentArtifact"] for item in payload}
        self.assertIn("mshta.exe", component_names)
        self.assertIn("mshta child process chain", component_names)
        self.assertNotIn("remote script retrieval", component_names)

    def test_update_playbook_details_sets_selected_capabilities_and_focus_layer(self):
        mutation = '''
            mutation UpdateWorkbenchCapabilities(
                $graphId: UUID!,
                $capabilityIds: [UUID!],
                $focusLayer: String
            ) {
                updatePlaybookDetails(
                    graphId: $graphId,
                    selectedCapabilityAbstractionIds: $capabilityIds,
                    detectionFocusLayer: $focusLayer
                ) {
                    graph {
                        id
                        detectionFocusLayer
                        selectedCapabilityAbstractions {
                            componentArtifact
                        }
                    }
                }
            }
        '''
        response = self.query(
            mutation,
            variables={
                "graphId": str(self.graph.id),
                "capabilityIds": [str(self.shared_entry.id), str(self.org_entry.id), str(self.hidden_entry.id)],
                "focusLayer": "PROCESS_BEHAVIOR",
            },
        )
        self.assertResponseNoErrors(response)
        self.graph.refresh_from_db()
        self.assertEqual(self.graph.detection_focus_layer, "PROCESS_BEHAVIOR")
        selected = set(self.graph.selected_capability_abstractions.values_list("component_artifact", flat=True))
        self.assertEqual(selected, {"mshta.exe", "mshta child process chain"})

    def test_capability_abstractions_query_without_technique_returns_all_org_plus_baseline(self):
        query = '''
            query CapabilityAbstractions {
                capabilityAbstractions {
                    componentArtifact
                }
            }
        '''
        response = self.query(query)
        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]["capabilityAbstractions"]
        component_names = {item["componentArtifact"] for item in payload}
        self.assertIn("mshta.exe", component_names)
        self.assertIn("mshta child process chain", component_names)
        self.assertIn("powershell.exe", component_names)
        self.assertNotIn("remote script retrieval", component_names)

    def test_create_capability_abstraction_uses_provided_technique_id(self):
        mutation = '''
            mutation CreateCapabilityAbstraction(
                $techniqueId: String!,
                $abstractionLayer: String!,
                $componentArtifact: String!
            ) {
                createCapabilityAbstraction(
                    techniqueId: $techniqueId,
                    abstractionLayer: $abstractionLayer,
                    componentArtifact: $componentArtifact
                ) {
                    capabilityAbstraction {
                        id
                    }
                }
            }
        '''
        response = self.query(
            mutation,
            variables={
                "techniqueId": self.technique_two.technique_id,
                "abstractionLayer": "TOOL",
                "componentArtifact": "custom powershell artifact",
            },
        )
        self.assertResponseNoErrors(response)
        created_id = json.loads(response.content)["data"]["createCapabilityAbstraction"]["capabilityAbstraction"]["id"]
        created = CapabilityAbstraction.objects.get(id=created_id)
        self.assertEqual(created.technique.technique_id, self.technique_two.technique_id)
        self.assertEqual(created.organization, self.org)

    def test_delete_capability_abstraction_allows_admin_for_custom_org_entry(self):
        self.client.force_login(self.admin_user)
        mutation = '''
            mutation DeleteCapabilityAbstraction($id: UUID!) {
                deleteCapabilityAbstraction(capabilityAbstractionId: $id) {
                    ok
                }
            }
        '''
        response = self.query(mutation, variables={"id": str(self.org_entry.id)})
        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]["deleteCapabilityAbstraction"]
        self.assertTrue(payload["ok"])
        self.assertFalse(CapabilityAbstraction.objects.filter(id=self.org_entry.id).exists())

    def test_delete_capability_abstraction_denies_non_admin(self):
        self.client.force_login(self.user)
        mutation = '''
            mutation DeleteCapabilityAbstraction($id: UUID!) {
                deleteCapabilityAbstraction(capabilityAbstractionId: $id) {
                    ok
                }
            }
        '''
        response = self.query(mutation, variables={"id": str(self.org_entry.id)})
        payload = json.loads(response.content)
        self.assertIn("errors", payload)
        self.assertTrue(CapabilityAbstraction.objects.filter(id=self.org_entry.id).exists())

    def test_technique_change_without_capability_ids_preserves_selections(self):
        """Changing the workbench technique without passing selectedCapabilityAbstractionIds
        must NOT clear the existing selected capability abstractions."""
        # Pre-select an entry for this graph.
        self.graph.selected_capability_abstractions.set([self.org_entry])
        self.graph.refresh_from_db()
        self.assertEqual(self.graph.selected_capability_abstractions.count(), 1)

        mutation = '''
            mutation UpdateTechniqueOnly($graphId: UUID!, $techniqueId: String!) {
                updatePlaybookDetails(
                    graphId: $graphId,
                    mitreTechniqueId: $techniqueId
                ) {
                    graph {
                        id
                        selectedCapabilityAbstractions {
                            id
                            componentArtifact
                        }
                    }
                }
            }
        '''
        response = self.query(
            mutation,
            variables={
                "graphId": str(self.graph.id),
                "techniqueId": self.technique_two.technique_id,
            },
        )
        self.assertResponseNoErrors(response)
        self.graph.refresh_from_db()
        # Selections must still be there after a technique-only update.
        selected = set(self.graph.selected_capability_abstractions.values_list("id", flat=True))
        self.assertIn(self.org_entry.id, selected)

    def test_update_selected_capability_abstractions_does_not_delete_library_entry(self):
        """Removing an abstraction from the workbench selection must not delete it from
        the Capability Abstraction Library."""
        self.graph.selected_capability_abstractions.set([self.org_entry])

        mutation = '''
            mutation ClearSelection($graphId: UUID!) {
                updatePlaybookDetails(
                    graphId: $graphId,
                    selectedCapabilityAbstractionIds: []
                ) {
                    graph {
                        id
                        selectedCapabilityAbstractions {
                            id
                        }
                    }
                }
            }
        '''
        response = self.query(mutation, variables={"graphId": str(self.graph.id)})
        self.assertResponseNoErrors(response)
        self.graph.refresh_from_db()
        # Selection is now empty …
        self.assertEqual(self.graph.selected_capability_abstractions.count(), 0)
        # … but the library entry itself still exists.
        self.assertTrue(CapabilityAbstraction.objects.filter(id=self.org_entry.id).exists())

    def test_filter_by_technique_does_not_auto_select_results(self):
        """Querying capabilityAbstractions for a technique must never modify
        the graph's selectedCapabilityAbstractions — it is a read-only library query."""
        # Ensure no selections exist initially.
        self.graph.selected_capability_abstractions.clear()

        query = '''
            query CapabilityAbstractions($techniqueId: String!) {
                capabilityAbstractions(techniqueId: $techniqueId) {
                    id
                    componentArtifact
                }
            }
        '''
        response = self.query(query, variables={"techniqueId": self.technique.technique_id})
        self.assertResponseNoErrors(response)
        # The query should return library entries …
        payload = json.loads(response.content)["data"]["capabilityAbstractions"]
        self.assertGreater(len(payload), 0)
        # … but must NOT have changed the graph's selections.
        self.graph.refresh_from_db()
        self.assertEqual(self.graph.selected_capability_abstractions.count(), 0)

    def test_selections_from_multiple_techniques_are_persisted(self):
        """The user must be able to select abstractions from two different techniques
        and save them both on the same workbench."""
        mutation = '''
            mutation UpdateWorkbenchCapabilities(
                $graphId: UUID!,
                $capabilityIds: [UUID!]
            ) {
                updatePlaybookDetails(
                    graphId: $graphId,
                    selectedCapabilityAbstractionIds: $capabilityIds
                ) {
                    graph {
                        selectedCapabilityAbstractions {
                            id
                            componentArtifact
                        }
                    }
                }
            }
        '''
        # Select entries from two different techniques in a single save.
        response = self.query(
            mutation,
            variables={
                "graphId": str(self.graph.id),
                "capabilityIds": [str(self.org_entry.id), str(self.org_entry_other_technique.id)],
            },
        )
        self.assertResponseNoErrors(response)
        self.graph.refresh_from_db()
        selected = set(self.graph.selected_capability_abstractions.values_list("component_artifact", flat=True))
        self.assertIn("mshta child process chain", selected)
        self.assertIn("powershell.exe", selected)

    def test_multi_technique_selections_survive_incremental_save_and_reload(self):
        """Selections added from a second technique must be merged with existing
        selections and still be present after reloading the workbench graph."""
        update_mutation = '''
            mutation UpdateWorkbenchCapabilities(
                $graphId: UUID!,
                $capabilityIds: [UUID!]
            ) {
                updatePlaybookDetails(
                    graphId: $graphId,
                    selectedCapabilityAbstractionIds: $capabilityIds
                ) {
                    graph {
                        id
                        selectedCapabilityAbstractions {
                            id
                        }
                    }
                }
            }
        '''
        graph_query = '''
            query ReloadWorkbench($graphId: UUID!) {
                playbookGraph(id: $graphId) {
                    selectedCapabilityAbstractions {
                        componentArtifact
                        technique {
                            techniqueId
                        }
                    }
                }
            }
        '''

        response = self.query(
            update_mutation,
            variables={
                "graphId": str(self.graph.id),
                "capabilityIds": [str(self.shared_entry.id), str(self.org_entry.id)],
            },
        )
        self.assertResponseNoErrors(response)

        response = self.query(
            update_mutation,
            variables={
                "graphId": str(self.graph.id),
                "capabilityIds": [
                    str(self.shared_entry.id),
                    str(self.org_entry.id),
                    str(self.org_entry_other_technique.id),
                ],
            },
        )
        self.assertResponseNoErrors(response)

        response = self.query(graph_query, variables={"graphId": str(self.graph.id)})
        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]["playbookGraph"]["selectedCapabilityAbstractions"]

        selected = {
            (item["componentArtifact"], item["technique"]["techniqueId"])
            for item in payload
        }
        self.assertEqual(
            selected,
            {
                ("mshta.exe", "T1218.005"),
                ("mshta child process chain", "T1218.005"),
                ("powershell.exe", "T1059.001"),
            },
        )
