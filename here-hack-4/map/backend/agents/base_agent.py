# pyre-ignore-all-errors
# ============================================================================
# Agent Base class — all agents inherit from this
# ============================================================================
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict
from backend.schemas.models import AgentResult

log = logging.getLogger("agents")


class BaseAgent(ABC):
    """Abstract base for every agent in the system."""

    name: str = "base_agent"

    @abstractmethod
    async def execute(self, payload: Dict[str, Any]) -> Any:
        """Run the agent's core logic. Must be overridden."""
        ...

    async def run(self, task_id: str, payload: Dict[str, Any]) -> AgentResult:
        """Wrapper that times execution and catches errors."""
        t0 = time.time()
        try:
            log.info(f"[{self.name}] starting task {task_id}")
            data = await self.execute(payload)
            elapsed = time.time() - t0
            log.info(f"[{self.name}] completed in {elapsed:.2f}s")
            return AgentResult(task_id=task_id, agent_name=self.name,
                               success=True, data=data, elapsed_s=round(elapsed, 3))
        except Exception as e:
            elapsed = time.time() - t0
            log.error(f"[{self.name}] FAILED: {e}")
            return AgentResult(task_id=task_id, agent_name=self.name,
                               success=False, error=str(e), elapsed_s=round(elapsed, 3))
