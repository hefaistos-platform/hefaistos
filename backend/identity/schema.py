import graphene
import logging
import hashlib
import secrets
import json
import html
import re
from graphene_django import DjangoObjectType
from graphene_file_upload.scalars import Upload
from .models import (
    CustomUser,
    UserOrganizationMembership,
    UserAiCredential,
    PasswordResetToken,
    AccountSetupToken,
    UserMfaSettings,
    MfaLoginChallenge,
    MfaAuditEvent,
    WebAuthnCredential,
    WebAuthnChallenge,
    AuthProviderSettings,
)
from organizations.models import Organization, OrganizationManagerAccess
from .decorators import (
    role_required,
    Roles,
    is_bot_auditor_user,
    is_global_bot_auditor_user,
)
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from django.contrib.auth.signals import user_logged_in
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from graphql_jwt.shortcuts import get_token
import pyotp
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor
from playbooks.models import PlaybookGraph  # Safe import (models only, avoids circular schema import)
from ach.models import ACHAnalysis
from advops.models import ADVOPSReport
from core.mcs_logging import emit_security_event, extract_client_ip
from core.email_templates import get_frontend_base_url
from identity.oidc import (
    OidcAuthError,
    build_authorization_url,
    complete_code_exchange,
)

logger = logging.getLogger(__name__)
SESSION_TIMEOUT_HOURS_ALLOWED = {2, 4, 8, 12, 24}
WORKBENCH_SECTION_KEYS = {'part1', 'part2', 'part3', 'part4', 'part5', 'part6', 'capabilityMap', 'capabilityLibrary', 'activityOverview'}


def _normalize_workbench_visibility_defaults(raw_defaults):
    if raw_defaults is None:
        return {}

    payload = raw_defaults
    if isinstance(raw_defaults, str):
        try:
            payload = json.loads(raw_defaults)
        except json.JSONDecodeError:
            logger.warning("Invalid workbench visibility defaults JSON payload; falling back to empty defaults.")
            return {}

    if not isinstance(payload, dict):
        return {}

    section_visibility = payload.get('sectionVisibility')
    if not isinstance(section_visibility, dict):
        return {}

    normalized_visibility = {}
    for key, value in section_visibility.items():
        normalized_key = str(key).strip() if key else ''
        if normalized_key not in WORKBENCH_SECTION_KEYS:
            continue
        normalized_visibility[normalized_key] = bool(value)

    return {'sectionVisibility': normalized_visibility}

class UserPlaybookGraphLiteType(DjangoObjectType):
    """A lightweight PlaybookGraph representation for embedding in UserType without importing playbooks.schema (avoids circular import)."""
    robustnessLevel = graphene.Int(source='robustness_level')

    class Meta:
        model = PlaybookGraph
        fields = ('id', 'title', 'status', 'updated_at', 'robustness_level')

class UserACHAnalysisLiteType(DjangoObjectType):
    """Lite ACH Analysis representation."""
    class Meta:
        model = ACHAnalysis
        fields = ('id', 'title', 'status', 'updated_at')

class UserADVOPSReportLiteType(DjangoObjectType):
    """Lite ADVOPS Report representation."""
    class Meta:
        model = ADVOPSReport
        fields = ('id', 'hunt_id', 'hypothesis', 'status', 'priority', 'created_at')

class UserType(DjangoObjectType):
    avatar_url = graphene.String(description="Absolute URL to the user's avatar image (if set).")
    session_timeout_hours = graphene.Int(description="Auto-logout timeout in hours.")
    created_playbooks = graphene.List(UserPlaybookGraphLiteType, description="Playbook graphs authored by the user (latest first).")
    ach_analyses = graphene.List(UserACHAnalysisLiteType, description="ACH Analyses created by the user.")
    advops_reports = graphene.List(UserADVOPSReportLiteType, description="ADVOPS Reports created by the user.")
    active_organization = graphene.Field(lambda: OrganizationSummaryType)
    default_organization = graphene.Field(lambda: OrganizationSummaryType)

    # Expose AbstractUser fields needed by UserManagementPage
    lastLogin = graphene.DateTime(source='last_login', description="Timestamp of last successful login.")
    isStaff = graphene.Boolean(source='is_staff', description="True if user has Django staff privileges.")
    isSuperuser = graphene.Boolean(source='is_superuser', description="True if user is a Django superuser.")

    class Meta:
        model = CustomUser
        # Use 'fields' ONLY (omit password) to avoid Graphene assertion (cannot set both fields & exclude).
        # Note: 'avatar' is NOT included here because we use a computed resolver 'avatar_url' instead.
        fields = (
            'id', 'username', 'email', 'role', 'bio', 'job_title', 'slack_handle', 'session_timeout_hours', 'organization',
            'email_notify_review_approved',
            'email_notify_system_message',
            'email_notify_chat_message',
            'email_notify_workbench_edited',
            'email_notify_news_digest',
            'workbench_visibility_defaults',
        )

    def resolve_avatar_url(self, info):
        if getattr(self, 'avatar', None):
            try:
                # MEDIA_URL is relative ('/media/'), so build_absolute_uri correctly
                # resolves to the actual host/port the client is using (via
                # X-Forwarded-Host + SECURE_PROXY_SSL_HEADER set in settings).
                url = info.context.build_absolute_uri(self.avatar.url)
            except Exception:
                url = self.avatar.url
            # Attempt cache-busting with modified timestamp
            try:
                storage = self.avatar.storage
                ts = storage.get_modified_time(self.avatar.name).timestamp()
                return f"{url}?v={int(ts)}"
            except Exception:
                return url
        return None

    def resolve_session_timeout_hours(self, info):
        value = getattr(self, 'session_timeout_hours', None)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 4

    def resolve_created_playbooks(self, info):
        # Filter by author (self) – ordered by most recently updated
        return PlaybookGraph.objects.filter(author=self).order_by('-updated_at')

    def resolve_ach_analyses(self, info):
        return ACHAnalysis.objects.filter(owner=self).order_by('-created_at')

    def resolve_advops_reports(self, info):
        return ADVOPSReport.objects.filter(author=self).order_by('-created_at')

    def resolve_active_organization(self, info):
        org = getattr(self, 'organization', None)
        if not org:
            return None
        return OrganizationSummaryType(
            id=org.id,
            name=org.name,
            is_default=bool(getattr(self, 'default_organization_id', None) == org.id),
            is_active=True,
        )

    def resolve_default_organization(self, info):
        org = getattr(self, 'default_organization', None)
        if not org:
            return None
        return OrganizationSummaryType(
            id=org.id,
            name=org.name,
            is_default=True,
            is_active=bool(getattr(self, 'organization_id', None) == org.id),
        )

    id = graphene.String()  # Change from graphene.ID to String

    @staticmethod
    def resolve_id(obj, info):
        """Convert UUID to string."""
        return str(obj.id) if obj.id else None


class AuthSettingsType(graphene.ObjectType):
    auth_mode = graphene.String()
    default_login_provider = graphene.String()
    enable_entra = graphene.Boolean()
    enable_oidc = graphene.Boolean()
    allow_local_breakglass = graphene.Boolean()
    auto_provision_users = graphene.Boolean()
    sync_claims_on_login = graphene.Boolean()
    enforce_local_mfa = graphene.Boolean()
    breakglass_usernames = graphene.String()
    entra_tenant_id = graphene.String()
    entra_client_id = graphene.String()
    has_entra_client_secret = graphene.Boolean()
    entra_redirect_uri = graphene.String()
    entra_scopes = graphene.String()
    entra_email_claim = graphene.String()
    entra_username_claim = graphene.String()
    entra_role_claim = graphene.String()
    oidc_issuer_url = graphene.String()
    oidc_client_id = graphene.String()
    has_oidc_client_secret = graphene.Boolean()
    oidc_redirect_uri = graphene.String()
    oidc_scopes = graphene.String()
    oidc_email_claim = graphene.String()
    oidc_username_claim = graphene.String()
    oidc_role_claim = graphene.String()
    oidc_verify_ssl = graphene.Boolean()
    has_oidc_ca_certificate = graphene.Boolean()
    role_admin_values = graphene.String()
    role_analyst_values = graphene.String()
    role_reviewer_values = graphene.String()
    default_provisioned_role = graphene.String()
    updated_at = graphene.DateTime()


class PublicAuthOptionsType(graphene.ObjectType):
    auth_mode = graphene.String(required=True)
    default_login_provider = graphene.String(required=True)
    enable_entra = graphene.Boolean(required=True)
    enable_oidc = graphene.Boolean(required=True)
    show_local_login = graphene.Boolean(required=True)


class PublicAuthOrganizationType(graphene.ObjectType):
    id = graphene.UUID(required=True)
    name = graphene.String(required=True)
    enable_entra = graphene.Boolean(required=True)
    enable_oidc = graphene.Boolean(required=True)
    default_login_provider = graphene.String(required=True)


class OrganizationSummaryType(graphene.ObjectType):
    id = graphene.UUID(required=True)
    name = graphene.String(required=True)
    is_default = graphene.Boolean(required=True)
    is_active = graphene.Boolean(required=True)


def _can_manage_auth_settings(user) -> bool:
    if not user or user.is_anonymous:
        return False
    if is_bot_auditor_user(user):
        return False
    return bool(
        getattr(user, 'is_superuser', False)
        or getattr(user, 'is_staff', False)
        or getattr(user, 'role', None) == Roles.ADMIN
    )


def _local_login_visible(settings_obj: AuthProviderSettings) -> bool:
    if not settings_obj.enable_entra and not settings_obj.enable_oidc:
        return True
    return bool(settings_obj.allow_local_breakglass)


def _public_auth_options(settings_obj: AuthProviderSettings) -> PublicAuthOptionsType:
    return PublicAuthOptionsType(
        auth_mode=settings_obj.auth_mode,
        default_login_provider=settings_obj.default_login_provider,
        enable_entra=bool(settings_obj.enable_entra),
        enable_oidc=bool(settings_obj.enable_oidc),
        show_local_login=_local_login_visible(settings_obj),
    )


def _sync_membership_for_user_org(user, organization):
    if not user or not organization:
        return
    UserOrganizationMembership.objects.get_or_create(user=user, organization=organization)


def _ordered_user_organizations(user):
    if not user or getattr(user, 'is_anonymous', True):
        return []
    rows = list(
        UserOrganizationMembership.objects.select_related('organization')
        .filter(user=user)
        .order_by('organization__name')
    )
    organizations = [row.organization for row in rows if row.organization]
    if user.organization and all(org.id != user.organization_id for org in organizations):
        organizations.append(user.organization)
    if user.default_organization and all(org.id != user.default_organization_id for org in organizations):
        organizations.append(user.default_organization)
    return organizations


def _ensure_user_default_and_active_organization(user):
    if not user or getattr(user, 'is_anonymous', True):
        return
    if user.organization:
        _sync_membership_for_user_org(user, user.organization)
    if user.default_organization:
        _sync_membership_for_user_org(user, user.default_organization)

    organizations = _ordered_user_organizations(user)
    if not organizations:
        changed = []
        if user.organization_id is not None:
            user.organization = None
            changed.append('organization')
        if user.default_organization_id is not None:
            user.default_organization = None
            changed.append('default_organization')
        if changed:
            user.save(update_fields=changed)
        return

    org_ids = {org.id for org in organizations}
    changed = []
    if not user.default_organization_id or user.default_organization_id not in org_ids:
        user.default_organization = user.organization if user.organization_id in org_ids else organizations[0]
        changed.append('default_organization')
    if not user.organization_id or user.organization_id not in org_ids:
        user.organization = user.default_organization
        changed.append('organization')
    if changed:
        user.save(update_fields=changed)


def _resolve_org_from_login_identifier(identifier: str):
    normalized = (identifier or '').strip()
    if not normalized:
        return None

    user = CustomUser.objects.select_related('default_organization', 'organization').filter(
        Q(username__iexact=normalized) | Q(email__iexact=normalized)
    ).first()
    if not user:
        return None
    _ensure_user_default_and_active_organization(user)
    return user.default_organization or user.organization


