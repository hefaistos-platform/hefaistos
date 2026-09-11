"""Organization-level AI-assisted scheduled operational tasks."""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

from django.db.models import Count, Q
from django.utils import timezone

from ai_assistant.ai_prompts import build_prompt_context, execute_prompt_template
from ai_assistant.engine import run_custom_prompt
from ai_assistant.models import OrgAISettings
from core.mcs_logging import emit_security_event
from identity.models import CustomUser
from mgmt_reports.models import AIPrompt, MonthlyReportSnapshot
from organizations.models import (
    DacDeploymentConfig,
    OpenTideHefPublishJob,
    Organization,
    OrganizationAITaskConfig,
    OrganizationAITaskRun,
    PlatformCredential,
)
from playbooks.models import DetectionPlaybook, PlaybookGraph
from rules.models import DetectionRule, RuleRepository
from services.publisher import get_publisher

logger = logging.getLogger(__name__)


def _emit_ai_task_event(
    *,
    config: OrganizationAITaskConfig,
    actor: Optional[CustomUser],
    trigger: str,
    status: str,
    duration_ms: int,
    summary: str,
    error_message: str,
):
    outcome = 'failure' if status == OrganizationAITaskRun.Status.FAILED else 'success'
    level = 'warning' if status == OrganizationAITaskRun.Status.FAILED else 'informational'
    reason = _truncate(error_message or summary or status, limit=500)

    try:
        emit_security_event(
            level=level,
            logger_name='security.mcs',
            message=f"Organization AI task {config.task_key} finished with status {status}",
            event_action='organization.ai_task.run',
            event_outcome=outcome,
            asvs_event_code='BIZLOGIC-AI-TASK-01',
            event_reason=reason,
            user_id=str(getattr(actor, 'id', '') or '') or None,
            user_name=getattr(actor, 'username', None) or ('scheduler' if trigger == OrganizationAITaskRun.Trigger.SCHEDULED else None),
            extra_context={
                'organization_id': str(config.organization_id),
                'task_key': config.task_key,
                'task_title': get_ai_task_definition(config.task_key).title if get_ai_task_definition(config.task_key) else config.task_key,
                'trigger': trigger,
                'status': status,
                'duration_ms': int(max(duration_ms, 0)),
            },
        )
    except Exception as exc:  # pragma: no cover - logging must never break task execution
        logger.debug('Failed to emit AI task security event: %s', exc)


@dataclass(frozen=True)
class OrgAITaskDefinition:
    key: str
    title: str
    description: str
    default_enabled: bool = False
    default_schedule: str = OrganizationAITaskConfig.Schedule.WEEKLY
    default_day_of_week: int = 0
    default_day_of_month: int = 1
    default_run_hour: int = 8
    default_run_minute: int = 0
    ai_required: bool = True


@dataclass
class TaskExecutionResult:
    status: str
    summary: str
    metadata: Dict[str, Any] | None = None


def _ok(summary: str, metadata: Optional[Dict[str, Any]] = None) -> TaskExecutionResult:
    return TaskExecutionResult(
        status=OrganizationAITaskRun.Status.SUCCESS,
        summary=summary,
        metadata=metadata or {},
    )


def _skip(summary: str, metadata: Optional[Dict[str, Any]] = None) -> TaskExecutionResult:
    return TaskExecutionResult(
        status=OrganizationAITaskRun.Status.SKIPPED,
        summary=summary,
        metadata=metadata or {},
    )


