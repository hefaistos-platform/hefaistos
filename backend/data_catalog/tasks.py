"""
Async runners for Data Catalog jobs.

Uses background daemon threads so GraphQL mutations can return quickly while
long-running MITRE scraping imports execute.
"""

import logging
import re
import threading
from time import monotonic
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


def _normalize_text(value):
    return (value or "").strip()


def _normalize_key(value):
    return re.sub(r"\s+", " ", _normalize_text(value)).lower()


def _guess_platform(*values):
    haystack = " ".join(_normalize_key(v) for v in values if v)
    if not haystack:
        return None

    windows_markers = ("windows", "wineventlog", "sysmon", "etw", "powershell")
    linux_markers = ("linux", "auditd", "syslog", "journald", "systemd")
    mac_markers = ("mac", "darwin", "osquery", "endpointsecurity", "unified log")
    cloud_markers = ("azure", "m365", "office 365", "aws", "gcp", "cloudtrail")
    network_markers = ("network", "dns", "proxy", "firewall", "netflow")

    if any(marker in haystack for marker in windows_markers):
        return "Windows"
    if any(marker in haystack for marker in linux_markers):
        return "Linux"
    if any(marker in haystack for marker in mac_markers):
        return "macOS"
    if any(marker in haystack for marker in cloud_markers):
        return "Cloud"
    if any(marker in haystack for marker in network_markers):
        return "Network"
    return None


def _extract_analytic_code(analytic_name):
    """Resolve an analytic anchor ID such as AN2030 from a display name."""
    text = _normalize_text(analytic_name)
    if not text:
        return ""

    explicit = re.search(r"\bAN(\d{1,6})\b", text, flags=re.IGNORECASE)
    if explicit:
        return f"AN{explicit.group(1)}"

    numeric = re.search(r"(\d{3,6})", text)
    if numeric:
        return f"AN{numeric.group(1)}"

    fallback = text.replace("Analytic", "AN").replace("analytic", "AN").replace(" ", "")
    if fallback.upper().startswith("AN"):
        return fallback.upper()
    return ""


def run_mitre_deep_import_job(job_id: str) -> None:
    """Dispatch a deep MITRE data-source import in a daemon thread."""
    thread = threading.Thread(target=_execute_mitre_deep_import_job, args=(job_id,), daemon=True)
    thread.start()