class Query(graphene.ObjectType):
    me = graphene.Field(UserType)
    all_users_in_org = graphene.List(UserType)
    my_ai_credentials = graphene.List(graphene.String, description="Providers with configured AI keys for current user.")
    mfa_status = graphene.Field(lambda: MfaStatusType)
    my_webauthn_credentials = graphene.List(lambda: WebAuthnCredentialType)
    auth_settings = graphene.Field(AuthSettingsType)
    public_auth_options = graphene.Field(
        PublicAuthOptionsType,
        organization_id=graphene.UUID(required=False),
    )
    public_auth_organizations = graphene.List(PublicAuthOrganizationType)
    my_organizations = graphene.List(OrganizationSummaryType)

    def resolve_all_users_in_org(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # Global bot auditors can enumerate users platform-wide for evaluation.
        if is_global_bot_auditor_user(user):
            return CustomUser.objects.all().order_by('username')

        # Default security: return users only from caller organization.
        return CustomUser.objects.filter(organization=user.organization)

    def resolve_my_ai_credentials(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        return [c.provider for c in UserAiCredential.objects.filter(user=user)]

    def resolve_mfa_status(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        settings_obj, _ = UserMfaSettings.objects.get_or_create(user=user)
        webauthn_count = WebAuthnCredential.objects.filter(user=user).count()
        return MfaStatusType(
            enabled=bool((settings_obj.totp_enabled and settings_obj.totp_secret) or webauthn_count > 0),
            totp_enabled=bool(settings_obj.totp_enabled and settings_obj.totp_secret),
            pending_enrollment=bool(settings_obj.pending_totp_secret),
            backup_codes_remaining=len(settings_obj.backup_codes_hashes or []),
            locked_until=settings_obj.locked_until,
            webauthn_keys=webauthn_count,
            admin_mfa_required=_mfa_required_for_user(user),
        )

    def resolve_my_webauthn_credentials(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        return WebAuthnCredential.objects.filter(user=user).order_by('-created_at')

    def resolve_me(self, info):
        """
        Resolve the current authenticated user.
        The JWT middleware should set user on info.context.
        """
        try:
            # info.context is the request object (graphql-jwt middleware sets it)
            request = info.context
            
            # If context is a dict (shouldn't happen with jwt middleware, but be safe)
            if isinstance(request, dict):
                request = request.get('request')
            
            # Get the user from the request
            if not request:
                raise Exception("No request context available")
                
            user = getattr(request, 'user', None)
            
            if not user:
                raise Exception("No user in request context")
                
            if user.is_anonymous:
                raise Exception("User is not authenticated")

            logger.info(f"resolve_me: User authenticated as {user.username}")
            # Return a fresh DB instance so profile fields edited in previous
            # requests are reflected immediately.
            fresh_user = CustomUser.objects.filter(pk=user.pk).first()
            if fresh_user:
                _ensure_user_default_and_active_organization(fresh_user)
            return fresh_user or user
            
        except AttributeError as e:
            logger.error(f"AttributeError in resolve_me: {str(e)}")
            raise Exception(f"Context error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in resolve_me: {str(e)}")
            raise

    def resolve_auth_settings(self, info):
        user = info.context.user
        if not _can_manage_auth_settings(user):
            raise Exception("Permission denied")
        return AuthProviderSettings.resolve_for_user(user)

    def resolve_public_auth_options(self, info, organization_id=None):
        settings_obj = AuthProviderSettings.resolve_for_org_id(organization_id) if organization_id else AuthProviderSettings.get_solo()
        if settings_obj is None:
            settings_obj = AuthProviderSettings.get_solo()
        return _public_auth_options(settings_obj)

    def resolve_public_auth_organizations(self, info):
        rows = (
            AuthProviderSettings.objects.select_related('organization')
            .filter(organization__isnull=False)
            .order_by('organization__name')
        )
        result = []
        for row in rows:
            if not (row.enable_entra or row.enable_oidc or row.allow_local_breakglass):
                continue
            if not row.organization:
                continue
            result.append(
                PublicAuthOrganizationType(
                    id=row.organization.id,
                    name=row.organization.name,
                    enable_entra=bool(row.enable_entra),
                    enable_oidc=bool(row.enable_oidc),
                    default_login_provider=row.default_login_provider,
                )
            )
        return result

    def resolve_my_organizations(self, info):
        user = info.context.user
        if not user or user.is_anonymous:
            raise Exception("Authentication required")
        _ensure_user_default_and_active_organization(user)
        organizations = _ordered_user_organizations(user)
        return [
            OrganizationSummaryType(
                id=org.id,
                name=org.name,
                is_default=bool(user.default_organization_id and org.id == user.default_organization_id),
                is_active=bool(user.organization_id and org.id == user.organization_id),
            )
            for org in organizations
        ]

def _frontend_url(path: str, request=None) -> str:
    base = get_frontend_base_url(request=request).rstrip('/')
    safe_path = path if path.startswith('/') else f'/{path}'
    if not base:
        return safe_path
    return f"{base}{safe_path}"


def _issue_account_setup_link(target_user, caller_user, request=None):
    AccountSetupToken.objects.filter(user=target_user, used=False).delete()
    _, raw_token = AccountSetupToken.issue_for_user(user=target_user, created_by=caller_user, hours_valid=24)
    return _frontend_url(f"/activate-account?token={raw_token}", request=request)


def _allowed_roles_for_assignment(caller):
    roles = [
        Roles.ADMIN,
        Roles.RESOURCE_MANAGER,
        Roles.ANALYST,
        Roles.REVIEWER,
        Roles.VIEWER,
        Roles.ELONE,
        Roles.BOT_AUDITOR_ORG,
    ]
    if getattr(caller, 'is_superuser', False) or getattr(caller, 'is_staff', False):
        roles.append(Roles.BOT_AUDITOR_GLOBAL)
    return roles


def _enforce_organization_user_limit(organization):
    if not organization:
        return
    max_users = getattr(organization, 'max_users', None)
    if max_users is None:
        return
    current_members = CustomUser.objects.filter(organization=organization).count()
    if current_members >= max_users:
        raise Exception(
            f"Organization '{organization.name}' has reached its maximum user limit ({max_users})."
        )


class InviteUser(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)
        email = graphene.String(required=True)
        role = graphene.String(required=True)
        organization_id = graphene.UUID(required=False)

    user = graphene.Field(UserType)
    message = graphene.String()
    setup_link = graphene.String()

    class Meta:
        description = "Creates (invites) a new user in the Admin's organization without sending any temporary password."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.RESOURCE_MANAGER])
    def mutate(root, info, username, email, role, organization_id=None):
        caller = info.context.user

        if role == Roles.BOT_AUDITOR_GLOBAL and not (caller.is_superuser or caller.is_staff):
            raise Exception("Only platform admins can assign BOT_AUDITOR_GLOBAL.")

        allowed_roles = _allowed_roles_for_assignment(caller)
        if role not in allowed_roles:
            raise Exception(f"Invalid role. Must be one of: {Roles.labels}")

        target_org = caller.organization
        if organization_id is not None:
            if (not caller.is_superuser and not caller.is_staff) and not OrganizationManagerAccess.objects.filter(
                user=caller,
                organization_id=organization_id,
            ).exists() and str(caller.organization_id) != str(organization_id):
                raise Exception('Permission denied to invite into this organization.')
            target_org = Organization.objects.filter(pk=organization_id).first()
            if not target_org:
                raise Exception('Organization not found.')

        if target_org and target_org.id:
            with transaction.atomic():
                locked_org = Organization.objects.select_for_update().get(pk=target_org.id)
                _enforce_organization_user_limit(locked_org)
                new_user = CustomUser(
                    username=(username or '').strip(),
                    email=(email or '').strip(),
                    role=role,
                    organization=locked_org,
                    default_organization=locked_org,
                )
                new_user.set_unusable_password()
                new_user.save()
                _sync_membership_for_user_org(new_user, locked_org)
        else:
            new_user = CustomUser(
                username=(username or '').strip(),
                email=(email or '').strip(),
                role=role,
                organization=target_org,
                default_organization=target_org,
            )
            new_user.set_unusable_password()
            new_user.save()
            _sync_membership_for_user_org(new_user, target_org)

        setup_url = _issue_account_setup_link(target_user=new_user, caller_user=caller, request=info.context)
        setup_link_to_return = None

        try:
            from core.email_service import get_email_service
            service = get_email_service(organization=caller.organization)
            if service.is_configured() and new_user.email:
                org_name = caller.organization.name if caller.organization else 'HEFAISTOS'
                mfa_note = (
                    "\nBecause this account has ADMIN role, setup includes mandatory MFA enrollment."
                    if role == Roles.ADMIN
                    else ""
                )
                service.send_message(
                    to=[new_user.email],
                    subject=f'Welcome to {org_name} - Complete Your HEFAISTOS Account Setup',
                    text=f"""Hello {new_user.username},

You have been invited to join {org_name} on HEFAISTOS.

Account details:
- Username: {new_user.username}
- Role: {role}
- Organization: {org_name}

Complete your account setup using this one-time secure link (valid for 24 hours):

{setup_url}
{mfa_note}

If you did not expect this invitation, please ignore this email.

Best regards,
The HEFAISTOS Team""",
                    html=f"""<html><body>
<h2>Welcome to {org_name}</h2>
<p>Hello <strong>{new_user.username}</strong>,</p>
<p>You have been invited to join <strong>{org_name}</strong> on HEFAISTOS.</p>
<h3>Account details:</h3>
<ul>
<li><strong>Username:</strong> {new_user.username}</li>
<li><strong>Role:</strong> {role}</li>
<li><strong>Organization:</strong> {org_name}</li>
</ul>
<p>Complete your account setup using this one-time secure link (valid for 24 hours):</p>
<p><a href="{setup_url}" style="color:#2563eb;text-decoration:underline">{setup_url}</a></p>
{"<p><strong>Because this account has ADMIN role, setup includes mandatory MFA enrollment.</strong></p>" if role == Roles.ADMIN else ""}
<p>If you did not expect this invitation, please ignore this email.</p>
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>""",
                )
                logger.info(f"Sent account setup invitation email to {new_user.username} at {new_user.email}")
            else:
                setup_link_to_return = setup_url
        except Exception as e:
            logger.error(f"Failed to send account setup invitation email to {new_user.email}: {e}")
            setup_link_to_return = setup_url

        return InviteUser(
            user=new_user,
            message="Invitation created. Setup link sent by email when email service is configured.",
            setup_link=setup_link_to_return,
        )


class PrepareAccountActivation(graphene.Mutation):
    class Arguments:
        token = graphene.String(required=True)

    username = graphene.String(required=True)
    email = graphene.String(required=True)
    role = graphene.String(required=True)
    requires_mfa = graphene.Boolean(required=True)
    totp_secret = graphene.String()
    otpauth_uri = graphene.String()
    expires_at = graphene.DateTime(required=True)

    @staticmethod
    def mutate(root, info, token):
        setup_token = AccountSetupToken.from_raw_token(token)
        if not setup_token:
            raise Exception("Invalid or already-used activation token.")
        if setup_token.is_expired():
            raise Exception("This activation token has expired. Ask your administrator for a new invitation.")

        target = setup_token.user
        requires_mfa = target.role == Roles.ADMIN
        totp_secret = None
        otpauth_uri = None

        if requires_mfa:
            settings_obj, _ = UserMfaSettings.objects.get_or_create(user=target)
            has_mfa = _has_mfa_method(target, settings_obj)
            requires_mfa = not has_mfa
            if requires_mfa:
                pending_secret = settings_obj.pending_totp_secret
                if not pending_secret:
                    pending_secret = pyotp.random_base32()
                    settings_obj.pending_totp_secret = pending_secret
                    settings_obj.save(update_fields=['pending_totp_secret_encrypted', 'updated_at'])
                totp_secret = pending_secret
                otpauth_uri = pyotp.TOTP(pending_secret).provisioning_uri(
                    name=target.username,
                    issuer_name="HEFAISTOS",
                )

        return PrepareAccountActivation(
            username=target.username,
            email=target.email or '',
            role=target.role,
            requires_mfa=requires_mfa,
            totp_secret=totp_secret,
            otpauth_uri=otpauth_uri,
            expires_at=setup_token.expires_at,
        )


class CompleteAccountActivation(graphene.Mutation):
    class Arguments:
        token = graphene.String(required=True)
        new_password = graphene.String(required=True)
        otp_code = graphene.String(required=False)

    ok = graphene.Boolean(required=True)
    message = graphene.String()
    backup_codes = graphene.List(graphene.String, required=True)

    @staticmethod
    def mutate(root, info, token, new_password, otp_code=None):
        setup_token = AccountSetupToken.from_raw_token(token)
        if not setup_token:
            raise Exception("Invalid or already-used activation token.")
        if setup_token.is_expired():
            raise Exception("This activation token has expired. Ask your administrator for a new invitation.")

        target = setup_token.user
        try:
            validate_password(new_password, user=target)
        except ValidationError as e:
            raise Exception(f"Password validation failed: {', '.join(e.messages)}")

        backup_codes = []
        source_ip = extract_client_ip(info.context)
        with transaction.atomic():
            token_hash = AccountSetupToken.hash_token(token)
            locked_token = AccountSetupToken.objects.select_for_update().select_related('user').filter(
                token_hash=token_hash,
                used=False,
            ).first()
            if not locked_token:
                raise Exception("Invalid or already-used activation token.")
            if locked_token.is_expired():
                raise Exception("This activation token has expired. Ask your administrator for a new invitation.")

            target = locked_token.user
            if target.role == Roles.ADMIN:
                mfa_settings, _ = UserMfaSettings.objects.get_or_create(user=target)
                has_mfa = _has_mfa_method(target, mfa_settings)
                if not has_mfa:
                    pending_secret = mfa_settings.pending_totp_secret
                    if not pending_secret:
                        raise Exception("MFA enrollment is required for this administrator account.")
                    if not pyotp.TOTP(pending_secret).verify((otp_code or '').strip(), valid_window=1):
                        raise Exception("Invalid MFA verification code")
                    backup_codes = _generate_backup_codes()
                    mfa_settings.totp_secret = pending_secret
                    mfa_settings.pending_totp_secret = ''
                    mfa_settings.totp_enabled = True
                    mfa_settings.backup_codes_hashes = _hash_backup_codes(backup_codes)
                    mfa_settings.backup_codes_generated_at = timezone.now()
                    mfa_settings.failed_attempts = 0
                    mfa_settings.locked_until = None
                    mfa_settings.save()
                    MfaAuditEvent.objects.create(
                        user=target,
                        event=MfaAuditEvent.Event.TOTP_ENROLL_CONFIRMED,
                        details={"source": "account_activation"},
                    )

            target.set_password(new_password)
            target.save(update_fields=['password'])
            AccountSetupToken.objects.filter(pk=locked_token.pk).update(
                used=True,
                used_at=timezone.now(),
            )

        target_user_id, target_user_name = _user_identity(target)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=f"User '{target_user_name}' completed account activation.",
            event_action='user_password_change_success',
            event_outcome='success',
            asvs_event_code='AUTHN-CHANGE-PASS-OK-01',
            event_category=['authentication'],
            event_type=['end', 'success'],
            user_id=target_user_id,
            user_name=target_user_name,
            source_ip=source_ip,
            request=info.context,
            http_status_code=200,
        )
        return CompleteAccountActivation(
            ok=True,
            message="Account setup completed successfully. You can now log in.",
            backup_codes=backup_codes,
        )

# Add this class
class DeleteUser(graphene.Mutation):
    class Arguments:
        user_id = graphene.ID(required=True)

    ok = graphene.Boolean()

    class Meta:
        description = "Deletes a user from the Admin's organization."

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, user_id):
        user = info.context.user

        # --- Security Check 1: Can't delete yourself ---
        if str(user.id) == user_id:
            raise Exception("You cannot delete your own account.")

        # --- Security Check 2: Find user *in your org* ---
        try:
            user_to_delete = CustomUser.objects.get(
                pk=user_id, 
                organization=user.organization
            )
        except CustomUser.DoesNotExist:
            raise Exception("User not found in your organization.")

        # --- Security Check 3: Don't delete service accounts? (Optional)
        if "svc" in user_to_delete.username:
            raise Exception("Cannot delete service accounts from this UI.")

        user_to_delete.delete()
        return DeleteUser(ok=True)

