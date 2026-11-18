"""Contract tests for the Machina Velocity Engine (MVE) draft validator.

These tests are dependency-free (no Django settings, no database) because
``mve_contract_validation`` is a pure module. They exist to pin two things
that are easy to break:

1. **Backward compatibility** -- the closed vocabularies (dimensions, analytic
   families) may only ever grow. A draft that validated before must still
   validate after a vocabulary addition.
2. **Closed-set discipline** -- unknown dimension/family/node values must still
   be rejected, so the vocabulary does not silently drift.

Run with:  pytest backend/playbooks/tests/test_mve_contract_validation.py
"""
from __future__ import annotations

import importlib.util
import pathlib

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / 'mve_contract_validation.py'
_spec = importlib.util.spec_from_file_location('mve_contract_validation', _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
mve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mve)


def _minimal_payload(*, analytic_family='sequence_compression', primary=None, stage='DRAFT'):
    """Smallest payload that exercises the vocabulary gates.

    Only the fields needed to reach the family/dimension checks are populated;
    the remaining stage-gated validators are given empty-but-well-typed values
    and any errors they raise are ignored by the callers below.
    """
    return dict(
        stage=stage,
        analytic_family=analytic_family,
        behavior_object={},
        dimensions={
            'primary': primary if primary is not None else ['volume'],
            'secondary': [],
            'rationale': 'test',
        },
        measurement_model={},
        time_window_logic={},
        baseline_strategy={},
        context_risk={},
        generation_profile={},
        downstream_handoff={},
    )


def _errors(*, analytic_family='sequence_compression', primary=None):
    return mve.validate_mve_draft_payload(**_minimal_payload(
        analytic_family=analytic_family, primary=primary))


def _family_rejected(errors):
    return any(e.get('path') == 'analytic_family' for e in errors)


def _dimension_rejected(errors):
    return any(str(e.get('path', '')).startswith('dimensions') for e in errors)


# --- vocabulary contents ---------------------------------------------------

def test_attempt_variation_dimension_is_supported():
    assert 'attempt_variation' in mve.ALLOWED_DIMENSIONS


def test_variation_amplification_family_is_supported():
    assert 'variation_amplification' in mve.ALLOWED_ANALYTIC_FAMILIES


def test_pre_existing_dimensions_and_families_still_present():
    # Guard against accidental removal while extending the vocabularies.
    for dimension in (
        'volume', 'cardinality', 'rate', 'acceleration', 'inter_arrival_timing',
        'duration', 'burstiness', 'fan_out', 'fan_in', 'sequence_compression',
        'periodicity', 'rhythm', 'novelty', 'baseline_deviation',
        'context_aware_deviation',
    ):
        assert dimension in mve.ALLOWED_DIMENSIONS, dimension
    for family in (
        'identity_fan_out', 'fan_in', 'burstiness', 'rate_anomaly',
        'acceleration', 'sequence_compression', 'periodicity_rhythm',
        'baseline_deviation', 'rare_event_amplification', 'hybrid_behavior_shape',
    ):
        assert family in mve.ALLOWED_ANALYTIC_FAMILIES, family


# --- acceptance ------------------------------------------------------------

def test_new_family_and_dimension_accepted():
    errors = _errors(analytic_family='variation_amplification', primary=['attempt_variation'])
    assert not _family_rejected(errors)
    assert not _dimension_rejected(errors)


def test_new_dimension_accepted_with_existing_family():
    # A dimension may be combined with any supported family.
    errors = _errors(analytic_family='rare_event_amplification', primary=['attempt_variation'])
    assert not _family_rejected(errors)
    assert not _dimension_rejected(errors)


# --- rejection (closed sets must stay closed) ------------------------------

def test_unknown_dimension_rejected():
    errors = _errors(primary=['not_a_dimension'])
    assert _dimension_rejected(errors)


def test_unknown_family_rejected():
    errors = _errors(analytic_family='not_a_family')
    assert _family_rejected(errors)


def test_feature_type_and_feature_set_are_free_form():
    """FEATURE nodes validate feature_type only as a non-empty string.

    This is why adding new features (e.g. distinct_inputs_per_target) needs no
    validator change -- and this test documents that contract explicitly.
    """
    errors: list[dict[str, str]] = []
    mve.validate_node_config('FEATURE', {'type': 'FEATURE', 'feature_type': 'distinct_inputs_per_target',
                                         'output_field': 'breadth'}, errors)
    assert not any('feature_type' in str(e.get('path', '')) for e in errors)

# --- UI / contract parity --------------------------------------------------
# The workbench tab hard-codes copies of the contract vocabularies. They are
# edited by hand, so they can drift or break (a missing quote once broke the
# whole tab). These tests read the TSX as text and compare it with the contract.

_TSX_PATH = pathlib.Path(__file__).resolve().parents[3] / 'frontend' / 'src' / 'components' / 'mve' / 'MveWorkbenchTab.tsx'


def _tsx_text():
    return _TSX_PATH.read_text(encoding='utf-8')


def _quoted_list_after(marker_regex):
    import re
    out = []
    for match in re.finditer(marker_regex, _tsx_text(), flags=re.S):
        out.append(re.findall(r"'([a-z0-9_]+)'", match.group(1)))
    return out


def test_ui_dimension_lists_match_contract():
    lists = _quoted_list_after(r"\[\s*('volume','cardinality'[^\]]*)\]")
    assert len(lists) == 2, 'expected primary and secondary dimension pickers'
    for dims in lists:
        assert set(dims) == set(mve.ALLOWED_DIMENSIONS)
        assert len(dims) == len(set(dims)), 'duplicate value in a picker'


def test_ui_family_list_matches_contract():
    import re
    block = re.search(r"label=\"Analytic Family\".*?options=\{\[(.*?)\]\}", _tsx_text(), flags=re.S)
    assert block, 'Analytic Family picker not found'
    values = re.findall(r"value: '([a-z_]+)'", block.group(1))
    assert set(values) == set(mve.ALLOWED_ANALYTIC_FAMILIES)


def test_ui_feature_lists_are_well_formed_and_include_new_features():
    lists = _quoted_list_after(r"\[\s*('event_count'[^\]]*)\]")
    assert len(lists) == 2, 'expected the feature-set picker and the FEATURE node picker'
    for features in lists:
        assert len(features) == len(set(features)), 'duplicate feature'
        assert 'sequence_compression_score' in features
        assert 'distinct_inputs_per_target' in features
    # The raw text must not contain an unterminated quote like  'name,'next'
    assert "_score,'" not in _tsx_text()

