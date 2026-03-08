from self_healing_agent.agent.state import AgentState
import os

def parse_raw_incident_text_router(state: AgentState):
   
    if not state.get('error_flag', True):
        return 'validate_input'
    else:
        return 'send_error_notification'

# def input_router(state: AgentState) -> str:
#     """Determines which node to go to next based on state"""
#     return "print_error" if state.get("error_flag", True) else "invoke_llm"

# def llm_response_router(state: AgentState):
#     """Determines which node to go to next based on state"""
#     return 'print_error' if state.get('error_flag', True) else 'validate_ai_output'


# def post_validation_router(state: AgentState):
#     return state.get("decision", {}).get("route", "HITL_INVESTIGATION")


# def after_validation_router(state: AgentState) -> str:
#     return state.get("decision", {}).get("route", "HITL_INVESTIGATION")

# def tool_retry_router(state: AgentState) -> str:
#     """
#     Router for LangGraph conditional edges.
#     """
#     return state.get("tool_retry_decision", "NO_RETRY")