class UploadAvatar(graphene.Mutation):
    class Arguments:
        file = Upload(required=True)

    user = graphene.Field(UserType)

    @staticmethod
    def mutate(root, info, file, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")
        content_type = getattr(file, 'content_type', '')
        if content_type and not content_type.startswith('image/'):
            raise Exception('Invalid file type. Please upload an image.')
        size = getattr(file, 'size', None)
        if size and size > 2 * 1024 * 1024:
            raise Exception('Avatar exceeds 2MB size limit.')
        name = getattr(file, 'name', 'avatar')
        ext = name.split('.')[-1].lower() if '.' in name else 'png'
        safe_ext = ext if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp'] else 'png'
        filename = f"avatar_{user.id}.{safe_ext}"
        try:
            from PIL import Image
            from io import BytesIO
            from django.core.files.base import ContentFile
            if hasattr(file, 'seek'):
                file.seek(0)
            img = Image.open(file)
            img.load()  # Force Pillow to fully decode the image now so the file
                        # pointer is at the end before we start processing, making
                        # the except-block fallback safe to seek(0) and re-read
            save_format = 'PNG' if safe_ext == 'png' else 'JPEG'
            # JPEG does not support alpha; always convert to RGB for JPEG output
            if save_format == 'JPEG':
                if img.mode != 'RGB':
                    img = img.convert('RGB')
            else:
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
            max_size = 256
            w, h = img.size
            if w < h:
                new_w = max_size
                new_h = int(h * (max_size / w))
            else:
                new_h = max_size
                new_w = int(w * (max_size / h))
            img = img.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - max_size) // 2
            top = (new_h - max_size) // 2
            img = img.crop((left, top, left + max_size, top + max_size))
            buffer = BytesIO()
            img.save(buffer, format=save_format, optimize=True)
            buffer.seek(0)
            user.avatar.save(filename, ContentFile(buffer.read()), save=True)
        except Exception:
            # Fallback: save original file; seek to beginning first since Pillow
            # may have advanced the file pointer during processing
            if hasattr(file, 'seek'):
                file.seek(0)
            user.avatar.save(filename, file, save=True)
        return UploadAvatar(user=user)