_TASK_DEFINITIONS: List[OrgAITaskDefinition] = [
    OrgAITaskDefinition(
        key='push_rules_workbenches_to_git',
        title='Push changed rules/workbenches to Git',
        description='Queue Git push/deploy jobs for eligible workbenches and produce an AI run summary.',
        default_schedule=OrganizationAITaskConfig.Schedule.WEEKLY,
        default_day_of_week=0,
        default_run_hour=8,
        ai_required=False,
    ),
    OrgAITaskDefinition(
        key='sync_deployed_l1_portal',
        title='Sync deployed L1 portal snapshots',
        description='Reconcile DEPLOYED workbenches to keep L1 portal entries and share links current.',
        default_enabled=True,
        default_schedule=OrganizationAITaskConfig.Schedule.DAILY,
        default_run_hour=6,
        ai_required=False,
    ),
    OrgAITaskDefinition(
        key='pull_all_rule_repositories',
        title='Pull all configured rule repositories',
        description='Queue repository pull jobs for all organization repositories with AI-assisted follow-up summary.',
        default_schedule=OrganizationAITaskConfig.Schedule.DAILY,
        default_run_hour=7,
        ai_required=False,
    ),
    OrgAITaskDefinition(
        key='ai_review_changed_rules',
        title='AI review of recently changed rules',
        description='Use AI to prioritize review focus and highlight likely quality/security issues in recently updated rules.',
        default_schedule=OrganizationAITaskConfig.Schedule.DAILY,
        default_run_hour=9,
    ),
    OrgAITaskDefinition(
        key='ai_similar_rule_recommendations',
        title='AI similar-rule recommendations',
        description='Generate AI recommendations for new rule variants and expansion opportunities.',
        default_schedule=OrganizationAITaskConfig.Schedule.WEEKLY,
        default_day_of_week=1,
        default_run_hour=10,
    ),
    OrgAITaskDefinition(
        key='stale_workbench_triage',
        title='Stale workbench triage',
        description='Use AI to prioritize stale/inactive workbenches and suggest concrete next actions.',
        default_schedule=OrganizationAITaskConfig.Schedule.WEEKLY,
        default_day_of_week=2,
        default_run_hour=8,
    ),
    OrgAITaskDefinition(
        key='failed_publish_deploy_triage',
        title='Failed publish/deploy triage',
        description='Use AI to summarize recent HEF publish/deploy failures and propose likely remediations.',
        default_schedule=OrganizationAITaskConfig.Schedule.DAILY,
        default_run_hour=11,
    ),
    OrgAITaskDefinition(
        key='coverage_gap_digest',
        title='Coverage gap digest',
        description='Run AI gap-analysis digest over current detection program posture.',
        default_schedule=OrganizationAITaskConfig.Schedule.WEEKLY,
        default_day_of_week=3,
        default_run_hour=8,
    ),
    OrgAITaskDefinition(
        key='detection_debt_snapshot',
        title='Detection debt snapshot',
        description='Produce AI debt snapshot with remediation priorities across rules and workbenches.',
        default_schedule=OrganizationAITaskConfig.Schedule.WEEKLY,
        default_day_of_week=4,
        default_run_hour=8,
    ),
    OrgAITaskDefinition(
        key='executive_risk_narrative',
        title='Executive risk narrative',
        description='Create AI-generated executive-level risk narrative from current security operations metrics.',
        default_schedule=OrganizationAITaskConfig.Schedule.MONTHLY,
        default_day_of_month=1,
        default_run_hour=7,
    ),
    OrgAITaskDefinition(
        key='compliance_evidence_draft',
        title='Compliance evidence draft',
        description='Generate AI draft of compliance evidence narrative for audit/governance stakeholders.',
        default_schedule=OrganizationAITaskConfig.Schedule.MONTHLY,
        default_day_of_month=2,
        default_run_hour=7,
    ),
    OrgAITaskDefinition(
        key='platform_credential_health_check',
        title='Platform credential health check + remediation',
        description='Run platform connectivity tests and generate AI remediation recommendations.',
        default_schedule=OrganizationAITaskConfig.Schedule.WEEKLY,
        default_day_of_week=1,
        default_run_hour=6,
        ai_required=False,
    ),
    OrgAITaskDefinition(
        key='program_review_digest',
        title='Program review digest',
        description='Generate monthly AI strategic program review with priority actions for the next quarter.',
        default_schedule=OrganizationAITaskConfig.Schedule.MONTHLY,
        default_day_of_month=3,
        default_run_hour=7,
    ),
]

_TASK_BY_KEY = {task.key: task for task in _TASK_DEFINITIONS}


def get_ai_task_definitions() -> List[OrgAITaskDefinition]:
    return list(_TASK_DEFINITIONS)


def get_ai_task_definition(task_key: str) -> OrgAITaskDefinition | None:
    return _TASK_BY_KEY.get((task_key or '').strip())


def _clamp(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, ivalue))


