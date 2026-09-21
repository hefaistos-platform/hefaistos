from time import time
from unittest.mock import MagicMock, patch

import jwt
from django.test import RequestFactory, TestCase

from identity.models import AuthProviderSettings
from identity.oidc import _OIDC_TOKEN_CLOCK_SKEW_SECONDS, complete_code_exchange
from organizations.models import Organization


class OidcTokenValidationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="OIDC Token Validation Org")
        self.settings_obj = AuthProviderSettings.objects.create(
            singleton_key="oidc-token-validation",
            organization=self.org,
            enable_oidc=True,
            oidc_issuer_url="https://issuer.example.com",
            oidc_client_id="client-id",
            oidc_client_secret="client-secret",
            oidc_redirect_uri="https://app.example.com/auth/oidc/callback",
        )
        self.request = RequestFactory().get("/graphql")

    def _token_response(self, id_token="id-token"):
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"id_token": id_token}
        return token_response

    @patch("identity.oidc._get_signing_key_from_jwks")
    @patch("identity.oidc.requests.post")
    @patch("identity.oidc._get_discovery_document")
    @patch("identity.oidc._verify_signed_state")
    def test_complete_code_exchange_passes_clock_skew_leeway(
        self,
        mock_verify_state,
        mock_discovery,
        mock_post,
        mock_signing_key,
    ):
        mock_verify_state.return_value = {
            "provider": "oidc",
            "nonce": "nonce-1",
            "organization_id": str(self.org.id),
        }
        mock_discovery.return_value = {
            "token_endpoint": "https://issuer.example.com/token",
            "jwks_uri": "https://issuer.example.com/jwks",
            "issuer": "https://issuer.example.com",
        }
        mock_post.return_value = self._token_response()
        mock_signing_key.return_value = object()

        with patch("identity.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = {"nonce": "nonce-1", "exp": int(time()) + 300}
            complete_code_exchange(request=self.request, code="auth-code", state="state")

        self.assertEqual(
            mock_decode.call_args.kwargs["leeway"],
            _OIDC_TOKEN_CLOCK_SKEW_SECONDS,
        )

    @patch("identity.oidc._get_signing_key_from_jwks")
    @patch("identity.oidc.requests.post")
    @patch("identity.oidc._get_discovery_document")
    @patch("identity.oidc._verify_signed_state")
    def test_complete_code_exchange_accepts_iat_skew_within_leeway(
        self,
        mock_verify_state,
        mock_discovery,
        mock_post,
        mock_signing_key,
    ):
        mock_verify_state.return_value = {
            "provider": "oidc",
            "nonce": "nonce-2",
            "organization_id": str(self.org.id),
        }
        mock_discovery.return_value = {
            "token_endpoint": "https://issuer.example.com/token",
            "jwks_uri": "https://issuer.example.com/jwks",
            "issuer": "https://issuer.example.com",
        }
        mock_post.return_value = self._token_response()
        mock_signing_key.return_value = object()

        def _decode_with_skew_acceptance(*args, **kwargs):
            if kwargs.get("leeway", 0) >= 120:
                return {"nonce": "nonce-2", "exp": int(time()) + 300}
            raise jwt.ImmatureSignatureError("The token is not yet valid (iat)")

        with patch("identity.oidc.jwt.decode", side_effect=_decode_with_skew_acceptance):
            provider, _, _, _ = complete_code_exchange(
                request=self.request,
                code="auth-code",
                state="state",
            )

        self.assertEqual(provider, "oidc")

    @patch("identity.oidc._get_signing_key_from_jwks")
    @patch("identity.oidc.requests.post")
    @patch("identity.oidc._get_discovery_document")
    @patch("identity.oidc._verify_signed_state")
    def test_complete_code_exchange_rejects_iat_beyond_leeway(
        self,
        mock_verify_state,
        mock_discovery,
        mock_post,
        mock_signing_key,
    ):
        mock_verify_state.return_value = {
            "provider": "oidc",
            "nonce": "nonce-3",
            "organization_id": str(self.org.id),
        }
        mock_discovery.return_value = {
            "token_endpoint": "https://issuer.example.com/token",
            "jwks_uri": "https://issuer.example.com/jwks",
            "issuer": "https://issuer.example.com",
        }
        mock_post.return_value = self._token_response()
        mock_signing_key.return_value = object()

        with patch(
            "identity.oidc.jwt.decode",
            side_effect=jwt.ImmatureSignatureError("The token is not yet valid (iat)"),
        ):
            with self.assertRaises(jwt.ImmatureSignatureError):
                complete_code_exchange(request=self.request, code="auth-code", state="state")
