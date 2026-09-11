from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.system_update_service import (
    SystemUpdateConflictError,
    emit_update_audit_event,
    get_system_update_service,
)


def _require_superuser(request):
    if not bool(getattr(request.user, 'is_superuser', False)):
        emit_update_audit_event(
            request=request,
            user=request.user,
            action='authorization',
            outcome='failure',
            reason='Superuser role is required for system updates.',
            status_code=status.HTTP_403_FORBIDDEN,
        )
        return Response({'detail': 'Superuser role is required for system updates.'}, status=status.HTTP_403_FORBIDDEN)
    return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def system_update_check(request):
    denied = _require_superuser(request)
    if denied:
        return denied

    service = get_system_update_service()
    payload = service.get_version_info()
    emit_update_audit_event(
        request=request,
        user=request.user,
        action='check',
        outcome='success',
        reason='System update capability checked.',
        status_code=status.HTTP_200_OK,
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def system_update_start(request):
    denied = _require_superuser(request)
    if denied:
        return denied

    force_flag = bool((request.data or {}).get('force', False))
    mode = 'force' if force_flag else 'default'
    service = get_system_update_service()

    try:
        job = service.start_update(
            actor_id=str(getattr(request.user, 'id', 'unknown')),
            actor_username=getattr(request.user, 'username', 'unknown'),
            force=force_flag,
        )
    except SystemUpdateConflictError as exc:
        conflict_message = 'An update job is already running.'
        emit_update_audit_event(
            request=request,
            user=request.user,
            action='start',
            outcome='failure',
            reason=str(exc),
            mode=mode,
            job_id=exc.job_id,
            status_code=status.HTTP_409_CONFLICT,
        )
        return Response(
            {'detail': conflict_message, 'running_job_id': exc.job_id},
            status=status.HTTP_409_CONFLICT,
        )
    except Exception as exc:
        error_message = 'Failed to queue update job due to an internal error.'
        emit_update_audit_event(
            request=request,
            user=request.user,
            action='start',
            outcome='failure',
            reason=f'Failed to queue update job: {exc}',
            mode=mode,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return Response(
            {'detail': error_message},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    emit_update_audit_event(
        request=request,
        user=request.user,
        action='start',
        outcome='success',
        reason='System update job accepted.',
        mode=job.mode,
        job_id=job.id,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return Response({'job_id': job.id, 'status': job.status, 'mode': job.mode}, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def system_update_job_status(request, job_id):
    denied = _require_superuser(request)
    if denied:
        return denied

    service = get_system_update_service()
    job = service.get_job(str(job_id))
    if job is None:
        return Response({'detail': 'Update job not found.'}, status=status.HTTP_404_NOT_FOUND)

    return Response(service.serialize_job(job), status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def system_update_job_logs(request, job_id):
    denied = _require_superuser(request)
    if denied:
        return denied

    try:
        start = int(request.query_params.get('start', '0'))
    except ValueError:
        start = 0

    try:
        limit = int(request.query_params.get('limit', '500'))
    except ValueError:
        limit = 500

    service = get_system_update_service()
    job = service.get_job(str(job_id))
    if job is None:
        return Response({'detail': 'Update job not found.'}, status=status.HTTP_404_NOT_FOUND)

    logs, total = service.get_logs(str(job_id), start=start, limit=limit)
    return Response(
        {
            'job_id': str(job_id),
            'status': job.status,
            'start': max(0, start),
            'returned': len(logs),
            'total': total,
            'logs': logs,
        },
        status=status.HTTP_200_OK,
    )
