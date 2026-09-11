"""
OpenTIDE HEF Import Worker
==========================
RabbitMQ consumer that processes asynchronous OpenTIDE HEF import jobs.

Listens on the ``opentide.hef.import.queued`` routing key and:
  1. Marks the job as PROCESSING
  2. Resolves the GitHub repository credentials from profile or manual fields
  3. For each selected bundle: fetch → validate → bundle_to_hex_v2 →
     deserialize_playbook_graph_hex_v2 (or update on OVERWRITE)
  4. Optionally imports per-platform rule files as DetectionRule objects
  5. Honours the Dry-run flag (validate only, no DB writes)
  6. Checks idempotency key (profile_id, commit_sha, bundle_path) to skip duplicates
  7. Enforces the hard cap HEF_IMPORT_MAX_BUNDLES_PER_JOB (default 100)
  8. Writes ActivityLog entries and final COMPLETED / FAILED status
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import django
import pika

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

if not django.conf.settings.configured:
    django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from core.rabbitmq import EXCHANGE_NAME, RABBITMQ_HOST, RABBITMQ_PASS, RABBITMQ_PORT, RABBITMQ_USER  # noqa: E402
from organizations.models import OpenTideHefImportJob  # noqa: E402
from playbooks.hef_import import (  # noqa: E402
    bundle_to_hex_v2,
    discover_hef_bundles,
    fetch_bundle_files,
    get_repo_client,
    import_per_platform_rules,
    validate_bundle,
)

logger = logging.getLogger(__name__)

QUEUE_NAME = 'opentide.hef.import.jobs'
ROUTING_KEY_IN = 'opentide.hef.import.queued'


def _get_max_bundles() -> int:
    return int(getattr(settings, 'HEF_IMPORT_MAX_BUNDLES_PER_JOB', 100))


def _resolve_repo_details(job: 'OpenTideHefImportJob'):
    """Return (repo_owner, repo_name, branch, token, target_folder, repo_url, provider, api_base_url, verify_ssl)."""
    from playbooks.hef_publish import extract_repository_details

    if job.profile:
        repo = job.profile.repository
        if not repo:
            raise RuntimeError('HEF publish profile has no repository configured')
        details = extract_repository_details(repo.git_url)
        if not details:
            raise RuntimeError(f'Cannot parse owner/repo from URL: {repo.git_url}')
        repo_owner, repo_name, _provider = details
        branch = job.profile.branch or 'main'
        token = repo.token or ''
        target_folder = job.profile.target_folder or job.target_folder or ''
        repo_url = repo.git_url
        provider = repo.provider
        api_base_url = repo.api_base_url
        verify_ssl = bool(getattr(repo, 'verify_ssl', True))
    else:
        repo_owner = job.repo_owner
        repo_name = job.repo_name
        branch = job.branch or 'main'
        target_folder = job.target_folder or ''
        from rules.models import RuleRepository
        repo_qs = RuleRepository.objects.filter(
            organization=job.organization,
            git_url__icontains=f'/{repo_owner}/{repo_name}',
        )
        repo_obj = repo_qs.first() if repo_qs.exists() else None
        token = repo_obj.token if repo_obj else ''
        repo_url = repo_obj.git_url if repo_obj else f'https://github.com/{repo_owner}/{repo_name}'
        provider = repo_obj.provider if repo_obj else 'GITHUB'
        api_base_url = repo_obj.api_base_url if repo_obj else None
        verify_ssl = bool(getattr(repo_obj, 'verify_ssl', True)) if repo_obj else True

    if not token:
        raise RuntimeError(
            f'No repository token available for {repo_owner}/{repo_name}. '
            'Configure a repository with a PAT or use a HEF publish profile.'
        )
    return repo_owner, repo_name, branch, token, target_folder, repo_url, provider, api_base_url, verify_ssl


def _idempotency_key(job, bundle_path: str) -> str:
    profile_id = str(job.profile_id) if job.profile_id else 'manual'
    return f'{profile_id}::{job.source_commit_sha}::{bundle_path}'


def process_import_job(task_id: str) -> None:
    logger.info('Processing HEF import job %s', task_id)

    try:
        job = OpenTideHefImportJob.objects.select_related(
            'user', 'organization', 'profile__repository',
        ).get(pk=task_id)
    except OpenTideHefImportJob.DoesNotExist:
        logger.error('HEF import job %s not found - skipping', task_id)
        return

    if job.status not in ('QUEUED',):
        logger.warning('HEF import job %s already in status %s - skipping', task_id, job.status)
        return

    job.status = 'PROCESSING'
    job.started_at = timezone.now()
    job.progress = 'Starting HEF import process...'
    job.save(update_fields=['status', 'started_at', 'progress'])

    results = []
    error_message = ''

    try:
        repo_owner, repo_name, branch, token, target_folder, repo_url, provider, api_base_url, verify_ssl = _resolve_repo_details(job)

        # --- Discover bundles when no specific paths were pre-selected ---
        selected_paths = job.selected_bundles or []
        commit_sha = job.source_commit_sha or ''

        discovered_files_by_path = {}
        if not selected_paths:
            job.progress = 'Discovering HEF bundles...'
            job.save(update_fields=['progress'])
            bundles, resolved_sha = discover_hef_bundles(
                repo_owner, repo_name, branch, token,
                target_folder=target_folder,
                commit_sha=commit_sha or None,
                repo_url=repo_url,
                provider=provider,
                api_base_url=api_base_url,
                verify_ssl=verify_ssl,
            )
            discovered_files_by_path = {
                b.get('path'): b.get('files')
                for b in bundles
                if isinstance(b, dict) and b.get('path') and isinstance(b.get('files'), dict)
            }
            selected_paths = [b['path'] for b in bundles]
            if not commit_sha:
                commit_sha = resolved_sha
                job.source_commit_sha = commit_sha
                job.save(update_fields=['source_commit_sha'])

        # --- Enforce hard cap ---
        max_bundles = _get_max_bundles()
        if len(selected_paths) > max_bundles:
            selected_paths = selected_paths[:max_bundles]
            logger.warning(
                'HEF import job %s: truncated to %d bundles (cap=%d)',
                task_id, max_bundles, max_bundles,
            )

        total = len(selected_paths)
        job.progress = f'0/{total} bundles processed'
        job.save(update_fields=['progress'])

        for idx, bundle_path in enumerate(selected_paths, start=1):
            bundle_result = {
                'bundle_path': bundle_path,
                'workbench_id': None,
                'status': 'PENDING',
                'errors': [],
            }

            try:
                # --- Idempotency check ---
                ikey = _idempotency_key(job, bundle_path)
                # Check for an already-completed import job covering the same key
                from playbooks.models import PlaybookGraph
                already_exists = PlaybookGraph.objects.filter(
                    organization=job.organization,
                    imported_from_repo=f'{repo_owner}/{repo_name}',
                    imported_from_commit_sha=commit_sha,
                    imported_from_path=bundle_path,
                ).exists()
                if already_exists and job.conflict_mode == 'SKIP':
                    bundle_result['status'] = 'SKIPPED'
                    bundle_result['errors'] = ['Skipped: already imported with identical idempotency key']
                    results.append(bundle_result)
                    job.progress = f'{idx}/{total} bundles processed'
                    job.results = results
                    job.save(update_fields=['progress', 'results'])
                    continue

                # --- Fetch bundle YAML files ---
                # Resolve the sibling paths from the MDR path
                discovered_files = discovered_files_by_path.get(bundle_path) or {}
                if discovered_files:
                    file_paths = {
                        'mdr': discovered_files.get('mdr') or bundle_path,
                        'tvm': discovered_files.get('tvm'),
                        'dom': discovered_files.get('dom'),
                        'bdr': discovered_files.get('bdr'),
                    }
                else:
                    file_paths = _infer_file_paths(bundle_path, target_folder)
                fetched = fetch_bundle_files(
                    repo_owner,
                    repo_name,
                    token,
                    file_paths,
                    commit_sha,
                    repo_url=repo_url,
                    provider=provider,
                    api_base_url=api_base_url,
                    verify_ssl=verify_ssl,
                )

                # Also fetch platform rule files
                platform_files = _fetch_platform_files(
                    repo_owner,
                    repo_name,
                    token,
                    bundle_path,
                    target_folder,
                    commit_sha,
                    repo_url=repo_url,
                    provider=provider,
                    api_base_url=api_base_url,
                    verify_ssl=verify_ssl,
                )

                # --- Validate ---
                is_valid, validation_errors = validate_bundle(fetched)
                if not is_valid:
                    bundle_result['status'] = 'VALIDATION_FAILED'
                    bundle_result['errors'] = validation_errors
                    results.append(bundle_result)
                    job.progress = f'{idx}/{total} bundles processed'
                    job.results = results
                    job.save(update_fields=['progress', 'results'])
                    continue

                if job.dry_run:
                    bundle_result['status'] = 'DRY_RUN_OK'
                    results.append(bundle_result)
                    job.progress = f'{idx}/{total} bundles processed'
                    job.results = results
                    job.save(update_fields=['progress', 'results'])
                    continue

                # --- Convert to HEX v2 ---
                hex_doc = bundle_to_hex_v2(fetched)
                mdr_uuid = hex_doc.get('metadata', {}).get('mdr_uuid', '')

                # --- Conflict handling ---
                from playbooks.schema import deserialize_playbook_graph_hex_v2, update_playbook_graph_from_hex_v2

                existing_graph = None
                if mdr_uuid:
                    existing_graph = PlaybookGraph.objects.filter(
                        organization=job.organization,
                        imported_from_path__endswith=mdr_uuid,
                    ).first() or PlaybookGraph.objects.filter(
                        organization=job.organization,
                        title=hex_doc['metadata']['name'],
                    ).first()

                if existing_graph and job.conflict_mode == 'SKIP':
                    bundle_result['status'] = 'SKIPPED'
                    bundle_result['workbench_id'] = str(existing_graph.id)
                    bundle_result['errors'] = ['Skipped: workbench with matching MDR UUID already exists']
                    results.append(bundle_result)
                    job.progress = f'{idx}/{total} bundles processed'
                    job.results = results
                    job.save(update_fields=['progress', 'results'])
                    continue

                if existing_graph and job.conflict_mode == 'OVERWRITE':
                    graph = update_playbook_graph_from_hex_v2(hex_doc, existing_graph, job.user, None)
                else:
                    # NEW_COPY or no conflict: append restore suffix when there is a UUID conflict
                    if existing_graph and job.conflict_mode == 'NEW_COPY':
                        restore_date = timezone.now().strftime('%Y-%m-%d')
                        hex_doc['metadata']['name'] = (
                            f'{hex_doc["metadata"]["name"]} (restored {restore_date})'
                        )
                    graph = deserialize_playbook_graph_hex_v2(hex_doc, job.organization, job.user)

                # --- Populate provenance fields ---
                graph.imported_from_repo = f'{repo_owner}/{repo_name}'
                graph.imported_from_commit_sha = commit_sha
                graph.imported_from_path = bundle_path
                graph.imported_at = timezone.now()
                graph.imported_by = job.user
                graph.save(update_fields=[
                    'imported_from_repo', 'imported_from_commit_sha',
                    'imported_from_path', 'imported_at', 'imported_by',
                ])

                # --- Per-platform rule import ---
                if job.import_platform_rules and platform_files:
                    fetched_with_platform = dict(fetched)
                    fetched_with_platform['platform_files'] = platform_files
                    import_per_platform_rules(graph, fetched_with_platform)

                # --- ActivityLog ---
                from playbooks.models import ActivityLog
                ActivityLog.objects.create(
                    playbook=graph,
                    user=job.user,
                    action='OPENTIDE_HEF_IMPORT',
                    details=(
                        f'Imported from {repo_owner}/{repo_name}@{commit_sha[:8]} '
                        f'bundle: {bundle_path}'
                    ),
                )

                bundle_result['status'] = 'COMPLETED'
                bundle_result['workbench_id'] = str(graph.id)

            except Exception as exc:
                logger.exception('HEF import job %s: error processing bundle %s', task_id, bundle_path)
                bundle_result['status'] = 'FAILED'
                bundle_result['errors'] = [str(exc)]

            results.append(bundle_result)
            job.progress = f'{idx}/{total} bundles processed'
            job.results = results
            job.save(update_fields=['progress', 'results'])

        # --- Final status ---
        failed = [r for r in results if r['status'] == 'FAILED']
        completed = [r for r in results if r['status'] == 'COMPLETED']
        if not results:
            job.status = 'FAILED'
            error_message = 'No bundles were found or processed'
        elif failed and not completed:
            job.status = 'FAILED'
            error_message = f'All {len(failed)} bundles failed to import'
        else:
            job.status = 'COMPLETED'
            if failed:
                error_message = f'{len(failed)} bundle(s) failed; {len(completed)} completed'

    except Exception as exc:
        logger.exception('HEF import job %s failed with unhandled error', task_id)
        job.status = 'FAILED'
        error_message = str(exc)

    job.completed_at = timezone.now()
    job.error_message = error_message
    job.results = results
    job.save(update_fields=['status', 'completed_at', 'error_message', 'results'])
    logger.info(
        'HEF import job %s finished with status=%s results=%d',
        task_id, job.status, len(results),
    )


def _infer_file_paths(
    mdr_path: str,
    target_folder: str,
) -> dict:
    """Derive expected TVM/DOM/MDR/BDR paths from the known MDR path.

    The structure within a target_folder is::

        Objects/Threat Vectors/<name>.yaml
        Objects/Detection Objectives/<name>.yaml
        Objects/Detection Rules/<name>.yaml   ← mdr_path
        Objects/Business Rules/<name>.yaml

    We extract <name> from the MDR path and reconstruct the siblings.
    """
    import posixpath

    # Strip target_folder prefix
    base = (target_folder or '').strip('/')
    prefix = (base + '/') if base else ''

    mdr_dir = f'{prefix}Objects/Detection Rules/'
    if mdr_path.startswith(mdr_dir):
        name = mdr_path[len(mdr_dir):]
        if name.endswith('.yaml'):
            name = name[:-5]
    else:
        # Fallback: use filename stem
        name = posixpath.basename(mdr_path).replace('.yaml', '')

    lower_name = name.lower()

    # New title-based format:
    #   <Title>_mdr.yaml + siblings <Title>_tvm|dom|bdr.yaml
    if lower_name.endswith('_mdr'):
        root = name[:-4]
        return {
            'mdr': mdr_path,
            'tvm': f'{prefix}Objects/Threat Vectors/{root}_tvm.yaml',
            'dom': f'{prefix}Objects/Detection Objectives/{root}_dom.yaml',
            'bdr': f'{prefix}Objects/Business Rules/{root}_bdr.yaml',
        }

    # Legacy heuristic format:
    #   mdr_<x>.yaml + siblings dom_<x>.yaml / tvm_<x>.yaml / bdr_<x>.yaml
    if lower_name.startswith('mdr_'):
        root = name[4:]
        return {
            'mdr': mdr_path,
            'tvm': f'{prefix}Objects/Threat Vectors/tvm_{root}.yaml',
            'dom': f'{prefix}Objects/Detection Objectives/dom_{root}.yaml',
            'bdr': f'{prefix}Objects/Business Rules/bdr_{root}.yaml',
        }

    # Generic fallback: use identical stem across object folders.
    return {
        'mdr': mdr_path,
        'tvm': f'{prefix}Objects/Threat Vectors/{name}.yaml',
        'dom': f'{prefix}Objects/Detection Objectives/{name}.yaml',
        'bdr': f'{prefix}Objects/Business Rules/{name}.yaml',
    }


def _fetch_platform_files(
    repo_owner: str,
    repo_name: str,
    token: str,
    mdr_path: str,
    target_folder: str,
    commit_sha: str,
    *,
    repo_url: str | None = None,
    provider: str = 'AUTO',
    api_base_url: str | None = None,
    verify_ssl: bool = True,
) -> dict:
    """Try to discover and fetch per-platform rule files adjacent to the bundle.

    Returns a mapping of platform → list of ``{path, content}`` dicts.
    Does not raise on failure; logs warnings instead.
    """
    import posixpath
    from playbooks.hef_import import _PLATFORM_SUBDIRS

    base = (target_folder or '').strip('/')
    prefix = (base + '/') if base else ''

    mdr_dir = f'{prefix}Objects/Detection Rules/'
    if mdr_path.startswith(mdr_dir):
        name_with_ext = mdr_path[len(mdr_dir):]
        name = name_with_ext[:-5] if name_with_ext.endswith('.yaml') else name_with_ext
    else:
        name = posixpath.basename(mdr_path).replace('.yaml', '')

    name_candidates = [name]
    lower_name = name.lower()
    if lower_name.endswith('_mdr'):
        name_candidates.append(name[:-4])
    else:
        name_candidates.append(f'{name}_mdr')
    if lower_name.startswith('mdr_'):
        name_candidates.append(name[4:])

    # Preserve order while removing duplicates.
    deduped_candidates = []
    seen_candidates = set()
    for candidate in name_candidates:
        if candidate and candidate not in seen_candidates:
            deduped_candidates.append(candidate)
            seen_candidates.add(candidate)

    platform_files: dict = {}
    client = get_repo_client(
        repo_url=repo_url or f'https://github.com/{repo_owner}/{repo_name}',
        token=token,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )

    for platform in _PLATFORM_SUBDIRS:
        # Try common extensions
        for ext in ('.kql', '.spl', '.spl', '.yml', '.yaml', '.xml'):
            if platform == 'kql' and ext not in ('.kql',):
                continue
            if platform in ('sigma', 'wazuh') and ext not in ('.yml', '.yaml', '.xml'):
                continue
            found = False
            for candidate in deduped_candidates:
                path = f'{prefix}{platform}/{candidate}{ext}'
                try:
                    content = client.get_file_content(path, commit_sha)
                    if content is not None:
                        platform_files.setdefault(platform, []).append({'path': path, 'content': content})
                        found = True
                        break
                except Exception as exc:
                    logger.debug('HEF import: could not fetch platform file %s: %s', path, exc)
            if found:
                break  # found one, stop trying extensions

    return platform_files


def on_message(channel, method, properties, body):
    try:
        payload = json.loads(body)
        task_id = payload.get('task_id')
        if not task_id:
            logger.error('HEF import worker: received message without task_id - discarding')
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        process_import_job(task_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception('HEF import worker: unhandled error in on_message')
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def run_worker(max_retries: int = 10, retry_delay: int = 5) -> None:
    connection = None
    for attempt in range(1, max_retries + 1):
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            connection = pika.BlockingConnection(parameters)
            break
        except Exception as exc:
            logger.warning(
                'HEF import worker: RabbitMQ connection attempt %d/%d failed: %s',
                attempt, max_retries, exc,
            )
            if attempt < max_retries:
                time.sleep(retry_delay)

    if not connection or not connection.is_open:
        logger.error('Could not connect to RabbitMQ after %d attempts - exiting', max_retries)
        return

    channel = connection.channel()
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY_IN)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    logger.info(
        'OpenTIDE HEF import worker listening on queue %s (routing key: %s)',
        QUEUE_NAME, ROUTING_KEY_IN,
    )

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info('HEF import worker shutting down...')
        channel.stop_consuming()
    finally:
        if connection and connection.is_open:
            connection.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_worker()
