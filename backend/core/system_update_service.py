from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.mcs_logging import emit_security_event


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace('+00:00', 'Z')


_REPO_MARKERS = ('docker-compose.yml', 'docker-compose.yaml', 'VERSION')


def _resolve_repo_root(explicit_root: Path | None = None) -> Path:
    """
    Best-effort repository root detection across host and container layouts.

    Priority:
    1) ``HEFAISTOS_REPO_ROOT`` env override,
    2) explicit constructor value,
    3) walk up from module/cwd and pick first directory with known repo markers.
    """
    ordered_candidates: list[Path] = []

    env_root = (os.environ.get('HEFAISTOS_REPO_ROOT') or '').strip()
    if env_root:
        ordered_candidates.append(Path(env_root))
    if explicit_root is not None:
        ordered_candidates.append(Path(explicit_root))

    module_path = Path(__file__).resolve()
    ordered_candidates.extend([module_path.parent, *module_path.parents, Path.cwd()])

    seen: set[str] = set()
    for candidate in ordered_candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)

        for scope in [resolved, *resolved.parents]:
            if any((scope / marker).exists() for marker in _REPO_MARKERS):
                return scope

    if explicit_root is not None:
        return Path(explicit_root).expanduser().resolve()
    return module_path.parent


def _configured_version_fallback() -> str | None:
    env_version = (os.environ.get('HEFAISTOS_VERSION') or '').strip()
    if env_version:
        return env_version
    try:
        from django.conf import settings

        configured = str(getattr(settings, 'HEFAISTOS_VERSION', '') or '').strip()
        if configured:
            return configured
    except Exception:
        pass
    return None


def _extract_numeric_version_tuple(raw_version: str | None) -> tuple[int, ...] | None:
    """Parse a loose dotted version string (optionally prefixed with 'v')."""
    if not raw_version:
        return None
    cleaned = raw_version.strip()
    if cleaned.lower().startswith('v'):
        cleaned = cleaned[1:]
    match = re.match(r'^(\d+(?:\.\d+)*)', cleaned)
    if not match:
        return None
    try:
        return tuple(int(part) for part in match.group(1).split('.'))
    except Exception:
        return None


def _compare_versions(local_version: str | None, repo_version: str | None) -> bool | None:
    """Return True when repo version is newer, False when not newer, None when unknown."""
    local_tuple = _extract_numeric_version_tuple(local_version)
    repo_tuple = _extract_numeric_version_tuple(repo_version)
    if local_tuple is None or repo_tuple is None:
        return None
    width = max(len(local_tuple), len(repo_tuple))
    padded_local = local_tuple + (0,) * (width - len(local_tuple))
    padded_repo = repo_tuple + (0,) * (width - len(repo_tuple))
    return padded_repo > padded_local


def _is_dubious_ownership_error(stdout: str | None, stderr: str | None) -> bool:
    combined = f"{stdout or ''}\n{stderr or ''}".lower()
    return 'detected dubious ownership' in combined


_REDACTION_PATTERNS = [
    re.compile(r'(?i)(bearer\s+)[^\s\"\']+'),
    re.compile(r'(?i)((?:password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*)[^\s\"\']+'),
    re.compile(r'://[^\s:/]+:[^\s@]+@'),
]


def redact_sensitive(value: str) -> str:
    text = value or ''
    text = _REDACTION_PATTERNS[0].sub(r'\1[REDACTED]', text)
    text = _REDACTION_PATTERNS[1].sub(r'\1[REDACTED]', text)
    text = _REDACTION_PATTERNS[2].sub('://[REDACTED]:[REDACTED]@', text)
    return text


@dataclass
class UpdateStep:
    name: str
    command: list[str]
    timeout_seconds: int


@dataclass
class SystemUpdateJob:
    id: str
    actor_id: str
    actor_username: str
    mode: str
    status: str = 'PENDING'
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failed_step: str | None = None
    error: str | None = None
    logs: list[dict[str, str]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)


class SystemUpdateConflictError(Exception):
    def __init__(self, message: str, job_id: str | None = None):
        super().__init__(message)
        self.job_id = job_id


