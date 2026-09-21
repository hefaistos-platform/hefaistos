from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from organizations.models import Organization, OrganizationBillingProfile
from unittest.mock import MagicMock, patch
from io import StringIO
import pyotp
import json

from identity.models import AccountSetupToken, UserMfaSettings, UserOrganizationMembership, AuthProviderSettings
from identity.schema import (
    InviteUser,
    PrepareAccountActivation,
    CompleteAccountActivation,
    StartMfaLogin,
    StartOidcLogin,
    SubmitRegistrationRequest,
    UpdateProfile,
)
from identity.decorators import role_required, Roles
from core.schema import schema
from django.test import RequestFactory

User = get_user_model()


def _make_info(user):
    """Build a minimal GraphQL info mock with the given user on its context."""
    info = MagicMock()
    info.context.user = user
    return info


def _dummy_func(*args, **kwargs):
    return "ok"


class CustomUserModelTests(TestCase):

    def setUp(self):
        """
        Set up a test organization to be used by all tests.
        """
        self.organization = Organization.objects.create(name="Test Organization")

    def test_create_user(self):
        """
        Tests that a user can be created and linked to an organization.
        """
        user = User.objects.create_user(
            username="testuser",
            email="normal@user.com",
            password="foo",
            organization=self.organization
        )
        self.assertEqual(user.email, "normal@user.com")
        self.assertEqual(user.organization.name, "Test Organization")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class RoleRequiredDecoratorTests(TestCase):
    """Tests for the role_required decorator — org-scoped admin vs platform admins."""

    def setUp(self):
        self.org = Organization.objects.create(name="Decorator Test Org")

    def _make_user(self, role=Roles.VIEWER, is_superuser=False, is_staff=False, username="tester"):
        user = User(username=username, role=role, is_superuser=is_superuser, is_staff=is_staff, organization=self.org)
        user.is_anonymous = False
        return user

    def test_admin_role_allowed(self):
        """A user with ADMIN role passes the org-scoped check."""
        user = self._make_user(role=Roles.ADMIN)
        info = _make_info(user)
        wrapped = role_required([Roles.ADMIN])(_dummy_func)
        result = wrapped(info)
        self.assertEqual(result, "ok")

    def test_non_admin_role_denied(self):
        """A user with VIEWER role is denied access to an ADMIN-only mutation."""
        user = self._make_user(role=Roles.VIEWER)
        info = _make_info(user)
        wrapped = role_required([Roles.ADMIN])(_dummy_func)
        with self.assertRaises(PermissionDenied):
            wrapped(info)

    def test_bot_auditor_denied_even_if_role_allowed(self):
        """Bot auditor roles are hard read-only and denied from role-gated writes."""
        user = self._make_user(role=Roles.BOT_AUDITOR_ORG)
        info = _make_info(user)
        wrapped = role_required([Roles.BOT_AUDITOR_ORG, Roles.ADMIN])(_dummy_func)
        with self.assertRaises(PermissionDenied):
            wrapped(info)

    def test_bot_auditor_allowed_for_query_operation(self):
        """Bot auditor roles can call role-gated QUERY resolvers (read-only visibility)."""
        user = self._make_user(role=Roles.BOT_AUDITOR_ORG)
        info = _make_info(user)
        info.operation = MagicMock()
        info.operation.operation = "query"
        wrapped = role_required([Roles.ADMIN])(_dummy_func)
        self.assertEqual(wrapped(info), "ok")

    def test_superuser_bypasses_role_check(self):
        """A superuser (platform admin) bypasses org-scoped role checks regardless of their role field."""
        user = self._make_user(role=Roles.VIEWER, is_superuser=True)
        info = _make_info(user)
        wrapped = role_required([Roles.ADMIN])(_dummy_func)
        result = wrapped(info)
        self.assertEqual(result, "ok")

    def test_staff_bypasses_role_check(self):
        """A staff member (platform admin) bypasses org-scoped role checks regardless of their role field."""
        user = self._make_user(role=Roles.ANALYST, is_staff=True)
        info = _make_info(user)
        wrapped = role_required([Roles.ADMIN])(_dummy_func)
        result = wrapped(info)
        self.assertEqual(result, "ok")

    def test_anonymous_user_denied(self):
        """Anonymous users are always denied."""
        anon = MagicMock()
        anon.is_anonymous = True
        info = _make_info(anon)
        wrapped = role_required([Roles.ADMIN])(_dummy_func)
        with self.assertRaises(PermissionDenied):
            wrapped(info)


class AccountSetupFlowTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Activation Org")
        self.admin = User.objects.create_user(
            username="orgadmin",
            email="admin@example.com",
            password="AdminPass123!",
            role=Roles.ADMIN,
            organization=self.org,
        )

    def _make_info(self, user=None):
        info = MagicMock()
        if user is not None:
            info.context.user = user
        info.context.META = {"REMOTE_ADDR": "127.0.0.1"}
        return info

    @patch("identity.schema.emit_security_event")
    @patch("core.email_service.get_email_service")
    def test_invite_user_creates_unusable_password_and_setup_token(self, mock_get_email_service, _mock_emit):
        service = MagicMock()
        service.is_configured.return_value = False
        mock_get_email_service.return_value = service

        info = self._make_info(self.admin)
        result = InviteUser.mutate(
            None,
            info,
            username="newuser",
            email="newuser@example.com",
            role=Roles.ANALYST,
        )

        created = User.objects.get(username="newuser")
        self.assertFalse(created.has_usable_password())
        self.assertEqual(AccountSetupToken.objects.filter(user=created, used=False).count(), 1)
        self.assertIsNotNone(result.setup_link)
        self.assertIn("activate-account?token=", result.setup_link)

    @patch("identity.schema.emit_security_event")
    def test_admin_activation_requires_totp_and_enables_mfa(self, _mock_emit):
        invited = User.objects.create_user(
            username="newadmin",
            email="newadmin@example.com",
            role=Roles.ADMIN,
            organization=self.org,
        )
        invited.set_unusable_password()
        invited.save(update_fields=["password"])

        _token_obj, raw_token = AccountSetupToken.issue_for_user(user=invited, created_by=self.admin, hours_valid=24)

        public_info = self._make_info()
        prepared = PrepareAccountActivation.mutate(None, public_info, token=raw_token)
        self.assertTrue(prepared.requires_mfa)
        self.assertTrue(prepared.totp_secret)
        otp = pyotp.TOTP(prepared.totp_secret).now()

        completed = CompleteAccountActivation.mutate(
            None,
            public_info,
            token=raw_token,
            new_password="NewAdminPass123!",
            otp_code=otp,
        )
        self.assertTrue(completed.ok)
        self.assertGreater(len(completed.backup_codes), 0)

        invited.refresh_from_db()
        self.assertTrue(invited.check_password("NewAdminPass123!"))

        mfa_settings = UserMfaSettings.objects.get(user=invited)
        self.assertTrue(mfa_settings.totp_enabled)
        self.assertTrue(bool(mfa_settings.totp_secret))
        self.assertEqual(AccountSetupToken.objects.filter(user=invited, used=False).count(), 0)


