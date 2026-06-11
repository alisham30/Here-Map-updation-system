# pyre-ignore-all-errors
# ============================================================================
# Shared application state — singleton accessors
# ============================================================================
"""
Holds the in-memory state for the running application.
This avoids circular imports and gives all route modules
a single place to access the orchestrator, baseline agent, etc.
"""
from typing import Any, Dict

_state: Dict[str, Any] = {
    "pipeline_running": False,
    "records": [],
    "review_queue": [],
    "summary": {},
}

_baseline_agent = None
_orchestrator = None


def get_state() -> Dict[str, Any]:
    return _state


def set_baseline_agent(agent):
    global _baseline_agent
    _baseline_agent = agent


def get_baseline_agent():
    return _baseline_agent


def set_orchestrator(orch):
    global _orchestrator
    _orchestrator = orch


def get_orchestrator():
    return _orchestrator
