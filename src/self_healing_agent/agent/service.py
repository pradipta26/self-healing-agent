# self_healing_agent/src/self_healing_agent/agent/service.py
import json
from typing import Any
import uuid
from datetime import datetime, timezone

from self_healing_agent.agent.graph import build_graph
from self_healing_agent.core.models import IncidentPayload
from self_healing_agent.agent.state import AgentState

def run_incident(payload: IncidentPayload) -> dict[str, Any]:
    state: AgentState = {
        "trace_id": str(uuid.uuid4()),
        "incident_id": str(uuid.uuid4()),
        "incident_raw": payload.incident_details,
        "warnings": [],
        "trace": [],
        "error_flag": False,
        "error_message": None,
        "event_ids": [],
        "autonomy_mode": "SHADOW",
        "kill_switch_state": "DISABLED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }
    graph = build_graph()
    response = graph.invoke(state)
    return response


def _quick_test_main() -> None:
    samples = [
        # (
        #     "Host Infra",
        #     """System: GTV , DC: AWS-W , MetricName: Server CPU % , Application: GTV-ONE SEARCH-INFRA for host: 143-251-36-229.vpc.verizon.com , Instance: 143-251-36-229.vpc.verizon.com has Server CPU % >= 99.0"""
        # ),
        # (
        #     "Host Infra",
        #     "System: DAGV , DC: AWS-W , MetricName: jvm mismatch , Application: DAGV-DAGV-JVM-STATUS for host: AWS-W MCS PNO-DAGV JVM Status Mismatch, 6 missing, 2 extra DAGV-BATCH-CASSANDRAREALTIME-PRD-AW2:DAGV-BATCH-CASSANDRAREALTIME-PRD-AW2 = missing, WLS-DAGV-CXPNOB2-AW2:144-70-44-235.vpc.verizon.com:CXP_PNO_B2C:Server1:13001 = missing, WLS-DAGV-CXPNOB2-AW2:144-70-46-194.vpc.verizon.com:CXP_PNO_B2C:Server3:13003 = missing, WLS-DAGV-CXPNOB2-AW2:144-70-87-170.vpc.verizon.com:DVS_PNO_B2C:Server3:13003 = missing, Instance: Reference List: AWS-West.PNO_JVMList has jvm mismatch >= 0.0",
        # ),
        #         (
        #     "Host Infra",
        #     """System: BSUV , DC: TDC , MetricName: /log usage , Application: BSUV-SCMDATA-INFRA for host: tdclpbsuva010.verizon.com , Instance: tdclpbsuva010.verizon.com:/log has /log usage >= 96.0"""
        # ),
        (
            "Host Infra",
            "System: B6VV , DC: SDC , MetricName: /var/adm/WebSphere usage , Application: B6VV-DVS-INFRA for host: saclpb6vva511.sdc.vzwcorp.com , Instance: saclpb6vva511.sdc.vzwcorp.com:/var/adm/WebSphere has /var/adm/WebSphere usage >= 92.0",
        ),
        # (
        #     "Service DC",
        #     "Reason: 300% more traffic is observed compared to past window average traffic - 8188.0 System: BVHV, DC: SDC, MetricName: Traffic, Application: BVHV-SAFEGUARD-SSOIGSTREAMPROCESSING"
            
        # ),
        # (
        #     "Service DC",
        #     "Reason: 1 hosts have alb-502-count >= 7.0, Configured Host Capacity - 0 System: HIVV, DC: AWS-E, MetricName: alb-502-count, Application: HIVV-SOE-Sales-ALB-Logs"
            
        # ),
        # (
        #     "Service Instance",
        #     "Reason: Active Threads >= 200.0, Avg Response Time(ms) >= 20000.0 System: B6LV, DC: TDC, MetricName: Active Threads, Avg Response Time(ms), Application: B6LV-ACSS-AMQ, Instance: tdclpb6lva018:ACSS-MQ:acsstr-mq1:5701",
        # ),
        # (
        #     "Service Instance",
        #     "Reason: Avg Response Time(ms) >= 17086.0 System: B6VV, DC: AWS-W, MetricName: Avg Response Time(ms), Application: B6VV-ORBPM-B2B-NOTIFICATION, Instance: msb2b-834-aws-west2.orbpm.vpc.verizon.com_NOTIFICATION_9098",
        # ),
        # (
        #     "Service Instance",
        #     "Reason: 5xx >= 30.0 System: WHUV, DC: TDC, MetricName: 5xx, Application: WHUV-WORKHUB-NXTGEN-INFRA, Instance: WORKHUB_NXTGEN_LOGS|opt|application|access_log",
        # ),
        # (
        #     "Service Instance",
        #     "Reason: pegaerrors >= 105000.0 System: F5SV, DC: AWS-W, MetricName: pegaerrors, Application: F5SV-RTD-NBX-NEXTGEN, Instance: ERROR: ORA-12541 - Cannot connect. No listener at host nbxmprdr.cqou6muk7g9i.us",
        # ),
        # (
        #     "Service Instance",
        #     "Reason: oracle-db-sp-queue-status >= 3.0 System: BRHV, DC: TDC, MetricName: oracle-db-sp-queue-status, Application: BRHV-BRHV_SPLEX-Common-Operations, Instance: tdclpbrhvd008.verizon.com:Post:cjcmeast_revo_q4:2058",
        # ),
        # (
        #     "Service Instance",
        #     "Reason: 5xx >= 30.0 System: WHUV, DC: TDC, MetricName: 5xx, Application: WHUV-WORKHUB-NXTGEN-INFRA, Instance: WORKHUB_NXTGEN_LOGS|opt|application|access_log",
        # ),
        # (
        #     "System Instance",
        #     "Reason: CW_ReadIOPS >= 20000.0 System: F5SV, DC: AWS-E, MetricName: CW_ReadIOPS, Application: F5SV-F5SV Databases-OMP, Host: ompeprd",
        # ),
        # (
        #     "System Instance",
        #     "Reason: ibmmqdepth_TDCqueues >= 32000.0 System: DAGV, DC: TDC, MetricName: ibmmqdepth_TDCqueues, Application: DAGV-CPF_MQ-IBMMQ, Host: tdclpdagva102.tdc.vzwcorp.com"

        # ),
        # (
        #     "System DC",
        #     "Reason: 1 hosts have oracle-db-session-blocker >= 300.0 System: EV6V, DC: SDC, MetricName: oracle-db-session-blocker, Application: EV6V-EVV-Databases-VIP",
        # ),
    ]

    for idx, (label, details) in enumerate(samples, start=1):
        payload = IncidentPayload(incident_details=details)
        state: AgentState = run_incident(payload)
        print(f"state keys: {list(state.keys())}")
        print(f"\n[{idx}] {label}")
        print(json.dumps(state, indent=2))


if __name__ == "__main__":
    _quick_test_main()

# Execution command for quick test:
# cd self_healing_agent                                        
# PYTHONPATH=src python src/self_healing_agent/agent/service.py