class OrganizationUserLimitEnforcementTests(TestCase):
    def setUp(self):
        self.full_org = Organization.objects.create(name="Full Org", max_users=2)
        self.source_org = Organization.objects.create(name="Source Org", max_users=10)

        # Fill full_org to capacity
        self.resident = User.objects.create_user(
            username="resident",
            email="resident@example.com",
            password="ResidentPass123!",
            role=Roles.ANALYST,
            organization=self.full_org,
        )

        self.org_admin = User.objects.create_user(
            username="orgadmin_limit",
            email="orgadmin_limit@example.com",
            password="AdminPass123!",
            role=Roles.ADMIN,
            organization=self.full_org,
        )
        self.super_admin = User.objects.create_superuser(
            username="superadmin_limit",
            email="superadmin_limit@example.com",
            password="SuperPass123!",
        )
        self.movable_user = User.objects.create_user(
            username="movable_user",
            email="movable@example.com",
            password="MovePass123!",
            role=Roles.ANALYST,
            organization=self.source_org,
        )

    def test_invite_user_blocked_when_org_is_at_capacity(self):
        info = _make_info(self.org_admin)
        with self.assertRaises(Exception) as ctx:
            InviteUser.mutate(
                None,
                info,
                username="new_limited_user",
                email="new_limited_user@example.com",
                role=Roles.ANALYST,
            )
        self.assertIn("maximum user limit", str(ctx.exception))
        self.assertFalse(User.objects.filter(username="new_limited_user").exists())

    def test_admin_update_user_blocks_move_into_full_org(self):
        info = _make_info(self.super_admin)
        from identity.schema import Mutation as IdentityMutation
        root = IdentityMutation()

        with self.assertRaises(Exception) as ctx:
            root.resolve_admin_update_user(
                info,
                user_id=self.movable_user.id,
                organization_id=self.full_org.id,
            )

        self.assertIn("maximum user limit", str(ctx.exception))
        self.movable_user.refresh_from_db()
        self.assertEqual(self.movable_user.organization_id, self.source_org.id)


class UnlimitedOrganizationUserInviteTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Unlimited Org", max_users=None)
        self.org_admin = User.objects.create_user(
            username="orgadmin_unlimited",
            email="orgadmin_unlimited@example.com",
            password="AdminPass123!",
            role=Roles.ADMIN,
            organization=self.org,
        )
        OrganizationBillingProfile.objects.create(
            organization=self.org,
            included_users=OrganizationBillingProfile.BASE_USERS,
            included_organizations=OrganizationBillingProfile.BASE_ORGANIZATIONS,
        )

    def test_invite_user_allows_unlimited_org_even_with_billing_profile(self):
        info = _make_info(self.org_admin)
        result = InviteUser.mutate(
            None,
            info,
            username="new_unlimited_user",
            email="new_unlimited_user@example.com",
            role=Roles.ANALYST,
        )

        self.assertIsNotNone(result.user)
        self.assertTrue(User.objects.filter(username="new_unlimited_user", organization=self.org).exists())


class BotMfaBypassLoginTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Bot MFA Org")
        self.bot_org = User.objects.create_user(
            username="bot_org_user",
            email="bot_org@example.com",
            password="BotPass123!",
            role=Roles.BOT_AUDITOR_ORG,
            organization=self.org,
        )
        self.bot_global = User.objects.create_user(
            username="bot_global_user",
            email="bot_global@example.com",
            password="BotPass123!",
            role=Roles.BOT_AUDITOR_GLOBAL,
            organization=self.org,
        )

        # Even if MFA is configured, BOT users must not be challenged.
        org_settings, _ = UserMfaSettings.objects.get_or_create(user=self.bot_org)
        org_settings.totp_enabled = True
        org_settings.totp_secret = pyotp.random_base32()
        org_settings.save()

        global_settings, _ = UserMfaSettings.objects.get_or_create(user=self.bot_global)
        global_settings.totp_enabled = True
        global_settings.totp_secret = pyotp.random_base32()
        global_settings.save()

    def _make_login_info(self):
        info = MagicMock()
        info.context = MagicMock()
        info.context.META = {"REMOTE_ADDR": "127.0.0.1"}
        return info

    @patch("identity.schema.emit_security_event")
    def test_org_bot_bypasses_mfa_challenge(self, _mock_emit):
        result = StartMfaLogin.mutate(
            None,
            self._make_login_info(),
            username="bot_org_user",
            password="BotPass123!",
        )
        self.assertFalse(result.mfa_required)
        self.assertIsNone(result.challenge_id)
        self.assertTrue(bool(result.token))

    @patch("identity.schema.emit_security_event")
    def test_global_bot_bypasses_mfa_challenge(self, _mock_emit):
        result = StartMfaLogin.mutate(
            None,
            self._make_login_info(),
            username="bot_global_user",
            password="BotPass123!",
        )
        self.assertFalse(result.mfa_required)
        self.assertIsNone(result.challenge_id)
        self.assertTrue(bool(result.token))


class UpdateProfileSessionTimeoutTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Profile Timeout Org")
        self.user = User.objects.create_user(
            username="profile_user",
            email="profile_user@example.com",
            password="ProfilePass123!",
            role=Roles.ANALYST,
            organization=self.org,
        )

    def test_update_profile_accepts_supported_timeout_value(self):
        info = _make_info(self.user)
        result = UpdateProfile.mutate(None, info, session_timeout_hours=8)

        self.user.refresh_from_db()
        self.assertEqual(self.user.session_timeout_hours, 8)
        self.assertEqual(result.user.session_timeout_hours, 8)

    def test_update_profile_accepts_camel_case_timeout_kwarg(self):
        info = _make_info(self.user)
        result = UpdateProfile.mutate(None, info, sessionTimeoutHours=12)

        self.user.refresh_from_db()
        self.assertEqual(self.user.session_timeout_hours, 12)
        self.assertEqual(result.user.session_timeout_hours, 12)

    def test_update_profile_uses_graphql_variable_values_fallback(self):
        info = _make_info(self.user)
        info.variable_values = {'sessionTimeoutHours': 24}
        result = UpdateProfile.mutate(None, info)

        self.user.refresh_from_db()
        self.assertEqual(self.user.session_timeout_hours, 24)
        self.assertEqual(result.user.session_timeout_hours, 24)

    def test_update_profile_rejects_unsupported_timeout_value(self):
        info = _make_info(self.user)

        with self.assertRaises(Exception) as ctx:
            UpdateProfile.mutate(None, info, session_timeout_hours=6)

        self.assertIn("sessionTimeoutHours", str(ctx.exception))

    def test_graphql_me_returns_session_timeout_as_int(self):
        self.user.session_timeout_hours = 8
        self.user.save(update_fields=['session_timeout_hours'])

        req = RequestFactory().post('/graphql')
        req.user = self.user
        result = schema.execute('{ me { sessionTimeoutHours } }', context_value=req)

        self.assertIsNone(result.errors)
        self.assertEqual(result.data['me']['sessionTimeoutHours'], 8)


class WorkbenchVisibilityDefaultsGraphQLTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Workbench Defaults Org")
        self.user = User.objects.create_user(
            username="workbench_defaults_user",
            email="workbench-defaults@example.com",
            role=Roles.ANALYST,
            organization=self.org,
        )
        self.user.set_password("Pass12345!")
        self.user.save(update_fields=["password"])

    def _make_request(self):
        req = RequestFactory().post('/graphql')
        req.user = self.user
        return req

    def test_update_workbench_visibility_defaults_persists_and_returns_on_me(self):
        mutation = '''
            mutation UpdateWorkbenchDefaults($payload: JSONString) {
                updateWorkbenchVisibilityDefaults(workbenchVisibilityDefaults: $payload) {
                    user {
                        workbenchVisibilityDefaults
                    }
                }
            }
        '''
        payload = '{"sectionVisibility":{"part4":false,"part5":true}}'
        result = schema.execute(
            mutation,
            variable_values={"payload": payload},
            context_value=self._make_request(),
        )
        self.assertIsNone(result.errors)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.workbench_visibility_defaults,
            {"sectionVisibility": {"part4": False, "part5": True}},
        )

        query_result = schema.execute('{ me { workbenchVisibilityDefaults } }', context_value=self._make_request())
        self.assertIsNone(query_result.errors)
        self.assertEqual(
            json.loads(query_result.data['me']['workbenchVisibilityDefaults']),
            {"sectionVisibility": {"part4": False, "part5": True}},
        )

    def test_update_workbench_visibility_defaults_supports_new_section_keys(self):
        """New section keys capabilityMap, capabilityLibrary, activityOverview are accepted and persisted."""
        mutation = '''
            mutation UpdateWorkbenchDefaults($payload: JSONString) {
                updateWorkbenchVisibilityDefaults(workbenchVisibilityDefaults: $payload) {
                    user {
                        workbenchVisibilityDefaults
                    }
                }
            }
        '''
        payload = '{"sectionVisibility":{"capabilityMap":false,"capabilityLibrary":true,"activityOverview":false}}'
        result = schema.execute(
            mutation,
            variable_values={"payload": payload},
            context_value=self._make_request(),
        )
        self.assertIsNone(result.errors)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.workbench_visibility_defaults,
            {"sectionVisibility": {"capabilityMap": False, "capabilityLibrary": True, "activityOverview": False}},
        )

    def test_update_workbench_visibility_defaults_rejects_unknown_section_keys(self):
        """Unknown section keys are silently dropped during normalization."""
        mutation = '''
            mutation UpdateWorkbenchDefaults($payload: JSONString) {
                updateWorkbenchVisibilityDefaults(workbenchVisibilityDefaults: $payload) {
                    user {
                        workbenchVisibilityDefaults
                    }
                }
            }
        '''
        payload = '{"sectionVisibility":{"part4":true,"unknownSection":true}}'
        result = schema.execute(
            mutation,
            variable_values={"payload": payload},
            context_value=self._make_request(),
        )
        self.assertIsNone(result.errors)

        self.user.refresh_from_db()
        # unknownSection should be silently dropped
        self.assertEqual(
            self.user.workbench_visibility_defaults,
            {"sectionVisibility": {"part4": True}},
        )

    def test_reset_workbench_visibility_defaults_clears_payload(self):
        self.user.workbench_visibility_defaults = {"sectionVisibility": {"part4": False}}
        self.user.save(update_fields=["workbench_visibility_defaults"])

        mutation = '''
            mutation {
                updateWorkbenchVisibilityDefaults(reset: true) {
                    user {
                        workbenchVisibilityDefaults
                    }
                }
            }
        '''
        result = schema.execute(mutation, context_value=self._make_request())
        self.assertIsNone(result.errors)

        self.user.refresh_from_db()
        self.assertEqual(self.user.workbench_visibility_defaults, {})


class SubmitRegistrationRequestTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Registration Org")
        self.platform_admin = User.objects.create_superuser(
            username="platform_admin",
            email="platform-admin@example.com",
            password="SuperPass123!",
        )

    @patch("core.email_service.get_email_service")
    def test_submit_registration_request_sends_email_to_platform_admins(self, mock_get_email_service):
        service = MagicMock()
        service.is_configured.return_value = True
        service.send_message.return_value = True
        service.from_email = "noreply@example.com"
        mock_get_email_service.return_value = service

        info = MagicMock()
        info.context = MagicMock()
        info.context.user = MagicMock(is_anonymous=True)
        info.context.META = {"REMOTE_ADDR": "127.0.0.1"}

        result = SubmitRegistrationRequest.mutate(
            None,
            info,
            name="John Doe",
            email="john.doe@example.com",
            subject="Need access",
            message="Please register my account.",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Registration request sent successfully.")


class MultiOrganizationAuthTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Org A")
        self.org_b = Organization.objects.create(name="Org B")
        self.org_c = Organization.objects.create(name="Org C")

        self.user = User.objects.create_user(
            username="multi_org_user",
            email="multi@example.com",
            role=Roles.ANALYST,
            organization=self.org_a,
            default_organization=self.org_a,
        )
        self.login_password = "P" + "ass12345!"
        self.user.set_password(self.login_password)
        self.user.save(update_fields=["password"])
        UserOrganizationMembership.objects.get_or_create(user=self.user, organization=self.org_a)
        UserOrganizationMembership.objects.get_or_create(user=self.user, organization=self.org_b)

    def _request(self, user=None):
        req = RequestFactory().post('/graphql')
        req.user = user or self.user
        req.META = {"REMOTE_ADDR": "127.0.0.1"}
        return req

    def test_switch_active_organization_changes_org_when_member(self):
        mutation = """
            mutation SwitchOrg($orgId: UUID!) {
              switchActiveOrganization(organizationId: $orgId) {
                ok
                activeOrganization { id }
              }
            }
        """
        result = schema.execute(
            mutation,
            variable_values={"orgId": str(self.org_b.id)},
            context_value=self._request(),
        )
        self.assertIsNone(result.errors)
        self.assertTrue(result.data["switchActiveOrganization"]["ok"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.organization_id, self.org_b.id)

    def test_switch_active_organization_rejects_non_member(self):
        mutation = """
            mutation SwitchOrg($orgId: UUID!) {
              switchActiveOrganization(organizationId: $orgId) {
                ok
                message
              }
            }
        """
        result = schema.execute(
            mutation,
            variable_values={"orgId": str(self.org_c.id)},
            context_value=self._request(),
        )
        self.assertIsNotNone(result.errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.organization_id, self.org_a.id)

    @patch("identity.schema.emit_security_event")
    def test_local_login_moves_active_org_to_default(self, _mock_emit):
        self.user.organization = self.org_b
        self.user.default_organization = self.org_a
        self.user.save(update_fields=["organization", "default_organization"])

        info = MagicMock()
        info.context = self._request()
        StartMfaLogin.mutate(
            None,
            info,
            "multi_org_user",
            self.login_password,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.organization_id, self.org_a.id)

    @patch("identity.schema.build_authorization_url")
    def test_start_oidc_login_resolves_org_from_identifier(self, mock_build_authorization_url):
        mock_build_authorization_url.return_value = ("https://example.com/oidc", "ENTRA")
        AuthProviderSettings.objects.update_or_create(
            organization=self.org_a,
            defaults={"singleton_key": "orga-key", "enable_entra": True},
        )
        AuthProviderSettings.objects.update_or_create(
            organization=self.org_b,
            defaults={"singleton_key": "orgb-key", "enable_entra": True},
        )

        info = MagicMock()
        info.context = self._request()
        result = StartOidcLogin.mutate(None, info, provider="ENTRA", identifier="multi@example.com")

        self.assertEqual(result.provider, "ENTRA")
        self.assertEqual(result.authorization_url, "https://example.com/oidc")
        self.assertTrue(mock_build_authorization_url.called)
        service.send_message.assert_called_once()

        kwargs = service.send_message.call_args.kwargs
        self.assertEqual(kwargs["to"], ["platform-admin@example.com"])
        self.assertEqual(kwargs["headers"]["Reply-To"], "john.doe@example.com")


class ResetLocalLoginCommandTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Scoped Auth Org")
        self.user = User.objects.create_user(
            username="hunt3r",
            email="hunt3r@example.com",
            ******,
            organization=self.org,
            default_organization=self.org,
            role=Roles.ADMIN,
        )

    def test_add_username_targets_users_org_settings(self):
        AuthProviderSettings.get_solo()
        org_settings = AuthProviderSettings.get_for_organization(self.org)
        org_settings.enable_oidc = True
        org_settings.auth_mode = AuthProviderSettings.AuthMode.OIDC_ONLY
        org_settings.allow_local_breakglass = False
        org_settings.breakglass_usernames = "admin"
        org_settings.save(
            update_fields=[
                "enable_oidc",
                "auth_mode",
                "allow_local_breakglass",
                "breakglass_usernames",
            ]
        )

        stdout = StringIO()
        call_command("reset_local_login", add_username="hunt3r", stdout=stdout)

        org_settings.refresh_from_db()
        global_settings = AuthProviderSettings.get_solo()
        self.assertEqual(
            org_settings.auth_mode,
            AuthProviderSettings.AuthMode.OIDC_AND_LOCAL_BREAKGLASS,
        )
        self.assertTrue(org_settings.allow_local_breakglass)
        self.assertIn("hunt3r", org_settings.breakglass_usernames_list())
        self.assertFalse(global_settings.enable_oidc)
        self.assertNotIn("hunt3r", global_settings.breakglass_usernames_list())
        self.assertIn("derived from user 'hunt3r'", stdout.getvalue())

    def test_add_username_falls_back_to_global_for_users_without_org(self):
        User.objects.create_user(
            username="globaluser",
            email="global@example.com",
            ******,
        )

        stdout = StringIO()
        call_command("reset_local_login", add_username="globaluser", stdout=stdout)

        global_settings = AuthProviderSettings.get_solo()
        self.assertIn("globaluser", global_settings.breakglass_usernames_list())
        self.assertIn("global (platform-wide)", stdout.getvalue())
