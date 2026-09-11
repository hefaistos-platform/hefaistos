from django.contrib import admin
from .models import (
	Entity,
	Organization,
	MISPInstance,
	SharedSmtpProfile,
	OrganizationSmtpSettings,
	OpenTidePublishProfile,
	OpenTideHefPublishJob,
	OrganizationAITaskConfig,
	OrganizationAITaskRun,
	HefaistosInstanceIdentity,
	HefaistosRemotePeer,
	HefaistosInboundShareKey,
	HefaistosPullJob,
)


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
	list_display = ("name", "created_at")
	search_fields = ("name",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
	list_display = ("name", "entity", "max_users", "created_at", "updated_at")
	list_filter = ("entity",)
	search_fields = ("name",)


@admin.register(MISPInstance)
class MISPInstanceAdmin(admin.ModelAdmin):
	list_display = ("name", "organization", "url", "verify_ssl", "created_at")
	list_filter = ("organization", "verify_ssl")
	search_fields = ("name", "url")


@admin.register(SharedSmtpProfile)
class SharedSmtpProfileAdmin(admin.ModelAdmin):
	list_display = ("name", "smtp_server", "smtp_port", "login_method", "is_active", "updated_at")
	list_filter = ("is_active", "encryption", "login_method")
	search_fields = ("name", "smtp_server", "smtp_username")
	readonly_fields = ("id", "created_at", "updated_at")


@admin.register(OrganizationSmtpSettings)
class OrganizationSmtpSettingsAdmin(admin.ModelAdmin):
	list_display = (
		"organization",
		"shared_profile",
		"enforce_shared",
		"custom_enabled",
		"custom_smtp_server",
		"custom_smtp_port",
		"updated_at",
	)
	list_filter = ("enforce_shared", "custom_enabled")
	search_fields = ("organization__name", "custom_smtp_server")
	readonly_fields = ("created_at", "updated_at")


@admin.register(OpenTidePublishProfile)
class OpenTidePublishProfileAdmin(admin.ModelAdmin):
	list_display = (
		"name",
		"organization",
		"repository",
		"branch",
		"target_folder",
		"enabled",
		"updated_at",
	)
	list_filter = ("organization", "enabled", "use_graph_configured_platforms")
	search_fields = ("name", "branch", "target_folder")
	readonly_fields = ("id", "created_at", "updated_at", "created_by")


@admin.register(OpenTideHefPublishJob)
class OpenTideHefPublishJobAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"playbook",
		"organization",
		"status",
		"branch",
		"commit_sha",
		"created_at",
		"completed_at",
	)
	list_filter = ("organization", "status", "branch")
	search_fields = ("commit_sha", "github_url", "commit_message", "error_message")
	readonly_fields = tuple(
		f.name for f in OpenTideHefPublishJob._meta.fields
	)

	def has_add_permission(self, request):  # pragma: no cover - admin-only behavior
		# Jobs are created exclusively by the publish flow.
		return False

	def has_change_permission(self, request, obj=None):  # pragma: no cover
		# View-only in admin – jobs are immutable history.
		return False


@admin.register(OrganizationAITaskConfig)
class OrganizationAITaskConfigAdmin(admin.ModelAdmin):
	list_display = (
		"organization",
		"task_key",
		"enabled",
		"schedule",
		"next_run_at",
		"last_run_at",
		"last_status",
		"updated_at",
	)
	list_filter = ("organization", "enabled", "schedule", "last_status")
	search_fields = ("organization__name", "task_key", "last_message")


@admin.register(OrganizationAITaskRun)
class OrganizationAITaskRunAdmin(admin.ModelAdmin):
	list_display = (
		"organization",
		"task_key",
		"status",
		"trigger",
		"started_at",
		"completed_at",
		"duration_ms",
		"run_by",
	)
	list_filter = ("organization", "status", "trigger", "task_key")
	search_fields = ("organization__name", "task_key", "output_summary", "error_message")
	readonly_fields = tuple(f.name for f in OrganizationAITaskRun._meta.fields)

	def has_add_permission(self, request):  # pragma: no cover
		return False


@admin.register(HefaistosInstanceIdentity)
class HefaistosInstanceIdentityAdmin(admin.ModelAdmin):
	list_display = ("organization", "instance_id", "created_at", "updated_at")
	readonly_fields = ("organization", "singleton_key", "instance_id", "created_at", "updated_at")

	def has_add_permission(self, request):  # pragma: no cover
		return False

	def has_delete_permission(self, request, obj=None):  # pragma: no cover
		return False


@admin.register(HefaistosRemotePeer)
class HefaistosRemotePeerAdmin(admin.ModelAdmin):
	list_display = (
		"name",
		"organization",
		"remote_url",
		"remote_instance_id",
		"default_scope",
		"auto_pull_enabled",
		"auto_pull_schedule",
		"next_auto_pull_at",
		"enabled",
		"last_sync_at",
		"last_sync_status",
	)
	list_filter = (
		"organization",
		"enabled",
		"default_scope",
		"auto_pull_enabled",
		"auto_pull_schedule",
		"verify_ssl",
		"allow_self_signed",
	)
	search_fields = ("name", "remote_url", "remote_instance_id")
	readonly_fields = (
		"id",
		"created_at",
		"updated_at",
		"last_sync_at",
		"last_sync_status",
		"last_sync_message",
		"next_auto_pull_at",
	)


@admin.register(HefaistosInboundShareKey)
class HefaistosInboundShareKeyAdmin(admin.ModelAdmin):
	list_display = (
		"name",
		"organization",
		"key_hint",
		"is_active",
		"expires_at",
		"last_used_at",
		"updated_at",
	)
	list_filter = ("organization", "is_active")
	search_fields = ("name", "key_hint", "key_hash")
	readonly_fields = ("id", "key_hash", "created_at", "updated_at", "last_used_at")


@admin.register(HefaistosPullJob)
class HefaistosPullJobAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"organization",
		"peer",
		"requested_scope",
		"status",
		"started_at",
		"completed_at",
		"triggered_by",
	)
	list_filter = ("organization", "status", "requested_scope")
	search_fields = ("id", "message")
	readonly_fields = tuple(f.name for f in HefaistosPullJob._meta.fields)

	def has_add_permission(self, request):  # pragma: no cover
		return False

	def has_change_permission(self, request, obj=None):  # pragma: no cover
		return False