class UpdateProfile(graphene.Mutation):
    """Allows authenticated users to update their profile information."""
    class Arguments:
        bio = graphene.String()
        job_title = graphene.String()
        slack_handle = graphene.String()
        # Explicit GraphQL argument name for reliability across schema configurations.
        session_timeout_hours = graphene.Int(name='sessionTimeoutHours')

    user = graphene.Field(
        UserType,
        description="Updated user profile with new bio, job_title, slack_handle, and session_timeout_hours.",
    )

    @staticmethod
    def mutate(root, info, bio=None, job_title=None, slack_handle=None, session_timeout_hours=None, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        if session_timeout_hours is None and 'sessionTimeoutHours' in kwargs:
            session_timeout_hours = kwargs.get('sessionTimeoutHours')
        if session_timeout_hours is None and 'session_timeout_hours' in kwargs:
            session_timeout_hours = kwargs.get('session_timeout_hours')
        # Final fallback: read directly from GraphQL variables payload.
        if session_timeout_hours is None:
            try:
                variable_values = getattr(info, 'variable_values', None) or {}
                if isinstance(variable_values, dict):
                    session_timeout_hours = variable_values.get('sessionTimeoutHours', variable_values.get('session_timeout_hours'))
            except Exception:
                session_timeout_hours = None

        changed_fields = []
        requested_timeout_hours = None
        if bio is not None and bio != user.bio:
            user.bio = bio
            changed_fields.append('bio')
        if job_title is not None and job_title != user.job_title:
            user.job_title = job_title
            changed_fields.append('job_title')
        if slack_handle is not None and slack_handle != user.slack_handle:
            user.slack_handle = slack_handle
            changed_fields.append('slack_handle')
        if session_timeout_hours is not None:
            try:
                parsed_hours = int(session_timeout_hours)
            except (TypeError, ValueError):
                raise Exception("sessionTimeoutHours must be one of: 2, 4, 8, 12, 24")
            if parsed_hours not in SESSION_TIMEOUT_HOURS_ALLOWED:
                raise Exception("sessionTimeoutHours must be one of: 2, 4, 8, 12, 24")
            requested_timeout_hours = parsed_hours

        if changed_fields:
            user.save(update_fields=changed_fields)
        if requested_timeout_hours is not None:
            # Use direct queryset update for reliability across auth/user wrappers.
            rows_updated = CustomUser.objects.filter(pk=user.pk).update(
                session_timeout_hours=requested_timeout_hours,
            )
            if rows_updated != 1:
                raise Exception("Failed to persist sessionTimeoutHours. Please try again.")
            user.refresh_from_db(fields=['session_timeout_hours'])
            if int(user.session_timeout_hours) != int(requested_timeout_hours):
                raise Exception("Failed to persist sessionTimeoutHours. Please try again.")

        return UpdateProfile(user=user)


class UpdateWorkbenchVisibilityDefaults(graphene.Mutation):
    class Arguments:
        workbench_visibility_defaults = graphene.JSONString(name='workbenchVisibilityDefaults')
        reset = graphene.Boolean(default_value=False)

    user = graphene.Field(UserType)

    @staticmethod
    def mutate(root, info, workbench_visibility_defaults=None, reset=False):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Not logged in")

        if not reset and workbench_visibility_defaults is None:
            raise Exception("workbenchVisibilityDefaults must be provided when reset is false")

        normalized_defaults = {} if reset else _normalize_workbench_visibility_defaults(workbench_visibility_defaults)
        user.workbench_visibility_defaults = normalized_defaults
        user.save(update_fields=['workbench_visibility_defaults'])
        return UpdateWorkbenchVisibilityDefaults(user=user)


class ChangePassword(graphene.Mutation):
    """Allows authenticated users to change their own password."""
    class Arguments:
        current_password = graphene.String(required=True, description="User's current password for verification")
        new_password = graphene.String(required=True, description="New password to set")

    ok = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, current_password, new_password):
        user = info.context.user
        source_ip = extract_client_ip(info.context)
        if user.is_anonymous:
            raise Exception("Authentication required")
        
        # Verify current password
        if not user.check_password(current_password):
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"Password change denied for user '{user_name}' from IP {source_ip}: current password mismatch.",
                event_action='user_password_change_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-PRIMARY-01',
                event_reason='Current password verification failed.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=info.context,
                http_status_code=401,
            )
            raise Exception("Current password is incorrect")
        
        # Validate new password using Django's validators
        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            raise Exception(f"Password validation failed: {', '.join(e.messages)}")
        
        # Set the new password
        user.set_password(new_password)
        user.save(update_fields=['password'])
        user_id, user_name = _user_identity(user)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=f"User '{user_name}' successfully changed their password.",
            event_action='user_password_change_success',
            event_outcome='success',
            asvs_event_code='AUTHN-CHANGE-PASS-OK-01',
            event_category=['authentication'],
            event_type=['end', 'success'],
            user_id=user_id,
            user_name=user_name,
            source_ip=source_ip,
            request=info.context,
            http_status_code=200,
        )
        
        # Send password change confirmation email
        try:
            from core.email_service import get_email_service
            from core.email_templates import login_link_text, login_link_html
            service = get_email_service(organization=user.organization)
            if service.is_configured() and user.email:
                from django.utils import timezone
                service.send_message(
                    to=[user.email],
                    subject='Password Changed - HEFAISTOS',
                    text=f"""Hello {user.username},

Your password was successfully changed on {timezone.now().strftime('%Y-%m-%d at %H:%M UTC')}.

If you did not make this change, please contact your administrator immediately.

{login_link_text()}

Best regards,
The HEFAISTOS Team""",
                    html=f"""<html><body>
<h2>Password Changed</h2>
<p>Hello <strong>{user.username}</strong>,</p>
<p>Your password was successfully changed on <strong>{timezone.now().strftime('%Y-%m-%d at %H:%M UTC')}</strong>.</p>
<p><strong>If you did not make this change, please contact your administrator immediately.</strong></p>
{login_link_html()}
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
                )
                logger.info(f"Sent password change confirmation email to {user.username}")
        except Exception as e:
            logger.error(f"Failed to send password change email to {user.email}: {e}")
        
        logger.info(f"Password changed successfully for user: {user.username}")
        return ChangePassword(ok=True, message="Password changed successfully")


class UpdateNotificationPreferences(graphene.Mutation):
    class Arguments:
        emailNotifyReviewApproved = graphene.Boolean()
        emailNotifySystemMessage = graphene.Boolean()
        emailNotifyChatMessage = graphene.Boolean()
        emailNotifyWorkbenchEdited = graphene.Boolean()
        emailNotifyNewsDigest = graphene.Boolean()

    user = graphene.Field(UserType)

    class Meta:
        description = "Updates email notification preferences for the current user."

    @staticmethod
    def mutate(root, info, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        changed = []
        mapping = {
            'emailNotifyReviewApproved': 'email_notify_review_approved',
            'emailNotifySystemMessage': 'email_notify_system_message',
            'emailNotifyChatMessage': 'email_notify_chat_message',
            'emailNotifyWorkbenchEdited': 'email_notify_workbench_edited',
            'emailNotifyNewsDigest': 'email_notify_news_digest',
        }
        for arg_key, field_name in mapping.items():
            if arg_key in kwargs and kwargs[arg_key] is not None:
                setattr(user, field_name, bool(kwargs[arg_key]))
                changed.append(field_name)
        if changed:
            user.save(update_fields=changed)
        return UpdateNotificationPreferences(user=user)

class UserAiCredentialType(DjangoObjectType):
    class Meta:
        model = UserAiCredential
        fields = ("id", "provider", "created_at", "updated_at")

class SetUserAiKey(graphene.Mutation):
    class Arguments:
        provider = graphene.String(required=True)
        api_key = graphene.String(required=True)

    credential = graphene.Field(UserAiCredentialType)

    @staticmethod
    def mutate(root, info, provider, api_key):
        import hashlib
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        provider_norm = provider.strip().lower()
        if provider_norm not in [p.value for p in UserAiCredential.Provider]:
            raise Exception("Unsupported provider")
        fingerprint = hashlib.sha256(api_key.encode('utf-8')).hexdigest()
        cred, _ = UserAiCredential.objects.update_or_create(
            user=user,
            provider=provider_norm,
            defaults={
                'encrypted_key': api_key,
                'key_fingerprint': fingerprint,
            }
        )
        return SetUserAiKey(credential=cred)

class DeleteUserAiKey(graphene.Mutation):
    class Arguments:
        provider = graphene.String(required=True)

    ok = graphene.Boolean()

    @staticmethod
    def mutate(root, info, provider):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        provider_norm = provider.strip().lower()
        UserAiCredential.objects.filter(user=user, provider=provider_norm).delete()
        return DeleteUserAiKey(ok=True)


class MfaStatusType(graphene.ObjectType):
    enabled = graphene.Boolean(required=True)
    totp_enabled = graphene.Boolean(required=True)
    pending_enrollment = graphene.Boolean(required=True)
    backup_codes_remaining = graphene.Int(required=True)
    locked_until = graphene.DateTime()
    webauthn_keys = graphene.Int(required=True)
    admin_mfa_required = graphene.Boolean(required=True)


def _mfa_required_for_user(user):
    return getattr(user, 'role', None) == Roles.ADMIN


def _should_bypass_mfa_for_user(user):
    """Bot auditor accounts are non-interactive and must authenticate with username/password only."""
    return is_bot_auditor_user(user)


def _has_mfa_method(user, settings_obj):
    has_totp = bool(settings_obj.totp_enabled and settings_obj.totp_secret)
    has_webauthn = WebAuthnCredential.objects.filter(user=user).exists()
    return has_totp or has_webauthn


def _get_webauthn_rp_id():
    return getattr(settings, 'WEBAUTHN_RP_ID', None) or "localhost"


def _get_webauthn_origin():
    configured = getattr(settings, 'WEBAUTHN_ORIGIN', None)
    if configured:
        return configured
    frontend_url = get_frontend_base_url()
    if frontend_url:
        return frontend_url.rstrip('/')
    return "http://localhost:3000"


def _user_identity(user):
    if not user:
        return "anonymous", None
    user_id = getattr(user, 'id', None)
    return (str(user_id) if user_id else "anonymous"), getattr(user, 'username', None)


def _parse_claim_values(claim_value):
    if claim_value is None:
        return []
    if isinstance(claim_value, list):
        return [str(item).strip() for item in claim_value if str(item).strip()]
    text = str(claim_value).strip()
    if not text:
        return []
    if ',' in text:
        return [part.strip() for part in text.split(',') if part.strip()]
    return [text]


def _map_role_from_claims(
    settings_obj: AuthProviderSettings,
    role_claim_value,
    apply_default_fallback: bool = True,
):
    values = {item.lower() for item in _parse_claim_values(role_claim_value)}
    admin_values = {item.lower() for item in settings_obj.role_admin_values_list()}
    analyst_values = {item.lower() for item in settings_obj.role_analyst_values_list()}
    reviewer_values = {item.lower() for item in settings_obj.role_reviewer_values_list()}

    if values & admin_values:
        return Roles.ADMIN
    if values & analyst_values:
        return Roles.ANALYST
    if values & reviewer_values:
        return Roles.REVIEWER
    if apply_default_fallback:
        return settings_obj.default_provisioned_role or Roles.VIEWER
    return None


def _sanitize_username(candidate: str) -> str:
    raw = (candidate or "").strip()
    if not raw:
        raw = "user"
    cleaned = re.sub(r"[^A-Za-z0-9@.+\-_]+", "_", raw)
    cleaned = cleaned.strip("._-")
    if not cleaned:
        cleaned = "user"
    return cleaned[:150]


def _resolve_sso_identity(claims: dict, config, provider: str):
    email_claim = str(getattr(config, 'email_claim', '') or '').strip()
    username_claim = str(getattr(config, 'username_claim', '') or '').strip()
    role_claim = str(getattr(config, 'role_claim', '') or '').strip()

    email = str(claims.get(email_claim) or '').strip() if email_claim else ''
    if not email:
        email = str(claims.get('preferred_username') or claims.get('upn') or claims.get('email') or '').strip()

    username_raw = str(claims.get(username_claim) or '').strip() if username_claim else ''
    if not username_raw:
        username_raw = email
    if not username_raw:
        username_raw = str(claims.get('name') or '').strip()
    if not username_raw:
        username_raw = f"{provider}_{str(claims.get('sub') or 'user')[:24]}"

    username = _sanitize_username(username_raw)
    role_value = claims.get(role_claim) if role_claim else claims.get('roles')
    return {
        'email': email,
        'username': username,
        'role_value': role_value,
    }


def _find_or_create_sso_user(identity_data: dict, claims: dict, settings_obj: AuthProviderSettings, target_org: Organization | None):
    email = (identity_data.get('email') or '').strip()
    username = _sanitize_username(identity_data.get('username') or '')
    role_value = identity_data.get('role_value')

    if target_org is None:
        target_org = settings_obj.organization
    if target_org is None:
        target_org = Organization.objects.order_by('created_at').first()

    user = None
    if email:
        user = CustomUser.objects.filter(email__iexact=email, organization=target_org).first()
    if not user and username:
        user = CustomUser.objects.filter(username__iexact=username, organization=target_org).first()

    provisioned_role = _map_role_from_claims(settings_obj, role_value, apply_default_fallback=True)
    mapped_role = _map_role_from_claims(settings_obj, role_value, apply_default_fallback=False)

    if user is None:
        if not settings_obj.auto_provision_users:
            raise Exception("User is not provisioned in HEFAISTOS and auto-provision is disabled.")

        if not target_org:
            raise Exception("No organization is available for auto-provisioned users.")

        base_username = username
        suffix = 1
        while CustomUser.objects.filter(username__iexact=username, organization=target_org).exists():
            suffix += 1
            username = _sanitize_username(f"{base_username}_{suffix}")

        user = CustomUser(
            username=username,
            email=email,
            organization=target_org,
            default_organization=target_org,
            role=provisioned_role or settings_obj.default_provisioned_role or Roles.VIEWER,
        )
        user.set_unusable_password()
        user.save()
        _sync_membership_for_user_org(user, target_org)
        return user

    if settings_obj.sync_claims_on_login:
        changed = []
        if email and user.email != email:
            user.email = email
            changed.append('email')
        if not user.is_superuser and not user.is_staff and mapped_role and user.role != mapped_role:
            user.role = mapped_role
            changed.append('role')
        if changed:
            user.save(update_fields=changed)
    _sync_membership_for_user_org(user, target_org)
    _ensure_user_default_and_active_organization(user)

    return user


def _is_local_login_allowed_for_user(user, settings_obj: AuthProviderSettings) -> bool:
    if not settings_obj.enable_entra and not settings_obj.enable_oidc:
        return True

    if settings_obj.auth_mode == AuthProviderSettings.AuthMode.ENTRA_AND_LOCAL_BREAKGLASS:
        if not settings_obj.allow_local_breakglass:
            return False
        allowed = settings_obj.breakglass_usernames_list()
        username = (getattr(user, 'username', '') or '').strip().lower()
        if getattr(user, 'is_superuser', False):
            if not allowed:
                return True
            return username in allowed
        return username in allowed

    return False


class StartMfaLogin(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)
        password = graphene.String(required=True)

    token = graphene.String()
    mfa_required = graphene.Boolean(required=True)
    challenge_id = graphene.String()
    message = graphene.String()
    has_webauthn = graphene.Boolean(required=True)

    @staticmethod
    def mutate(root, info, username, password):
        request = info.context
        source_ip = extract_client_ip(request)

        user = authenticate(request=request, username=username, password=password)
        if not user:
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=(
                    f"Failed login attempt for user '{username}' from IP {source_ip}. "
                    "Reason: Invalid credentials."
                ),
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-PRIMARY-01',
                event_reason='Invalid credentials provided.',
                event_category=['authentication'],
                event_type=['start', 'failure'],
                user_id=username or 'anonymous',
                user_name=username or None,
                source_ip=source_ip,
                request=request,
                http_status_code=401,
            )
            raise Exception("Invalid credentials")

        auth_settings = AuthProviderSettings.resolve_for_user(user)
        if not _is_local_login_allowed_for_user(user, auth_settings):
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=(
                    f"Local login attempt blocked for '{user_name}' from IP {source_ip}. "
                    "Reason: Local username/password login disabled by authentication policy."
                ),
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-PRIMARY-01',
                event_reason='Local login disabled by authentication policy.',
                event_category=['authentication'],
                event_type=['denied', 'failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=403,
            )
            raise Exception("Local username/password login is disabled. Use OIDC sign-in.")

        mfa_settings, _ = UserMfaSettings.objects.get_or_create(user=user)
        if _should_bypass_mfa_for_user(user):
            _ensure_user_default_and_active_organization(user)
            token = get_token(user)
            user_logged_in.send(sender=user.__class__, request=request, user=user)
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='informational',
                logger_name='AuthService',
                message=(
                    f"Bot account '{user_name}' successfully logged in from IP {source_ip} "
                    "using primary credentials only."
                ),
                event_action='user_login_success',
                event_outcome='success',
                asvs_event_code='AUTHN-SUCCESS-PRIMARY-01',
                event_reason='Bot auditor MFA bypass policy applied.',
                event_category=['authentication'],
                event_type=['end', 'success'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=200,
            )
            return StartMfaLogin(
                token=token,
                mfa_required=False,
                challenge_id=None,
                message="Login successful",
                has_webauthn=False,
            )
        if mfa_settings.is_locked():
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='error',
                logger_name='AuthService',
                message=(
                    f"Account for user '{user_name}' remains locked due to repeated "
                    "failed MFA attempts."
                ),
                event_action='user_account_locked',
                event_outcome='failure',
                asvs_event_code='AUTHN-LOCKOUT-01',
                event_reason='MFA verification is temporarily locked due to repeated failures.',
                event_category=['authentication'],
                event_type=['denied', 'failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=423,
            )
            raise Exception("MFA verification is temporarily locked due to repeated failures")

        has_webauthn = WebAuthnCredential.objects.filter(user=user).exists()
        has_totp = bool(mfa_settings.totp_enabled and mfa_settings.totp_secret)
        must_use_mfa = _mfa_required_for_user(user)

        if must_use_mfa and not (has_totp or has_webauthn):
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='error',
                logger_name='AuthService',
                message=(
                    f"Administrator login blocked for '{user_name}' because no MFA method "
                    "is enrolled."
                ),
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-MFA-01',
                event_reason='Administrator account requires MFA enrollment before login.',
                event_category=['authentication'],
                event_type=['denied', 'failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=403,
            )
            raise Exception("Administrator account requires MFA, but no MFA method is enrolled")

        if not has_totp and not has_webauthn:
            _ensure_user_default_and_active_organization(user)
            token = get_token(user)
            user_logged_in.send(sender=user.__class__, request=request, user=user)
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='informational',
                logger_name='AuthService',
                message=f"User '{user_name}' successfully logged in from IP {source_ip}.",
                event_action='user_login_success',
                event_outcome='success',
                asvs_event_code='AUTHN-SUCCESS-PRIMARY-01',
                event_category=['authentication'],
                event_type=['end', 'success'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=200,
            )
            return StartMfaLogin(token=token, mfa_required=False, challenge_id=None, message="Login successful", has_webauthn=False)

        challenge = MfaLoginChallenge.create_for_user(user=user)
        MfaAuditEvent.objects.create(
            user=user,
            event=MfaAuditEvent.Event.LOGIN_CHALLENGE_CREATED,
            details={"challenge_id": challenge.challenge_id},
        )
        user_id, user_name = _user_identity(user)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=(
                f"Primary authentication succeeded for user '{user_name}' from IP {source_ip}; "
                "MFA challenge issued."
            ),
            event_action='user_login_success',
            event_outcome='success',
            asvs_event_code='AUTHN-SUCCESS-PRIMARY-01',
            event_reason='Primary credentials accepted; MFA challenge required.',
            event_category=['authentication'],
            event_type=['start', 'success'],
            user_id=user_id,
            user_name=user_name,
            source_ip=source_ip,
            request=request,
            asvs_details={
                'authentication': {
                    'mfa_required': True,
                    'challenge_id': challenge.challenge_id,
                    'available_methods': (['totp'] if has_totp else []) + (['webauthn'] if has_webauthn else []),
                }
            },
        )
        return StartMfaLogin(
            token=None,
            mfa_required=True,
            challenge_id=challenge.challenge_id,
            message="MFA required",
            has_webauthn=has_webauthn,
        )


class VerifyMfaLogin(graphene.Mutation):
    class Arguments:
        challenge_id = graphene.String(required=True)
        otp_code = graphene.String()
        backup_code = graphene.String()

    token = graphene.String()
    ok = graphene.Boolean(required=True)
    message = graphene.String()

    @staticmethod
    def mutate(root, info, challenge_id, otp_code=None, backup_code=None):
        request = info.context
        source_ip = extract_client_ip(request)

        try:
            challenge = MfaLoginChallenge.objects.select_related('user').get(challenge_id=challenge_id, used=False)
        except MfaLoginChallenge.DoesNotExist:
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"Invalid MFA challenge identifier submitted from IP {source_ip}.",
                event_action='user_mfa_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-MFA-01',
                event_reason='Invalid MFA challenge identifier.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id='anonymous',
                source_ip=source_ip,
                request=request,
                http_status_code=400,
            )
            raise Exception("Invalid MFA challenge")

        if challenge.is_expired():
            user_id, user_name = _user_identity(challenge.user)
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"MFA challenge expired for user '{user_name}' from IP {source_ip}.",
                event_action='user_mfa_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-MFA-01',
                event_reason='MFA challenge expired.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=400,
            )
            raise Exception("MFA challenge expired")

        user = challenge.user
        mfa_settings, _ = UserMfaSettings.objects.get_or_create(user=user)
        if mfa_settings.is_locked():
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='error',
                logger_name='AuthService',
                message=f"MFA verification blocked for locked account '{user_name}' from IP {source_ip}.",
                event_action='user_account_locked',
                event_outcome='failure',
                asvs_event_code='AUTHN-LOCKOUT-01',
                event_reason='MFA verification is temporarily locked.',
                event_category=['authentication'],
                event_type=['denied', 'failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=423,
            )
            raise Exception("MFA verification is temporarily locked due to repeated failures")

        verified = False
        mfa_method = 'totp' if otp_code else ('backup_code' if backup_code else 'unknown')
        if otp_code:
            secret = mfa_settings.totp_secret
            if secret:
                verified = pyotp.TOTP(secret).verify((otp_code or '').strip(), valid_window=1)
        elif backup_code:
            verified = mfa_settings.verify_and_consume_backup_code(backup_code)

        if not verified:
            challenge.failed_attempts = challenge.failed_attempts + 1
            challenge.save(update_fields=['failed_attempts'])
            mfa_settings.failed_attempts = mfa_settings.failed_attempts + 1
            if mfa_settings.failed_attempts >= 5:
                mfa_settings.lock_for_minutes(15)
                MfaAuditEvent.objects.create(
                    user=user,
                    event=MfaAuditEvent.Event.LOGIN_LOCKED,
                    details={"reason": "too_many_failed_attempts"},
                )
                user_id, user_name = _user_identity(user)
                emit_security_event(
                    level='error',
                    logger_name='AuthService',
                    message=(
                        f"Account for user '{user_name}' has been locked after repeated MFA failures "
                        f"from IP {source_ip}."
                    ),
                    event_action='user_account_locked',
                    event_outcome='failure',
                    asvs_event_code='AUTHN-LOCKOUT-01',
                    event_reason='Too many failed MFA attempts.',
                    event_category=['authentication'],
                    event_type=['failure'],
                    user_id=user_id,
                    user_name=user_name,
                    source_ip=source_ip,
                    request=request,
                    http_status_code=423,
                )
            mfa_settings.save(update_fields=['failed_attempts', 'locked_until'])
            MfaAuditEvent.objects.create(
                user=user,
                event=MfaAuditEvent.Event.LOGIN_FAILED,
                details={"challenge_id": challenge_id},
            )
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=(
                    f"MFA challenge failed for user '{user_name}' from IP {source_ip}. "
                    f"Method: {mfa_method}."
                ),
                event_action='user_mfa_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-MFA-01',
                event_reason='Invalid MFA verification code.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=401,
                asvs_details={'authentication': {'mfa_method': mfa_method}},
            )
            raise Exception("Invalid MFA code")

        challenge.used = True
        challenge.save(update_fields=['used'])
        mfa_settings.failed_attempts = 0
        mfa_settings.locked_until = None
        mfa_settings.save(update_fields=['failed_attempts', 'locked_until', 'backup_codes_hashes'])
        MfaAuditEvent.objects.create(
            user=user,
            event=MfaAuditEvent.Event.LOGIN_SUCCESS,
            details={"challenge_id": challenge_id},
        )
        _ensure_user_default_and_active_organization(user)
        token = get_token(user)
        user_logged_in.send(sender=user.__class__, request=request, user=user)
        user_id, user_name = _user_identity(user)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=(
                f"User '{user_name}' successfully completed MFA challenge using '{mfa_method}' "
                f"from IP {source_ip}."
            ),
            event_action='user_mfa_success',
            event_outcome='success',
            asvs_event_code='AUTHN-SUCCESS-MFA-01',
            event_category=['authentication'],
            event_type=['end', 'success'],
            user_id=user_id,
            user_name=user_name,
            source_ip=source_ip,
            request=request,
            http_status_code=200,
            asvs_details={'authentication': {'mfa_method': mfa_method}},
        )
        return VerifyMfaLogin(token=token, ok=True, message="MFA verified")


class WebAuthnCredentialType(DjangoObjectType):
    class Meta:
        model = WebAuthnCredential
        fields = ("id", "name", "created_at", "last_used_at")


class StartWebAuthnRegistration(graphene.Mutation):
    class Arguments:
        credential_name = graphene.String()

    challenge_id = graphene.String(required=True)
    options_json = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, credential_name=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        rp_id = _get_webauthn_rp_id()
        excluded = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in WebAuthnCredential.objects.filter(user=user)
        ]
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="HEFAISTOS",
            user_id=str(user.id).encode("utf-8"),
            user_name=user.username,
            user_display_name=user.username,
            exclude_credentials=excluded or None,
        )
        challenge = WebAuthnChallenge.create_challenge(
            challenge_type=WebAuthnChallenge.ChallengeType.REGISTRATION,
            challenge=bytes_to_base64url(options.challenge),
            user=user,
            username=user.username,
        )
        return StartWebAuthnRegistration(
            challenge_id=challenge.challenge_id,
            options_json=options_to_json(options),
        )


class FinishWebAuthnRegistration(graphene.Mutation):
    class Arguments:
        challenge_id = graphene.String(required=True)
        credential = graphene.JSONString(required=True)
        credential_name = graphene.String()

    ok = graphene.Boolean(required=True)
    credential_obj = graphene.Field(WebAuthnCredentialType)

    @staticmethod
    def mutate(root, info, challenge_id, credential, credential_name=None):
        if isinstance(credential, str):
            credential = json.loads(credential)
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        try:
            challenge = WebAuthnChallenge.objects.get(
                challenge_id=challenge_id,
                user=user,
                challenge_type=WebAuthnChallenge.ChallengeType.REGISTRATION,
                used=False,
            )
        except WebAuthnChallenge.DoesNotExist:
            raise Exception("Invalid WebAuthn registration challenge")
        if challenge.is_expired():
            raise Exception("WebAuthn registration challenge expired")

        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=_get_webauthn_rp_id(),
            expected_origin=_get_webauthn_origin(),
            require_user_verification=True,
        )
        cred = WebAuthnCredential.objects.create(
            user=user,
            name=(credential_name or "Security Key").strip() or "Security Key",
            credential_id=bytes_to_base64url(verification.credential_id),
            public_key=bytes_to_base64url(verification.credential_public_key),
            sign_count=verification.sign_count,
            transports=[],
        )
        challenge.used = True
        challenge.save(update_fields=['used'])
        return FinishWebAuthnRegistration(ok=True, credential_obj=cred)


class StartWebAuthnMfaAuthentication(graphene.Mutation):
    class Arguments:
        login_challenge_id = graphene.String(required=True)

    options_json = graphene.String(required=True)
    webauthn_challenge_id = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, login_challenge_id):
        try:
            login_challenge = MfaLoginChallenge.objects.select_related('user').get(challenge_id=login_challenge_id, used=False)
        except MfaLoginChallenge.DoesNotExist:
            raise Exception("Invalid MFA login challenge")
        if login_challenge.is_expired():
            raise Exception("MFA challenge expired")
        user = login_challenge.user
        credentials = list(WebAuthnCredential.objects.filter(user=user))
        if not credentials:
            raise Exception("No security keys registered")
        allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in credentials]
        options = generate_authentication_options(
            rp_id=_get_webauthn_rp_id(),
            allow_credentials=allow,
        )
        challenge = WebAuthnChallenge.create_challenge(
            challenge_type=WebAuthnChallenge.ChallengeType.AUTHENTICATION,
            challenge=bytes_to_base64url(options.challenge),
            user=user,
            username=user.username,
        )
        return StartWebAuthnMfaAuthentication(
            options_json=options_to_json(options),
            webauthn_challenge_id=challenge.challenge_id,
        )


class VerifyWebAuthnMfaAuthentication(graphene.Mutation):
    class Arguments:
        login_challenge_id = graphene.String(required=True)
        webauthn_challenge_id = graphene.String(required=True)
        credential = graphene.JSONString(required=True)

    ok = graphene.Boolean(required=True)
    token = graphene.String()

    @staticmethod
    def mutate(root, info, login_challenge_id, webauthn_challenge_id, credential):
        request = info.context
        source_ip = extract_client_ip(request)
        if isinstance(credential, str):
            credential = json.loads(credential)
        try:
            login_challenge = MfaLoginChallenge.objects.select_related('user').get(challenge_id=login_challenge_id, used=False)
        except MfaLoginChallenge.DoesNotExist:
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"Invalid WebAuthn MFA login challenge received from IP {source_ip}.",
                event_action='user_mfa_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-MFA-01',
                event_reason='Invalid MFA login challenge.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id='anonymous',
                source_ip=source_ip,
                request=request,
                http_status_code=400,
            )
            raise Exception("Invalid MFA login challenge")
        if login_challenge.is_expired():
            raise Exception("MFA challenge expired")
        try:
            webauthn_challenge = WebAuthnChallenge.objects.get(
                challenge_id=webauthn_challenge_id,
                challenge_type=WebAuthnChallenge.ChallengeType.AUTHENTICATION,
                user=login_challenge.user,
                used=False,
            )
        except WebAuthnChallenge.DoesNotExist:
            raise Exception("Invalid WebAuthn challenge")
        if webauthn_challenge.is_expired():
            raise Exception("WebAuthn challenge expired")

        credential_id = credential.get("id")
        stored = WebAuthnCredential.objects.filter(user=login_challenge.user, credential_id=credential_id).first()
        if not stored:
            raise Exception("Security key is not registered for this user")

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(webauthn_challenge.challenge),
            expected_rp_id=_get_webauthn_rp_id(),
            expected_origin=_get_webauthn_origin(),
            credential_public_key=base64url_to_bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
            require_user_verification=True,
        )
        stored.sign_count = verification.new_sign_count
        stored.last_used_at = timezone.now()
        stored.save(update_fields=['sign_count', 'last_used_at'])
        webauthn_challenge.used = True
        webauthn_challenge.save(update_fields=['used'])
        login_challenge.used = True
        login_challenge.save(update_fields=['used'])
        _ensure_user_default_and_active_organization(login_challenge.user)
        token = get_token(login_challenge.user)
        user_logged_in.send(sender=login_challenge.user.__class__, request=request, user=login_challenge.user)
        user_id, user_name = _user_identity(login_challenge.user)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=f"User '{user_name}' successfully completed MFA challenge using 'webauthn'.",
            event_action='user_mfa_success',
            event_outcome='success',
            asvs_event_code='AUTHN-SUCCESS-MFA-01',
            event_category=['authentication'],
            event_type=['end', 'success'],
            user_id=user_id,
            user_name=user_name,
            source_ip=source_ip,
            request=request,
            http_status_code=200,
            asvs_details={'authentication': {'mfa_method': 'webauthn'}},
        )
        return VerifyWebAuthnMfaAuthentication(ok=True, token=token)


class StartPasswordlessLogin(graphene.Mutation):
    class Arguments:
        username = graphene.String(required=True)

    webauthn_challenge_id = graphene.String(required=True)
    options_json = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, username):
        request = info.context
        source_ip = extract_client_ip(request)
        try:
            user = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"Passwordless login failed for unknown user '{username}' from IP {source_ip}.",
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-PRIMARY-01',
                event_reason='Unknown username.',
                event_category=['authentication'],
                event_type=['start', 'failure'],
                user_id=username or 'anonymous',
                user_name=username or None,
                source_ip=source_ip,
                request=request,
                http_status_code=401,
            )
            raise Exception("Invalid credentials")
        creds = list(WebAuthnCredential.objects.filter(user=user))
        if not creds:
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=(
                    f"Passwordless login denied for user '{user_name}' from IP {source_ip} "
                    "because no security key is enrolled."
                ),
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-MFA-01',
                event_reason='No WebAuthn credentials enrolled.',
                event_category=['authentication'],
                event_type=['denied', 'failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=403,
            )
            raise Exception("No security key enrolled for this account")
        allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds]
        options = generate_authentication_options(
            rp_id=_get_webauthn_rp_id(),
            allow_credentials=allow,
        )
        challenge = WebAuthnChallenge.create_challenge(
            challenge_type=WebAuthnChallenge.ChallengeType.PASSWORDLESS,
            challenge=bytes_to_base64url(options.challenge),
            user=user,
            username=user.username,
        )
        return StartPasswordlessLogin(
            webauthn_challenge_id=challenge.challenge_id,
            options_json=options_to_json(options),
        )


class VerifyPasswordlessLogin(graphene.Mutation):
    class Arguments:
        webauthn_challenge_id = graphene.String(required=True)
        credential = graphene.JSONString(required=True)

    ok = graphene.Boolean(required=True)
    token = graphene.String()

    @staticmethod
    def mutate(root, info, webauthn_challenge_id, credential):
        request = info.context
        source_ip = extract_client_ip(request)
        if isinstance(credential, str):
            credential = json.loads(credential)
        try:
            challenge = WebAuthnChallenge.objects.select_related('user').get(
                challenge_id=webauthn_challenge_id,
                challenge_type=WebAuthnChallenge.ChallengeType.PASSWORDLESS,
                used=False,
            )
        except WebAuthnChallenge.DoesNotExist:
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"Invalid passwordless challenge received from IP {source_ip}.",
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-PRIMARY-01',
                event_reason='Invalid passwordless challenge identifier.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id='anonymous',
                source_ip=source_ip,
                request=request,
                http_status_code=400,
            )
            raise Exception("Invalid passwordless challenge")
        if challenge.is_expired():
            user_id, user_name = _user_identity(challenge.user)
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"Expired passwordless challenge for user '{user_name}' from IP {source_ip}.",
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-PRIMARY-01',
                event_reason='Passwordless challenge expired.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=400,
            )
            raise Exception("Passwordless challenge expired")
        user = challenge.user
        credential_id = credential.get("id")
        stored = WebAuthnCredential.objects.filter(user=user, credential_id=credential_id).first()
        if not stored:
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=(
                    f"Passwordless login failed for user '{user_name}' from IP {source_ip}: "
                    "security key not registered."
                ),
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-MFA-01',
                event_reason='Security key is not registered for this user.',
                event_category=['authentication'],
                event_type=['failure'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=401,
            )
            raise Exception("Security key is not registered for this user")

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=_get_webauthn_rp_id(),
            expected_origin=_get_webauthn_origin(),
            credential_public_key=base64url_to_bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
            require_user_verification=True,
        )
        stored.sign_count = verification.new_sign_count
        stored.last_used_at = timezone.now()
        stored.save(update_fields=['sign_count', 'last_used_at'])
        challenge.used = True
        challenge.save(update_fields=['used'])
        _ensure_user_default_and_active_organization(user)
        token = get_token(user)
        user_logged_in.send(sender=user.__class__, request=info.context, user=user)
        user_id, user_name = _user_identity(user)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=f"User '{user_name}' successfully logged in with passwordless WebAuthn from IP {source_ip}.",
            event_action='user_login_success',
            event_outcome='success',
            asvs_event_code='AUTHN-SUCCESS-PRIMARY-01',
            event_category=['authentication'],
            event_type=['end', 'success'],
            user_id=user_id,
            user_name=user_name,
            source_ip=source_ip,
            request=request,
            http_status_code=200,
        )
        return VerifyPasswordlessLogin(ok=True, token=token)


class DeleteWebAuthnCredential(graphene.Mutation):
    class Arguments:
        credential_id = graphene.ID(required=True)

    ok = graphene.Boolean(required=True)

    @staticmethod
    def mutate(root, info, credential_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        WebAuthnCredential.objects.filter(id=credential_id, user=user).delete()
        return DeleteWebAuthnCredential(ok=True)

def _generate_backup_codes(count: int = 8):
    return [secrets.token_hex(4).upper() for _ in range(count)]


def _hash_backup_codes(codes):
    return [hashlib.sha256(code.strip().encode('utf-8')).hexdigest() for code in codes]


class BeginTotpEnrollment(graphene.Mutation):
    secret = graphene.String(required=True)
    otpauth_uri = graphene.String(required=True)

    @staticmethod
    def mutate(root, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        settings_obj, _ = UserMfaSettings.objects.get_or_create(user=user)
        secret = pyotp.random_base32()
        settings_obj.pending_totp_secret = secret
        settings_obj.save(update_fields=['pending_totp_secret_encrypted', 'updated_at'])
        issuer = "HEFAISTOS"
        uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=issuer)
        MfaAuditEvent.objects.create(
            user=user,
            event=MfaAuditEvent.Event.TOTP_ENROLL_STARTED,
            details={},
        )
        return BeginTotpEnrollment(secret=secret, otpauth_uri=uri)


class ConfirmTotpEnrollment(graphene.Mutation):
    ok = graphene.Boolean(required=True)
    backup_codes = graphene.List(graphene.String, required=True)

    class Arguments:
        otp_code = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, otp_code):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        settings_obj, _ = UserMfaSettings.objects.get_or_create(user=user)
        pending_secret = settings_obj.pending_totp_secret
        if not pending_secret:
            raise Exception("No pending TOTP enrollment")
        if not pyotp.TOTP(pending_secret).verify((otp_code or '').strip(), valid_window=1):
            raise Exception("Invalid TOTP code")

        backup_codes = _generate_backup_codes()
        settings_obj.totp_secret = pending_secret
        settings_obj.pending_totp_secret = ''
        settings_obj.totp_enabled = True
        settings_obj.backup_codes_hashes = _hash_backup_codes(backup_codes)
        settings_obj.backup_codes_generated_at = timezone.now()
        settings_obj.failed_attempts = 0
        settings_obj.locked_until = None
        settings_obj.save()
        MfaAuditEvent.objects.create(
            user=user,
            event=MfaAuditEvent.Event.TOTP_ENROLL_CONFIRMED,
            details={},
        )
        return ConfirmTotpEnrollment(ok=True, backup_codes=backup_codes)


class DisableTotpMfa(graphene.Mutation):
    ok = graphene.Boolean(required=True)

    class Arguments:
        current_password = graphene.String(required=True)
        otp_code = graphene.String()
        backup_code = graphene.String()

    @staticmethod
    def mutate(root, info, current_password, otp_code=None, backup_code=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        if not user.check_password(current_password):
            raise Exception("Current password is incorrect")
        settings_obj, _ = UserMfaSettings.objects.get_or_create(user=user)
        if not settings_obj.totp_enabled:
            return DisableTotpMfa(ok=True)

        valid = False
        if otp_code and settings_obj.totp_secret:
            valid = pyotp.TOTP(settings_obj.totp_secret).verify((otp_code or '').strip(), valid_window=1)
        elif backup_code:
            valid = settings_obj.verify_and_consume_backup_code(backup_code)
        if not valid:
            raise Exception("Invalid MFA verification code")

        settings_obj.totp_enabled = False
        settings_obj.totp_secret = ''
        settings_obj.pending_totp_secret = ''
        settings_obj.backup_codes_hashes = []
        settings_obj.failed_attempts = 0
        settings_obj.locked_until = None
        settings_obj.save()
        MfaAuditEvent.objects.create(
            user=user,
            event=MfaAuditEvent.Event.TOTP_DISABLED,
            details={},
        )
        return DisableTotpMfa(ok=True)


class RegenerateBackupCodes(graphene.Mutation):
    ok = graphene.Boolean(required=True)
    backup_codes = graphene.List(graphene.String, required=True)

    class Arguments:
        current_password = graphene.String(required=True)
        otp_code = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, current_password, otp_code):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        if not user.check_password(current_password):
            raise Exception("Current password is incorrect")
        settings_obj, _ = UserMfaSettings.objects.get_or_create(user=user)
        if not settings_obj.totp_enabled or not settings_obj.totp_secret:
            raise Exception("TOTP MFA is not enabled")
        if not pyotp.TOTP(settings_obj.totp_secret).verify((otp_code or '').strip(), valid_window=1):
            raise Exception("Invalid TOTP code")

        backup_codes = _generate_backup_codes()
        settings_obj.backup_codes_hashes = _hash_backup_codes(backup_codes)
        settings_obj.backup_codes_generated_at = timezone.now()
        settings_obj.save(update_fields=['backup_codes_hashes', 'backup_codes_generated_at', 'updated_at'])
        MfaAuditEvent.objects.create(
            user=user,
            event=MfaAuditEvent.Event.BACKUP_CODES_REGENERATED,
            details={},
        )
        return RegenerateBackupCodes(ok=True, backup_codes=backup_codes)


class AdminResetUserMfa(graphene.Mutation):
    ok = graphene.Boolean(required=True)
    message = graphene.String()

    class Arguments:
        user_id = graphene.ID(required=True)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, user_id):
        caller = info.context.user
        try:
            if caller.is_superuser:
                target = CustomUser.objects.get(pk=user_id)
            else:
                target = CustomUser.objects.get(pk=user_id, organization=caller.organization)
        except CustomUser.DoesNotExist:
            raise Exception("User not found in your organization.")

        settings_obj, _ = UserMfaSettings.objects.get_or_create(user=target)
        settings_obj.totp_enabled = False
        settings_obj.totp_secret = ''
        settings_obj.pending_totp_secret = ''
        settings_obj.backup_codes_hashes = []
        settings_obj.failed_attempts = 0
        settings_obj.locked_until = None
        settings_obj.save()
        MfaLoginChallenge.objects.filter(user=target, used=False, expires_at__gt=timezone.now()).update(used=True)
        WebAuthnCredential.objects.filter(user=target).delete()
        WebAuthnChallenge.objects.filter(user=target, used=False, expires_at__gt=timezone.now()).update(used=True)
        MfaAuditEvent.objects.create(
            user=target,
            event=MfaAuditEvent.Event.ADMIN_RESET,
            details={"admin": caller.username},
        )
        return AdminResetUserMfa(ok=True, message="User MFA reset successfully.")


class AdminResetUserPassword(graphene.Mutation):
    """Allows an admin/superuser to reset any user's password."""
    class Arguments:
        user_id = graphene.ID(required=True)
        new_password = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, user_id, new_password):
        caller = info.context.user
        try:
            if caller.is_superuser:
                target = CustomUser.objects.get(pk=user_id)
            else:
                target = CustomUser.objects.get(pk=user_id, organization=caller.organization)
        except CustomUser.DoesNotExist:
            raise Exception("User not found in your organization.")

        # Validate new password
        try:
            validate_password(new_password, user=target)
        except ValidationError as e:
            raise Exception(f"Password validation failed: {', '.join(e.messages)}")

        target.set_password(new_password)
        target.save(update_fields=['password'])
        source_ip = extract_client_ip(info.context)
        target_user_id, target_user_name = _user_identity(target)
        caller_user_id, caller_user_name = _user_identity(caller)
        emit_security_event(
            level='informational',
            logger_name='UserManagementService',
            message=(
                f"Administrator '{caller_user_name}' reset password for user "
                f"'{target_user_name}'."
            ),
            event_action='user_account_updated',
            event_outcome='success',
            asvs_event_code='MGMT-USER-UPDATE-01',
            event_reason='Administrator-triggered password reset.',
            event_category=['authentication', 'authorization'],
            event_type=['info', 'success'],
            user_id=caller_user_id,
            user_name=caller_user_name,
            source_ip=source_ip,
            request=info.context,
            http_status_code=200,
            asvs_details={
                'management': {
                    'target_user_id': target_user_id,
                    'target_user_name': target_user_name,
                    'changed_fields': ['password'],
                }
            },
        )

        # Optionally send notification email
        try:
            from core.email_service import get_email_service
            from core.email_templates import login_link_text, login_link_html
            service = get_email_service(organization=target.organization)
            if service.is_configured() and target.email:
                service.send_message(
                    to=[target.email],
                    subject='Your HEFAISTOS Password Was Reset',
                    text=f"""Hello {target.username},

Your password was reset by an administrator ({caller.username}). Please log in with your new password.

{login_link_text()}

If you did not expect this change, please contact your administrator immediately.

Best regards,
The HEFAISTOS Team""",
                    html=f"""<html><body>
<h2>Password Reset</h2>
<p>Hello <strong>{target.username}</strong>,</p>
<p>Your password was reset by an administrator (<strong>{caller.username}</strong>).</p>
<p>Please log in with your new password.</p>
{login_link_html()}
<p>If you did not expect this change, please contact your administrator immediately.</p>
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
                )
                logger.info(f"Sent password reset notification to {target.username}")
        except Exception as e:
            logger.error(f"Failed to send password reset email to {target.email}: {e}")

        logger.info(f"Admin '{caller.username}' reset password for user '{target.username}'")
        return AdminResetUserPassword(ok=True, message="Password reset successfully.")


class RequestPasswordReset(graphene.Mutation):
    """Allows a user to request a password reset token by providing their username or email."""
    class Arguments:
        username_or_email = graphene.String(required=True)

    ok = graphene.Boolean()
    # Return the reset token directly (admins can copy/share it when email is not configured)
    reset_token = graphene.String()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, username_or_email):
        import secrets
        from django.db.models import Q
        source_ip = extract_client_ip(info.context)

        # Find user by username or email (case-insensitive)
        try:
            target = CustomUser.objects.get(
                Q(username__iexact=username_or_email) | Q(email__iexact=username_or_email)
            )
        except CustomUser.DoesNotExist:
            # Do not reveal whether the user exists (security)
            return RequestPasswordReset(ok=True, reset_token=None, message="If an account with that username/email exists, a reset link has been generated.")
        except CustomUser.MultipleObjectsReturned:
            # If multiple users match (shouldn't happen), use username exact match
            try:
                target = CustomUser.objects.get(username__iexact=username_or_email)
            except CustomUser.DoesNotExist:
                return RequestPasswordReset(ok=True, reset_token=None, message="If an account with that username/email exists, a reset link has been generated.")

        # Invalidate any existing unused tokens for this user
        PasswordResetToken.objects.filter(user=target, used=False).delete()

        # Generate a secure token
        token_value = secrets.token_urlsafe(32)
        PasswordResetToken.objects.create(user=target, token=token_value)
        target_user_id, target_user_name = _user_identity(target)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=f"Password reset was requested for user '{target_user_name}' from IP {source_ip}.",
            event_action='user_password_reset_requested',
            event_outcome='success',
            asvs_event_code='AUTHN-CHANGE-PASS-REQ-01',
            event_category=['authentication'],
            event_type=['start', 'success'],
            user_id=target_user_id,
            user_name=target_user_name,
            source_ip=source_ip,
            request=info.context,
            http_status_code=200,
        )

        # Try to send email with reset link
        reset_token_to_return = None
        try:
            from core.email_service import get_email_service
            service = get_email_service(organization=target.organization)
            if service.is_configured() and target.email:
                reset_url = _frontend_url(f"/reset-password?token={token_value}", request=info.context)
                service.send_message(
                    to=[target.email],
                    subject='HEFAISTOS Password Reset Request',
                    text=f"""Hello {target.username},

You requested a password reset. Use the link below to reset your password (valid for 1 hour):

{reset_url}

If you did not request a password reset, please ignore this message.

Best regards,
The HEFAISTOS Team""",
                    html=f"""<html><body>
<h2>Password Reset Request</h2>
<p>Hello <strong>{target.username}</strong>,</p>
<p>You requested a password reset. Click the link below to reset your password (valid for 1 hour):</p>
<p><a href="{reset_url}" style="color:#2563eb;text-decoration:underline">{reset_url}</a></p>
<p>If you did not request a password reset, please ignore this message.</p>
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
                )
                logger.info(f"Sent password reset email to {target.username}")
            else:
                # Email not configured — return token so admin can share it
                reset_token_to_return = token_value
        except Exception as e:
            logger.error(f"Failed to send password reset email: {e}")
            reset_token_to_return = token_value

        return RequestPasswordReset(
            ok=True,
            reset_token=reset_token_to_return,
            message="If an account with that username/email exists, a reset link has been generated."
        )


