from langgraph.graph import END, START, StateGraph

from self_healing_agent.agent.state import AgentState
from self_healing_agent.agent.nodes.parse_raw_incident_text import parse_raw_incident_details
from self_healing_agent.agent.nodes.validate_input import validate_input
from self_healing_agent.agent.nodes.error_notification import send_error_notification
from self_healing_agent.agent.router.router_functions import parse_raw_incident_text_router

def build_graph():
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node('parse_raw_incident_text', parse_raw_incident_details)
    graph_builder.add_node('send_error_notification', send_error_notification)
    graph_builder.add_node('validate_input', validate_input)

    # # graph_builder.add_node("build_evidence_candidates", build_evidence_candidates)
    # # graph_builder.add_node("invoke_llm", call_llm)
    # # graph_builder.add_node("validate_ai_output", validate_ai_response)

    # # Tool chain
    # graph_builder.add_node("prepare_tool_call", prepare_tool_call)
    # graph_builder.add_node("run_diagnostics_executor", run_diagnostics_executor)
    # graph_builder.add_node("run_diagnostics_verifier", run_diagnostics_verifier)
    # graph_builder.add_node("tool_retry_gate", tool_retry_gate)
    # graph_builder.add_node("tool_policy_gate", tool_policy_gate)

    # graph_builder.add_node("print_error", print_error)
    # graph_builder.add_node("propose_actions", propose_actions)
    # graph_builder.add_node("human_handoff", human_handoff)
    # graph_builder.add_node("rollback_compensation_stub", rollback_compensation_stub)

    graph_builder.add_edge(START, "parse_raw_incident_text")
    #graph_builder.add_edge("validate_input", "build_evidence_candidates")

    graph_builder.add_conditional_edges(
        "parse_raw_incident_text",
        parse_raw_incident_text_router,
        {'validate_input': 'validate_input', 'send_error_notification': "send_error_notification"},
    )

    graph_builder.add_edge("validate_input", END)
    graph_builder.add_edge("send_error_notification", END)

    # graph_builder.add_conditional_edges(
    #     "invoke_llm",
    #     llm_response_router,
    #     {"validate_ai_output": "validate_ai_output", "print_error": "print_error"},
    # )
    # graph_builder.add_edge("print_error", END)

    # # Gate tools ONLY on PROPOSE
    # graph_builder.add_conditional_edges(
    #     "validate_ai_output",
    #     post_validation_router,
    #     {
    #         "PROPOSE": "prepare_tool_call",
    #         "HITL_APPROVAL": "human_handoff",
    #         "HITL_INVESTIGATION": "human_handoff",
    #         "HITL_SME_REVIEW": "human_handoff",
    #     },
    # )
    # graph_builder.add_edge("human_handoff", END)

    # # Tool chain
    # graph_builder.add_edge("prepare_tool_call", "run_diagnostics_executor")
    # graph_builder.add_edge("run_diagnostics_executor", "run_diagnostics_verifier")
    # # edges to tool_retry_gate (insert into build_graph after run_diagnostics_verifier)
    # graph_builder.add_edge("run_diagnostics_verifier", "tool_retry_gate")
    # # retry decision:
    # graph_builder.add_conditional_edges(
    #     "tool_retry_gate",
    #     tool_retry_router,
    #     {
    #         "RETRY_TOOL": "run_diagnostics_executor",
    #         "NO_RETRY": "tool_policy_gate",
    #     },
    # )
    # # After tools, decision may stay PROPOSE or become HITL_*. Note: Tool chain runs only when route=PROPOSE ✅
    # # If tools cause escalation to HITL_INVESTIGATION, you run rollback first ✅
    # # Then you go to human_handoff with rollback context ✅
    # # This keeps rollback tool-failure-only, not for normal investigation routes.
    # graph_builder.add_conditional_edges(
    #     "tool_policy_gate",
    #     post_validation_router,
    #     {
    #         "PROPOSE": "propose_actions",
    #         "HITL_APPROVAL": "human_handoff",
    #         "HITL_INVESTIGATION": "rollback_compensation_stub",
    #         "HITL_SME_REVIEW": "human_handoff",
    #     },
    # )

    # graph_builder.add_edge("rollback_compensation_stub", "human_handoff")
    # graph_builder.add_edge("propose_actions", END)

    return graph_builder.compile()

