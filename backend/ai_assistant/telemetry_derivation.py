"""
Telemetry Tagging: derives an "expected telemetry" tag list for a Workbench
object as a byproduct of completed behavior-first analysis.

Design intent (see Docs/TELEMETRY_TAGGING.md for full rationale):

- Behavior/technique/procedure authoring comes FIRST. Telemetry requirements
  are generated FROM that analysis, never used to gate or steer it.
- Output is always human-reviewable/editable and never silently trusted or
  auto-committed as fact.
- Every derived entry is tagged status="unverified" in this milestone: the
  reference data used here (MitreDataComponent, ChokepointEntry,
  DataSourceField) reflects MITRE's generic vocabulary / a bulk MITRE import,
  NOT a verified inventory of what a specific organization's SIEM actually
  ingests. A future milestone may add an org-environment health/verification
  layer; this module intentionally does not pretend that layer exists yet.
- Derivation is HARD-GATED behind five required Workbench fields (ATT&CK TTP,
  Strategic Goal, Technical Context, Detection Rule, Threat Surface Taxonomy).
  The gate is enforced both here (defense in depth) and in
  `PlaybookGraph.telemetry_tagging_gate_passed()` / the GraphQL mutation.
"""

import logging
import uuid
from typing import Any, Dict, List

from ai_assistant.opentide_enrichment import call_ai_provider, _parse_json_response

logger = logging.getLogger(__name__)


class TelemetryGateError(Exception):
    """Raised when derivation is attempted against a Workbench object that has
    not satisfied the required-field gate. Carries the missing-field list so
    callers (GraphQL mutation) can surface it directly to the user."""

    def __init__(self, missing_fields: List[str]):
        self.missing_fields = missing_fields
        super().__init__(
            "Telemetry tagging gate not satisfied. Missing: " + ", ".join(missing_fields)
        )


def _collect_reference_candidates(playbook) -> Dict[str, Any]:
    """
    Pull candidate telemetry vocabulary from existing MITRE-derived reference
    data already imported into HEFAISTOS. This is reference/vocabulary data
    only (see module docstring) — never treated as org ground truth.

    Returns a dict with:
      - data_components: list of {name, description, data_source_name}
      - chokepoint_hints: list of {telemetry_prerequisites, data_components,
        native_rule_hints, platforms} for matching technique/sub-technique
      - field_vocab: list of "DataSource.field_name" style strings for
        components matching the technique's data sources
    """
    technique = playbook.mitre_technique
    data_components: List[Dict[str, str]] = []
    chokepoint_hints: List[Dict[str, Any]] = []
    field_vocab: List[str] = []

    if technique is None:
        return {
            "data_components": data_components,
            "chokepoint_hints": chokepoint_hints,
            "field_vocab": field_vocab,
        }

    # --- MitreDataComponent (technique -> data component -> data source) ---
    try:
        for component in technique.data_components.select_related("data_source").all():
            data_components.append({
                "name": component.name,
                "description": (component.description or "")[:400],
                "data_source_name": component.data_source.name if component.data_source else "",
            })
    except Exception:
        logger.exception("Failed to collect MitreDataComponent candidates for technique %s", technique.technique_id)

    # --- ChokepointEntry (active snapshot only, by technique/sub-technique id) ---
    try:
        from platform_data.models import ChokepointEntry, ChokepointSnapshot

        active_snapshot = ChokepointSnapshot.objects.filter(
            status=ChokepointSnapshot.Status.ACTIVE
        ).first()
        if active_snapshot is not None:
            entries = ChokepointEntry.objects.filter(
                snapshot=active_snapshot,
                primary_technique_id=technique.technique_id,
            )
            for entry in entries[:10]:
                chokepoint_hints.append({
                    "title": entry.title,
                    "telemetry_prerequisites": entry.telemetry_prerequisites,
                    "data_components": entry.data_components,
                    "native_rule_hints": entry.native_rule_hints,
                    "platforms": entry.platforms,
                })
    except Exception:
        logger.exception("Failed to collect ChokepointEntry candidates for technique %s", technique.technique_id)

    # --- DataSourceField vocabulary (field-name terminology only) ---
    try:
        from data_catalog.models import DataSource

        component_source_names = {
            dc["data_source_name"] for dc in data_components if dc["data_source_name"]
        }
        if component_source_names:
            sources = DataSource.objects.filter(
                organization=playbook.organization,
                name__in=component_source_names,
            ).prefetch_related("fields")
            for source in sources:
                for field in source.fields.all()[:20]:
                    field_vocab.append(f"{source.name}.{field.field_name}")
    except Exception:
        logger.exception("Failed to collect DataSourceField vocabulary for playbook %s", playbook.id)

    return {
        "data_components": data_components,
        "chokepoint_hints": chokepoint_hints,
        "field_vocab": field_vocab,
    }


