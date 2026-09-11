"""OpenTIDE VelocityDetection compiler for Machina Velocity Engine drafts."""

from __future__ import annotations

from typing import Any, Dict, List

import yaml


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or fallback).strip()
    return text


def _build_chain_sequence(draft) -> List[Dict[str, Any]]:
    sequence: List[Dict[str, Any]] = []
    nodes = list(
        draft.nodes.select_related(
            "capability_abstraction",
            "capability_abstraction__technique",
            "data_source",
            "detection_rule",
        ).order_by("step_order", "created_at")
    )
    for idx, node in enumerate(nodes, start=1):
        cap = node.capability_abstraction
        technique_ref = _safe_text(node.technique_ref)
        tactic_ref = _safe_text(node.tactic_ref)
        if not technique_ref and cap and cap.technique:
            technique_ref = _safe_text(getattr(cap.technique, "technique_id", ""))
        source = "data_catalog" if node.node_type == "EVENT" else "rule_hub"
        item: Dict[str, Any] = {
            # Export always uses strict chain position (1..N), independent of any stale
            # persisted step values from earlier drafts.
            "step": idx,
            "type": "event" if node.node_type == "EVENT" else "rule",
            "source": source,
            "capability_abstraction": f"CAP-LIB-{str(cap.id)[:8]}" if cap else "",
            "tactic_ref": tactic_ref,
            "technique_ref": technique_ref,
        }
        if node.node_type == "EVENT":
            item["criteria"] = node.criteria or {}
            if node.data_source_id:
                item["data_source_id"] = str(node.data_source_id)
        else:
            item["rule_id"] = str(node.detection_rule_id or "")
            if node.criteria:
                item["criteria"] = node.criteria
        sequence.append({k: v for k, v in item.items() if v not in ("", None)})
    return sequence


def compile_velocity_detection(draft) -> Dict[str, Any]:
    """Compile an ``MveDraft`` into an OpenTIDE-compatible VelocityDetection payload."""

    chain = _build_chain_sequence(draft)
    payload: Dict[str, Any] = {
        "version": "opentide/v1.2",
        "kind": "VelocityDetection",
        "metadata": {
            "id": f"MVE-CHAIN-{str(draft.id).split('-')[0].upper()}",
            "name": _safe_text(draft.name, "Untitled Velocity Chain"),
            "author": "HEFAISTOS Workbench",
            "tags": ["MVE", "VelocityDetection"],
            "description": (
                "Generated from Machina Velocity Engine chain editor. "
                "Use CI/CD translators for platform-specific syntax."
            ),
            "analytic_family": _safe_text(getattr(draft, 'analytic_family', ''), ''),
            "primary_methodology": _safe_text(getattr(draft, 'primary_methodology', ''), 'volumetric_de'),
        },
        "engine_parameters": {
            "anchor_entity": _safe_text(draft.anchor_entity, "host.hostname"),
            "velocity_constraints": {
                "max_total_span": f"{int(draft.max_total_span_ms or 0)}ms",
            },
        },
        "mve_modeling": {
            "behavior_object": getattr(draft, 'behavior_object', {}) or {},
            "dimensions": getattr(draft, 'dimensions', {}) or {},
            "measurement_model": getattr(draft, 'measurement_model', {}) or {},
            "time_window_logic": getattr(draft, 'time_window_logic', {}) or {},
            "baseline_strategy": getattr(draft, 'baseline_strategy', {}) or {},
            "context_risk": getattr(draft, 'context_risk', {}) or {},
            "generation_profile": getattr(draft, 'generation_profile', {}) or {},
            "downstream_handoff": getattr(draft, 'downstream_handoff', {}) or {},
            "validation_summary": getattr(draft, 'validation_summary', {}) or {},
        },
        "chain_sequence": chain,
        "response_routing": {
            "severity": "CRITICAL" if getattr(draft, "is_advops_validated", False) else "HIGH",
            "mitre_d3fend": [],
            "mitre_engage": [],
        },
    }
    return payload


def dump_velocity_detection_yaml(draft) -> str:
    """Return YAML text for an ``MveDraft`` VelocityDetection payload."""

    data = compile_velocity_detection(draft)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
