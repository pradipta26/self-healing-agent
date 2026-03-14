# src/self_healing_agent/utils/incident_normalizer.py

from __future__ import annotations

import re
from typing import Any


def _clean_text(value: str | None) -> str:
    """Light text normalization for embedding-friendly strings."""
    if not value:
        return ""

    text = value.strip()
    text = text.replace("_", " ")
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_datacenter(dc: str | None) -> str:
    if not dc:
        return ""
    return dc.upper().replace("-", "").replace("_", "").strip()


def normalize_incident_type(value: str | None) -> str:
    if not value:
        return ""

    mapping = {
        "Host Infra": "host infrastructure",
        "Service Instance": "service instance",
        "Service DC": "service datacenter",
        "System Instance": "system instance",
        "System DC": "system datacenter",
    }

    return mapping.get(value.strip(), value.strip().lower())


def normalize_hosts(hosts: list[str] | None) -> list[str]:
    """
    Normalize host list.
    Removes ports when present (embedding does not benefit from ports).
    """

    if not hosts:
        return []

    normalized: list[str] = []

    for host in hosts:
        host = host.strip()

        if ":" in host:
            hostname, rest = host.split(":", 1)

            if rest.isdigit():
                host = hostname

        normalized.append(host)

    return normalized


def extract_reason_signal(
    incident_reason: str | None,
    metric_name: str | None,
) -> str:
    """
    Extract semantic signal from INCIDENT_REASON.

    Example:
      'Reason: oracle-db-session-blocker >= 1000.0;System: CHHV...'

    ->
      'oracle db session blocker exceeded threshold 1000'
    """

    if not incident_reason:
        return ""

    text = incident_reason.strip()

    match = re.search(r"Reason:\s*(.*?)\s*;\s*System:", text, re.IGNORECASE)

    if match:
        reason = match.group(1)
    else:
        reason = text

    reason = _clean_text(reason)

    reason = reason.replace(">=", " exceeded threshold ")
    reason = reason.replace("<=", " below threshold ")
    reason = reason.replace(">", " above ")
    reason = reason.replace("<", " below ")
    reason = reason.replace("=", " equal to ")

    reason = re.sub(r"\s+", " ", reason)

    metric = _clean_text(metric_name)

    if metric and metric.lower() not in reason.lower():
        reason = f"{metric} {reason}"

    return reason.strip()


def build_problem_chunk(record: dict[str, Any]) -> str:
    """
    Generate normalized semantic problem description used for embeddings.
    """

    service = _clean_text(record.get("SERVICE_DOMAIN"))
    app = _clean_text(record.get("APP_NAME"))
    metric = _clean_text(record.get("METRIC_NAME"))
    dc = normalize_datacenter(record.get("DATACENTER"))
    incident_type = normalize_incident_type(record.get("INCIDENT_TYPE"))
    hosts = normalize_hosts(record.get("HOSTS"))

    reason = extract_reason_signal(
        record.get("INCIDENT_REASON"),
        record.get("METRIC_NAME"),
    )

    parts: list[str] = []

    if service:
        parts.append(f"{service} service")

    if incident_type:
        parts.append(f"{incident_type} incident")

    if dc:
        parts.append(f"in {dc} datacenter")

    if app:
        parts.append(f"application {app}")

    if metric:
        parts.append(f"metric {metric}")

    if reason:
        reason = re.sub(r"\b\d+(\.\d+)?\b", "", reason)
        parts.append(f"reason {reason}")

    if hosts:
        parts.append(f"host {hosts}")

    text = ". ".join(parts)

    if not text.endswith("."):
        text += "."

    return text


def normalized_resolution(resolution_text: str) -> tuple[str, str]:
    """
    Generate resolution text used for RAG retrieval.
    """

    closure = _clean_text(resolution_text)

    if not closure:
        return "", ""
    
    normalized_text = closure.lower().strip()

    # Replace separators
    normalized_text = normalized_text.replace("_", " ")
    normalized_text = normalized_text.replace("-", " ")

    # Remove session IDs or numeric tokens (10364/35749, 12345 etc.)
    normalized_text = re.sub(r"\b\d+(/\d+)?\b", "", normalized_text)

    # Normalize RDS/hostname style strings to generic host
    normalized_text = re.sub(r"\b[a-z0-9\-\.]+\.(amazonaws|rds|internal)[a-z0-9\-\.]*\b", "database host", normalized_text)

    # Collapse whitespace
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    return f"resolution {closure}.", normalized_text

def normalize_resolution_text(closure_remarks: str | None) -> str:
    """
    Normalize resolution text for embedding generation.

    Keeps remediation verbs but removes noise such as IDs,
    ports, and overly specific hostnames.
    """

    if not closure_remarks:
        return ""

    text = closure_remarks.lower().strip()

    # Replace separators
    text = text.replace("_", " ")
    text = text.replace("-", " ")

    # Remove session IDs or numeric tokens (10364/35749, 12345 etc.)
    text = re.sub(r"\b\d+(/\d+)?\b", "", text)

    # Normalize RDS/hostname style strings to generic host
    text = re.sub(r"\b[a-z0-9\-\.]+\.(amazonaws|rds|internal)[a-z0-9\-\.]*\b", "database host", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text