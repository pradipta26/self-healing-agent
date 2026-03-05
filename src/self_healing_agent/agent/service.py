import re
import json
from typing import Any

from self_healing_agent.core.models import IncidentPayload


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


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
    match = re.search(r"([A-Za-z0-9.-]+\.verizon\.com)", value)
    return match.group(1).strip() if match else ""


def _extract_instances_from_tail(value: str) -> list[str]:
    all_matches = re.findall(r"([A-Za-z0-9.-]+\.verizon\.com)", value)
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


def _parse_infra_host(text: str) -> dict[str, Any]:
    service_domain = _extract_between(text, "System:", ",")
    datacenter = _extract_between(text, "DC:", ",")
    metric_name_raw = _extract_metric_value(text)
    app_name = _extract_infra_app_name(text)

    app_reason = _extract_between(text, " for host:")
    reason = str(app_reason).strip() if app_reason else ""

    instance_tail = _extract_between(text, "Instance:")
    instances = _extract_instances_from_tail(instance_tail)

    return {
        "incident_type": "infra_host",
        "service_domain": service_domain or None,
        "datacenter": datacenter or None,
        "metric_name": _extract_metric_names(metric_name_raw),
        "app_name": app_name or None,
        "host": _extract_host_from_infra(text),
        "instances": instances,
        "reason": reason or None,
    }


def _parse_service_dc_or_instance(text: str) -> dict[str, Any]:
    
    service_domain = _extract_between(text, "System:", ",")
    datacenter = _extract_between(text, "DC:", ",")
    metric_name_raw = _extract_metric_value(text)
    metric_names = _extract_metric_names(metric_name_raw)
    app_name = _extract_between(text, "Application:", ",").strip()
    if not app_name:
        app_name = _extract_between(text, "Application:").strip()

    reason = _extract_between(text, "Reason:", "System:")
    reason = reason.strip(" ,")

    instance_tail = _extract_between(text, "Instance:")
    if not instance_tail and "Host:" in text:
        instance_tail = _extract_between(text, "Host:")
    instances = _extract_instances_from_tail(instance_tail)
    if not instances and instance_tail:
        derived_host = _extract_derived_host(instance_tail.strip())
        instances = [derived_host] if derived_host else [instance_tail.strip()]

    if "Host:" in text:
        incident_type = "system_instance"
    elif "Instance:" in text:
        incident_type = "service_instance"
    elif _is_system_metric(metric_names):
        incident_type = "system_dc"
    else:
        incident_type = "service_dc"

    return {
        "incident_type": incident_type,
        "service_domain": service_domain or None,
        "datacenter": datacenter or None,
        "metric_name": metric_names,
        "app_name": app_name or None,
        "host": None,
        "instances": instances if incident_type in ("service_instance", "system_instance") else [],
        "reason": reason or None,
    }


def _parse_incident_details(incident_details: str) -> dict[str, Any]:
    text = _normalize_text(incident_details)

    if text.startswith("System:") and "Application:" in text and "for host:" in text:
        return _parse_infra_host(text)

    if text.startswith("Reason:"):
        return _parse_service_dc_or_instance(text)

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
