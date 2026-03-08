from self_healing_agent.agent.state import AgentState


def validate_input(state: AgentState):
    return {'trace': state.get('trace', []) + ["validate_input:ok"]}