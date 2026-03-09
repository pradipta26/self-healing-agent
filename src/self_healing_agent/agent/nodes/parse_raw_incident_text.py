import re
import os
from typing import Any

from self_healing_agent.agent.state import AgentState

FQDN_REGEX = re.compile(r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,63}\.?$")

def _normalize_text(value: str) -> str:
    text = value.replace("\n", " ").strip()
    text = re.sub(r"\b(Reason|System|Instance|Application|Host|DC|MetricName|host)\s+:", r"\1:", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return re.sub(r"\s+", " ", text).strip() or ""


def _extract_between(text: str, start_key: str, end_key: str | None = None) -> str:
    start_idx = text.find(start_key)
    if start_idx == -1:
        return ""
    start_idx += len(start_key)
    if end_key is None:
        return text[start_idx:].strip()
    end_idx = text.find(end_key, start_idx)
    if end_idx == -1:
        return text[start_idx:].strip()
    return text[start_idx:end_idx].strip()


def _extract_derived_host(instances: str) -> str:
    text = instances.strip()
    host_patterns = [
        r"\b(at host|host:|host)\s+([A-Za-z0-9._-]+)",
    ]
    for pattern in host_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(2).strip().rstrip(".,;:")

    if ":" in text:
        first_part = text.split(":", 1)[0].strip().rstrip(".,;:")
        looks_host_like = any(ch.isdigit() for ch in first_part) or "." in first_part or "-" in first_part
        if first_part and looks_host_like and re.match(r"^[A-Za-z0-9._-]+$", first_part):
            return first_part
    return ""


def _extract_metrics(text: str) -> list[str]:
    match = re.search(r"MetricName:\s*(.*?)\s*,\s*Application:", text)
    if not match:
        return []
    metric_value = match.group(1).strip()
    return [part.strip() for part in metric_value.split(",") if part.strip()]


def _is_system_metric(metric_names: list[str]) -> bool:
    keywords = ("oracle-db", "sqldb", "ibmmq", "cassandra", "rmq")
    lowered = [metric.lower() for metric in metric_names]
    return any(any(keyword in metric for keyword in keywords) for metric in lowered)


def _extract_infra_app_name(text: str) -> str:
    app_segment = _extract_between(text, "Application:", " for host:").strip()
    if not app_segment:
        return ""

    first_token = app_segment.split(" ")[0].strip()
    if first_token.count("-") >= 2:
        return first_token
    return app_segment


def _extract_host_from_infra(text: str) -> str | None:
    host_raw = _extract_between(text, "for host:", ",")
    host_raw = host_raw.strip()
    if not host_raw:
        return None

    jvm_idx = host_raw.find("JVM")
    if jvm_idx != -1:
        host_raw = host_raw[:jvm_idx].strip(" ,-")

    agent_match = re.search(r"\bagent\b", host_raw, re.IGNORECASE)
    if agent_match:
        host_raw = host_raw[: agent_match.end()]

    match = re.search(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\.com$", host_raw)
    host = match.group(0).strip() if match else ""
    if host:
        return host

    return host_raw.strip() or None

def _derive_reason_from_instance_tail(instance_tail: str, metric_name_hint: str|None = None,) -> tuple[str, list[str]]:
    """
    Derive a clean 'reason' string from the tail captured after 'Instance:'.
    Returns: (reason, warnings)
    """
    warnings: list[str] = []
    raw_tail = instance_tail.strip()

    # Rule 1: prefer "after last ' has '"
    idx = instance_tail.rfind(" has ")
    if idx > -1:
        reason = instance_tail[idx + len(" has ") :]
        return reason, warnings

    # Rule 2: find a comparator expression near the end
    # Strategy: locate last comparator; take a window before it.
    comparator_re = re.compile(r"(>=|<=|==|=|>|<)")
    matches = list(comparator_re.finditer(instance_tail))
    if matches:
        last = matches[-1]
        comp_pos = last.start()

        # Take up to ~80 chars before comparator to capture metric-ish phrase
        left_start = max(0, comp_pos - 80)
        left = instance_tail[left_start:comp_pos].strip(" ,;:")
        right = instance_tail[comp_pos:].strip(" ,;:")

        reason = f"{left} {right}".strip()

        # Optional sanity check: if metric hint provided, ensure it's at least somewhat present
        if metric_name_hint and metric_name_hint.lower() not in reason.lower():
            warnings.append("REASON_DERIVATION_WEAK_METRIC_MISMATCH")

        return reason, warnings

    # Rule 3: fallback to the whole tail (but warn)
    warnings.append("REASON_DERIVATION_FALLBACK_RAW_INSTANCE")
    return raw_tail, warnings

def _parse_common_fields(text: str) -> dict[str, Any]:
    warnings: list[str] = []
    service_domain = _extract_between(text, "System:", ",")
    if not service_domain: 
        warnings.append("MISSING_SERVICE_DOMAIN")
    datacenter = _extract_between(text, "DC:", ",")
    if not datacenter and not datacenter.strip(): 
        warnings.append("MISSING_DATACENTER")
    else:
        datacenter = datacenter.upper().replace("-", "").replace("_", "").strip()
    metric_names = _extract_metrics(text)
    if not metric_names:
        warnings.append("MISSING_METRIC_NAME")
    app_name = _extract_between(text, "Application:", ",").strip()
    if not app_name:
        app_name = _extract_between(text, "Application:").strip()
    
    env = os.getenv("SHA_ENV", "DEV").upper()
    return (
        env,
        service_domain,
        datacenter,
        metric_names,
        app_name,
        warnings,
    )

def _parse_infra_host(text: str) -> dict[str, Any]:
    env, service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fields(text)
    app_name = _extract_infra_app_name(text)
    if not app_name:
        warnings.append("MISSING_APP_NAME")
    host = _extract_host_from_infra(text)
    if not host:
        warnings.append("MISSING_HOST")
    elif host and not bool(FQDN_REGEX.fullmatch(host)):
        warnings.append("HOST_NOT_FQDN")
    
    instance_tail = _extract_between(text, "Instance:").strip()

    instances: list[str] = []
    if instance_tail:
        if "has " in instance_tail:
            instances = [instance_tail.strip()[0:instance_tail.strip().find(" has ")]]
        else:
            instances = [instance_tail.split()[0].strip()]  # take first token as instance if no 'has' found
    if not instances:
        warnings.append("MISSING_INSTANCE")
    # Extract reason
    reason, reason_warnings = _derive_reason_from_instance_tail(instance_tail)
    warnings.extend(reason_warnings)
    
    # Extract instance hosts from tail
    instance_hosts: list[str] = []
    candidate = instance_tail
    for sep in (":", "|"):
        if sep in candidate:
            candidate = candidate.split(sep, 1)[0].strip()
            break

    # Step 2: validate candidate as hostname/FQDN-ish
    if re.match(r"^[A-Za-z0-9._-]+$", candidate):
        instance_hosts = [candidate]        
    return {
        'structured_input': {
            "incident_type": "infra_host",
            'env': env,  # Default to PROD - will be updated in the future based on additional parsing if needed
            "service_domain": service_domain,
            "datacenter": datacenter,
            "metric_name": metric_names,
            "app_name": app_name,
            "host": host,
            "instances": instances if instances else [],
            "instance_host": instance_hosts,
            "reason": reason,
        },
        'warnings': warnings,
        'trace': ['parse_raw_incident_text:warning'] if warnings else ['parse_raw_incident_text:ok'],
        'error_flag': False,
        'error_message': None
    }


def _parse_service_instance(text: str) -> dict[str, Any]:
    env, service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fields(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")

    instances = _extract_between(text, "Instance:")
    instance_host = _extract_derived_host(instances)

    return {
        'structured_input': {
            'incident_type': "service_instance",
            'env': env, 
            'service_domain': service_domain,
            'datacenter': datacenter,
            'metric_name': metric_names,
            'app_name': app_name,
            'host': None,
            'instances': [instances] if instances else [],
            'instance_host': [instance_host] if instance_host else [],
            'reason': reason,
        },
        'warnings': warnings,
        'trace': ['parse_raw_incident_text:warning'] if warnings else ['parse_raw_incident_text:ok'],
        'error_flag': False,
        'error_message': None
    }   


def _parse_system_instance(text: str) -> dict[str, Any]:
    env, service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fieleds(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")

    host = _extract_between(text, "Host:")
    if not host:
        warnings.append("MISSING_HOST")
    elif not bool(FQDN_REGEX.fullmatch(host)):
        warnings.append("HOST_NOT_FQDN")

    return {
        'structured_input': {
            'incident_type': "system_instance",
            'env': env,  # Default to PROD - will be updated in the future based on additional parsing if needed
            "service_domain": service_domain,
            "datacenter": datacenter,
            "metric_name": metric_names,
            "app_name": app_name,
            "host": host,
            "instances": [],
            "instance_host": [],
            "reason": reason,
        },
        'warnings': warnings,
        'trace': ['parse_raw_incident_text:warning'] if warnings else ['parse_raw_incident_text:ok'],
        'error_flag': False,
        'error_message': None
    }

 
def _parse_service_dc(text: str) -> dict[str, Any]:
    env, service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fields(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")
    
    return {
        'structured_input': {
        "incident_type": "service_dc",
        'env': env,
        "service_domain": service_domain,
        "datacenter": datacenter,
        "metric_name": metric_names,
        "app_name": app_name,
        "host": None,
        "instances": [],
        "instance_host": [],
        "reason": reason,
        },
        'warnings': warnings,
        'trace': ['parse_raw_incident_text:warning'] if warnings else ['parse_raw_incident_text:ok'],
        'error_flag': False,
        'error_message': None
    }


def _parse_system_dc(text: str) -> dict[str, Any]:
    env, service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fields(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")
    
    return {
        'structured_input': {
            "incident_type": "system_dc",
            'env': env,
            "service_domain": service_domain,
            "datacenter": datacenter,
            "metric_name": metric_names,
            "app_name": app_name,
            "host": None,
            "instances": [],
            "instance_host": [],
            "reason": reason,
        },
        'warnings': warnings,
        'trace': ['parse_raw_incident_text:warning'] if warnings else ['parse_raw_incident_text:ok'],
        'error_flag': False,
        'error_message': None
    }


def parse_raw_incident_details(state: AgentState) -> dict[str, Any]:
    text = _normalize_text(state['incident_raw'])
    if text:
        if text.startswith("System:"):
            return _parse_infra_host(text)

        if text.startswith("Reason:"):
            has_host = "Host:" in text
            has_instance = "Instance:" in text

            if has_host and not has_instance:
                return _parse_system_instance(text)
            if has_instance:
                return _parse_service_instance(text)

            metric_names = _extract_metrics(text)
            if _is_system_metric(metric_names):
                return _parse_system_dc(text)
            return _parse_service_dc(text)

    return {
        'structured_input': {
            "incident_type": None,
            "env": None,
            "service_domain": None,
            "datacenter": None,
            "metric_name": [],
            "app_name": None,
            "host": None,
            "instances": [],
            "reason": None,
        },
        'warnings': ["UNRECOGNIZED_INPUTTEXT_FORMAT"],
        'trace': ['parse_raw_incident_text:warning'],
        'error_flag': True,
        'error_message': "Unrecognized input text format"
    }
