import re
import json
from typing import Any

from self_healing_agent.core.models import IncidentPayload
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


def _extract_host(value: str) -> str:
    match = re.search(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\.com$", value)
    return match.group(0).strip() if match else ""


def _extract_instances_from_tail(value: str) -> list[str]:
    all_matches = re.findall(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\.com$", value)
    return [item.strip() for item in all_matches]


def _extract_derived_host(instance_tail: str) -> str:
    text = instance_tail.strip()
    host_patterns = [
        r"\b(at host|host:|host)\s+([A-Za-z0-9._-]+)",
    ]
    for pattern in host_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(2).strip().rstrip(".,;:")
    return ""


def _extract_metric_names(metric_value: str) -> list[str]:
    metric_value = metric_value.strip()
    if not metric_value:
        return []
    return [part.strip() for part in metric_value.split(",") if part.strip()]


def _extract_metric_value(text: str) -> str:
    match = re.search(r"MetricName:\s*(.*?)\s*,\s*Application:", text)
    if not match:
        return ""
    return match.group(1).strip()

def _extract_metrics(text: str) -> str:
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

    host = _extract_host(host_raw)
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

def _parse_common_fileds(text: str) -> dict[str, Any]:
    warnings: list[str] = []
    service_domain = _extract_between(text, "System:", ",")
    if not service_domain: 
        warnings.append("MISSING_SERVICE_DOMAIN")
    datacenter = _extract_between(text, "DC:", ",")
    if not datacenter: 
        warnings.append("MISSING_DATACENTER")
    #metric_name_raw = _extract_metric_value(text)
    metric_names = _extract_metrics(text)
    if not metric_names:
        warnings.append("MISSING_METRIC_NAME")
    app_name = _extract_between(text, "Application:", ",").strip()
    if not app_name:
        app_name = _extract_between(text, "Application:").strip()
    
    return (
        service_domain,
        datacenter,
        metric_names,
        app_name,
        warnings)

def _parse_infra_host(text: str) -> dict[str, Any]:
    service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fileds(text)
    app_name = _extract_infra_app_name(text)
    if not app_name:
        warnings.append("MISSING_APP_NAME")
    host = _extract_host_from_infra(text)
    if not host:
        warnings.append("MISSING_HOST")
    elif host and not bool(FQDN_REGEX.fullmatch(host)):
        warnings.append("HOST_NOT_FQDN")
    
    instance_tail = _extract_between(text, "Instance:").strip()
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
        "incident_type": "infra_host",
        "service_domain": service_domain,
        "datacenter": datacenter,
        "metric_name": metric_names,
        "app_name": app_name,
        "host": host,
        "instances": instances if instances else [],
        "instance_host": instance_hosts,
        "reason": reason or None,
        "warnings": warnings,
    }

def _parse_system_instance(text: str) -> dict[str, Any]:
    service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fileds(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")

    host = _extract_between(text, "Host:")
    if not bool(FQDN_REGEX.fullmatch(host)):
        warnings.append("HOST_NOT_FQDN")

    return {
        "incident_type": "system_instance",
        "service_domain": service_domain,
        "datacenter": datacenter,
        "metric_name": metric_names,
        "app_name": app_name,
        "host": host,
        "instances": [],
        "instance_host": [],
        "reason": reason,
        "warnings": warnings
    }

def _parse_service_instance(text: str) -> dict[str, Any]:
    service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fileds(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")

    instances = _extract_between(text, "Instance:")
    instance_host = _extract_derived_host(instances)

    return {
        "incident_type": "service_instance",
        "service_domain": service_domain,
        "datacenter": datacenter,
        "metric_name": metric_names,
        "app_name": app_name,
        "host": None,
        "instances": instances,
        "instance_host": [instance_host] if instance_host else [],
        "reason": reason,
        "warnings": warnings
    }

def _parse_system_dc(text: str) -> dict[str, Any]:
    service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fileds(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")
    
    return {
        "incident_type": "system_dc",
        "service_domain": service_domain,
        "datacenter": datacenter,
        "metric_name": metric_names,
        "app_name": app_name,
        "host": None,
        "instances": [],
        "instance_host": [],
        "reason": reason,
        "warnings": warnings
    }

def _parse_service_dc(text: str) -> dict[str, Any]:
    service_domain, datacenter, metric_names, app_name, warnings = _parse_common_fileds(text)
    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")
    if not reason:
        warnings.append("MISSING_REASON")
    
    return {
        "incident_type": "service_dc",
        "service_domain": service_domain,
        "datacenter": datacenter,
        "metric_name": metric_names,
        "app_name": app_name,
        "host": None,
        "instances": [],
        "instance_host": [],
        "reason": reason,
        "warnings": warnings
    }

def _parse_incident_details(incident_details: str) -> dict[str, Any]:
    text = _normalize_text(incident_details)  #re.sub(r"\s+", " ", incident_details.strip())
    if text:
        if text.startswith("System:"):
            return _parse_infra_host(text)
        elif text.startswith("Reason:"):
            if "Host:" in text and text.split(',')[-1].strip().startswith("Host:"):
                incident_type = "system_instance"
                return _parse_system_instance(text)
            elif "Instance:" in text and text.split(',')[-1].strip().startswith("Instance:"):
                incident_type = "service_instance"
                return _parse_service_instance(text)
            else:
                metric_names = _extract_metrics(text)
                if _is_system_metric(metric_names):
                    incident_type = "system_dc"
                    return _parse_system_dc(text)
                else:
                    incident_type = "service_dc"
                    return _parse_service_dc(text)

    return {
        "incident_type": None,
        "service_domain": None,
        "datacenter": None,
        "metric_name": [],
        "app_name": None,
        "host": None,
        "instances": [],
        "reason": None,
    }


def run_incident(payload: IncidentPayload) -> dict[str, Any]:
    parsed_incident = _parse_incident_details(payload.incident_details)
    return {
        "status": "processed",
        "parsed_incident": parsed_incident,
    }


def _quick_test_main() -> None:
    samples = [
        (
            "Host Infra",
            """System: GTV , DC: AWS-W , MetricName: Server CPU % , Application: GTV-ONE SEARCH-INFRA for host: 143-251-36-229.vpc.verizon.com , Instance: 143-251-36-229.vpc.verizon.com has Server CPU % >= 99.0"""
        ),
        (
            "Host Infra",
            "System: DAGV , DC: AWS-W , MetricName: jvm mismatch , Application: DAGV-DAGV-JVM-STATUS for host: AWS-W MCS PNO-DAGV JVM Status Mismatch, 6 missing, 2 extra DAGV-BATCH-CASSANDRAREALTIME-PRD-AW2:DAGV-BATCH-CASSANDRAREALTIME-PRD-AW2 = missing, WLS-DAGV-CXPNOB2-AW2:144-70-44-235.vpc.verizon.com:CXP_PNO_B2C:Server1:13001 = missing, WLS-DAGV-CXPNOB2-AW2:144-70-46-194.vpc.verizon.com:CXP_PNO_B2C:Server3:13003 = missing, WLS-DAGV-CXPNOB2-AW2:144-70-87-170.vpc.verizon.com:DVS_PNO_B2C:Server3:13003 = missing, Instance: Reference List: AWS-West.PNO_JVMList has jvm mismatch >= 0.0",
        ),
                (
            "Host Infra",
            """System: BSUV , DC: TDC , MetricName: /log usage , Application: BSUV-SCMDATA-INFRA for host: tdclpbsuva010.verizon.com , Instance: tdclpbsuva010.verizon.com:/log has /log usage >= 96.0"""
        ),
        (
            "Host Infra",
            "System: B6VV , DC: SDC , MetricName: /var/adm/WebSphere usage , Application: B6VV-DVS-INFRA for host: saclpb6vva511.sdc.vzwcorp.com , Instance: saclpb6vva511.sdc.vzwcorp.com:/var/adm/WebSphere has /var/adm/WebSphere usage >= 92.0",
        ),
        (
            "Service DC",
            "Reason: 300% more traffic is observed compared to past window average traffic - 8188.0 System: BVHV, DC: SDC, MetricName: Traffic, Application: BVHV-SAFEGUARD-SSOIGSTREAMPROCESSING"
            
        ),
        (
            "Service DC",
            "Reason: 1 hosts have alb-502-count >= 7.0, Configured Host Capacity - 0 System: HIVV, DC: AWS-E, MetricName: alb-502-count, Application: HIVV-SOE-Sales-ALB-Logs"
            
        ),
        (
            "Service Instance",
            "Reason: Active Threads >= 200.0, Avg Response Time(ms) >= 20000.0 System: B6LV, DC: TDC, MetricName: Active Threads, Avg Response Time(ms), Application: B6LV-ACSS-AMQ, Instance: tdclpb6lva018:ACSS-MQ:acsstr-mq1:5701",
        ),
        (
            "Service Instance",
            "Reason: Avg Response Time(ms) >= 17086.0 System: B6VV, DC: AWS-W, MetricName: Avg Response Time(ms), Application: B6VV-ORBPM-B2B-NOTIFICATION, Instance: msb2b-834-aws-west2.orbpm.vpc.verizon.com_NOTIFICATION_9098",
        ),
        (
            "Service Instance",
            "Reason: 5xx >= 30.0 System: WHUV, DC: TDC, MetricName: 5xx, Application: WHUV-WORKHUB-NXTGEN-INFRA, Instance: WORKHUB_NXTGEN_LOGS|opt|application|access_log",
        ),
        (
            "Service Instance",
            "Reason: pegaerrors >= 105000.0 System: F5SV, DC: AWS-W, MetricName: pegaerrors, Application: F5SV-RTD-NBX-NEXTGEN, Instance: ERROR: ORA-12541 - Cannot connect. No listener at host nbxmprdr.cqou6muk7g9i.us",
        ),
        (
            "Service Instance",
            "Reason: oracle-db-sp-queue-status >= 3.0 System: BRHV, DC: TDC, MetricName: oracle-db-sp-queue-status, Application: BRHV-BRHV_SPLEX-Common-Operations, Instance: tdclpbrhvd008.verizon.com:Post:cjcmeast_revo_q4:2058",
        ),
        (
            "Service Instance",
            "Reason: 5xx >= 30.0 System: WHUV, DC: TDC, MetricName: 5xx, Application: WHUV-WORKHUB-NXTGEN-INFRA, Instance: WORKHUB_NXTGEN_LOGS|opt|application|access_log",
        ),
        (
            "System Instance",
            "Reason: CW_ReadIOPS >= 20000.0 System: F5SV, DC: AWS-E, MetricName: CW_ReadIOPS, Application: F5SV-F5SV Databases-OMP, Host: ompeprd",
        ),
        (
            "System Instance",
            "Reason: ibmmqdepth_TDCqueues >= 32000.0 System: DAGV, DC: TDC, MetricName: ibmmqdepth_TDCqueues, Application: DAGV-CPF_MQ-IBMMQ, Host: tdclpdagva102.tdc.vzwcorp.com"

        ),
        (
            "System DC",
            "Reason: 1 hosts have oracle-db-session-blocker >= 300.0 System: EV6V, DC: SDC, MetricName: oracle-db-session-blocker, Application: EV6V-EVV-Databases-VIP",
        ),
    ]

    for idx, (label, details) in enumerate(samples, start=1):
        payload = IncidentPayload(incident_details=details)
        result = run_incident(payload)
        print(f"\n[{idx}] {label}")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _quick_test_main()

# Execution command for quick test:
# cd self_healing_agent                                        
# PYTHONPATH=src python src/self_healing_agent/agent/service.py
