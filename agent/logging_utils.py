"""Execution logging utilities for the agent workflow."""
from agent.state import AgentState


VALID_LEVELS = {"INFO", "WARNING", "ERROR"}


def format_log_event(
    message: str,
    level: str = "INFO"
) -> str:
    """Return a formatted log entry."""

    level = level.upper()

    if level not in VALID_LEVELS:
        raise ValueError(f"Unsupported log level: {level}")

    return f"[{level}] {message}"


def log_event(
    state: AgentState,
    message: str,
    level: str = "INFO"
) -> None:
    """Append an execution log to the existing AgentState."""

    entry = format_log_event(message, level)
    state.logs.append(entry)