def _execute_mitre_deep_import_job(job_id: str) -> None:
    from data_catalog.models import DataSource, DataSourceField, MitreDeepImportJob
    from platform_data.models import MitreAnalytic, MitreDataComponent, MitreDomain
    from platform_data.scraper import scrape_mitre_log_sources_json

    FIELD_BATCH_SIZE = 500
    SOURCE_UPDATE_BATCH_SIZE = 250
    PROGRESS_SAVE_EVERY_ANALYTICS = 20
    PROGRESS_SAVE_MIN_INTERVAL_SEC = 2.0

    try:
        job = MitreDeepImportJob.objects.get(id=job_id)
    except MitreDeepImportJob.DoesNotExist:
        logger.error("MitreDeepImportJob %s not found", job_id)
        return

    job.status = MitreDeepImportJob.Status.RUNNING
    job.started_at = datetime.now(tz=timezone.utc)
    job.save(update_fields=['status', 'started_at', 'updated_at'])

    import_log = []
    seen_rows = set()
    created_count = 0
    existing_count = 0
    updated_count = 0
    total_rows = 0
    imported_rows = 0
    failed_analytics = 0

    existing_sources = {
        _normalize_key(ds.name): ds
        for ds in DataSource.objects.filter(organization=job.organization)
    }

    existing_field_names = {}
    for source_id, field_name in DataSourceField.objects.filter(
        data_source__organization=job.organization
    ).values_list('data_source_id', 'field_name'):
        existing_field_names.setdefault(source_id, set()).add(field_name)

    pending_field_inserts = []
    pending_source_updates = {}

    processed_analytics = 0
    total_analytics = 0

    last_progress_flush_ts = monotonic()
    last_progress_saved_analytics = 0

    def flush_field_inserts():
        nonlocal pending_field_inserts
        if not pending_field_inserts:
            return
        DataSourceField.objects.bulk_create(
            pending_field_inserts,
            batch_size=FIELD_BATCH_SIZE,
            ignore_conflicts=True,
        )
        pending_field_inserts = []

    def flush_source_updates():
        if not pending_source_updates:
            return
        DataSource.objects.bulk_update(
            list(pending_source_updates.values()),
            ['platform', 'description', 'updated_at'],
            batch_size=SOURCE_UPDATE_BATCH_SIZE,
        )
        pending_source_updates.clear()

    def queue_field(source, field_name, data_type, description, example_value):
        source_id = source.id
        if not source_id:
            return

        source_fields = existing_field_names.setdefault(source_id, set())
        if field_name in source_fields:
            return

        source_fields.add(field_name)
        pending_field_inserts.append(
            DataSourceField(
                data_source=source,
                field_name=field_name,
                data_type=data_type,
                description=description,
                example_value=example_value,
            )
        )
        if len(pending_field_inserts) >= FIELD_BATCH_SIZE:
            flush_field_inserts()

    def queue_standard_fields(source, data_component, provider, channel):
        queue_field(
            source=source,
            field_name='data_component',
            data_type='string',
            description='Imported from MITRE ATT&CK deep import',
            example_value=data_component,
        )
        queue_field(
            source=source,
            field_name='provider',
            data_type='string',
            description='Imported from MITRE ATT&CK deep import',
            example_value=provider,
        )
        queue_field(
            source=source,
            field_name='channel',
            data_type='string',
            description='Imported from MITRE ATT&CK deep import',
            example_value=channel,
        )

    def update_source_if_missing_values(source, guessed_platform, description):
        nonlocal updated_count

        touched = False
        if guessed_platform and not _normalize_text(source.platform):
            source.platform = guessed_platform
            touched = True
        if description and not _normalize_text(source.description):
            source.description = description
            touched = True

        if touched:
            source.updated_at = datetime.now(tz=timezone.utc)
            pending_source_updates[source.id] = source
            updated_count += 1
            if len(pending_source_updates) >= SOURCE_UPDATE_BATCH_SIZE:
                flush_source_updates()

    def flush_progress(force=False):
        nonlocal last_progress_flush_ts, last_progress_saved_analytics

        now_ts = monotonic()
        analytics_since_last_save = processed_analytics - last_progress_saved_analytics
        interval_elapsed = now_ts - last_progress_flush_ts

        if not force and analytics_since_last_save < PROGRESS_SAVE_EVERY_ANALYTICS and interval_elapsed < PROGRESS_SAVE_MIN_INTERVAL_SEC:
            return

        job.total_analytics = total_analytics
        job.processed_analytics = processed_analytics
        job.failed_analytics = failed_analytics
        job.total_rows = total_rows
        job.imported_rows = imported_rows
        job.created_count = created_count
        job.existing_count = existing_count
        job.updated_count = updated_count
        job.log = "\n".join(import_log[-400:])
        job.save(update_fields=[
            'total_analytics',
            'processed_analytics',
            'failed_analytics',
            'total_rows',
            'imported_rows',
            'created_count',
            'existing_count',
            'updated_count',
            'log',
            'updated_at',
        ])

        last_progress_flush_ts = now_ts
        last_progress_saved_analytics = processed_analytics

    final_status = MitreDeepImportJob.Status.SUCCESS
    final_error = ''

    try:
        components = MitreDataComponent.objects.filter(
            domain=MitreDomain.ENTERPRISE,
            data_source__isnull=False,
        )
        if not job.include_revoked:
            components = components.filter(
                techniques__revoked=False,
                techniques__deprecated=False,
            )

        components = (
            components
            .select_related('data_source')
            .order_by('data_source__name', 'name')
            .distinct()
        )

        # Pass 1/2: import the static MITRE required data-component catalog.
        for component in components:
            source_name = _normalize_text(component.data_source.name if component.data_source else '')
            component_name = _normalize_text(component.name)
            if not source_name or not component_name:
                continue

            name = f"{source_name} - {component_name}"
            lookup = _normalize_key(name)
            guessed_platform = _guess_platform(source_name, component_name)
            description = (
                "Imported from MITRE ATT&CK required data source catalog."
                f"\n\nData Component: {component_name}"
            )

            source = existing_sources.get(lookup)
            if source is None:
                source = DataSource.objects.create(
                    name=name,
                    organization=job.organization,
                    platform=guessed_platform,
                    description=description,
                )
                existing_sources[lookup] = source
                created_count += 1
            else:
                existing_count += 1
                update_source_if_missing_values(source, guessed_platform, description)

            queue_standard_fields(
                source=source,
                data_component=component_name,
                provider=source_name,
                channel=component_name,
            )

        flush_field_inserts()
        flush_source_updates()

        analytics = MitreAnalytic.objects.filter(
            domain=MitreDomain.ENTERPRISE,
            detection_strategy__isnull=False,
            detection_strategy__url__isnull=False,
        )
        if not job.include_revoked:
            analytics = analytics.filter(
                detection_strategy__techniques__revoked=False,
                detection_strategy__techniques__deprecated=False,
            )

        analytics = list(
            analytics
            .select_related('detection_strategy')
            .order_by('name')
            .distinct()
        )

        total_analytics = len(analytics)
        flush_progress(force=True)

        # Pass 2/2: scrape each analytic for provider/channel rows.
        for analytic in analytics:
            strategy = analytic.detection_strategy
            strategy_url = _normalize_text(getattr(strategy, 'url', ''))
            analytic_code = _extract_analytic_code(analytic.name)

            if not strategy_url or not analytic_code:
                failed_analytics += 1
                import_log.append(
                    f"[WARN] Skipped analytic '{analytic.name}' (missing strategy URL or anchor code)."
                )
            else:
                rows = scrape_mitre_log_sources_json(strategy_url, analytic_code) or []
                total_rows += len(rows)

                for row in rows:
                    data_component = _normalize_text(row.get('data_component'))
                    provider = _normalize_text(row.get('log_provider'))
                    channel = _normalize_text(row.get('channel'))

                    if not provider or not channel:
                        continue

                    dedupe_key = (
                        _normalize_key(data_component),
                        _normalize_key(provider),
                        _normalize_key(channel),
                    )
                    if dedupe_key in seen_rows:
                        continue
                    seen_rows.add(dedupe_key)
                    imported_rows += 1

                    source_name = f"{provider} - {channel}"
                    lookup = _normalize_key(source_name)
                    guessed_platform = _guess_platform(provider, channel, data_component)
                    source_description = (
                        f"Auto-added from MITRE deep import: {data_component} | {provider} | {channel}\n\n"
                        f"Strategy: {getattr(strategy, 'def_id', '') or getattr(strategy, 'name', 'Unknown')}\n"
                        f"Analytic: {analytic.name} ({analytic_code})"
                    )

                    source = existing_sources.get(lookup)
                    if source is None:
                        source = DataSource.objects.create(
                            name=source_name,
                            organization=job.organization,
                            platform=guessed_platform,
                            description=source_description,
                        )
                        existing_sources[lookup] = source
                        created_count += 1
                    else:
                        existing_count += 1
                        update_source_if_missing_values(source, guessed_platform, source_description)

                    queue_standard_fields(
                        source=source,
                        data_component=data_component,
                        provider=provider,
                        channel=channel,
                    )

            processed_analytics += 1
            flush_progress(force=False)

        import_log.append(
            f"[DONE] Imported rows={imported_rows}, created={created_count}, existing={existing_count}, updated={updated_count}"
        )
    except Exception as exc:
        logger.exception("MitreDeepImportJob %s failed: %s", job_id, exc)
        final_status = MitreDeepImportJob.Status.FAILED
        final_error = str(exc)
        import_log.append(f"[ERROR] {exc}")
    finally:
        flush_field_inserts()
        flush_source_updates()
        flush_progress(force=True)

    job.status = final_status
    job.error = final_error
    job.total_analytics = total_analytics
    job.processed_analytics = processed_analytics
    job.failed_analytics = failed_analytics
    job.total_rows = total_rows
    job.imported_rows = imported_rows
    job.created_count = created_count
    job.existing_count = existing_count
    job.updated_count = updated_count
    job.log = "\n".join(import_log[-500:])
    job.finished_at = datetime.now(tz=timezone.utc)
    job.save(update_fields=[
        'status',
        'error',
        'total_analytics',
        'processed_analytics',
        'failed_analytics',
        'total_rows',
        'imported_rows',
        'created_count',
        'existing_count',
        'updated_count',
        'log',
        'finished_at',
        'updated_at',
    ])