def _build_prompt(playbook, reference: Dict[str, Any]) -> Dict[str, str]:
    technique = playbook.mitre_technique
    technique_label = (
        f"{technique.technique_id}: {technique.name}" if technique else "Unknown"
    )
    threat_surface = playbook.threat_surface or []

    data_components_text = "\n".join(
        f"- {dc['name']} (source: {dc['data_source_name'] or 'unspecified'}): {dc['description']}"
        for dc in reference["data_components"]
    ) or "(none available)"

    chokepoint_text = "\n".join(
        f"- {c['title']}: telemetry_prerequisites={c['telemetry_prerequisites']!r}, "
        f"data_components={c['data_components']!r}, platforms={c['platforms']!r}"
        for c in reference["chokepoint_hints"]
    ) or "(no active chokepoint entries for this technique)"

    field_vocab_text = ", ".join(reference["field_vocab"]) or "(no cataloged field vocabulary available)"

    system_prompt = (
        "You are a senior detection engineer performing telemetry-requirement analysis. "
        "You derive WHAT TELEMETRY a detection needs from behavior-first analysis that has "
        "ALREADY been written (technique, goal, technical context, detection rule, threat "
        "surface). You do NOT invent detection logic, and you do NOT recommend which specific "
        "event IDs to detect on as a substitute for behavior — you describe telemetry that "
        "supports observing the described behavior. Return only strict JSON."
    )

    user_prompt = (
        "Derive the telemetry requirements for the detection object below.\n\n"
        "Use the technique-derived reference candidates and the org's cataloged field "
        "vocabulary as your primary vocabulary source. Also extract any additional specific "
        "telemetry implied by the technical context free text (tool names, artifacts, etc.) "
        "that the technique mapping alone would not surface. Cross-check candidates against "
        "the detection rule body: if the rule clearly queries a field/source not covered by "
        "your candidate list, include it too, and if a candidate is clearly irrelevant to what "
        "the rule actually queries, drop it or lower confidence.\n\n"
        f"ATT&CK TECHNIQUE: {technique_label}\n"
        f"STRATEGIC GOAL: {playbook.goal}\n"
        f"TECHNICAL CONTEXT: {playbook.technical_context}\n"
        f"THREAT SURFACE TAXONOMY: {threat_surface}\n"
        f"DETECTION RULE BODY:\n{playbook.detection_rule}\n\n"
        f"REFERENCE DATA COMPONENTS (MITRE ATT&CK, generic vocabulary):\n{data_components_text}\n\n"
        f"ACTIVE CHOKEPOINT HINTS (if any):\n{chokepoint_text}\n\n"
        f"ORG DATA CATALOG FIELD VOCABULARY (terminology reference only, not verified "
        f"environment presence):\n{field_vocab_text}\n\n"
        "Output ONLY a JSON object with a single key \"telemetry_requirements\", a list of "
        "objects with this exact shape (no markdown, no extra keys):\n"
        "{\n"
        '  "telemetry_requirements": [\n'
        "    {\n"
        '      "source": "<human label for the log source, e.g. \'Windows Security Event Log\'>",\n'
        '      "component": "<MITRE data component name if applicable, else empty string>",\n'
        '      "fields": ["<specific field name>", "..."],\n'
        '      "rationale": "<one sentence: why this is needed, tied to the technique/context/rule>"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Return the JSON object only."
    )

    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def derive_telemetry_requirements(playbook, user_settings) -> List[Dict[str, Any]]:
    """
    Run the AI-assisted telemetry derivation pass for *playbook*.

    Raises TelemetryGateError if the required-field gate is not satisfied.
    Returns a list of telemetry requirement dicts, each already carrying
    status="unverified" and origin="ai_derived". Callers are responsible for
    persisting the result — this function does not save the model.
    """
    missing = playbook.telemetry_tagging_missing_fields()
    if missing:
        raise TelemetryGateError(missing)

    reference = _collect_reference_candidates(playbook)
    prompts = _build_prompt(playbook, reference)

    raw = call_ai_provider(
        "",
        user_settings,
        response_format="json",
        system_prompt=prompts["system_prompt"],
        user_prompt=prompts["user_prompt"],
    )
    result = _parse_json_response(raw, {})
    raw_entries = result.get("telemetry_requirements", [])
    if not isinstance(raw_entries, list):
        raw_entries = []

    cleaned: List[Dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        fields = entry.get("fields", [])
        if not isinstance(fields, list):
            fields = []
        cleaned.append({
            "id": str(uuid.uuid4()),
            "source": str(entry.get("source", "")).strip(),
            "component": str(entry.get("component", "")).strip(),
            "fields": [str(f).strip() for f in fields if str(f).strip()],
            "rationale": str(entry.get("rationale", "")).strip(),
            "origin": "ai_derived",
            # Always unverified in this milestone: see module docstring.
            "status": "unverified",
        })

    return cleaned
