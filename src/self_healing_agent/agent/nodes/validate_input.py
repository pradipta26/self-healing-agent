from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import uuid
import yaml

from self_healing_agent.agent.state import AgentState, DecisionSnapshot


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    return False


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "array[string]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if expected_type == "null":
        return value is None
    return True


def _validate_properties(
    payload: dict[str, Any],
    properties: dict[str, Any],
    errors: list[str],
    prefix: str,
) -> bool:
    status_flag = True
    for field, rules in properties.items():
        value = payload.get(field)
        expected_type = rules.get("type")
        enum_values = rules.get("enum")

        if value is None:
            continue

        if isinstance(expected_type, str) and not _matches_type(value, expected_type):
            errors.append(
                f"{prefix}.{field} expected type {expected_type}, got {type(value).__name__}"
            )
            status_flag = False

        if isinstance(enum_values, list) and value not in enum_values:
            errors.append(
                f"{prefix}.{field} must be one of {enum_values}, got {value!r}"
            )
            status_flag = False

    return status_flag


def _load_validation_schema_from_env_config() -> dict[str, Any]:
    runtime_env = os.getenv("SHA_ENV", "dev").strip().lower() or "dev"
    project_root = Path(__file__).resolve().parents[4]
    config_path = project_root / "configs" / "env" / f"{runtime_env}_config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        loaded: Any = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise ValueError(f"Top-level config must be a mapping in {config_path}")

    validation_schema = loaded.get("validation_schema")
    if not isinstance(validation_schema, dict):
        raise ValueError(f"Missing/invalid validation_schema in {config_path}")

    return validation_schema

def _create_decision_snapshot(decision_id: str, trigger_codes: list[str] | None = None) -> DecisionSnapshot:
    trigger_codes = trigger_codes or []
    decision: DecisionSnapshot = {
        "decision_id": decision_id, #state.get("decision_id", uuid.uuid4()),
        "policy_version": "v0",
        "route": "HITL_INVESTIGATION",
        "confidence": "UNKNOWN",
        "actionability": "INPUT_INVALID",
        "escalation_type": "INPUT_VALIDATION_ERROR",
        "trigger_codes": trigger_codes,
        "service_match": False,
        "required_human_role": "INVESTIGATOR",
        "summary": "Input validation failed; cannot safely continue.",
        "facts": {"stage": "validate_input"},
    }
    return decision


def validate_input(state: AgentState) -> dict[str, Any]:
    warnings = list(state.get("warnings", []))
    errors: list[str] = []
    trigger_codes: list[str] = []
    decision_id = str(uuid.uuid4())
    structured_input = state.get("structured_input")
    if not isinstance(structured_input, dict):
        errors.append("structured_input must be an object")
        decision_id = str(uuid.uuid4())
        return {
            "warnings": warnings + ["INPUT_VALIDATION_FAILED"],
            "error_flag": True,
            "error_message": "Validation failed:\n- " + "\n- ".join(errors),
            "trace": state.get("trace", []) + ["validate_input:not_ok"],
            "decision_id": decision_id,
            "decision": _create_decision_snapshot(
                decision_id=decision_id,
                trigger_codes=["INPUT_PARSE_FAILED"]
            )
        }

    try:
        validation_schema = _load_validation_schema_from_env_config()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Schema loading failed: {exc}")
        decision_id = str(uuid.uuid4())
        return {
            "warnings": warnings + ["INPUT_VALIDATION_SCHEMA_LOAD_FAILED"],
            "error_flag": True,
            "error_message": "Validation failed:\n- " + "\n- ".join(errors),
            "trace": state.get("trace", []) + ["validate_input:not_ok"],
            "decision_id": decision_id,
            "decision": _create_decision_snapshot(
                decision_id=decision_id,
                trigger_codes=["INPUT_SCHEMA_LOAD_FAILED"]
            )
        }

    common_fields = validation_schema.get("common_fields", {})
    common_properties = common_fields.get("properties", {})
    common_required = common_fields.get("required", [])

    missing_flag = False
    for field in common_required:
        if _is_missing(structured_input.get(field)):
            missing_flag = True
            errors.append(f"Missing required common field: {field}")
    if missing_flag:
        trigger_codes.append("INPUT_MISSING_REQUIRED_FIELD")

    if isinstance(common_properties, dict):
        status_flag = _validate_properties(
            payload=structured_input,
            properties=common_properties,
            errors=errors,
            prefix="structured_input",
        )
        if not status_flag:
            trigger_codes.append("INPUT_VALIDATION_FAILED")

    else:
        trigger_codes.append("INPUT_SCHEMA_LOAD_FAILED")

    incident_type = structured_input.get("incident_type")
    by_incident_type = validation_schema.get("by_incident_type", {})

    if not isinstance(incident_type, str) or not incident_type.strip():
        errors.append("structured_input.incident_type must be a non-empty string")
        trigger_codes.append("INPUT_MISSING_REQUIRED_FIELD")
    elif incident_type not in by_incident_type:
        errors.append(
            f"Unsupported incident_type {incident_type!r}. "
            f"Expected one of {list(by_incident_type.keys())}"
        )
        trigger_codes.append("INPUT_UNSUPPORTED_INCIDENT_TYPE")
    else:
        type_schema = by_incident_type.get(incident_type, {})
        type_required = type_schema.get("required", [])
        type_properties = type_schema.get("properties", {})

        missing_flag = False
        for field in type_required:
            if _is_missing(structured_input.get(field)):
                missing_flag = True
                errors.append(f"Missing required {incident_type} field: {field}")
        
        if missing_flag:
            trigger_codes.append("INPUT_MISSING_REQUIRED_FIELD")

        if isinstance(type_properties, dict):
            status_flag = _validate_properties(
                payload=structured_input,
                properties=type_properties,
                errors=errors,
                prefix=f"structured_input[{incident_type}]",
            )
            if not status_flag:
                trigger_codes.append("INPUT_VALIDATION_FAILED")

    if errors:
        decision_id = str(uuid.uuid4())
        return {
            "warnings": warnings + ["INPUT_VALIDATION_FAILED"],
            "error_flag": True,
            "error_message": "Validation failed:\n- " + "\n- ".join(errors),
            "trace": state.get("trace", []) + ["validate_input:not_ok"],
            "decision_id": decision_id,
            "decision": _create_decision_snapshot(
                decision_id=decision_id,
                trigger_codes=list(dict.fromkeys(trigger_codes))
            )
        }

    return {
        "warnings": warnings,
        "error_flag": False,
        "error_message": None,
        "trace": state.get("trace", []) + ["validate_input:ok"],
    }
