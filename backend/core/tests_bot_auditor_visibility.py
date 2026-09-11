import json

from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase

from ach.models import ACHAnalysis
from advops.models import ADVOPSReport
from news.models import NewsPost
from organizations.models import Organization
from playbooks.models import PlaybookGraph, L1PortalEntry


class BotAuditorReadVisibilityTests(GraphQLTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()

        self.org_a = Organization.objects.create(name="Org A")
        self.org_b = Organization.objects.create(name="Org B")

        self.user_a = User.objects.create_user(
            username="author-a",
            password="password",
            organization=self.org_a,
            role="ADMIN",
        )
        self.user_b = User.objects.create_user(
            username="author-b",
            password="password",
            organization=self.org_b,
            role="ADMIN",
        )

        self.bot_org = User.objects.create_user(
            username="bot-org",
            password="password",
            organization=self.org_a,
            role="BOT_AUDITOR_ORG",
        )
        self.bot_global = User.objects.create_user(
            username="bot-global",
            password="password",
            organization=None,
            role="BOT_AUDITOR_GLOBAL",
        )

        PlaybookGraph.objects.create(
            title="Graph A",
            organization=self.org_a,
            author=self.user_a,
            status="DEPLOYED",
            is_shared=False,
        )
        graph_b = PlaybookGraph.objects.create(
            title="Graph B",
            organization=self.org_b,
            author=self.user_b,
            status="DEPLOYED",
            is_shared=False,
        )
        graph_a = PlaybookGraph.objects.get(title="Graph A")

        L1PortalEntry.objects.create(
            graph=graph_a,
            organization=self.org_a,
            title="L1 A",
            response_playbook="RP A",
            known_false_positives="KFP A",
            blind_spots_coverage_gaps="BS A",
        )
        L1PortalEntry.objects.create(
            graph=graph_b,
            organization=self.org_b,
            title="L1 B",
            response_playbook="RP B",
            known_false_positives="KFP B",
            blind_spots_coverage_gaps="BS B",
        )

        ACHAnalysis.objects.create(
            title="ACH A",
            description="A",
            owner=self.user_a,
            status="RESEARCH",
        )
        ACHAnalysis.objects.create(
            title="ACH B",
            description="B",
            owner=self.user_b,
            status="RESEARCH",
        )

        ADVOPSReport.objects.create(
            hunt_id="ADV-2099-01-001",
            hypothesis="Hunt A",
            author=self.user_a,
            organization=self.org_a,
            status=ADVOPSReport.Status.IDEA,
        )
        ADVOPSReport.objects.create(
            hunt_id="ADV-2099-01-002",
            hypothesis="Hunt B",
            author=self.user_b,
            organization=self.org_b,
            status=ADVOPSReport.Status.IDEA,
        )
        NewsPost.objects.create(
            title="Draft A",
            content="Draft news A",
            author=self.user_a,
            is_published=False,
            category="ANNOUNCEMENT",
            priority="MEDIUM",
        )
        NewsPost.objects.create(
            title="Draft B",
            content="Draft news B",
            author=self.user_b,
            is_published=False,
            category="ANNOUNCEMENT",
            priority="MEDIUM",
        )

    def _query_counts(self):
        query = """
            query BotVisibility {
                allPlaybookGraphs { id }
                achAnalyses { id }
                allAdvopsReports { id }
                l1PortalEntries(limit: 200) { id }
                allNews(includeExpired: true, includeUnpublished: true, limit: 200) { id }
            }
        """
        response = self.query(query)
        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]
        return (
            len(payload["allPlaybookGraphs"]),
            len(payload["achAnalyses"]),
            len(payload["allAdvopsReports"]),
            len(payload["l1PortalEntries"]),
            len(payload["allNews"]),
        )

    def test_org_bot_sees_platform_scoped_items(self):
        self.client.force_login(self.bot_org)
        graph_count, ach_count, advops_count, l1_count, news_count = self._query_counts()
        self.assertEqual(graph_count, 2)
        self.assertEqual(ach_count, 2)
        self.assertEqual(advops_count, 2)
        self.assertEqual(l1_count, 2)
        self.assertEqual(news_count, 2)

    def test_global_bot_sees_platform_scoped_items(self):
        self.client.force_login(self.bot_global)
        graph_count, ach_count, advops_count, l1_count, news_count = self._query_counts()
        self.assertEqual(graph_count, 2)
        self.assertEqual(ach_count, 2)
        self.assertEqual(advops_count, 2)
        self.assertEqual(l1_count, 2)
        self.assertEqual(news_count, 2)