def compute_next_run_at(
    config: OrganizationAITaskConfig,
    reference: Optional[Any] = None,
) -> Any:
    """Compute next scheduled execution time for a task configuration."""
    now = reference or timezone.now()
    run_hour = _clamp(config.run_hour, 0, 23, 8)
    run_minute = _clamp(config.run_minute, 0, 59, 0)
    schedule = (config.schedule or OrganizationAITaskConfig.Schedule.WEEKLY).upper()

    if schedule == OrganizationAITaskConfig.Schedule.DAILY:
        candidate = now.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if schedule == OrganizationAITaskConfig.Schedule.WEEKLY:
        day_of_week = _clamp(config.day_of_week, 0, 6, 0)
        days_ahead = (day_of_week - now.weekday()) % 7
        candidate = (now + timedelta(days=days_ahead)).replace(
            hour=run_hour,
            minute=run_minute,
            second=0,
            microsecond=0,
        )
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    # MONTHLY
    day_of_month = _clamp(config.day_of_month, 1, 28, 1)
    current_month_last = calendar.monthrange(now.year, now.month)[1]
    safe_day = min(day_of_month, current_month_last)
    candidate = now.replace(
        day=safe_day,
        hour=run_hour,
        minute=run_minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now:
        if now.month == 12:
            year, month = now.year + 1, 1
        else:
            year, month = now.year, now.month + 1
        month_last = calendar.monthrange(year, month)[1]
        candidate = candidate.replace(year=year, month=month, day=min(day_of_month, month_last))
    return candidate


def _truncate(text: str, limit: int = 12000) -> str:
    raw = (text or '').strip()
    if len(raw) <= limit:
        return raw
    return raw[: limit - 3] + '...'


def _resolve_context_user(
    organization: Organization,
    preferred: Optional[CustomUser] = None,
) -> Optional[CustomUser]:
    if preferred and getattr(preferred, 'organization_id', None) == organization.id:
        return preferred
    admins = (
        CustomUser.objects
        .filter(organization=organization, is_active=True)
        .filter(Q(role='ADMIN') | Q(is_superuser=True) | Q(is_staff=True))
        .order_by('id')
    )
    if admins.exists():
        return admins.first()
    return (
        CustomUser.objects
        .filter(organization=organization, is_active=True)
        .order_by('id')
        .first()
    )


def _get_org_ai_settings(organization: Organization) -> tuple[Optional[OrgAISettings], Optional[str]]:
    settings = OrgAISettings.objects.filter(organization=organization).first()
    if not settings:
        return None, 'Organization AI settings are not configured.'
    if not settings.has_any_provider:
        return None, 'Organization AI provider is not configured or all providers are disabled.'
    return settings, None


def _run_org_ai_prompt(
    organization: Organization,
    user_prompt: str,
    system_prompt: Optional[str] = None,
) -> tuple[Optional[str], str, Optional[str]]:
    settings, settings_error = _get_org_ai_settings(organization)
    if settings_error:
        return None, 'NONE', settings_error
    try:
        result_text, provider = run_custom_prompt(
            settings,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        logger.exception('AI prompt execution failed for org=%s: %s', organization.id, exc)
        return None, 'NONE', f'AI prompt execution failed: {exc}'

    result_text = (result_text or '').strip()
    if not result_text:
        return None, provider, 'AI returned an empty response.'
    if result_text.startswith('Error:'):
        return None, provider, result_text
    return result_text, provider, None


def _execute_seed_prompt(
    organization: Organization,
    actor: Optional[CustomUser],
    prompt_title: str,
    custom_input: str = '',
    custom_context: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], str, Optional[str]]:
    prompt = AIPrompt.objects.filter(title=prompt_title, is_active=True).first()
    if not prompt:
        return None, 'NONE', f"Prompt '{prompt_title}' is not available."

    settings, settings_error = _get_org_ai_settings(organization)
    if settings_error:
        return None, 'NONE', settings_error

    context_user = _resolve_context_user(organization, actor)
    if not context_user:
        return None, 'NONE', 'No active user exists in organization to build prompt context.'

    context = build_prompt_context(
        context_user,
        custom_input=custom_input,
        custom_context=custom_context or {},
    )
    try:
        _rendered_prompt, result_markdown, provider = execute_prompt_template(
            settings,
            prompt.prompt_template,
            context,
            prompt_title=prompt.title,
        )
    except Exception as exc:
        logger.exception('Seed prompt execution failed for org=%s prompt=%s: %s', organization.id, prompt_title, exc)
        return None, 'NONE', f"Prompt '{prompt_title}' failed: {exc}"

    result_markdown = (result_markdown or '').strip()
    if not result_markdown:
        return None, provider, f"Prompt '{prompt_title}' returned an empty result."
    if result_markdown.startswith('Error:'):
        return None, provider, result_markdown
    return result_markdown, provider, None


def _task_push_rules_workbenches_to_git(
    organization: Organization,
    actor: Optional[CustomUser],
) -> TaskExecutionResult:
    dac = DacDeploymentConfig.objects.filter(organization=organization).first()
    if not dac or dac.mode == DacDeploymentConfig.Mode.NONE:
        return _skip('DaC deployment mode is disabled (NONE); no Git push automation is configured.')

    eligible = list(
        PlaybookGraph.objects.filter(
            organization=organization,
            status__in=[
                DetectionPlaybook.PlaybookStatus.APPROVED,
                DetectionPlaybook.PlaybookStatus.DEPLOYED,
            ],
        ).order_by('-updated_at')[:50]
    )
    if not eligible:
        return _skip('No APPROVED/DEPLOYED workbenches available for Git push automation.')

    # Private helper in playbooks.schema is the same logic used on DEPLOYED transitions.
    from playbooks.schema import _queue_dac_deployment_automation  # pylint: disable=import-outside-toplevel

    run_actor = _resolve_context_user(organization, actor)
    queued = 0
    errors: List[str] = []
    for graph in eligible:
        try:
            if _queue_dac_deployment_automation(graph, run_actor or graph.author):
                queued += 1
        except Exception as exc:
            errors.append(f'{graph.title}: {exc}')

    skipped = max(len(eligible) - queued - len(errors), 0)
    base_summary = (
        f'Git push automation run completed. Eligible workbenches: {len(eligible)}. '
        f'Queued jobs: {queued}. Already queued/skipped: {skipped}. Errors: {len(errors)}.'
    )

    ai_text, provider, ai_error = _run_org_ai_prompt(
        organization,
        user_prompt=(
            'Summarize this Git push automation run for detection engineering leadership, '
            'including quick follow-up recommendations.\n\n'
            f'{base_summary}\n'
            + ('\nErrors:\n' + '\n'.join(f'- {e}' for e in errors[:20]) if errors else '')
        ),
        system_prompt=(
            'You are a detection engineering operations assistant. '
            'Return concise markdown with: Summary, Risks, and Next Actions.'
        ),
    )

    summary = _truncate(ai_text) if ai_text else _truncate(
        f'{base_summary}\n'
        + (f'\nAI summary skipped: {ai_error}' if ai_error else '')
        + ('\n\nFirst errors:\n' + '\n'.join(f'- {e}' for e in errors[:5]) if errors else '')
    )
    if errors and queued == 0:
        return TaskExecutionResult(
            status=OrganizationAITaskRun.Status.FAILED,
            summary=summary,
            metadata={'queued': queued, 'errors': errors[:25], 'provider': provider},
        )
    if queued == 0 and not errors:
        return TaskExecutionResult(
            status=OrganizationAITaskRun.Status.SKIPPED,
            summary=summary,
            metadata={'queued': queued, 'errors': [], 'provider': provider},
        )
    return _ok(summary, {'queued': queued, 'errors': errors[:25], 'provider': provider})


def _task_sync_deployed_l1_portal(
    organization: Organization,
    _actor: Optional[CustomUser],
) -> TaskExecutionResult:
    deployed_qs = PlaybookGraph.objects.filter(
        organization=organization,
        status=DetectionPlaybook.PlaybookStatus.DEPLOYED,
    ).order_by('-updated_at')

    total = deployed_qs.count()
    if total == 0:
        return _skip('No DEPLOYED workbenches found; nothing to sync for L1 portal.')

    from playbooks.l1_portal import upsert_l1_portal_snapshot  # pylint: disable=import-outside-toplevel

    synced = 0
    errors: List[str] = []
    for graph in deployed_qs.iterator(chunk_size=200):
        try:
            entry = upsert_l1_portal_snapshot(graph)
            if entry:
                synced += 1
        except Exception as exc:
            errors.append(f'{graph.title} ({graph.id}): {exc}')

    summary = (
        f'L1 portal sync completed. Deployed scanned: {total}. '
        f'Entries synced: {synced}. Errors: {len(errors)}.'
    )
    metadata = {
        'scanned': total,
        'synced': synced,
        'errors': errors[:25],
    }
    if errors and synced == 0:
        return TaskExecutionResult(
            status=OrganizationAITaskRun.Status.FAILED,
            summary=_truncate(summary + '\n\nFirst errors:\n' + '\n'.join(f'- {e}' for e in errors[:5])),
            metadata=metadata,
        )
    if synced == 0:
        return _skip(summary, metadata)
    if errors:
        return _ok(
            _truncate(summary + '\n\nFirst errors:\n' + '\n'.join(f'- {e}' for e in errors[:5])),
            metadata,
        )
    return _ok(summary, metadata)


def _task_pull_all_rule_repositories(
    organization: Organization,
    actor: Optional[CustomUser],
) -> TaskExecutionResult:
    repos = list(RuleRepository.objects.filter(organization=organization).order_by('id'))
    if not repos:
        return _skip('No repositories configured for this organization.')

    publisher = get_publisher()
    queued = 0
    errors: List[str] = []
    for repo in repos:
        payload = {
            'action': 'pull_repo',
            'repository_id': str(repo.id),
            'organization_id': str(organization.id),
            'triggered_by_user_id': str(actor.id) if actor else None,
            'scheduled': True,
        }
        try:
            publisher.publish_message('rule.repo.pull.requested', payload)
            queued += 1
        except Exception as exc:
            errors.append(f'{repo.name}: {exc}')

    base_summary = (
        f'Repository pull task completed. Total repos: {len(repos)}. '
        f'Queued pull requests: {queued}. Errors: {len(errors)}.'
    )
    ai_text, provider, ai_error = _run_org_ai_prompt(
        organization,
        user_prompt=(
            'Create a short operator summary for repository sync execution and suggest top 3 follow-up checks.\n\n'
            f'{base_summary}\n'
            + ('\nErrors:\n' + '\n'.join(f'- {e}' for e in errors[:20]) if errors else '')
        ),
        system_prompt='You are a DevSecOps assistant. Return concise markdown for operations teams.',
    )
    summary = _truncate(ai_text) if ai_text else _truncate(
        f'{base_summary}\n'
        + (f'\nAI summary skipped: {ai_error}' if ai_error else '')
        + ('\n\nFirst errors:\n' + '\n'.join(f'- {e}' for e in errors[:5]) if errors else '')
    )

    if queued == 0 and errors:
        return TaskExecutionResult(
            status=OrganizationAITaskRun.Status.FAILED,
            summary=summary,
            metadata={'queued': queued, 'errors': errors[:25], 'provider': provider},
        )
    if queued == 0 and not errors:
        return TaskExecutionResult(
            status=OrganizationAITaskRun.Status.SKIPPED,
            summary=summary,
            metadata={'queued': queued, 'errors': [], 'provider': provider},
        )
    return _ok(summary, {'queued': queued, 'errors': errors[:25], 'provider': provider})


def _task_ai_review_changed_rules(
    organization: Organization,
    _actor: Optional[CustomUser],
) -> TaskExecutionResult:
    since = timezone.now() - timedelta(days=7)
    rules = list(
        DetectionRule.objects.filter(
            organization=organization,
            updated_at__gte=since,
        ).select_related('playbook').order_by('-updated_at')[:30]
    )
    if not rules:
        return _skip('No rule changes detected in the last 7 days.')

    lines = []
    for rule in rules:
        pb = rule.playbook.title if rule.playbook else 'Standalone'
        lines.append(
            f"- {rule.title} [{rule.format}] | playbook={pb} | updated={rule.updated_at.isoformat()}"
        )

    result, provider, error = _run_org_ai_prompt(
        organization,
        user_prompt=(
            'Review recently changed detection rules and return:\n'
            '1) top review priorities,\n'
            '2) likely quality risks,\n'
            '3) concrete validation checklist for analysts.\n\n'
            f'Changed rules ({len(rules)}):\n' + '\n'.join(lines)
        ),
        system_prompt=(
            'You are a senior detection engineering reviewer. '
            'Return concise markdown with sections: Priorities, Risks, Validation Checklist.'
        ),
    )
    if error:
        return _skip(f'AI review skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'rule_count': len(rules)})


def _task_ai_similar_rule_recommendations(
    organization: Organization,
    _actor: Optional[CustomUser],
) -> TaskExecutionResult:
    total_rules = DetectionRule.objects.filter(organization=organization).count()
    if total_rules == 0:
        return _skip('No detection rules available yet.')

    format_counts = list(
        DetectionRule.objects.filter(organization=organization)
        .values('format')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    latest_rules = list(
        DetectionRule.objects.filter(organization=organization)
        .select_related('playbook')
        .order_by('-updated_at')[:20]
    )

    stats_lines = [f"- {entry['format']}: {entry['count']}" for entry in format_counts]
    sample_lines = [
        f"- {rule.title} [{rule.format}] | playbook={(rule.playbook.title if rule.playbook else 'Standalone')}"
        for rule in latest_rules
    ]

    result, provider, error = _run_org_ai_prompt(
        organization,
        user_prompt=(
            'Recommend similar rule opportunities for this detection program. '
            'Return a prioritized backlog of suggested rule variants and why they matter.\n\n'
            f'Total rules: {total_rules}\n'
            'Rules by format:\n'
            + '\n'.join(stats_lines)
            + '\n\nRecent rule samples:\n'
            + '\n'.join(sample_lines)
        ),
        system_prompt='You are a detection strategy advisor. Return actionable markdown for backlog planning.',
    )
    if error:
        return _skip(f'Similar-rule recommendation skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'total_rules': total_rules})


def _task_stale_workbench_triage(
    organization: Organization,
    _actor: Optional[CustomUser],
) -> TaskExecutionResult:
    stale_before = timezone.now() - timedelta(days=14)
    stale_workbenches = list(
        PlaybookGraph.objects.filter(
            organization=organization,
            status__in=['IDEA', 'RESEARCH', 'DEVELOPMENT', 'REVIEW', 'TESTING', 'TUNING'],
            updated_at__lt=stale_before,
        ).order_by('updated_at')[:40]
    )
    if not stale_workbenches:
        return _skip('No stale workbenches found (older than 14 days in non-deployed states).')

    lines = [
        f"- {wb.title} | status={wb.status} | updated={wb.updated_at.isoformat()}"
        for wb in stale_workbenches
    ]
    result, provider, error = _run_org_ai_prompt(
        organization,
        user_prompt=(
            'Triage these stale workbenches and provide:\n'
            '1) ordered priority queue,\n'
            '2) recommended owner action,\n'
            '3) escalation candidates.\n\n'
            f'Stale workbenches ({len(stale_workbenches)}):\n' + '\n'.join(lines)
        ),
        system_prompt='You are a SOC workflow optimization assistant. Return concise operational markdown.',
    )
    if error:
        return _skip(f'Stale workbench triage skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'stale_count': len(stale_workbenches)})


def _task_failed_publish_deploy_triage(
    organization: Organization,
    _actor: Optional[CustomUser],
) -> TaskExecutionResult:
    since = timezone.now() - timedelta(days=30)
    failed_jobs = list(
        OpenTideHefPublishJob.objects.filter(
            organization=organization,
            status='FAILED',
            created_at__gte=since,
        ).select_related('playbook').order_by('-created_at')[:40]
    )
    if not failed_jobs:
        return _skip('No failed HEF publish/deploy jobs in the last 30 days.')

    lines = []
    for job in failed_jobs:
        playbook_title = job.playbook.title if job.playbook else 'Unknown'
        lines.append(
            f"- {playbook_title} | created={job.created_at.isoformat()} | error={job.error_message[:240]}"
        )

    result, provider, error = _run_org_ai_prompt(
        organization,
        user_prompt=(
            'Analyze these failed publish/deploy jobs and provide:\n'
            '1) recurring root causes,\n'
            '2) immediate fixes,\n'
            '3) prevention controls.\n\n'
            f'Failed jobs ({len(failed_jobs)}):\n' + '\n'.join(lines)
        ),
        system_prompt='You are a release reliability engineer for detection pipelines.',
    )
    if error:
        return _skip(f'Failed-job triage skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'failed_jobs': len(failed_jobs)})


def _task_coverage_gap_digest(
    organization: Organization,
    actor: Optional[CustomUser],
) -> TaskExecutionResult:
    result, provider, error = _execute_seed_prompt(
        organization,
        actor,
        prompt_title='Gap Analysis Advisor',
        custom_input='Focus on concrete detection coverage gaps and 30-day remediation priorities.',
    )
    if error:
        return _skip(f'Coverage gap digest skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'seed_prompt': 'Gap Analysis Advisor'})


def _task_detection_debt_snapshot(
    organization: Organization,
    actor: Optional[CustomUser],
) -> TaskExecutionResult:
    result, provider, error = _execute_seed_prompt(
        organization,
        actor,
        prompt_title='Detection Debt Snapshot',
        custom_input='Emphasize debt items that can be reduced in the next sprint and quarter.',
    )
    if error:
        return _skip(f'Detection debt snapshot skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'seed_prompt': 'Detection Debt Snapshot'})


def _task_executive_risk_narrative(
    organization: Organization,
    actor: Optional[CustomUser],
) -> TaskExecutionResult:
    result, provider, error = _execute_seed_prompt(
        organization,
        actor,
        prompt_title='Executive Risk Narrative',
        custom_input='Keep tone board-ready and include top decisions required this month.',
    )
    if error:
        return _skip(f'Executive risk narrative skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'seed_prompt': 'Executive Risk Narrative'})


def _task_compliance_evidence_draft(
    organization: Organization,
    actor: Optional[CustomUser],
) -> TaskExecutionResult:
    result, provider, error = _execute_seed_prompt(
        organization,
        actor,
        prompt_title='Compliance Evidence Draft',
        custom_input='Highlight evidence clarity, traceability, and immediate audit follow-up actions.',
    )
    if error:
        return _skip(f'Compliance evidence draft skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'seed_prompt': 'Compliance Evidence Draft'})


def _task_platform_credential_health_check(
    organization: Organization,
    _actor: Optional[CustomUser],
) -> TaskExecutionResult:
    credentials = list(
        PlatformCredential.objects.filter(organization=organization).order_by('platform')
    )
    if not credentials:
        return _skip('No platform credentials configured for this organization.')

    checks: List[Dict[str, Any]] = []
    for credential in credentials:
        try:
            success, message = credential.test_connection()
        except Exception as exc:
            success, message = False, str(exc)
        checks.append({
            'platform': credential.platform,
            'success': bool(success),
            'message': (message or '').strip(),
        })

    ok_count = sum(1 for c in checks if c['success'])
    fail_count = len(checks) - ok_count
    base_summary = (
        f'Platform health check completed. Total: {len(checks)}. '
        f'Successful: {ok_count}. Failed: {fail_count}.'
    )
    checklist = '\n'.join(
        f"- {c['platform']}: {'OK' if c['success'] else 'FAILED'} ({c['message'][:240]})"
        for c in checks
    )

    ai_text, provider, ai_error = _run_org_ai_prompt(
        organization,
        user_prompt=(
            'Based on these platform credential test results, provide prioritized remediation guidance '
            'for admins.\n\n'
            f'{base_summary}\n{checklist}'
        ),
        system_prompt='You are a SecOps platform integration advisor. Return concise markdown.',
    )
    summary = _truncate(ai_text) if ai_text else _truncate(
        f'{base_summary}\n\n{checklist}\n'
        + (f'\nAI remediation guidance skipped: {ai_error}' if ai_error else '')
    )
    return _ok(summary, {'provider': provider, 'checks': checks})


def _task_program_review_digest(
    organization: Organization,
    actor: Optional[CustomUser],
) -> TaskExecutionResult:
    snapshots = list(
        MonthlyReportSnapshot.objects.filter(organization=organization).order_by('-year', '-month')[:6]
    )
    snapshots_payload = [
        {'year': s.year, 'month': s.month, 'stats': s.stats_json}
        for s in reversed(snapshots)
    ]
    result, provider, error = _execute_seed_prompt(
        organization,
        actor,
        prompt_title='Quarterly Program Review',
        custom_input='Emphasize strategic priorities and measurable outcomes for next quarter.',
        custom_context={'monthly_snapshots': snapshots_payload},
    )
    if error:
        return _skip(f'Program review digest skipped: {error}')
    return _ok(_truncate(result or ''), {'provider': provider, 'seed_prompt': 'Quarterly Program Review'})


_TASK_HANDLERS: Dict[str, Callable[[Organization, Optional[CustomUser]], TaskExecutionResult]] = {
    'push_rules_workbenches_to_git': _task_push_rules_workbenches_to_git,
    'sync_deployed_l1_portal': _task_sync_deployed_l1_portal,
    'pull_all_rule_repositories': _task_pull_all_rule_repositories,
    'ai_review_changed_rules': _task_ai_review_changed_rules,
    'ai_similar_rule_recommendations': _task_ai_similar_rule_recommendations,
    'stale_workbench_triage': _task_stale_workbench_triage,
    'failed_publish_deploy_triage': _task_failed_publish_deploy_triage,
    'coverage_gap_digest': _task_coverage_gap_digest,
    'detection_debt_snapshot': _task_detection_debt_snapshot,
    'executive_risk_narrative': _task_executive_risk_narrative,
    'compliance_evidence_draft': _task_compliance_evidence_draft,
    'platform_credential_health_check': _task_platform_credential_health_check,
    'program_review_digest': _task_program_review_digest,
}


def ensure_org_task_configs(
    organization: Organization,
    updated_by: Optional[CustomUser] = None,
) -> List[OrganizationAITaskConfig]:
    for definition in _TASK_DEFINITIONS:
        OrganizationAITaskConfig.objects.get_or_create(
            organization=organization,
            task_key=definition.key,
            defaults={
                'enabled': definition.default_enabled,
                'schedule': definition.default_schedule,
                'day_of_week': definition.default_day_of_week,
                'day_of_month': definition.default_day_of_month,
                'run_hour': definition.default_run_hour,
                'run_minute': definition.default_run_minute,
                'updated_by': updated_by,
            },
        )
    configs = {
        cfg.task_key: cfg
        for cfg in OrganizationAITaskConfig.objects.filter(organization=organization)
    }
    return [configs[d.key] for d in _TASK_DEFINITIONS if d.key in configs]


def get_or_create_task_config(
    organization: Organization,
    task_key: str,
    updated_by: Optional[CustomUser] = None,
) -> OrganizationAITaskConfig:
    definition = get_ai_task_definition(task_key)
    if not definition:
        raise ValueError(f'Unknown AI task key: {task_key}')

    config, _created = OrganizationAITaskConfig.objects.get_or_create(
        organization=organization,
        task_key=definition.key,
        defaults={
            'enabled': definition.default_enabled,
            'schedule': definition.default_schedule,
            'day_of_week': definition.default_day_of_week,
            'day_of_month': definition.default_day_of_month,
            'run_hour': definition.default_run_hour,
            'run_minute': definition.default_run_minute,
            'updated_by': updated_by,
        },
    )
    return config


def update_task_config(
    config: OrganizationAITaskConfig,
    *,
    enabled: Optional[bool] = None,
    schedule: Optional[str] = None,
    day_of_week: Optional[int] = None,
    day_of_month: Optional[int] = None,
    run_hour: Optional[int] = None,
    run_minute: Optional[int] = None,
    updated_by: Optional[CustomUser] = None,
) -> OrganizationAITaskConfig:
    if enabled is not None:
        config.enabled = bool(enabled)
    if schedule is not None:
        normalized = str(schedule).strip().upper()
        valid = {choice for choice, _label in OrganizationAITaskConfig.Schedule.choices}
        if normalized not in valid:
            raise ValueError(f'Invalid schedule: {schedule}. Valid: {sorted(valid)}')
        config.schedule = normalized
    if day_of_week is not None:
        config.day_of_week = _clamp(day_of_week, 0, 6, config.day_of_week)
    if day_of_month is not None:
        config.day_of_month = _clamp(day_of_month, 1, 28, config.day_of_month)
    if run_hour is not None:
        config.run_hour = _clamp(run_hour, 0, 23, config.run_hour)
    if run_minute is not None:
        config.run_minute = _clamp(run_minute, 0, 59, config.run_minute)
    if updated_by is not None:
        config.updated_by = updated_by

    config.next_run_at = compute_next_run_at(config) if config.enabled else None
    config.save()
    return config


def run_task_config(
    config: OrganizationAITaskConfig,
    *,
    trigger: str = OrganizationAITaskRun.Trigger.MANUAL,
    actor: Optional[CustomUser] = None,
) -> OrganizationAITaskRun:
    definition = get_ai_task_definition(config.task_key)
    if not definition:
        raise ValueError(f'Unknown AI task key: {config.task_key}')
    handler = _TASK_HANDLERS.get(config.task_key)
    if not handler:
        raise ValueError(f'No handler registered for AI task key: {config.task_key}')

    run = OrganizationAITaskRun.objects.create(
        organization=config.organization,
        task_config=config,
        task_key=config.task_key,
        status=OrganizationAITaskRun.Status.SKIPPED,
        trigger=trigger,
        run_by=actor,
    )

    started_at = run.started_at or timezone.now()
    status = OrganizationAITaskRun.Status.SUCCESS
    output_summary = ''
    error_message = ''
    metadata: Dict[str, Any] = {}

    try:
        result = handler(config.organization, actor)
        status = result.status
        output_summary = _truncate(result.summary)
        metadata = result.metadata or {}
        # If this task requires AI and no AI provider exists, reflect it explicitly.
        if definition.ai_required and status == OrganizationAITaskRun.Status.SKIPPED and 'AI' not in output_summary.upper():
            output_summary = _truncate(f'AI-dependent task skipped. {output_summary}')
    except Exception as exc:  # pragma: no cover - defensive guard for scheduler stability
        logger.exception('AI task execution failed for org=%s task=%s: %s', config.organization_id, config.task_key, exc)
        status = OrganizationAITaskRun.Status.FAILED
        error_message = str(exc)
        output_summary = _truncate(f'Execution failed: {exc}')

    completed_at = timezone.now()
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    run.status = status
    run.completed_at = completed_at
    run.duration_ms = max(duration_ms, 0)
    run.output_summary = output_summary
    run.error_message = _truncate(error_message, limit=4000)
    run.metadata = metadata
    run.save()

    config.last_run_at = completed_at
    config.last_status = status
    config.last_message = output_summary or run.error_message
    config.next_run_at = compute_next_run_at(config, reference=completed_at + timedelta(seconds=1)) if config.enabled else None
    if actor is not None:
        config.updated_by = actor
    config.save(update_fields=[
        'last_run_at',
        'last_status',
        'last_message',
        'next_run_at',
        'updated_by',
        'updated_at',
    ])

    _emit_ai_task_event(
        config=config,
        actor=actor,
        trigger=trigger,
        status=status,
        duration_ms=run.duration_ms or 0,
        summary=output_summary,
        error_message=run.error_message or '',
    )
    return run


def run_task_now(
    organization: Organization,
    task_key: str,
    actor: Optional[CustomUser] = None,
) -> OrganizationAITaskRun:
    config = get_or_create_task_config(organization, task_key, updated_by=actor)
    return run_task_config(
        config,
        trigger=OrganizationAITaskRun.Trigger.MANUAL,
        actor=actor,
    )


def run_due_ai_tasks() -> Dict[str, int]:
    """Run all due, enabled AI tasks across organizations."""
    now = timezone.now()
    ran = 0
    initialized = 0
    failed = 0

    configs = (
        OrganizationAITaskConfig.objects
        .select_related('organization')
        .filter(enabled=True)
        .order_by('next_run_at', 'updated_at')
    )

    for config in configs:
        if config.task_key not in _TASK_BY_KEY:
            logger.warning('Skipping unknown AI task key in DB: %s', config.task_key)
            continue

        if config.next_run_at is None:
            config.next_run_at = compute_next_run_at(config, reference=now)
            config.save(update_fields=['next_run_at', 'updated_at'])
            initialized += 1
            continue

        if config.next_run_at > now:
            continue

        run = run_task_config(
            config,
            trigger=OrganizationAITaskRun.Trigger.SCHEDULED,
            actor=None,
        )
        ran += 1
        if run.status == OrganizationAITaskRun.Status.FAILED:
            failed += 1

    return {
        'ran': ran,
        'initialized': initialized,
        'failed': failed,
    }