class ResetPassword(graphene.Mutation):
    """Allows a user to reset their password using a valid reset token."""
    class Arguments:
        token = graphene.String(required=True)
        new_password = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, token, new_password):
        source_ip = extract_client_ip(info.context)
        try:
            reset_token = PasswordResetToken.objects.select_related('user').get(token=token, used=False)
        except PasswordResetToken.DoesNotExist:
            raise Exception("Invalid or already-used password reset token.")

        if reset_token.is_expired():
            raise Exception("This password reset token has expired. Please request a new one.")

        target = reset_token.user

        # Validate new password
        try:
            validate_password(new_password, user=target)
        except ValidationError as e:
            raise Exception(f"Password validation failed: {', '.join(e.messages)}")

        # Set new password and mark token as used
        target.set_password(new_password)
        target.save(update_fields=['password'])
        reset_token.used = True
        reset_token.save(update_fields=['used'])

        logger.info(f"Password reset successfully for user '{target.username}' via token.")
        target_user_id, target_user_name = _user_identity(target)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=f"User '{target_user_name}' successfully completed password reset flow.",
            event_action='user_password_change_success',
            event_outcome='success',
            asvs_event_code='AUTHN-CHANGE-PASS-OK-01',
            event_category=['authentication'],
            event_type=['end', 'success'],
            user_id=target_user_id,
            user_name=target_user_name,
            source_ip=source_ip,
            request=info.context,
            http_status_code=200,
        )
        return ResetPassword(ok=True, message="Password has been reset successfully. You can now log in.")


