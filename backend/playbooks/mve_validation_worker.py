"""
Machina Velocity Engine validation worker.

Consumes RabbitMQ events and validates saved MVE draft chains against available
ADVOPS/ACH historical content using lightweight, explainable heuristics.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import django
import pika

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

if not django.conf.settings.configured:
    django.setup()

from django.utils import timezone  # noqa: E402

from ach.models import ACHAnalysis  # noqa: E402
from advops.models import ADVOPSReport  # noqa: E402
from core.rabbitmq import (  # noqa: E402
    EXCHANGE_NAME,
    RABBITMQ_HOST,
    RABBITMQ_PASS,
    RABBITMQ_PORT,
    RABBITMQ_USER,
    publish_event,
)
from playbooks.models import MveDraft, MveValidationRun  # noqa: E402
from playbooks.mve_contract_validation import validate_mve_draft_payload  # noqa: E402

logger = logging.getLogger(__name__)

QUEUE_NAME = "mve.validation.jobs"
ROUTING_KEY_IN = "mve.validation.requested"
ROUTING_KEY_COMPLETED = "mve.validation.completed"
ROUTING_KEY_FAILED = "mve.validation.failed"


def _normalize_terms(draft: MveDraft) -> Dict[str, List[str]]:
    nodes = list(
        draft.nodes.select_related(
            "capability_abstraction",
            "capability_abstraction__technique",
        ).order_by("step_order", "created_at")
    )
    technique_refs: List[str] = []
    abstraction_terms: List[str] = []
    for node in nodes:
        tech_id = (node.technique_ref or "").strip().upper()
        if not tech_id and node.capability_abstraction and node.capability_abstraction.technique:
            tech_id = (node.capability_abstraction.technique.technique_id or "").strip().upper()
        if tech_id:
            technique_refs.append(tech_id)
        artifact = ""
        if node.capability_abstraction:
            artifact = (node.capability_abstraction.component_artifact or "").strip().lower()
        if artifact:
            abstraction_terms.extend([t for t in artifact.split() if len(t) >= 4])
    return {
        "technique_refs": list(dict.fromkeys(technique_refs)),
        "abstraction_terms": list(dict.fromkeys(abstraction_terms)),
    }


def _validate_against_advops(draft: MveDraft, terms: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    technique_refs = terms["technique_refs"]
    abstraction_terms = terms["abstraction_terms"]
    reports = ADVOPSReport.objects.filter(organization=draft.organization).order_by("-updated_at")[:200]
    for report in reports:
        corpus = " ".join(
            [
                report.hypothesis or "",
                report.mitre_summary or "",
                report.detection_logic_summary or "",
                report.infrastructure_summary or "",
            ]
        ).upper()
        matched_techniques = [tech for tech in technique_refs if tech in corpus]
        matched_terms = [term for term in abstraction_terms if term.upper() in corpus]
        if matched_techniques or matched_terms:
            matches.append(
                {
                    "report_id": str(report.id),
                    "hunt_id": report.hunt_id,
                    "title": report.hypothesis[:120] if report.hypothesis else report.hunt_id,
                    "matched_techniques": matched_techniques,
                    "matched_terms": matched_terms[:10],
                    "confidence": min(1.0, (len(matched_techniques) * 0.4) + (len(matched_terms) * 0.1)),
                }
            )
    return sorted(matches, key=lambda item: item.get("confidence", 0), reverse=True)[:25]


def _validate_against_ach(draft: MveDraft, terms: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    technique_refs = set(terms["technique_refs"])
    analyses = ACHAnalysis.objects.filter(owner__organization=draft.organization).prefetch_related(
        "hypotheses__mitre_technique"
    ).order_by("-updated_at")[:200]
    for analysis in analyses:
        analysis_techniques = {
            (hyp.mitre_technique.technique_id or "").strip().upper()
            for hyp in analysis.hypotheses.all()
            if hyp.mitre_technique
        }
        common = sorted(technique_refs.intersection(analysis_techniques))
        if common:
            coverage_ratio = len(common) / max(1, len(technique_refs))
            matches.append(
                {
                    "analysis_id": str(analysis.id),
                    "title": analysis.title,
                    "matched_techniques": common,
                    "coverage_ratio": round(coverage_ratio, 3),
                }
            )
    return sorted(matches, key=lambda item: item.get("coverage_ratio", 0), reverse=True)[:25]


def process_validation_run(run_id: str) -> None:
    logger.info("Processing MVE validation run %s", run_id)
    try:
        run = MveValidationRun.objects.select_related("draft", "draft__organization").get(pk=run_id)
    except MveValidationRun.DoesNotExist:
        logger.error("MVE validation run %s not found", run_id)
        return

    run.status = MveValidationRun.RunStatus.RUNNING
    run.started_at = timezone.now()
    run.error_message = ""
    run.save(update_fields=["status", "started_at", "error_message"])

    try:
        draft = run.draft
        payload_errors = validate_mve_draft_payload(
            stage='GENERATION_READY',
            analytic_family=draft.analytic_family,
            behavior_object=draft.behavior_object,
            dimensions=draft.dimensions,
            measurement_model=draft.measurement_model,
            time_window_logic=draft.time_window_logic,
            baseline_strategy=draft.baseline_strategy,
            context_risk=draft.context_risk,
            generation_profile=draft.generation_profile,
            downstream_handoff=draft.downstream_handoff,
        )
        if payload_errors:
            raise ValueError(json.dumps({'validation_errors': payload_errors}))

        terms = _normalize_terms(draft)
        advops_matches = _validate_against_advops(draft, terms)
        ach_matches = _validate_against_ach(draft, terms)

        is_validated = bool(advops_matches)
        summary = {
            "validated": is_validated,
            "status_basis": draft.status,
            "anchor_entity": draft.anchor_entity,
            "max_total_span_ms": draft.max_total_span_ms,
            "analytic_family": draft.analytic_family,
            "behavior_object": draft.behavior_object or {},
            "dimensions": draft.dimensions or {},
            "measurement_model": draft.measurement_model or {},
            "time_window_logic": draft.time_window_logic or {},
            "baseline_strategy": draft.baseline_strategy or {},
            "context_risk": draft.context_risk or {},
            "technique_refs": terms["technique_refs"],
            "advops_match_count": len(advops_matches),
            "ach_match_count": len(ach_matches),
            "advops_matches": advops_matches,
            "ach_matches": ach_matches,
            "validation_methods": ["advops_corpus_match", "ach_technique_overlap"],
            "expected_result": {
                "requires_advops_overlap": True,
                "minimum_validation_signal": "advops_match_count > 0",
            },
            "blind_spots": [] if is_validated else ["No ADVOPS corpus overlap found for the modeled chain."],
        }

        draft.is_advops_validated = is_validated
        draft.validation_summary = summary
        draft.last_validated_at = timezone.now()
        if is_validated:
            draft.status = MveDraft.DraftStatus.VALIDATED
        elif draft.status == MveDraft.DraftStatus.DRAFT:
            draft.status = MveDraft.DraftStatus.MODELED
        draft.save(
            update_fields=[
                "is_advops_validated",
                "validation_summary",
                "last_validated_at",
                "status",
                "updated_at",
            ]
        )

        run.status = MveValidationRun.RunStatus.COMPLETED
        run.result_data = summary
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "result_data", "completed_at"])

        publish_event(
            ROUTING_KEY_COMPLETED,
            {
                "run_id": str(run.id),
                "draft_id": str(draft.id),
                "validated": is_validated,
                "advops_match_count": len(advops_matches),
            },
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("MVE validation run %s failed: %s", run_id, exc)
        run.status = MveValidationRun.RunStatus.FAILED
        run.error_message = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error_message", "completed_at"])
        publish_event(
            ROUTING_KEY_FAILED,
            {
                "run_id": str(run.id),
                "draft_id": str(run.draft_id),
                "error": str(exc),
            },
        )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=30,
        blocked_connection_timeout=300,
        connection_attempts=10,
        retry_delay=5,
    )

    while True:
        connection = None
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="topic", durable=True)
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY_IN)
            channel.basic_qos(prefetch_count=1)

            def on_message(ch, method, _properties, body):
                try:
                    payload = json.loads(body.decode("utf-8"))
                    run_id = str(payload.get("run_id") or "").strip()
                    if not run_id:
                        raise ValueError("Payload missing run_id")
                    process_validation_run(run_id)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.exception("Failed processing MVE message: %s", exc)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)
            logger.info("MVE validation worker started. queue=%s routing_key=%s", QUEUE_NAME, ROUTING_KEY_IN)
            channel.start_consuming()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("MVE worker connection loop failed: %s", exc)
            time.sleep(5)
        finally:
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception:  # pragma: no cover - best effort
                    pass


if __name__ == "__main__":
    main()
