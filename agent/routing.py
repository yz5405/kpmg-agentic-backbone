"""Conditional routing for agent workflow results."""
from agent.state import AgentState, SUCCESS, NO_EVIDENCE, ERROR


def determine_status(
    evidence: list[dict],
    error: str | None
) -> str:
    """Determine routing status based on evidence and error."""
    if error is not None:
        return ERROR

    if evidence:
        return SUCCESS

    return NO_EVIDENCE


def route_result(state: AgentState) -> AgentState:
    """Update and return the legacy workflow state."""
    state.status = determine_status(
        evidence=state.evidence,
        error=state.error
    )
    return state
