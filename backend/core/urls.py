"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, re_path, include
from django.views.generic.base import RedirectView
from django.conf import settings
from django.views.static import serve
from playbooks.views import attack_navigator_layer_json, issue_coverage_access_token
from ai_assistant.views import maieutic_ai, maieutic_hints, maieutic_validate
from lsp_server.views import lsp_status
from organizations.views import sharing_export, sharing_instance_info
from core.system_update_api_views import (
    system_update_check,
    system_update_start,
    system_update_job_status,
    system_update_job_logs,
)
from django.views.decorators.csrf import csrf_exempt
from graphene_file_upload.django import FileUploadGraphQLView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from core.schema import schema

urlpatterns = [
    # Friendly alias FIRST so it doesn't get swallowed by admin include
    path('admin/users', RedirectView.as_view(url='/admin/identity/customuser/', permanent=False)),
    path('admin/users/', RedirectView.as_view(url='/admin/identity/customuser/', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('graphql', csrf_exempt(FileUploadGraphQLView.as_view(graphiql=True))),
    path('api/coverage/token', issue_coverage_access_token, name='coverage-token'),
    path('api/coverage/layer.json', attack_navigator_layer_json, name='coverage-layer-json'),
    path('api/maieutic/validate', maieutic_validate, name='maieutic-validate'),
    path('api/maieutic/hints', maieutic_hints, name='maieutic-hints'),
    path('api/maieutic/ai', maieutic_ai, name='maieutic-ai'),
    path('api/lsp/status', lsp_status, name='lsp-status'),
    path('api/profile/', include('identity.urls')),
    # Instance-to-instance sharing API (read-only remote export surface)
    path('api/sharing/info', sharing_instance_info, name='sharing-info'),
    path('api/sharing/export', sharing_export, name='sharing-export'),
    path('api/webhooks/', include('webhooks.urls')),
    path('api/system/config/update/check', system_update_check, name='system-update-check'),
    path('api/system/config/update/start', system_update_start, name='system-update-start'),
    path('api/system/config/update/jobs/<uuid:job_id>', system_update_job_status, name='system-update-job-status'),
    path('api/system/config/update/jobs/<uuid:job_id>/logs', system_update_job_logs, name='system-update-job-logs'),
    # Serve user-uploaded media files (avatars, snapshots) in all environments
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