class SubmitRegistrationRequest(graphene.Mutation):
    """Public registration request form submission from login page."""
    class Arguments:
        name = graphene.String(required=True)
        email = graphene.String(required=True)
        subject = graphene.String(required=True)
        message = graphene.String(required=True)

    ok = graphene.Boolean(required=True)
    message = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, name, email, subject, message):
        request = info.context
        source_ip = extract_client_ip(request)
        submitted_at = timezone.now().isoformat()

        sender_name = (name or '').strip()
        sender_email = (email or '').strip()
        request_subject = (subject or '').strip()
        request_message = (message or '').strip()

        if not sender_name or not sender_email or not request_subject or not request_message:
            raise Exception("All fields are required.")

        if len(sender_name) > 120:
            raise Exception("Name is too long (max 120 characters).")
        if len(request_subject) > 200:
            raise Exception("Subject is too long (max 200 characters).")
        if len(request_message) > 5000:
            raise Exception("Message is too long (max 5000 characters).")

        try:
            validate_email(sender_email)
        except ValidationError:
            raise Exception("Enter a valid email address.")

        from core.email_service import get_email_service
        service = get_email_service(organization=None)
        if not service.is_configured():
            raise Exception("Registration service is currently unavailable.")

        # Prefer platform admins first; fallback to org admins if needed.
        recipient_emails = sorted({
            (value or '').strip()
            for value in CustomUser.objects.filter(is_active=True)
            .filter(Q(is_superuser=True) | Q(is_staff=True))
            .exclude(email__isnull=True)
            .exclude(email='')
            .values_list('email', flat=True)
            if value
        })
        if not recipient_emails:
            recipient_emails = sorted({
                (value or '').strip()
                for value in CustomUser.objects.filter(is_active=True, role=Roles.ADMIN)
                .exclude(email__isnull=True)
                .exclude(email='')
                .values_list('email', flat=True)
                if value
            })

        if not recipient_emails:
            fallback_recipient = (
                getattr(service, 'from_email', '') or getattr(service, 'smtp_username', '')
            )
            fallback_recipient = (fallback_recipient or '').strip()
            if '@' in fallback_recipient:
                recipient_emails = [fallback_recipient]

        if not recipient_emails:
            raise Exception("No registration recipient is configured.")

        email_subject = f"HEFAISTOS registration request: {request_subject}"
        text_body = (
            "New HEFAISTOS registration request submitted.\n\n"
            f"Name: {sender_name}\n"
            f"Email: {sender_email}\n"
            f"Subject: {request_subject}\n"
            f"Submitted at: {submitted_at}\n"
            f"Source IP: {source_ip}\n\n"
            "Message:\n"
            f"{request_message}\n"
        )

        escaped_message = html.escape(request_message)
        html_body = f"""<html><body>
<h2>New HEFAISTOS registration request</h2>
<p><strong>Name:</strong> {html.escape(sender_name)}</p>
<p><strong>Email:</strong> {html.escape(sender_email)}</p>
<p><strong>Subject:</strong> {html.escape(request_subject)}</p>
<p><strong>Submitted at:</strong> {html.escape(submitted_at)}</p>
<p><strong>Source IP:</strong> {html.escape(source_ip or 'unknown')}</p>
<p><strong>Message:</strong></p>
<pre style="white-space:pre-wrap;font-family:inherit">{escaped_message}</pre>
</body></html>"""

        sent = service.send_message(
            to=recipient_emails,
            subject=email_subject,
            text=text_body,
            html=html_body,
            headers={
                'Reply-To': sender_email,
                'X-HEFAISTOS-Form': 'registration',
            },
            hide_recipients=True,
        )
        if not sent:
            raise Exception("Failed to send registration request. Please try again later.")

        logger.info(
            "Registration request submitted by %s <%s> from IP %s",
            sender_name,
            sender_email,
            source_ip,
        )
        return SubmitRegistrationRequest(ok=True, message="Registration request sent successfully.")


