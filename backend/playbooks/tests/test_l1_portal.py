from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase, override_settings

from playbooks.l1_portal import build_l1_portal_share_url, build_l1_portal_title


class BuildL1PortalTitleTests(SimpleTestCase):
    def test_uses_workbench_title_with_pb_suffix_without_plus_sign(self):
        graph = SimpleNamespace(
            title='[DE-T1567-001][P][eSeL][APP][A] Masivni exfiltrace citlivych udaju'
        )

        self.assertEqual(
            build_l1_portal_title(graph),
            '[DE-T1567-001][P][eSeL][APP][A] Masivni exfiltrace citlivych udaju PB',
        )

    def test_falls_back_to_workbench_when_title_is_blank(self):
        graph = SimpleNamespace(title='   ')
        self.assertEqual(build_l1_portal_title(graph), 'Workbench PB')


class BuildL1PortalShareUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(PUBLIC_BASE_URL='https://public.example.org', FRONTEND_URL='https://frontend.example.org')
    def test_prefers_public_base_url(self):
        request = self.factory.get('/graphql', HTTP_HOST='localhost')
        self.assertEqual(
            build_l1_portal_share_url('486121ce-bc1f-4b17-ae34-ee561794496b', request=request),
            'https://public.example.org/l1-portal/486121ce-bc1f-4b17-ae34-ee561794496b',
        )

    @override_settings(PUBLIC_BASE_URL='', FRONTEND_URL='https://detect.example.org')
    def test_prefers_external_frontend_url_over_local_request_host(self):
        request = self.factory.get('/graphql', HTTP_HOST='localhost')
        self.assertEqual(
            build_l1_portal_share_url('486121ce-bc1f-4b17-ae34-ee561794496b', request=request),
            'https://detect.example.org/l1-portal/486121ce-bc1f-4b17-ae34-ee561794496b',
        )

    @override_settings(PUBLIC_BASE_URL='', FRONTEND_URL='"https://detect.example.org"')
    def test_uses_quoted_frontend_url_value(self):
        request = self.factory.get('/graphql', HTTP_HOST='localhost')
        self.assertEqual(
            build_l1_portal_share_url('486121ce-bc1f-4b17-ae34-ee561794496b', request=request),
            'https://detect.example.org/l1-portal/486121ce-bc1f-4b17-ae34-ee561794496b',
        )

    @override_settings(PUBLIC_BASE_URL='', FRONTEND_URL='https://localhost')
    def test_uses_request_host_when_frontend_url_is_local(self):
        request = self.factory.get('/graphql', secure=True, HTTP_HOST='detect.example.org')
        self.assertEqual(
            build_l1_portal_share_url('486121ce-bc1f-4b17-ae34-ee561794496b', request=request),
            'https://detect.example.org/l1-portal/486121ce-bc1f-4b17-ae34-ee561794496b',
        )

    @override_settings(PUBLIC_BASE_URL='', FRONTEND_URL='')
    def test_falls_back_to_relative_path_when_no_base_available(self):
        self.assertEqual(
            build_l1_portal_share_url('486121ce-bc1f-4b17-ae34-ee561794496b', request=None),
            '/l1-portal/486121ce-bc1f-4b17-ae34-ee561794496b',
        )
