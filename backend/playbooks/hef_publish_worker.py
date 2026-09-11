"""
OpenTIDE HEF Publish Worker
===========================
RabbitMQ consumer that processes asynchronous OpenTIDE HEF publish jobs.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import django
import pika

try:
    from elasticsearch.helpers import BulkIndexError as _EsBulkIndexError
except ImportError:  # pragma: no cover
    class _EsBulkIndexError(Exception):  # type: ignore[no-redef]
        errors: list = []

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

if not django.conf.settings.configured:
    django.setup()

from django.utils import timezone  # noqa: E402

from core.rabbitmq import EXCHANGE_NAME, publish_event, RABBITMQ_HOST, RABBITMQ_PASS, RABBITMQ_PORT, RABBITMQ_USER  # noqa: E402
from organizations.models import OpenTideHefPublishJob  # noqa: E402
from playbooks.hef_publish import (  # noqa: E402
    compile_opentide_bundle,
    compile_platform_rule_files,
    create_repository_commit,
)
from playbooks.repo_clients import RepoClient  # noqa: E402
from rules.opentide_publish import (  # noqa: E402
    OpenTideMDRValidationError,
    build_deployment_failure_summary,
    deploy_opentide_rule_to_platforms,
    upsert_opentide_rule_for_graph,
)

logger = logging.getLogger(__name__)

QUEUE_NAME = 'opentide.hef.publish.jobs'
ROUTING_KEY_IN = 'opentide.hef.publish.queued'
ROUTING_KEY_COMPLETED = 'opentide.hef.publish.completed'
ROUTING_KEY_FAILED = 'opentide.hef.publish.failed'

_MAX_ES_ERRORS_TO_LOG = 5
_MAX_TRACEBACK_LENGTH = 2000


def _recover_rule_after_index_failure(job, playbook, repository, mdr_yaml):
    from rules.models import DetectionRule  # noqa: PLC0415

    rule = DetectionRule.objects.filter(
        organization=job.organization,
        playbook=playbook,
        format='OPENTIDE',
    ).order_by('-updated_at').first()
    if rule is not None:
        return rule

    fallback_rule = DetectionRule(
        organization=job.organization,
        repository=repository,
        playbook=playbook,
        format='OPENTIDE',
        title=f"{playbook.title}-opentide",
        description='',
        author=(getattr(playbook.author, 'username', None) or 'unknown'),
        status='experimental',
        raw_content=mdr_yaml,
    )
    DetectionRule.objects.bulk_create([fallback_rule])

    return DetectionRule.objects.filter(
        organization=job.organization,
        playbook=playbook,
        format='OPENTIDE',
    ).order_by('-updated_at').first()


def _build_hef_index_entry(bundle, mdr_data: dict, commit_sha: str) -> dict:
    import datetime as _dt

    meta = mdr_data.get('metadata') or {}
    return {
        'path': bundle.get('mdr_path') or bundle.get('primary_path', ''),
        'mdr_uuid': str(meta.get('uuid') or ''),
        'title': meta.get('title') or mdr_data.get('name') or '',
        'status': meta.get('status') or mdr_data.get('status') or '',
        'last_commit_sha': commit_sha,
        'exported_at': _dt.datetime.utcnow().isoformat() + 'Z',
    }


def _update_repo_hef_index(
    client: RepoClient,
    bundle: dict,
    mdr_data: dict,
    commit_sha: str,
    target_folder: str,
    branch: str,
) -> None:
    base = (target_folder or '').strip('/')
    index_path = f'{base}/_hef_index.json' if base else '_hef_index.json'

    existing_content = client.get_file_content(index_path, branch)
    existing_entries: list = []
    if existing_content:
        try:
            existing_entries = json.loads(existing_content)
            if not isinstance(existing_entries, list):
                existing_entries = []
        except (json.JSONDecodeError, ValueError):
            existing_entries = []

    new_entry = _build_hef_index_entry(bundle, mdr_data, commit_sha)
    updated = [e for e in existing_entries if e.get('path') != new_entry['path']]
    updated.append(new_entry)

    client.commit_files(
        branch=branch,
        files={index_path: json.dumps(updated, indent=2, ensure_ascii=False)},
        commit_message='chore: update _hef_index.json manifest [skip ci]',
    )


def process_publish_job(task_id: str) -> None:
    logger.info('Processing HEF publish job %s', task_id)

    try:
        job = OpenTideHefPublishJob.objects.select_related(
            'playbook__organization', 'playbook__mitre_technique', 'user', 'profile', 'repository'
        ).prefetch_related('playbook__tags', 'playbook__linked_rules').get(pk=task_id)
    except OpenTideHefPublishJob.DoesNotExist:
        logger.error('HEF publish job %s not found - skipping', task_id)
        return

    if job.status not in ('QUEUED',):
        logger.warning('HEF publish job %s is already in status %s - skipping', task_id, job.status)
        return

    job.status = 'PROCESSING'
    job.started_at = timezone.now()
    job.progress = 'Starting HEF publish process...'
    job.save(update_fields=['status', 'started_at', 'progress'])

    playbook = job.playbook
    actor = job.user or getattr(playbook, 'author', None)
    repository = job.repository or (job.profile.repository if job.profile else None)

    try:
        if actor is None:
            raise RuntimeError('No actor available for HEF publish job')
        if repository is None:
            raise RuntimeError('No repository configured for HEF publish job')
        if not repository.git_url:
            raise RuntimeError('Selected repository has no git URL configured')
        if not repository.token:
            raise RuntimeError('Selected repository has no access token configured')

        job.progress = 'Compiling and validating OpenTIDE HEF bundle...'
        job.save(update_fields=['progress'])

        bundle, validation_errors = compile_opentide_bundle(
            playbook,
            target_folder=job.target_folder,
            use_ai_enrichment=False,
            force_bdr_generation=False,
        )
        if validation_errors:
            raise RuntimeError('OpenTIDE validation failed: ' + '; '.join(validation_errors))
        if bundle is None:
            raise RuntimeError('Failed to build OpenTIDE HEF bundle')

        repo_files = {}
        primary_path = None

        if job.push_opentide_bundle:
            repo_files.update(bundle['files'])
            primary_path = bundle['primary_path']

        if job.push_platform_rules:
            job.progress = 'Preparing standalone platform rule files...'
            job.save(update_fields=['progress'])
            rule_bundle, rule_errors = compile_platform_rule_files(
                playbook,
                target_folder=job.target_folder,
            )
            if rule_errors and not job.push_opentide_bundle:
                raise RuntimeError('Platform rules extraction failed: ' + '; '.join(rule_errors))
            if rule_bundle:
                repo_files.update(rule_bundle['files'])
                if primary_path is None:
                    primary_path = rule_bundle.get('primary_path')

        if not repo_files:
            raise RuntimeError('Nothing selected to push to repository.')

        job.progress = 'Pushing YAML bundle to repository...'
        job.save(update_fields=['progress'])

        commit_sha, client = create_repository_commit(
            repo_url=repository.git_url,
            token=repository.token,
            branch=job.branch,
            files=repo_files,
            commit_message=job.commit_message,
            provider=repository.provider,
            api_base_url=repository.api_base_url,
            verify_ssl=bool(getattr(repository, 'verify_ssl', True)),
        )
        remote_url = client.file_web_url(job.branch, primary_path)

        if job.push_opentide_bundle and bundle:
            try:
                import yaml as _yaml
                mdr_data = _yaml.safe_load(bundle.get('mdr_yaml') or '') or {}
                _update_repo_hef_index(
                    client=client,
                    bundle=bundle,
                    mdr_data=mdr_data,
                    commit_sha=commit_sha,
                    target_folder=job.target_folder or '',
                    branch=job.branch,
                )
            except Exception as idx_exc:  # noqa: BLE001
                logger.warning('HEF publish: failed to update _hef_index.json (non-fatal): %s', idx_exc)

        job.progress = 'Creating or updating OpenTIDE deployment rule...'
        job.save(update_fields=['progress'])

        rule = None
        try:
            rule = upsert_opentide_rule_for_graph(
                playbook,
                actor,
                bundle['mdr_yaml'],
                repository=repository,
            )
        except Exception as es_exc:  # noqa: BLE001
            if isinstance(es_exc, _EsBulkIndexError):
                es_detail = '; '.join(
                    str(err) for err in (getattr(es_exc, 'errors', None) or [])[:_MAX_ES_ERRORS_TO_LOG]
                )
                logger.warning(
                    'HEF publish job %s: Elasticsearch indexing failed (non-fatal). message=%s | errors=%s',
                    task_id,
                    es_exc,
                    es_detail or '<none>',
                )
                rule = _recover_rule_after_index_failure(
                    job=job,
                    playbook=playbook,
                    repository=repository,
                    mdr_yaml=bundle['mdr_yaml'],
                )
                if rule is None:
                    raise RuntimeError(
                        f'Elasticsearch indexing error and DetectionRule was not found in the database after the failure: {es_exc}'
                    ) from es_exc
            else:
                raise

        deployment_results = []
        deployed_platforms = []
        failure_summary = {}
        overall_success = True
        if job.requested_platforms:
            job.progress = 'Deploying OpenTIDE rule to configured platforms...'
            job.save(update_fields=['progress'])
            deployment_results, overall_success, _message = deploy_opentide_rule_to_platforms(
                rule,
                job.organization,
                job.requested_platforms,
            )
            deployed_platforms = [result['platform'] for result in deployment_results if result['success']]

        final_job_status = 'COMPLETED'
        if job.requested_platforms and not overall_success:
            final_job_status = 'FAILED'

        job.status = final_job_status
        job.rule = rule
        job.commit_sha = commit_sha
        job.github_url = remote_url
        job.file_paths = list(repo_files.keys())
        job.deployed_platforms = deployed_platforms
        job.deployment_results = deployment_results
        if final_job_status == 'FAILED':
            failure_summary = build_deployment_failure_summary(deployment_results)
            failed_platforms = failure_summary.get('failed_platforms') or []
            failure_types = failure_summary.get('failure_type_counts') or {}
            failure_type_label = ', '.join(
                f'{kind}={count}' for kind, count in sorted(failure_types.items())
            )
            job.error_message = (
                'Repository publish succeeded, but deployment failed for platform(s): '
                + ', '.join(failed_platforms)
            )
            if failure_type_label:
                job.error_message += f' | failure_types: {failure_type_label}'
            job.progress = f'Publish completed but deployment failed: {", ".join(failed_platforms)}'
        else:
            job.progress = f'Published successfully: {commit_sha[:8]}'
        job.failure_summary = failure_summary
        job.completed_at = timezone.now()
        job.save(update_fields=[
            'status', 'rule', 'commit_sha', 'github_url', 'file_paths', 'deployed_platforms',
            'deployment_results', 'failure_summary', 'progress', 'error_message', 'completed_at'
        ])

        payload = {
            'task_id': str(task_id),
            'playbook_id': str(playbook.id),
            'commit_sha': commit_sha,
            'file_paths': job.file_paths,
            'github_url': remote_url,
            'rule_id': str(rule.id),
            'deployed_platforms': deployed_platforms,
        }
        if final_job_status == 'FAILED':
            payload['deployment_results'] = deployment_results
            payload['failure_summary'] = failure_summary
            payload['error'] = job.error_message
            publish_event(ROUTING_KEY_FAILED, payload)
        else:
            publish_event(ROUTING_KEY_COMPLETED, payload)

    except OpenTideMDRValidationError as exc:
        logger.exception('HEF publish job %s FAILED [MDR_VALIDATION]: %s', task_id, exc)
        job.status = 'FAILED'
        job.error_message = f'MDR validation failed: {exc}'
        job.failure_summary = {
            'failed_count': 1,
            'failed_platforms': [],
            'failure_type_counts': {'MDR_VALIDATION': 1},
            'operator_hints': ['Fix MDR schema/validation issues before retrying publish.'],
        }
        job.progress = f'Failed [MDR_VALIDATION]: {exc}'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'failure_summary', 'progress', 'completed_at'])
        publish_event(ROUTING_KEY_FAILED, {
            'task_id': str(task_id),
            'playbook_id': str(playbook.id) if getattr(job, 'playbook_id', None) else None,
            'failure_summary': job.failure_summary,
            'error': f'MDR_VALIDATION: {exc}',
        })
    except ValueError as exc:
        logger.exception('HEF publish job %s FAILED [PAYLOAD_CONTRACT]: %s', task_id, exc)
        job.status = 'FAILED'
        job.error_message = f'Payload contract error: {exc}'
        job.failure_summary = {
            'failed_count': 1,
            'failed_platforms': [],
            'failure_type_counts': {'PAYLOAD_CONTRACT': 1},
            'operator_hints': ['Review payload shape and required fields for OpenTIDE deployment.'],
        }
        job.progress = f'Failed [PAYLOAD_CONTRACT]: {exc}'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'failure_summary', 'progress', 'completed_at'])
        publish_event(ROUTING_KEY_FAILED, {
            'task_id': str(task_id),
            'playbook_id': str(playbook.id) if getattr(job, 'playbook_id', None) else None,
            'failure_summary': job.failure_summary,
            'error': f'PAYLOAD_CONTRACT: {exc}',
        })
    except Exception as exc:
        import traceback  # noqa: PLC0415

        exc_type = type(exc).__name__
        exc_detail = str(exc) or repr(exc)
        tb_summary = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.exception('HEF publish job %s FAILED [UNEXPECTED]: %s', task_id, exc)
        job.status = 'FAILED'
        job.error_message = f'[{exc_type}] {exc_detail}'
        job.failure_summary = {
            'failed_count': 1,
            'failed_platforms': [],
            'failure_type_counts': {exc_type: 1},
            'operator_hints': ['Inspect worker logs for stack trace and underlying exception context.'],
        }
        job.progress = f'Failed [UNEXPECTED]: [{exc_type}] {exc_detail}'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'failure_summary', 'progress', 'completed_at'])
        publish_event(ROUTING_KEY_FAILED, {
            'task_id': str(task_id),
            'playbook_id': str(playbook.id) if getattr(job, 'playbook_id', None) else None,
            'failure_summary': job.failure_summary,
            'error': f'UNEXPECTED [{exc_type}]: {exc_detail}',
            'traceback': tb_summary[-_MAX_TRACEBACK_LENGTH:],
        })


def on_message(ch, method, properties, body):
    try:
        payload = json.loads(body.decode('utf-8'))
        task_id = payload.get('task_id')
        if not task_id:
            logger.error('Received HEF publish message without task_id - discarding: %s', payload)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        logger.info('Received HEF publish job: task_id=%s', task_id)
        process_publish_job(task_id)
    except json.JSONDecodeError:
        logger.error('Failed to decode HEF publish message body: %s', body)
    except Exception as exc:  # noqa: BLE001
        logger.exception('Unexpected error handling HEF publish message: %s', exc)
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)


def run_worker(max_retries: int = 10, retry_delay: int = 5) -> None:
    connection = None

    for attempt in range(1, max_retries + 1):
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                    heartbeat=1800,
                    blocked_connection_timeout=300,
                    connection_attempts=3,
                    retry_delay=2,
                )
            )
            logger.info('Connected to RabbitMQ at %s:%s', RABBITMQ_HOST, RABBITMQ_PORT)
            break
        except pika.exceptions.AMQPConnectionError as exc:
            logger.warning(
                'RabbitMQ connection attempt %d/%d failed: %s - retrying in %ds',
                attempt, max_retries, exc, retry_delay,
            )
            time.sleep(retry_delay)
    else:
        logger.error('Could not connect to RabbitMQ after %d attempts - exiting', max_retries)
        return

    channel = connection.channel()
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY_IN)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    logger.info(
        'OpenTIDE HEF publish worker listening on queue %s (routing key: %s)',
        QUEUE_NAME, ROUTING_KEY_IN,
    )

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info('HEF publish worker shutting down...')
        channel.stop_consuming()
    finally:
        if connection and connection.is_open:
            connection.close()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    run_worker()