class StartOidcLogin(graphene.Mutation):
    class Arguments:
        provider = graphene.String(required=True)
        organization_id = graphene.UUID(required=False)
        identifier = graphene.String(required=False)

    authorization_url = graphene.String(required=True)
    provider = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, provider, organization_id=None, identifier=None):
        request = info.context
        settings_obj = None
        target_org = None
        if organization_id:
            target_org = Organization.objects.filter(pk=organization_id).first()
            if target_org is None:
                raise Exception("Organization not found")
            settings_obj = AuthProviderSettings.get_for_organization(target_org)
        else:
            identifier_org = _resolve_org_from_login_identifier(identifier or '')
            if identifier_org is not None:
                target_org = identifier_org
                settings_obj = AuthProviderSettings.get_for_organization(target_org)

        if settings_obj is None:
            enabled_rows = list(
                AuthProviderSettings.objects.select_related('organization')
                .filter(organization__isnull=False)
                .filter(Q(enable_entra=True) | Q(enable_oidc=True))
            )
            provider_norm = str(provider or '').strip().upper()
            provider_filtered = []
            for row in enabled_rows:
                if provider_norm == 'ENTRA' and row.enable_entra:
                    provider_filtered.append(row)
                elif provider_norm == 'OIDC' and row.enable_oidc:
                    provider_filtered.append(row)
            if len(provider_filtered) == 1:
                settings_obj = provider_filtered[0]
                target_org = settings_obj.organization
            elif not (identifier or '').strip():
                raise Exception("Enter username or email before OIDC sign-in.")
            else:
                raise Exception("Unable to resolve organization for OIDC sign-in.")

        try:
            authorization_url, resolved_provider = build_authorization_url(
                request=request,
                settings_obj=settings_obj,
                provider=provider,
                organization_id=str(target_org.id) if target_org else None,
            )
        except OidcAuthError as exc:
            raise Exception(str(exc))

        return StartOidcLogin(
            authorization_url=authorization_url,
            provider=resolved_provider.upper(),
        )


class CompleteOidcLogin(graphene.Mutation):
    class Arguments:
        code = graphene.String(required=True)
        state = graphene.String(required=True)

    ok = graphene.Boolean(required=True)
    token = graphene.String()
    message = graphene.String()
    provider = graphene.String()

    @staticmethod
    def mutate(root, info, code, state):
        request = info.context
        source_ip = extract_client_ip(request)
        try:
            provider, config, claims, organization_id = complete_code_exchange(
                request=request,
                code=code,
                state=state,
            )
            settings_obj = AuthProviderSettings.resolve_for_org_id(organization_id) if organization_id else AuthProviderSettings.get_solo()
            if settings_obj is None:
                raise Exception("Organization authentication settings not found.")
            target_org = settings_obj.organization if settings_obj.organization_id else None
            identity_data = _resolve_sso_identity(claims=claims, config=config, provider=provider)
            user = _find_or_create_sso_user(
                identity_data=identity_data,
                claims=claims,
                settings_obj=settings_obj,
                target_org=target_org,
            )
            _ensure_user_default_and_active_organization(user)
            token = get_token(user)
            user_logged_in.send(sender=user.__class__, request=request, user=user)
            user_id, user_name = _user_identity(user)
            emit_security_event(
                level='informational',
                logger_name='AuthService',
                message=(
                    f"OIDC login successful for user '{user_name}' from IP {source_ip} "
                    f"via provider '{provider}'."
                ),
                event_action='user_login_success',
                event_outcome='success',
                asvs_event_code='AUTHN-SUCCESS-PRIMARY-01',
                event_reason='OIDC authentication flow completed successfully.',
                event_category=['authentication'],
                event_type=['end', 'success'],
                user_id=user_id,
                user_name=user_name,
                source_ip=source_ip,
                request=request,
                http_status_code=200,
            )
            return CompleteOidcLogin(
                ok=True,
                token=token,
                message='Login successful',
                provider=provider.upper(),
            )
        except Exception as exc:
            emit_security_event(
                level='warning',
                logger_name='AuthService',
                message=f"OIDC login failed from IP {source_ip}: {exc}",
                event_action='user_login_failed',
                event_outcome='failure',
                asvs_event_code='AUTHN-FAIL-PRIMARY-01',
                event_reason='OIDC authentication failed.',
                event_category=['authentication'],
                event_type=['failure'],
                source_ip=source_ip,
                request=request,
                http_status_code=401,
            )
            raise Exception(str(exc))


