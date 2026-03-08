from self_healing_agent.agent.state import AgentState

def send_error_notification(state: AgentState):
    trace = state.get("trace", [])
    print(f"Error encountered: {state.get('error_message', 'No error message found')}")
    return {'trace': trace + ["send_error_notification:ok"]}