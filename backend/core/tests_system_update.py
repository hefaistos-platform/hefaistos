from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.system_update_service import SystemUpdateConflictError, SystemUpdateService


class _FakeService:
    def __init__(self):
        self.job = SimpleNamespace(id=str(uuid.uuid4()), status='RUNNING')

    def get_version_info(self):
        return {
            'current_version': '1.2.3',
            'build': {'commit': 'abc123', 'checked_at': '2026-01-01T00:00:00Z'},
            'update_capability': {'can_update': True, 'reason': 'ok'},
            'running_job_id': None,
        }

    def start_update(self, *, actor_id: str, actor_username: str, force: bool):
        self.last_start = {'actor_id': actor_id, 'actor_username': actor_username, 'force': force}
        return SimpleNamespace(id=self.job.id, status='PENDING', mode='force' if force else 'default')

    def get_job(self, job_id: str):
        if str(job_id) != self.job.id:
            return None
        return self.job

    def get_logs(self, job_id: str, start: int = 0, limit: int = 500):
        logs = [
            {'ts': '2026-01-01T00:00:00Z', 'line': '$ docker compose pull'},
            {'ts': '2026-01-01T00:00:01Z', 'line': 'Pulled'},
            {'ts': '2026-01-01T00:00:02Z', 'line': 'Done'},
        ]
        return logs[start:start + limit], len(logs)

    def serialize_job(self, job):
        return {'id': job.id, 'status': job.status, 'mode': 'default', 'steps': [], 'summary': {'success': False}}


class SystemUpdateApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='RootPass123!',
        )
        self.admin_user = user_model.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='AdminPass123!',
            role='ADMIN',
            is_superuser=False,
            is_staff=False,
        )
        self.client = APIClient()

    def test_non_superuser_blocked_on_all_system_update_endpoints(self):
        self.client.force_authenticate(user=self.admin_user)
        sample_job = str(uuid.uuid4())

        checks = [
            ('get', '/api/system/config/update/check', {}),
            ('post', '/api/system/config/update/start', {'force': False}),
            ('get', f'/api/system/config/update/jobs/{sample_job}', {}),
            ('get', f'/api/system/config/update/jobs/{sample_job}/logs', {}),
        ]
        for method, path, payload in checks:
            if method == 'post':
                response = self.client.post(path, payload, format='json')
            else:
                response = self.client.get(path)
            self.assertEqual(response.status_code, 403)
            self.assertIn('Superuser role is required', str(response.data.get('detail', '')))

    def test_start_returns_conflict_when_job_running(self):
        self.client.force_authenticate(user=self.superuser)
        fake_service = _FakeService()
        with patch('core.system_update_api_views.get_system_update_service', return_value=fake_service):
            with patch.object(fake_service, 'start_update', side_effect=SystemUpdateConflictError('An update job is already running.', job_id='job-1')):
                response = self.client.post('/api/system/config/update/start', {'force': False}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data.get('running_job_id'), 'job-1')

    def test_status_and_logs_endpoints_return_expected_payload(self):
        self.client.force_authenticate(user=self.superuser)
        fake_service = _FakeService()
        with patch('core.system_update_api_views.get_system_update_service', return_value=fake_service):
            status_response = self.client.get(f'/api/system/config/update/jobs/{fake_service.job.id}')
            logs_response = self.client.get(f'/api/system/config/update/jobs/{fake_service.job.id}/logs?start=1&limit=1')

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.data.get('id'), fake_service.job.id)
        self.assertEqual(status_response.data.get('status'), 'RUNNING')

        self.assertEqual(logs_response.status_code, 200)
        self.assertEqual(logs_response.data.get('total'), 3)
        self.assertEqual(logs_response.data.get('returned'), 1)
        self.assertEqual(logs_response.data.get('logs')[0]['line'], 'Pulled')


class SystemUpdateServiceTests(TestCase):
    def test_command_sequence_selection_by_mode(self):
        service = SystemUpdateService()

        default_cmds = [' '.join(step.command) for step in service._command_steps(force=False)]
        force_cmds = [' '.join(step.command) for step in service._command_steps(force=True)]

        self.assertEqual(default_cmds, [
            'docker compose pull',
            'docker compose --profile batch run --rm migrate',
            'docker compose --profile workers --profile obs --profile devtools up -d --build --remove-orphans',
        ])
        self.assertEqual(force_cmds, [
            'docker compose down --remove-orphans',
            'docker compose pull',
            'docker compose --profile workers --profile obs --profile devtools up -d --build --remove-orphans',
            'docker compose --profile batch run --rm migrate',
        ])

    def test_single_flight_lock_raises_conflict(self):
        service = SystemUpdateService()
        service._running_job_id = 'already-running'

        with self.assertRaises(SystemUpdateConflictError) as ctx:
            service.start_update(actor_id='1', actor_username='root', force=False)

        self.assertEqual(ctx.exception.job_id, 'already-running')

    def test_get_version_info_includes_local_and_repository_versions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'VERSION').write_text('1.2.3\n', encoding='utf-8')
            (repo_root / 'docker-compose.yml').write_text('services: {}\n', encoding='utf-8')

            service = SystemUpdateService(repo_root=repo_root)

            with patch.object(service, '_check_update_capability', return_value=(True, 'ok', ['docker', 'compose'])):
                with patch.object(service, '_read_repository_version', return_value=('1.2.4', 'test-source', None)):
                    payload = service.get_version_info()

        self.assertEqual(payload['local_version'], '1.2.3')
        self.assertEqual(payload['current_version'], '1.2.3')
        self.assertEqual(payload['repository']['version'], '1.2.4')
        self.assertEqual(payload['repository']['source'], 'test-source')
        self.assertIsNone(payload['repository']['error'])
        self.assertTrue(payload['update_available'])
