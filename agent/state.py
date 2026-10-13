"""Shared state definitions for the KPMG Agentic Backbone MVP.

All workflow modules use this common state structure.
No LLM API or external framework is required.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


# Standard workflow statuses
PENDING = "PENDING"
SUCCESS = "SUCCESS"
NO_EVIDENCE = "NO_EVIDENCE"
ERROR = "ERROR"


@dataclass
class AgentState:
    """Shared data structure for a single-agent workflow."""

    # Original user question
    query: str

    # Financial filters extracted by query_parser.py
    filters: dict[str, Any] = field(default_factory=dict)

    # Maximum number of retrieved chunks
    top_k: int = 10

    # Retrieved evidence, including source metadata
    evidence: list[dict[str, Any]] = field(default_factory=list)

    # Current workflow status
    status: str = PENDING

    # Error message, if execution fails
    error: Optional[str] = None

    # Basic execution logs
    logs: list[str] = field(default_factory=list)


def create_initial_state(
    query: str,
    top_k: int = 10,
) -> AgentState:
    """Create a fresh AgentState for a new query.

    Validation is handled by the workflow/tool layer,
    allowing invalid inputs to enter the ERROR routing path.
    """
    return AgentState(
        query=query,
        top_k=top_k,
    )
