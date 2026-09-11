from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.decorators import Roles
from identity.models import AuthProviderSettings
from identity.schema import _find_or_create_sso_user
from organizations.models import Organization


User = get_user_model()


class OidcRoleSyncTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="OIDC Role Sync Org")
        self.settings_obj = AuthProviderSettings.objects.create(
            singleton_key="oidc-role-sync",
            organization=self.org,
            sync_claims_on_login=True,
            default_provisioned_role=Roles.VIEWER,
            role_admin_values="ADMIN",
            role_analyst_values="ANALYST",
            role_reviewer_values="REVIEWER",
        )

    def test_existing_user_role_is_preserved_when_claim_not_mapped(self):
        user = User.objects.create_user(
            username="existing-analyst",
            email="existing-analyst@example.com",
            role=Roles.ANALYST,
            organization=self.org,
            default_organization=self.org,
        )

        _find_or_create_sso_user(
            identity_data={
                "email": user.email,
                "username": user.username,
                "role_value": None,
            },
            claims={},
            settings_obj=self.settings_obj,
            target_org=self.org,
        )

        user.refresh_from_db()
        self.assertEqual(user.role, Roles.ANALYST)

    def test_existing_user_role_is_updated_when_claim_is_mapped(self):
        user = User.objects.create_user(
            username="existing-analyst-2",
            email="existing-analyst-2@example.com",
            role=Roles.ANALYST,
            organization=self.org,
            default_organization=self.org,
        )

        _find_or_create_sso_user(
            identity_data={
                "email": user.email,
                "username": user.username,
                "role_value": "ADMIN",
            },
            claims={},
            settings_obj=self.settings_obj,
            target_org=self.org,
        )

        user.refresh_from_db()
        self.assertEqual(user.role, Roles.ADMIN)

    def test_new_user_gets_default_role_when_claim_not_mapped(self):
        user = _find_or_create_sso_user(
            identity_data={
                "email": "new-user@example.com",
                "username": "new-user",
                "role_value": None,
            },
            claims={},
            settings_obj=self.settings_obj,
            target_org=self.org,
        )

        self.assertEqual(user.role, Roles.VIEWER)