class SystemUpdateService:
    DEFAULT_STEP_TIMEOUT_SECONDS = 20 * 60
    DEFAULT_OVERALL_TIMEOUT_SECONDS = 60 * 60

    def __init__(self, repo_root: Path | None = None):
        self.repo_root = _resolve_repo_root(repo_root)
        self._jobs: dict[str, SystemUpdateJob] = {}
        self._job_order: deque[str] = deque(maxlen=40)
        self._running_job_id: str | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _summarize_probe_output(result: subprocess.CompletedProcess[str]) -> str:
        output = ((result.stderr or '') + '\n' + (result.stdout or '')).strip()
        if not output:
            return f'exit code {result.returncode}'
        return output.splitlines()[0][:220]

    def _resolve_compose_base_command(self) -> tuple[list[str] | None, str]:
        env_override = (os.environ.get('HEFAISTOS_COMPOSE_CMD') or '').strip()
        candidates: list[list[str]] = []
        if env_override:
            candidates.append(env_override.split())
        candidates.extend([
            ['docker', 'compose'],
            ['docker-compose'],
        ])

        tried: set[str] = set()
        reasons: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            cmd_key = ' '.join(candidate)
            if cmd_key in tried:
                continue
            tried.add(cmd_key)
            try:
                probe = subprocess.run(
                    [*candidate, 'version'],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
            except FileNotFoundError:
                reasons.append(f"{cmd_key} command not found")
                continue
            except Exception as exc:
                reasons.append(f"{cmd_key} probe error: {exc}")
                continue

            if probe.returncode == 0:
                return candidate, f'{cmd_key} is available'

            reasons.append(f"{cmd_key} unavailable ({self._summarize_probe_output(probe)})")

        return None, '; '.join(reasons) if reasons else 'docker compose command probe failed'

    def _check_update_capability(self) -> tuple[bool, str, list[str] | None]:
        compose_file = self.repo_root / 'docker-compose.yml'
        if not compose_file.exists():
            compose_file = self.repo_root / 'docker-compose.yaml'
        if not compose_file.exists():
            return False, f'docker compose file not found under {self.repo_root}', None

        compose_base, command_reason = self._resolve_compose_base_command()
        if compose_base is None:
            return False, command_reason, None

        try:
            runtime_probe = subprocess.run(
                [*compose_base, 'ps', '--all'],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception as exc:
            return False, f'compose runtime probe failed: {exc}', compose_base

        if runtime_probe.returncode != 0:
            return False, f'compose runtime probe failed: {self._summarize_probe_output(runtime_probe)}', compose_base

        return True, command_reason, compose_base

    def _run_git_command(self, args: list[str], timeout_seconds: int) -> tuple[subprocess.CompletedProcess[str], bool]:
        """Run git command and retry once with safe.directory override on ownership warnings."""
        first = subprocess.run(
            ['git', *args],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if first.returncode == 0:
            return first, False

        if _is_dubious_ownership_error(first.stdout, first.stderr):
            retry = subprocess.run(
                ['git', '-c', f'safe.directory={self.repo_root}', *args],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            return retry, True

        return first, False

    @staticmethod
    def _friendly_repository_error(result: subprocess.CompletedProcess[str]) -> str:
        if _is_dubious_ownership_error(result.stdout, result.stderr):
            return 'Repository access is blocked by git ownership protection in this runtime. Set safe.directory for this repo path or configure HEFAISTOS_REPOSITORY_VERSION.'
        summary = SystemUpdateService._summarize_probe_output(result)
        return f'Repository version lookup failed: {summary}'

    def _read_repository_version(self) -> tuple[str | None, str, str | None]:
        """Resolve latest repo VERSION from origin/default branch without mutating local files."""
        env_override = (os.environ.get('HEFAISTOS_REPOSITORY_VERSION') or '').strip()
        if env_override:
            return env_override, 'HEFAISTOS_REPOSITORY_VERSION', None

        remote_head_ref = 'origin/HEAD'
        try:
            symref_probe, _retried = self._run_git_command(['symbolic-ref', '--short', 'refs/remotes/origin/HEAD'], timeout_seconds=6)
            if symref_probe.returncode == 0:
                candidate_ref = (symref_probe.stdout or '').strip()
                if candidate_ref:
                    remote_head_ref = candidate_ref
        except Exception:
            pass

        try:
            fetch_probe, _retried = self._run_git_command(['fetch', '--quiet', '--depth=1', 'origin'], timeout_seconds=20)
            if fetch_probe.returncode == 0:
                show_fetched, _retried = self._run_git_command(['show', 'FETCH_HEAD:VERSION'], timeout_seconds=8)
                if show_fetched.returncode == 0:
                    fetched_version = (show_fetched.stdout or '').strip()
                    if fetched_version:
                        return fetched_version, 'git FETCH_HEAD:VERSION', None
        except Exception:
            pass

        show_remote, _retried = self._run_git_command(['show', f'{remote_head_ref}:VERSION'], timeout_seconds=8)
        if show_remote.returncode == 0:
            remote_version = (show_remote.stdout or '').strip()
            if remote_version:
                return remote_version, f'git {remote_head_ref}:VERSION', None

        reason = self._friendly_repository_error(show_remote)
        return None, f'git {remote_head_ref}:VERSION', reason

    def _command_steps(self, force: bool, compose_base: list[str] | None = None) -> list[UpdateStep]:
        cmd = compose_base or ['docker', 'compose']

        def compose(*args: str) -> list[str]:
            return [*cmd, *args]

        if force:
            return [
                UpdateStep('compose_down', compose('down', '--remove-orphans'), self.DEFAULT_STEP_TIMEOUT_SECONDS),
                UpdateStep('compose_pull', compose('pull'), self.DEFAULT_STEP_TIMEOUT_SECONDS),
                UpdateStep('compose_up', compose('--profile', 'workers', '--profile', 'obs', '--profile', 'devtools', 'up', '-d', '--build', '--remove-orphans'), self.DEFAULT_STEP_TIMEOUT_SECONDS),
                UpdateStep('compose_migrate', compose('--profile', 'batch', 'run', '--rm', 'migrate'), self.DEFAULT_STEP_TIMEOUT_SECONDS),
            ]
        return [
            UpdateStep('compose_pull', compose('pull'), self.DEFAULT_STEP_TIMEOUT_SECONDS),
            UpdateStep('compose_migrate', compose('--profile', 'batch', 'run', '--rm', 'migrate'), self.DEFAULT_STEP_TIMEOUT_SECONDS),
            UpdateStep('compose_up', compose('--profile', 'workers', '--profile', 'obs', '--profile', 'devtools', 'up', '-d', '--build', '--remove-orphans'), self.DEFAULT_STEP_TIMEOUT_SECONDS),
        ]

    def _append_log(self, job: SystemUpdateJob, line: str):
        job.logs.append({'ts': _iso_utc(_utc_now()) or '', 'line': redact_sensitive(line.rstrip())})

    def _run_step(self, job: SystemUpdateJob, step: UpdateStep):
        self._append_log(job, f"$ {' '.join(step.command)}")
        process = subprocess.Popen(
            step.command,
            cwd=str(self.repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        line_queue: queue.Queue[str | None] = queue.Queue()

        def _reader():
            if process.stdout is None:
                line_queue.put(None)
                return
            for line in iter(process.stdout.readline, ''):
                line_queue.put(line)
            line_queue.put(None)

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        deadline = time.monotonic() + step.timeout_seconds
        stdout_closed = False

        while True:
            remaining = max(0.05, min(0.5, deadline - time.monotonic()))
            try:
                item = line_queue.get(timeout=remaining)
                if item is None:
                    stdout_closed = True
                else:
                    self._append_log(job, item)
            except queue.Empty:
                pass

            if time.monotonic() > deadline:
                process.kill()
                raise TimeoutError(f"Step timed out after {step.timeout_seconds}s: {' '.join(step.command)}")

            if process.poll() is not None and stdout_closed:
                break

        return_code = process.wait(timeout=5)
        if return_code != 0:
            raise RuntimeError(f"Step failed with exit code {return_code}: {' '.join(step.command)}")

    def _verify_minimal_readiness(self, job: SystemUpdateJob, compose_base: list[str]):
        step = UpdateStep('compose_health_check', [*compose_base, 'ps', '--services', '--filter', 'status=running'], 60)
        self._append_log(job, f"$ {' '.join(step.command)}")
        result = subprocess.run(
            step.command,
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            timeout=step.timeout_seconds,
            check=False,
        )
        combined = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
        if combined:
            for line in combined.splitlines():
                self._append_log(job, line)
        running = [line.strip() for line in (result.stdout or '').splitlines() if line.strip()]
        if result.returncode != 0:
            raise RuntimeError('Readiness check failed: compose ps returned non-zero exit code')
        if not running:
            raise RuntimeError('Readiness check failed: no running compose services found')
        job.result['health'] = {'ok': True, 'running_services': running}

    def _run_job(self, job: SystemUpdateJob, steps: list[UpdateStep], compose_base: list[str]):
        job.status = 'RUNNING'
        job.started_at = _utc_now()
        overall_deadline = time.monotonic() + self.DEFAULT_OVERALL_TIMEOUT_SECONDS

        try:
            for step in steps:
                if time.monotonic() > overall_deadline:
                    raise TimeoutError(f'Update exceeded overall timeout ({self.DEFAULT_OVERALL_TIMEOUT_SECONDS}s)')

                step_state = {
                    'name': step.name,
                    'command': step.command,
                    'status': 'RUNNING',
                    'started_at': _iso_utc(_utc_now()),
                    'ended_at': None,
                }
                job.steps.append(step_state)

                try:
                    self._run_step(job, step)
                    step_state['status'] = 'SUCCESS'
                except Exception as exc:
                    step_state['status'] = 'FAILED'
                    step_state['error'] = str(exc)
                    job.failed_step = step.name
                    raise
                finally:
                    step_state['ended_at'] = _iso_utc(_utc_now())

            self._verify_minimal_readiness(job, compose_base)
            job.status = 'SUCCESS'
        except Exception as exc:
            job.status = 'FAILED'
            job.error = str(exc)
            self._append_log(job, f'Update failed: {exc}')
        finally:
            job.ended_at = _utc_now()
            with self._lock:
                if self._running_job_id == job.id:
                    self._running_job_id = None

    def get_version_info(self) -> dict[str, Any]:
        version_file = self.repo_root / 'VERSION'
        local_version = version_file.read_text(encoding='utf-8').strip() if version_file.exists() else 'unknown'
        if not local_version or local_version == 'unknown':
            local_version = _configured_version_fallback() or 'unknown'

        commit = (
            (os.environ.get('HEFAISTOS_BUILD_COMMIT') or '').strip()
            or (os.environ.get('GIT_COMMIT') or '').strip()
            or 'unknown'
        )
        try:
            result, _retried = self._run_git_command(['rev-parse', 'HEAD'], timeout_seconds=8)
            if result.returncode == 0:
                commit = (result.stdout or '').strip() or 'unknown'
        except Exception:
            pass

        capability, capability_reason, _compose_base = self._check_update_capability()
        repository_version, repository_source, repository_error = self._read_repository_version()
        update_available = _compare_versions(local_version, repository_version)

        return {
            'current_version': local_version,
            'local_version': local_version,
            'repository': {
                'version': repository_version,
                'source': repository_source,
                'checked_at': _iso_utc(_utc_now()),
                'error': repository_error,
            },
            'update_available': update_available,
            'build': {
                'commit': commit,
                'checked_at': _iso_utc(_utc_now()),
            },
            'update_capability': {
                'can_update': capability,
                'reason': capability_reason,
            },
            'running_job_id': self._running_job_id,
        }

    def start_update(self, *, actor_id: str, actor_username: str, force: bool) -> SystemUpdateJob:
        with self._lock:
            if self._running_job_id:
                raise SystemUpdateConflictError('An update job is already running.', job_id=self._running_job_id)

            capability, reason, compose_base = self._check_update_capability()
            if not capability or compose_base is None:
                raise RuntimeError(f'Update capability is unavailable: {reason}')

            mode = 'force' if force else 'default'
            job_id = str(uuid.uuid4())
            job = SystemUpdateJob(
                id=job_id,
                actor_id=actor_id,
                actor_username=actor_username,
                mode=mode,
            )
            self._jobs[job.id] = job
            self._job_order.append(job.id)
            self._running_job_id = job.id
            job.result['repo_root'] = str(self.repo_root)
            job.result['compose_command'] = ' '.join(compose_base)

            steps = self._command_steps(force, compose_base)
            thread = threading.Thread(target=self._run_job, args=(job, steps, compose_base), daemon=True)
            thread.start()
            return job

    def get_job(self, job_id: str) -> SystemUpdateJob | None:
        return self._jobs.get(str(job_id))

    def get_logs(self, job_id: str, start: int = 0, limit: int = 500) -> tuple[list[dict[str, str]], int]:
        job = self.get_job(job_id)
        if job is None:
            return [], 0
        safe_start = max(0, int(start or 0))
        safe_limit = min(max(1, int(limit or 500)), 2000)
        logs_slice = job.logs[safe_start:safe_start + safe_limit]
        return logs_slice, len(job.logs)

    def serialize_job(self, job: SystemUpdateJob) -> dict[str, Any]:
        return {
            'id': job.id,
            'actor': {
                'id': job.actor_id,
                'username': job.actor_username,
            },
            'mode': job.mode,
            'status': job.status,
            'started_at': _iso_utc(job.started_at),
            'ended_at': _iso_utc(job.ended_at),
            'failed_step': job.failed_step,
            'error': job.error,
            'steps': job.steps,
            'summary': {
                'success': job.status == 'SUCCESS',
                'mode': job.mode,
                'failed_step': job.failed_step,
                'started_at': _iso_utc(job.started_at),
                'ended_at': _iso_utc(job.ended_at),
            },
            'result': job.result,
        }


_service_instance = SystemUpdateService()


def get_system_update_service() -> SystemUpdateService:
    return _service_instance


def emit_update_audit_event(*, request: Any, user: Any, action: str, outcome: str, reason: str, mode: str | None = None, job_id: str | None = None, status_code: int | None = None):
    emit_security_event(
        level='informational' if outcome == 'success' else 'warning',
        logger_name='security.system_update',
        message=f'System update {action} {outcome}',
        event_action=f'system_update.{action}',
        event_outcome=outcome,
        event_reason=reason,
        asvs_event_code='SYS-UPD-01',
        user_id=str(getattr(user, 'id', 'unknown')),
        user_name=getattr(user, 'username', None),
        request=request,
        http_status_code=status_code,
        event_category=['configuration', 'availability'],
        event_type=['change' if action == 'start' else 'info', outcome],
        extra_context={
            'mode': mode,
            'job_id': job_id,
            'timestamp': _iso_utc(_utc_now()),
        },
    )
