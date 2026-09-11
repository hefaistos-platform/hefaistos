"""
OpenTIDE Object Validator

Validates TVM, DOM, MDR, and BDR YAML structures against their JSON schemas.
"""

import json
import logging
import os
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Path to the schemas directory (sibling of this file's parent package)
_SCHEMAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')


def _load_schema(filename: str) -> Dict[str, Any]:
    """Load a JSON schema file from the schemas directory."""
    schema_path = os.path.join(_SCHEMAS_DIR, filename)
    with open(schema_path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def _validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate *data* against *schema* using jsonschema.

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    try:
        import jsonschema
    except ImportError:
        logger.warning("jsonschema is not installed; skipping schema validation.")
        return True, []

    errors: List[str] = []
    try:
        validator = jsonschema.Draft7Validator(schema)
        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            field_path = '.'.join(str(p) for p in error.path) if error.path else 'root'
            errors.append(f"{field_path}: {error.message}")
    except Exception as exc:
        logger.warning("Schema validation raised an unexpected error: %s", exc)
        errors.append(f"Validation error: {exc}")

    return len(errors) == 0, errors


def validate_tvm_structure(tvm_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a TVM dict against the TVM v2.1 JSON schema.

    Args:
        tvm_dict: Compiled TVM dictionary (as produced by compile_tvm_yaml).

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    try:
        schema = _load_schema('tvm_schema_v2_1.json')
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load TVM schema: %s", exc)
        return False, [f"Failed to load TVM schema: {exc}"]

    is_valid, errors = _validate_against_schema(tvm_dict, schema)
    if not is_valid:
        logger.warning("TVM validation failed for '%s': %s", tvm_dict.get('name'), errors)
    return is_valid, errors


def validate_dom_structure(dom_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a DOM dict against the DOM v2.1 JSON schema.

    Args:
        dom_dict: Compiled DOM dictionary (as produced by compile_dom_yaml).

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    try:
        schema = _load_schema('dom_schema_v2_1.json')
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load DOM schema: %s", exc)
        return False, [f"Failed to load DOM schema: {exc}"]

    is_valid, errors = _validate_against_schema(dom_dict, schema)
    if not is_valid:
        logger.warning("DOM validation failed for '%s': %s", dom_dict.get('name'), errors)
    return is_valid, errors


def validate_mdr_structure(mdr_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate an MDR dict against the MDR v2.1 JSON schema.

    Args:
        mdr_dict: Compiled MDR dictionary (as produced by compile_mdr_yaml).

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    try:
        schema = _load_schema('mdr_schema_v2_1.json')
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load MDR schema: %s", exc)
        return False, [f"Failed to load MDR schema: {exc}"]

    is_valid, errors = _validate_against_schema(mdr_dict, schema)
    if not is_valid:
        logger.warning("MDR validation failed for '%s': %s", mdr_dict.get('name'), errors)
    return is_valid, errors


def validate_bdr_structure(bdr_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a BDR dict against the BDR v2.0 JSON schema.

    Args:
        bdr_dict: Compiled BDR dictionary (as produced by compile_bdr_yaml_with_ai).

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    try:
        schema = _load_schema('bdr_schema_v2_1.json')
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load BDR schema: %s", exc)
        return False, [f"Failed to load BDR schema: {exc}"]

    is_valid, errors = _validate_against_schema(bdr_dict, schema)
    if not is_valid:
        logger.warning("BDR validation failed for '%s': %s", bdr_dict.get('name'), errors)
    return is_valid, errors
