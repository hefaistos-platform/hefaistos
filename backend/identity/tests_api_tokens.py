from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_jwt.shortcuts import get_token
from rest_framework.test import APIClient

from organizations.models import Organization
from identity.models import PersonalAPIToken


class PersonalAPITokenApiTests(TestCase):
    """Personal API token issuance/list/revoke mechanism tests.

    No scopes are currently allow-listed (ALLOWED_PERSONAL_API_SCOPES is empty —
    see identity/api_views.py for why: waiting_room:create was retired). These
    tests exercise the mechanism itself using a locally-declared test-only scope
    via monkeypatching, so the mechanism stays covered even with zero real scopes.
    """

    def setUp(self):
        user_model = get_user_model()
        self.org = Organization.objects.create(name='Token Org')
        self.user = user_model.objects.create_user(
            username='token-user',
            email='token-user@example.com',
            password='TokenPass123!',
            organization=self.org,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        from identity import api_views
        self._original_scopes = api_views.ALLOWED_PERSONAL_API_SCOPES
        api_views.ALLOWED_PERSONAL_API_SCOPES = {'test:scope'}
        self.addCleanup(setattr, api_views, 'ALLOWED_PERSONAL_API_SCOPES', self._original_scopes)

    def test_create_list_and_revoke_personal_token(self):
        create_response = self.client.post(
            '/api/profile/tokens',
            {
                'name': 'KQL Striker',
                'scopes': ['test:scope'],
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)
        raw_token = create_response.data.get('token')
        token_meta = create_response.data.get('token_meta') or {}

        self.assertTrue(str(raw_token).startswith(PersonalAPIToken.TOKEN_PREFIX))
        token_obj = PersonalAPIToken.objects.get(id=token_meta['id'])
        self.assertNotEqual(token_obj.token_hash, raw_token)
        self.assertEqual(token_meta['status'], 'active')

        list_response = self.client.get('/api/profile/tokens')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertNotIn('token', list_response.data[0])

        revoke_response = self.client.post(f"/api/profile/tokens/{token_meta['id']}/revoke", format='json')
        self.assertEqual(revoke_response.status_code, 200)
        self.assertEqual(revoke_response.data['status'], 'revoked')

        token_obj.refresh_from_db()
        self.assertIsNotNone(token_obj.revoked_at)

    def test_create_rejects_invalid_scope(self):
        response = self.client.post(
            '/api/profile/tokens',
            {
                'name': 'Bad Token',
                'scopes': ['not-a-real-scope'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_profile_tokens_accepts_graphql_jwt(self):
        raw_jwt = get_token(self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + raw_jwt)

        create_response = client.post(
            '/api/profile/tokens',
            {
                'name': 'GraphQL JWT token',
                'scopes': ['test:scope'],
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)

        list_response = client.get('/api/profile/tokens')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)

    def test_profile_tokens_accepts_forwarded_authorization_header(self):
        raw_jwt = get_token(self.user)
        client = APIClient()
        client.credentials(HTTP_X_HEFAISTOS_AUTHORIZATION='Bearer ' + raw_jwt)

        list_response = client.get('/api/profile/tokens')
        self.assertEqual(list_response.status_code, 200)
