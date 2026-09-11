from __future__ import annotations

from typing import Any


ALLOWED_ANALYTIC_FAMILIES = {
    'identity_fan_out',
    'fan_in',
    'burstiness',
    'rate_anomaly',
    'acceleration',
    'sequence_compression',
    'periodicity_rhythm',
    'baseline_deviation',
    'rare_event_amplification',
    'hybrid_behavior_shape',
}

ALLOWED_DIMENSIONS = {
    'volume',
    'cardinality',
    'rate',
    'acceleration',
    'inter_arrival_timing',
    'duration',
    'burstiness',
    'fan_out',
    'fan_in',
    'sequence_compression',
    'periodicity',
    'rhythm',
    'novelty',
    'baseline_deviation',
    'context_aware_deviation',
}

ALLOWED_OUTPUT_FORMATS = {'KQL', 'EQL', 'SPL', 'WAZUH'}

ALLOWED_NODE_TYPES = {'EVENT', 'RULE', 'FEATURE', 'BASELINE', 'CONTEXT', 'DECEPTION', 'DECISION'}


class MveValidationError(Exception):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__('MVE validation failed')
        self.errors = errors


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _ensure_dict(value: Any, path: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        errors.append({'path': path, 'code': 'invalid_type', 'message': f'{path} must be an object'})
        return {}
    return value


def _ensure_list(value: Any, path: str, errors: list[dict[str, str]]) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append({'path': path, 'code': 'invalid_type', 'message': f'{path} must be an array'})
        return []
    return value


def _require(condition: bool, path: str, code: str, message: str, errors: list[dict[str, str]]) -> None:
    if not condition:
        errors.append({'path': path, 'code': code, 'message': message})


def validate_behavior_object(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'behavior_object', errors)
    if stage in {'DRAFT', 'MODELED', 'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        _require(_is_non_empty_string(data.get('actor_entity_type')), 'behavior_object.actor_entity_type', 'required', 'actor_entity_type is required', errors)
        _require(_is_non_empty_string(data.get('action_family')), 'behavior_object.action_family', 'required', 'action_family is required', errors)
    if stage in {'MODELED', 'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        _require(_is_non_empty_string(data.get('target_entity_type')), 'behavior_object.target_entity_type', 'required', 'target_entity_type is required', errors)
        _require(_is_non_empty_string(data.get('channel')), 'behavior_object.channel', 'required', 'channel is required', errors)
        _require(_is_non_empty_string(data.get('detection_objective')), 'behavior_object.detection_objective', 'required', 'detection_objective is required', errors)
        _require(_is_non_empty_string(data.get('canonical_sentence')), 'behavior_object.canonical_sentence', 'required', 'canonical_sentence is required', errors)
    return data


def validate_dimensions(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'dimensions', errors)
    primary = _ensure_list(data.get('primary'), 'dimensions.primary', errors)
    secondary = _ensure_list(data.get('secondary'), 'dimensions.secondary', errors)
    for idx, item in enumerate(primary):
        _require(item in ALLOWED_DIMENSIONS, f'dimensions.primary[{idx}]', 'invalid_choice', f'Unsupported dimension: {item}', errors)
    for idx, item in enumerate(secondary):
        _require(item in ALLOWED_DIMENSIONS, f'dimensions.secondary[{idx}]', 'invalid_choice', f'Unsupported dimension: {item}', errors)
    if stage in {'DRAFT', 'MODELED', 'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        _require(len(primary) > 0, 'dimensions.primary', 'required', 'At least one primary dimension is required', errors)
    if stage in {'MODELED', 'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        _require(_is_non_empty_string(data.get('rationale')), 'dimensions.rationale', 'required', 'rationale is required', errors)
    return data


def validate_measurement_model(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'measurement_model', errors)
    if stage in {'MODELED', 'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        _require(_is_non_empty_string(data.get('counted_action')), 'measurement_model.counted_action', 'required', 'counted_action is required', errors)
        _require(len(_ensure_list(data.get('aggregation_keys'), 'measurement_model.aggregation_keys', errors)) > 0, 'measurement_model.aggregation_keys', 'required', 'aggregation_keys must contain at least one value', errors)
        _require(len(_ensure_list(data.get('grouping_keys'), 'measurement_model.grouping_keys', errors)) > 0, 'measurement_model.grouping_keys', 'required', 'grouping_keys must contain at least one value', errors)
        _require(len(_ensure_list(data.get('feature_set'), 'measurement_model.feature_set', errors)) > 0, 'measurement_model.feature_set', 'required', 'feature_set must contain at least one value', errors)
    return data


def validate_time_window_logic(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'time_window_logic', errors)
    if stage in {'MODELED', 'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        _require(_is_non_empty_string(data.get('lookback_window')), 'time_window_logic.lookback_window', 'required', 'lookback_window is required', errors)
        _require(_is_non_empty_string(data.get('detection_window')), 'time_window_logic.detection_window', 'required', 'detection_window is required', errors)
        _require(_is_non_empty_string(data.get('window_type')), 'time_window_logic.window_type', 'required', 'window_type is required', errors)
        _require(_is_non_empty_string(data.get('event_time_field')), 'time_window_logic.event_time_field', 'required', 'event_time_field is required', errors)
        _require(_is_non_empty_string(data.get('ordering_confidence')), 'time_window_logic.ordering_confidence', 'required', 'ordering_confidence is required', errors)
        if data.get('window_type') == 'sequence_window':
            _require(bool(data.get('max_total_span_ms') or data.get('max_inter_step_gap_ms')), 'time_window_logic', 'invalid_combination', 'sequence_window requires max_total_span_ms or max_inter_step_gap_ms', errors)
    return data


def validate_baseline_strategy(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'baseline_strategy', errors)
    if stage in {'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        baseline_required = data.get('baseline_required')
        _require(isinstance(baseline_required, bool), 'baseline_strategy.baseline_required', 'required', 'baseline_required must be explicitly boolean', errors)
        if baseline_required:
            _require(len(_ensure_list(data.get('baseline_types'), 'baseline_strategy.baseline_types', errors)) > 0, 'baseline_strategy.baseline_types', 'required', 'baseline_types must contain at least one value when baseline_required is true', errors)
    return data


def validate_context_risk(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'context_risk', errors)
    if stage in {'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        expected_automation = data.get('expected_automation')
        benign_overlaps = _ensure_list(data.get('benign_overlaps'), 'context_risk.benign_overlaps', errors)
        _require(_is_non_empty_string(expected_automation), 'context_risk.expected_automation', 'required', 'expected_automation is required', errors)
        _require(len(benign_overlaps) > 0, 'context_risk.benign_overlaps', 'required', 'benign_overlaps must not be empty at generation-ready stage', errors)
    return data


def validate_generation_profile(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'generation_profile', errors)
    if stage in {'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        output_format = str(data.get('selected_output_format') or '').upper()
        _require(output_format in ALLOWED_OUTPUT_FORMATS, 'generation_profile.selected_output_format', 'invalid_choice', 'selected_output_format must be one of KQL/EQL/SPL/WAZUH', errors)
        _require(_is_non_empty_string(data.get('generation_mode')), 'generation_profile.generation_mode', 'required', 'generation_mode is required', errors)
        hardening = _ensure_dict(data.get('hardening_options'), 'generation_profile.hardening_options', errors)
        grounding = _ensure_dict(data.get('grounding_inputs'), 'generation_profile.grounding_inputs', errors)
        for key in [
            'include_benign_overlap_handling',
            'include_baseline_comparison',
            'include_triage_evidence_fields',
            'include_deception_confidence_logic',
            'include_threshold_rationale_comments',
        ]:
            _require(isinstance(hardening.get(key), bool), f'generation_profile.hardening_options.{key}', 'required', f'{key} must be explicitly boolean', errors)
        for key in [
            'use_behavior_object',
            'use_dimensions',
            'use_measurement_model',
            'use_time_window_logic',
            'use_baseline_strategy',
            'use_context_risk',
            'use_node_graph',
        ]:
            _require(isinstance(grounding.get(key), bool), f'generation_profile.grounding_inputs.{key}', 'required', f'{key} must be explicitly boolean', errors)
    return data


def validate_downstream_handoff(value: Any, stage: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    data = _ensure_dict(value, 'downstream_handoff', errors)
    if stage in {'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        for key in ['open_in_monaco_editor', 'save_to_rule_hub', 'generate_opentide_yaml', 'append_to_workbench']:
            _require(isinstance(data.get(key), bool), f'downstream_handoff.{key}', 'required', f'{key} must be explicitly boolean', errors)
        if data.get('append_to_workbench'):
            _require(_is_non_empty_string(data.get('target_workbench_id')), 'downstream_handoff.target_workbench_id', 'required', 'target_workbench_id is required when append_to_workbench is true', errors)
    return data


def validate_node_config(node_type: str, value: Any, errors: list[dict[str, str]], *, path: str = 'node_config') -> dict[str, Any]:
    data = _ensure_dict(value, path, errors)
    _require(node_type in ALLOWED_NODE_TYPES, f'{path}.type', 'invalid_choice', f'Unsupported node type: {node_type}', errors)
    if node_type != 'EVENT' and node_type != 'RULE':
        _require(str(data.get('type') or '').upper() == node_type, f'{path}.type', 'required', f'{path}.type must equal {node_type}', errors)
    if node_type == 'FEATURE':
        _require(_is_non_empty_string(data.get('feature_type')), f'{path}.feature_type', 'required', 'feature_type is required', errors)
        _require(_is_non_empty_string(data.get('output_field')), f'{path}.output_field', 'required', 'output_field is required', errors)
    elif node_type == 'BASELINE':
        _require(_is_non_empty_string(data.get('baseline_type')), f'{path}.baseline_type', 'required', 'baseline_type is required', errors)
    elif node_type == 'CONTEXT':
        _require(_is_non_empty_string(data.get('condition')), f'{path}.condition', 'required', 'condition is required', errors)
        _require(_is_non_empty_string(data.get('effect')), f'{path}.effect', 'required', 'effect is required', errors)
    elif node_type == 'DECEPTION':
        _require(_is_non_empty_string(data.get('deception_type')), f'{path}.deception_type', 'required', 'deception_type is required', errors)
        _require(_is_non_empty_string(data.get('confidence_effect')), f'{path}.confidence_effect', 'required', 'confidence_effect is required', errors)
    elif node_type == 'DECISION':
        recommendation = data.get('downstream_recommendation')
        _require(_is_non_empty_string(recommendation), f'{path}.downstream_recommendation', 'required', 'downstream_recommendation is required', errors)
    return data


def validate_mve_draft_payload(*, stage: str, analytic_family: Any, behavior_object: Any, dimensions: Any, measurement_model: Any, time_window_logic: Any, baseline_strategy: Any, context_risk: Any, generation_profile: Any, downstream_handoff: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    normalized_stage = str(stage or 'DRAFT').upper()
    if normalized_stage in {'DRAFT', 'MODELED', 'GENERATION_READY', 'VALIDATED', 'EXPORTED'}:
        _require(str(analytic_family or '').strip() in ALLOWED_ANALYTIC_FAMILIES, 'analytic_family', 'required', 'analytic_family must be a supported value', errors)
    validate_behavior_object(behavior_object, normalized_stage, errors)
    validate_dimensions(dimensions, normalized_stage, errors)
    validate_measurement_model(measurement_model, normalized_stage, errors)
    validate_time_window_logic(time_window_logic, normalized_stage, errors)
    validate_baseline_strategy(baseline_strategy, normalized_stage, errors)
    validate_context_risk(context_risk, normalized_stage, errors)
    validate_generation_profile(generation_profile, normalized_stage, errors)
    validate_downstream_handoff(downstream_handoff, normalized_stage, errors)
    return errors
