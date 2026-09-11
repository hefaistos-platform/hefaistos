from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    CustomUser,
    UserOrganizationMembership,
    UserMfaSettings,
    MfaAuditEvent,
    WebAuthnCredential,
    WebAuthnChallenge,
    AccountSetupToken,
    AuthProviderSettings,
)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'organization', 'default_organization', 'role', 'is_staff') # <-- Add 'role'

    # Add 'role' to the fieldset
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        # --- ADD THIS SECTION ---
        ('Organization', {'fields': ('organization', 'default_organization', 'role')}),
        # --- END ADD ---
    )


@admin.register(UserMfaSettings)
class UserMfaSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'totp_enabled', 'backup_codes_count', 'failed_attempts', 'locked_until', 'updated_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at', 'backup_codes_generated_at')

    def backup_codes_count(self, obj):
        return len(obj.backup_codes_hashes or [])


@admin.register(MfaAuditEvent)
class MfaAuditEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'created_at')
    search_fields = ('user__username', 'event')
    readonly_fields = ('user', 'event', 'details', 'created_at')


@admin.register(WebAuthnCredential)
class WebAuthnCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'created_at', 'last_used_at')
    search_fields = ('user__username', 'name')


@admin.register(WebAuthnChallenge)
class WebAuthnChallengeAdmin(admin.ModelAdmin):
    list_display = ('challenge_type', 'user', 'username', 'used', 'expires_at', 'created_at')
    search_fields = ('user__username', 'username', 'challenge_type')


@admin.register(AccountSetupToken)
class AccountSetupTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_by', 'used', 'expires_at', 'created_at', 'used_at')
    search_fields = ('user__username', 'user__email', 'created_by__username')
    readonly_fields = ('token_hash', 'created_at', 'used_at')


@admin.register(AuthProviderSettings)
class AuthProviderSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'singleton_key',
        'auth_mode',
        'default_login_provider',
        'enable_entra',
        'enable_oidc',
        'allow_local_breakglass',
        'updated_at',
    )
    readonly_fields = ('updated_at',)


@admin.register(UserOrganizationMembership)
class UserOrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'created_at', 'updated_at')
    search_fields = ('user__username', 'user__email', 'organization__name')