class UpdateAuthSettings(graphene.Mutation):
    class Arguments:
        auth_mode = graphene.String(required=False)
        default_login_provider = graphene.String(required=False)
        enable_entra = graphene.Boolean(required=False)
        enable_oidc = graphene.Boolean(required=False)
        allow_local_breakglass = graphene.Boolean(required=False)
        auto_provision_users = graphene.Boolean(required=False)
        sync_claims_on_login = graphene.Boolean(required=False)
        enforce_local_mfa = graphene.Boolean(required=False)
        breakglass_usernames = graphene.String(required=False)
        entra_tenant_id = graphene.String(required=False)
        entra_client_id = graphene.String(required=False)
        entra_client_secret = graphene.String(required=False)
        entra_redirect_uri = graphene.String(required=False)
        entra_scopes = graphene.String(required=False)
        entra_email_claim = graphene.String(required=False)
        entra_username_claim = graphene.String(required=False)
        entra_role_claim = graphene.String(required=False)
        oidc_issuer_url = graphene.String(required=False)
        oidc_client_id = graphene.String(required=False)
        oidc_client_secret = graphene.String(required=False)
        oidc_redirect_uri = graphene.String(required=False)
        oidc_scopes = graphene.String(required=False)
        oidc_email_claim = graphene.String(required=False)
        oidc_username_claim = graphene.String(required=False)
        oidc_role_claim = graphene.String(required=False)
        oidc_verify_ssl = graphene.Boolean(required=False)
        oidc_ca_certificate = graphene.String(required=False)
        role_admin_values = graphene.String(required=False)
        role_analyst_values = graphene.String(required=False)
        role_reviewer_values = graphene.String(required=False)
        default_provisioned_role = graphene.String(required=False)

    ok = graphene.Boolean(required=True)
    message = graphene.String(required=True)
    settings = graphene.Field(AuthSettingsType)

    @staticmethod
    def mutate(root, info, **kwargs):
        user = info.context.user
        if not _can_manage_auth_settings(user):
            raise Exception("Permission denied")

        settings_obj = AuthProviderSettings.resolve_for_user(user)

        if kwargs.get('auth_mode') is not None:
            candidate = str(kwargs.get('auth_mode') or '').strip().upper()
            allowed = {choice for choice, _label in AuthProviderSettings.AuthMode.choices}
            if candidate not in allowed:
                raise Exception(f"Invalid auth_mode '{candidate}'")
            settings_obj.auth_mode = candidate

        if kwargs.get('default_login_provider') is not None:
            candidate = str(kwargs.get('default_login_provider') or '').strip().upper()
            allowed = {choice for choice, _label in AuthProviderSettings.DefaultLoginProvider.choices}
            if candidate not in allowed:
                raise Exception(f"Invalid default_login_provider '{candidate}'")
            settings_obj.default_login_provider = candidate

        simple_fields = [
            'enable_entra',
            'enable_oidc',
            'allow_local_breakglass',
            'auto_provision_users',
            'sync_claims_on_login',
            'enforce_local_mfa',
            'breakglass_usernames',
            'entra_tenant_id',
            'entra_client_id',
            'entra_redirect_uri',
            'entra_scopes',
            'entra_email_claim',
            'entra_username_claim',
            'entra_role_claim',
            'oidc_issuer_url',
            'oidc_client_id',
            'oidc_redirect_uri',
            'oidc_scopes',
            'oidc_email_claim',
            'oidc_username_claim',
            'oidc_role_claim',
            'oidc_verify_ssl',
            'role_admin_values',
            'role_analyst_values',
            'role_reviewer_values',
        ]
        for field in simple_fields:
            if field in kwargs and kwargs[field] is not None:
                setattr(settings_obj, field, kwargs[field])

        if kwargs.get('default_provisioned_role') is not None:
            candidate = str(kwargs.get('default_provisioned_role') or '').strip().upper()
            allowed = {choice for choice, _label in CustomUser.Roles.choices}
            if candidate not in allowed:
                raise Exception(f"Invalid default_provisioned_role '{candidate}'")
            settings_obj.default_provisioned_role = candidate

        if kwargs.get('entra_client_secret') is not None and str(kwargs.get('entra_client_secret')).strip():
            settings_obj.entra_client_secret = kwargs.get('entra_client_secret')
        if kwargs.get('oidc_client_secret') is not None and str(kwargs.get('oidc_client_secret')).strip():
            settings_obj.oidc_client_secret = kwargs.get('oidc_client_secret')
        if 'oidc_ca_certificate' in kwargs and kwargs.get('oidc_ca_certificate') is not None:
            cert_value = str(kwargs.get('oidc_ca_certificate') or '').strip()
            if cert_value and "BEGIN CERTIFICATE" not in cert_value:
                raise Exception("OIDC CA certificate must be PEM formatted.")
            settings_obj.oidc_ca_certificate = cert_value
        if not bool(getattr(settings_obj, 'oidc_verify_ssl', True)) and bool((settings_obj.oidc_ca_certificate or '').strip()):
            raise Exception("Clear OIDC CA certificate when TLS verification is disabled.")

        settings_obj.save()
        return UpdateAuthSettings(
            ok=True,
            message='Authentication settings saved',
            settings=settings_obj,
        )


class SwitchActiveOrganization(graphene.Mutation):
    class Arguments:
        organization_id = graphene.UUID(required=True)
        set_as_default = graphene.Boolean(required=False)

    ok = graphene.Boolean(required=True)
    message = graphene.String(required=True)
    active_organization = graphene.Field(OrganizationSummaryType)
    default_organization = graphene.Field(OrganizationSummaryType)

    @staticmethod
    def mutate(root, info, organization_id, set_as_default=False):
        user = info.context.user
        request = info.context
        source_ip = extract_client_ip(request)
        if not user or user.is_anonymous:
            raise Exception("Authentication required")

        _ensure_user_default_and_active_organization(user)
        memberships = _ordered_user_organizations(user)
        membership_ids = {org.id for org in memberships}
        target_org = Organization.objects.filter(pk=organization_id).first()
        if target_org is None:
            raise Exception("Organization not found")

        if target_org.id not in membership_ids:
            raise Exception("Permission denied to switch to this organization")

        changed_fields = []
        if user.organization_id != target_org.id:
            user.organization = target_org
            changed_fields.append('organization')
        if set_as_default and user.default_organization_id != target_org.id:
            user.default_organization = target_org
            changed_fields.append('default_organization')
        if changed_fields:
            user.save(update_fields=changed_fields)

        user_id, user_name = _user_identity(user)
        emit_security_event(
            level='informational',
            logger_name='AuthService',
            message=(
                f"User '{user_name}' switched active organization to '{target_org.name}' from IP {source_ip}."
            ),
            event_action='user_session_organization_switched',
            event_outcome='success',
            event_category=['authentication'],
            event_type=['change', 'success'],
            user_id=user_id,
            user_name=user_name,
            source_ip=source_ip,
            request=request,
            http_status_code=200,
        )

        return SwitchActiveOrganization(
            ok=True,
            message='Active organization switched',
            active_organization=OrganizationSummaryType(
                id=target_org.id,
                name=target_org.name,
                is_default=bool(user.default_organization_id and user.default_organization_id == target_org.id),
                is_active=True,
            ),
            default_organization=OrganizationSummaryType(
                id=(user.default_organization.id if user.default_organization else target_org.id),
                name=(user.default_organization.name if user.default_organization else target_org.name),
                is_default=True,
                is_active=bool(user.organization_id == (user.default_organization.id if user.default_organization else target_org.id)),
            ),
        )


class Mutation(graphene.ObjectType):
    prepare_account_activation = PrepareAccountActivation.Field()
    complete_account_activation = CompleteAccountActivation.Field()
    start_mfa_login = StartMfaLogin.Field()
    verify_mfa_login = VerifyMfaLogin.Field()
    start_webauthn_registration = StartWebAuthnRegistration.Field()
    finish_webauthn_registration = FinishWebAuthnRegistration.Field()
    start_webauthn_mfa_authentication = StartWebAuthnMfaAuthentication.Field()
    verify_webauthn_mfa_authentication = VerifyWebAuthnMfaAuthentication.Field()
    start_passwordless_login = StartPasswordlessLogin.Field()
    verify_passwordless_login = VerifyPasswordlessLogin.Field()
    delete_webauthn_credential = DeleteWebAuthnCredential.Field()
    begin_totp_enrollment = BeginTotpEnrollment.Field()
    confirm_totp_enrollment = ConfirmTotpEnrollment.Field()
    disable_totp_mfa = DisableTotpMfa.Field()
    regenerate_backup_codes = RegenerateBackupCodes.Field()
    admin_reset_user_mfa = AdminResetUserMfa.Field()
    invite_user = InviteUser.Field()
    delete_user = DeleteUser.Field()
    update_profile = UpdateProfile.Field()
    update_workbench_visibility_defaults = UpdateWorkbenchVisibilityDefaults.Field()
    upload_avatar = UploadAvatar.Field()
    change_password = ChangePassword.Field()
    # Admin edit user mutation
    admin_update_user = graphene.Field(
        UserType,
        user_id=graphene.ID(required=True),
        email=graphene.String(),
        role=graphene.String(),
        bio=graphene.String(),
        job_title=graphene.String(),
        slack_handle=graphene.String(),
        organization_id=graphene.UUID(),
    )
    set_user_ai_key = SetUserAiKey.Field()
    delete_user_ai_key = DeleteUserAiKey.Field()
    update_notification_preferences = UpdateNotificationPreferences.Field()
    admin_reset_user_password = AdminResetUserPassword.Field()
    request_password_reset = RequestPasswordReset.Field()
    reset_password = ResetPassword.Field()
    submit_registration_request = SubmitRegistrationRequest.Field()
    start_oidc_login = StartOidcLogin.Field()
    complete_oidc_login = CompleteOidcLogin.Field()
    update_auth_settings = UpdateAuthSettings.Field()
    switch_active_organization = SwitchActiveOrganization.Field()

    @role_required([Roles.ADMIN, Roles.RESOURCE_MANAGER])
    def resolve_admin_update_user(self, info, user_id, email=None, role=None, bio=None, job_title=None, slack_handle=None, organization_id=None):
        caller = info.context.user
        try:
            # Superusers can edit any user; org-scoped admins stay within their org
            if caller.is_superuser:
                target = CustomUser.objects.get(pk=user_id)
            else:
                managed_org_ids = list(
                    OrganizationManagerAccess.objects.filter(user=caller).values_list('organization_id', flat=True)
                )
                if caller.organization_id:
                    managed_org_ids.append(caller.organization_id)
                target = CustomUser.objects.get(pk=user_id, organization_id__in=managed_org_ids)
        except CustomUser.DoesNotExist:
            raise Exception("User not found in your organization.")

        changed_fields = []
        if email is not None:
            target.email = email
            changed_fields.append('email')
        if role is not None:
            if role == Roles.BOT_AUDITOR_GLOBAL and not (caller.is_superuser or caller.is_staff):
                raise Exception("Only platform admins can assign BOT_AUDITOR_GLOBAL.")
            allowed_roles = _allowed_roles_for_assignment(caller)
            if role not in allowed_roles:
                raise Exception(f"Invalid role. Must be one of: {Roles.labels}")
            target.role = role
            changed_fields.append('role')
        if bio is not None:
            target.bio = bio
            changed_fields.append('bio')
        if job_title is not None:
            target.job_title = job_title
            changed_fields.append('job_title')
        if slack_handle is not None:
            target.slack_handle = slack_handle
            changed_fields.append('slack_handle')

        if organization_id is not None:
            try:
                new_org = Organization.objects.get(pk=organization_id)
            except Organization.DoesNotExist:
                raise Exception("Organization not found")

            # Only superusers or explicit organization managers may reassign users to that org
            if (not caller.is_superuser) and caller.organization_id != new_org.id:
                has_access = OrganizationManagerAccess.objects.filter(
                    user=caller,
                    organization=new_org,
                ).exists()
                if not has_access:
                    raise Exception("Permission denied to assign user to that organization")

            target.organization = new_org
            if not target.default_organization_id:
                target.default_organization = new_org
                changed_fields.append('default_organization_id')
            # Use the actual field name for ForeignKey
            changed_fields.append('organization_id')

        if changed_fields:
            if 'organization_id' in changed_fields and target.organization_id:
                with transaction.atomic():
                    locked_org = Organization.objects.select_for_update().get(pk=target.organization_id)
                    already_member = CustomUser.objects.filter(
                        pk=target.pk,
                        organization=locked_org,
                    ).exists()
                    if not already_member:
                        _enforce_organization_user_limit(locked_org)
                    target.save(update_fields=changed_fields)
                    _sync_membership_for_user_org(target, locked_org)
            else:
                target.save(update_fields=changed_fields)
                if target.organization_id:
                    _sync_membership_for_user_org(target, target.organization)

            # Send notification email to user about profile changes by admin
            try:
                from core.email_service import get_email_service
                from core.email_templates import login_link_text, login_link_html
                service = get_email_service(organization=target.organization)
                if service.is_configured() and target.email:
                    changes_text = ', '.join(changed_fields)
                    service.send_message(
                        to=[target.email],
                        subject='Your HEFAISTOS Profile Was Updated',
                        text=f"""Hello {target.username},

Your profile was updated by an administrator ({caller.username}).

Changed fields: {changes_text}

If you did not expect this change, please contact your administrator.

{login_link_text()}

Best regards,
The HEFAISTOS Team""",
                        html=f"""<html><body>
<h2>Profile Updated</h2>
<p>Hello <strong>{target.username}</strong>,</p>
<p>Your profile was updated by an administrator (<strong>{caller.username}</strong>).</p>
<p><strong>Changed fields:</strong> {changes_text}</p>
<p>If you did not expect this change, please contact your administrator.</p>
{login_link_html()}
<p>Best regards,<br/>The HEFAISTOS Team</p>
</body></html>"""
                    )
                    logger.info(f"Sent profile update notification to {target.username}")
            except Exception as e:
                logger.error(f"Failed to send profile update email to {target.email}: {e}")

        return target
