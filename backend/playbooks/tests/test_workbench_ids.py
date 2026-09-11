import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene_django.utils.testing import GraphQLTestCase

from organizations.models import Organization
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph, WorkbenchIdCounter


class WorkbenchIdModelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.organization = Organization.objects.create(name="WB ID Org")
        self.user = User.objects.create_user(
            username="wbid-user",
            password="password",
            organization=self.organization,
            role="ANALYST",
        )

    def _numeric_id(self, custom_id: str) -> int:
        return int(custom_id[2:])

    def test_new_workbench_gets_id_without_mitre_technique(self):
        first = PlaybookGraph.objects.create(
            title="No Technique Yet",
            organization=self.organization,
            author=self.user,
        )
        second = PlaybookGraph.objects.create(
            title="Still No Technique",
            organization=self.organization,
            author=self.user,
        )

        self.assertRegex(first.custom_id or "", r"^DE\d{6}$")
        self.assertRegex(second.custom_id or "", r"^DE\d{6}$")
        self.assertEqual(self._numeric_id(second.custom_id), self._numeric_id(first.custom_id) + 1)
        self.assertEqual(
            WorkbenchIdCounter.objects.get(singleton_key=1).next_value,
            self._numeric_id(second.custom_id) + 1,
        )

    def test_deleted_workbench_id_is_not_reused(self):
        first = PlaybookGraph.objects.create(
            title="To Delete",
            organization=self.organization,
            author=self.user,
        )
        first_number = self._numeric_id(first.custom_id)
        first.delete()

        second = PlaybookGraph.objects.create(
            title="After Delete",
            organization=self.organization,
            author=self.user,
        )
        second_number = self._numeric_id(second.custom_id)

        self.assertGreater(second_number, first_number)
        self.assertEqual(second_number, first_number + 1)


class WorkbenchIdGraphQLTests(GraphQLTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.organization = Organization.objects.create(name="WB ID GraphQL Org")
        self.user = User.objects.create_user(
            username="wbid-graphql-user",
            password="password",
            organization=self.organization,
            role="ANALYST",
        )
        self.client.force_login(self.user)

        self.technique_a = MitreAttackTechnique.objects.create(
            technique_id="T1001",
            stix_id="attack-pattern--wbid-a",
            name="Data Obfuscation",
            description="Technique A",
            url="https://example.com/t1001",
        )
        self.technique_b = MitreAttackTechnique.objects.create(
            technique_id="T1003",
            stix_id="attack-pattern--wbid-b",
            name="Credential Dumping",
            description="Technique B",
            url="https://example.com/t1003",
        )
        self.graph = PlaybookGraph.objects.create(
            title="Technique Swap Workbench",
            organization=self.organization,
            author=self.user,
            mitre_technique=self.technique_a,
        )

    def test_updating_technique_does_not_change_custom_id(self):
        initial_id = self.graph.custom_id

        mutation = """
            mutation UpdateTechnique($graphId: UUID!, $mitreTechniqueId: String) {
                updatePlaybookDetails(
                    graphId: $graphId,
                    mitreTechniqueId: $mitreTechniqueId
                ) {
                    graph {
                        id
                        customId
                        mitreTechnique { techniqueId }
                    }
                }
            }
        """
        response = self.query(
            mutation,
            variables={
                "graphId": str(self.graph.id),
                "mitreTechniqueId": self.technique_b.technique_id,
            },
        )
        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]["updatePlaybookDetails"]["graph"]

        self.graph.refresh_from_db()
        self.assertEqual(payload["customId"], initial_id)
        self.assertEqual(self.graph.custom_id, initial_id)
        self.assertEqual(self.graph.mitre_technique_id, self.technique_b.id)

    def test_create_workbench_auto_prefixes_title_with_custom_id(self):
        mutation = """
            mutation CreateWorkbench($title: String!) {
                createPlaybookGraph(title: $title) {
                    graph {
                        id
                        title
                        customId
                    }
                }
            }
        """
        response = self.query(
            mutation,
            variables={"title": "[esel][app] This is test rule"},
        )
        self.assertResponseNoErrors(response)
        graph_payload = json.loads(response.content)["data"]["createPlaybookGraph"]["graph"]
        expected_prefix = f"[{graph_payload['customId']}]"
        self.assertTrue(graph_payload["title"].startswith(expected_prefix))
        self.assertEqual(
            graph_payload["title"],
            f"{expected_prefix}[esel][app] This is test rule",
        )

    def test_superuser_without_org_can_create_when_single_org_exists(self):
        User = get_user_model()
        superuser = User.objects.create_user(
            username="wbid-superuser-no-org",
            password="password",
            organization=None,
            role="VIEWER",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(superuser)

        mutation = """
            mutation CreateWorkbench($title: String!) {
                createPlaybookGraph(title: $title) {
                    graph {
                        id
                        title
                    }
                }
            }
        """
        response = self.query(
            mutation,
            variables={"title": "Superuser fallback workbench"},
        )
        self.assertResponseNoErrors(response)
        graph_id = json.loads(response.content)["data"]["createPlaybookGraph"]["graph"]["id"]
        created_graph = PlaybookGraph.objects.get(pk=graph_id)
        self.assertEqual(created_graph.organization_id, self.organization.id)

    def test_rename_keeps_custom_id_prefix_non_editable(self):
        mutation = """
            mutation RenameWorkbench($id: UUID!, $title: String!) {
                updatePlaybookGraphTitle(id: $id, title: $title) {
                    playbookGraph {
                        id
                        title
                        customId
                    }
                }
            }
        """
        response = self.query(
            mutation,
            variables={
                "id": str(self.graph.id),
                "title": "[DE999999]Renamed suffix",
            },
        )
        self.assertResponseNoErrors(response)
        graph_payload = json.loads(response.content)["data"]["updatePlaybookGraphTitle"]["playbookGraph"]

        self.graph.refresh_from_db()
        expected_title = f"[{self.graph.custom_id}]Renamed suffix"
        self.assertEqual(graph_payload["title"], expected_title)
        self.assertEqual(self.graph.title, expected_title)

    def test_rename_collapses_repeated_prefixes_to_single_id(self):
        mutation = """
            mutation RenameWorkbench($id: UUID!, $title: String!) {
                updatePlaybookGraphTitle(id: $id, title: $title) {
                    playbookGraph {
                        id
                        title
                        customId
                    }
                }
            }
        """
        repeated = f"[{self.graph.custom_id}][{self.graph.custom_id}][{self.graph.custom_id}]Test"
        response = self.query(
            mutation,
            variables={"id": str(self.graph.id), "title": repeated},
        )
        self.assertResponseNoErrors(response)
        graph_payload = json.loads(response.content)["data"]["updatePlaybookGraphTitle"]["playbookGraph"]
        expected_title = f"[{self.graph.custom_id}]Test"
        self.assertEqual(graph_payload["title"], expected_title)
