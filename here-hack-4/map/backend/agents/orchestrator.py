# pyre-ignore-all-errors
# ============================================================================
# Agent 1 — Master Orchestrator (capability planning + adaptive evidence loop)
# ============================================================================
"""
Coordinates all other agents. Unlike a static fan-out, this orchestrator:

  1. PLANS  — inspects the baseline + configured keys and decides which evidence
              agents are actually applicable (preconditions), emitting the plan
              as reasoning events instead of blindly broadcasting to everyone.
  2. ACTS   — dispatches the selected evidence agents in parallel (fault-isolated
              via asyncio.gather), then runs matching → fusion → decision.
  3. REFLECTS — finds records that came back `uncertain` and, if any baseline
              place is involved, runs a SECOND targeted round of evidence on just
              those places, then re-fuses and re-decides (plan → act → observe →
              re-plan). This adaptive loop is the agentic core.

Every decision the orchestrator makes is recorded in the event log so the run is
transparent and reproducible.
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Tuple

from backend.agents.base_agent import BaseAgent
from backend.agents._util import key_present
from backend.schemas.models import AgentResult
from backend.config import settings

log = logging.getLogger("orchestrator")

MAX_ROUNDS = 2  # round 1 (broad) + round 2 (targeted on uncertain)

# Evidence agents that can resolve an uncertain place on a second pass — the
# authoritative / real-time sources are most useful here.
RETRY_AGENTS = ["tripadvisor_evidence", "gov_data", "discussion_evidence"]


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"

    def __init__(self):
        # Agent registry — populated at startup by the pipeline
        self._agents: Dict[str, BaseAgent] = {}
        self._results: List[AgentResult] = []
        self._event_log: List[Dict] = []

    def register(self, agent: BaseAgent):
        self._agents[agent.name] = agent

    def _emit(self, events: List[Dict], stage: str, status: str, msg: str, data: Any = None):
        evt = {"stage": stage, "status": status, "message": msg, "elapsed": 0.0, "data": data}
        events.append(evt)
        log.info(f"[{stage}] {status}: {msg}")
        return evt

    # ── PLAN ────────────────────────────────────────────────────────────────

    def _plan_evidence_agents(self, baseline: List[Dict], events: List[Dict]) -> List[str]:
        """
        Decide which evidence agents to run based on data + key preconditions.
        Returns the ordered list of agent names that will be dispatched.
        """
        candidate_agents = [
            "gov_data", "website_extractor", "discussion_evidence",
            "visual_verification", "tripadvisor_evidence",
        ]
        any_website = any(p.get("website") for p in baseline)
        has_mapillary = key_present(settings.mapillary_access_token or os.getenv("MAPILLARY_ACCESS_TOKEN"))

        preconditions = {
            "gov_data": (True, "OneMap + ACRA + data.gov.sg are public — always run"),
            "website_extractor": (
                any_website,
                "at least one baseline place has a website" if any_website
                else "no baseline place has a website — skipping",
            ),
            "discussion_evidence": (
                key_present(settings.fetchlayer_api_key),
                "fetchlayer key present — Reddit search enabled" if key_present(settings.fetchlayer_api_key)
                else "no fetchlayer key — skipping Reddit discussion",
            ),
            "visual_verification": (
                has_mapillary,
                "Mapillary token present — street-level vision enabled" if has_mapillary
                else "no MAPILLARY_ACCESS_TOKEN — vision has no imagery, skipping",
            ),
            "tripadvisor_evidence": (
                key_present(settings.tripadvisor_api_key),
                "TripAdvisor key present — closure flags + review recency enabled"
                if key_present(settings.tripadvisor_api_key)
                else "no TripAdvisor key — skipping",
            ),
        }

        selected = []
        for agent_name in candidate_agents:
            if agent_name not in self._agents:
                continue
            ok, why = preconditions.get(agent_name, (True, "no preconditions"))
            if ok:
                selected.append(agent_name)
                self._emit(events, "plan", "selected", f"✓ {agent_name}: {why}")
            else:
                self._emit(events, "plan", "skipped", f"✗ {agent_name}: {why}")
        return selected

    # ── ACT (gather) ──────────────────────────────────────────────────────────

    async def _gather_evidence(self, agent_names: List[str], baseline: List[Dict],
                               events: List[Dict], stage: str) -> Tuple[List, Dict[str, int]]:
        """Dispatch the given evidence agents over `baseline` in parallel."""
        tasks, names = [], []
        for agent_name in agent_names:
            agent = self._agents.get(agent_name)
            if not agent:
                continue
            names.append(agent_name)
            tasks.append(agent.run(f"{agent_name}_{int(time.time()*1000)}", {
                "baseline": baseline,
                "target_place_ids": None,
            }))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        evidence, per_agent = [], {}
        for name, r in zip(names, results):
            if isinstance(r, AgentResult) and r.success and r.data:
                items = r.data if isinstance(r.data, list) else [r.data]
                evidence.extend(items)
                per_agent[name] = len(items)
                self._emit(events, stage, "progress", f"[{name}] → {len(items)} evidence items")
            elif isinstance(r, AgentResult):
                per_agent[name] = 0
                self._emit(events, stage, "warning", f"[{name}] {'failed: ' + str(r.error) if r.error else 'no evidence'}")
            else:  # raised exception escaped run() (shouldn't happen)
                per_agent[name] = 0
                self._emit(events, stage, "warning", f"[{name}] crashed: {r}")
        return evidence, per_agent

    # ── ACT (reason) ──────────────────────────────────────────────────────────

    async def _reason(self, baseline: List[Dict], evidence: List) -> List[Dict]:
        """matching → fusion → decision over the given baseline + evidence."""
        matcher = self._agents.get("matching")
        match_data = []
        if matcher:
            mr = await matcher.run("match_run", {"baseline": baseline, "evidence": evidence})
            match_data = mr.data if mr.success else []

        fuser = self._agents.get("fusion")
        fused = []
        if fuser:
            fr = await fuser.run("fusion_run", {"matches": match_data, "evidence": evidence, "baseline": baseline})
            fused = fr.data if fr.success else []

        decider = self._agents.get("decision")
        decided = []
        if decider:
            dr = await decider.run("decision_run", {"records": fused, "baseline": baseline})
            decided = dr.data if dr.success else []
        return decided

    # ── execute ───────────────────────────────────────────────────────────────

    async def execute(self, payload: Dict[str, Any]) -> Any:
        baseline_places = payload.get("baseline", [])
        events: List[Dict] = []
        t0 = time.time()

        self._emit(events, "baseline", "running", f"Baseline loaded: {len(baseline_places)} places")

        # ── PLAN ──
        selected = self._plan_evidence_agents(baseline_places, events)
        self._emit(events, "plan", "complete",
                   f"Plan: {len(selected)} evidence agents → {', '.join(selected) or 'none'}")

        # ── ACT: round 1 (broad) ──
        self._emit(events, "extraction", "running",
                   f"Round 1 — dispatching {len(selected)} evidence agents in parallel")
        evidence, per_agent_r1 = await self._gather_evidence(selected, baseline_places, events, "extraction")
        self._emit(events, "extraction", "complete", f"Round 1 evidence collected: {len(evidence)}")

        self._emit(events, "reasoning", "running", "Matching → fusion → decision (round 1)")
        decided = await self._reason(baseline_places, evidence)
        for r in decided:
            r.setdefault("evidence_rounds", 1)
        self._emit(events, "reasoning", "complete", f"Round 1 classified {len(decided)} records")

        rounds_run = 1

        # ── REFLECT + adaptive round 2 (targeted) ──
        uncertain = [r for r in decided if r.get("status") == "uncertain" and r.get("baseline_place_id")]
        self._emit(events, "reflection", "running",
                   f"{len(uncertain)} uncertain records reference a baseline place — considering a targeted second pass")

        if uncertain and len(selected) and rounds_run < MAX_ROUNDS:
            target_ids = {r["baseline_place_id"] for r in uncertain}
            target_baseline = [p for p in baseline_places if p.get("place_id") in target_ids]
            retry_agents = [a for a in RETRY_AGENTS if a in selected]

            self._emit(events, "reflection", "replan",
                       f"Re-querying {len(retry_agents)} authoritative agents on {len(target_baseline)} uncertain places: {', '.join(retry_agents)}")

            extra_evidence, _ = await self._gather_evidence(retry_agents, target_baseline, events, "reflection")
            self._emit(events, "reflection", "progress", f"Round 2 added {len(extra_evidence)} new evidence items")

            if extra_evidence:
                combined = evidence + extra_evidence
                redecided = await self._reason(baseline_places, combined)
                resolved = sum(1 for r in redecided if r.get("status") != "uncertain"
                               and r.get("baseline_place_id") in target_ids)
                for r in redecided:
                    r["evidence_rounds"] = 2 if r.get("baseline_place_id") in target_ids else r.get("evidence_rounds", 1)
                decided = redecided
                evidence = combined
                rounds_run = 2
                self._emit(events, "reflection", "complete",
                           f"Round 2 resolved {resolved}/{len(uncertain)} previously-uncertain places")
            else:
                self._emit(events, "reflection", "complete", "Round 2 found no new evidence — keeping round 1 verdicts")
        else:
            self._emit(events, "reflection", "complete", "No targeted second pass needed")

        # ── Discovery: new places that exist (NEA-licensed) but aren't on the map ──
        discoverer = self._agents.get("discovery")
        if discoverer:
            self._emit(events, "discovery", "running",
                       "Discovering licensed food premises missing from the baseline map")
            disc = await discoverer.run("discovery_run", {
                "full_baseline": payload.get("full_baseline", baseline_places),
            })
            new_places = disc.data if (disc.success and disc.data) else []
            for r in new_places:
                r.setdefault("evidence_rounds", 1)
            decided = decided + new_places
            self._emit(events, "discovery", "complete",
                       f"Discovered {len(new_places)} new places not yet on the map")

        # ── Review queue ──
        self._emit(events, "review", "running", "Generating review queue for uncertain cases")
        reviewer = self._agents.get("review")
        if reviewer:
            review_result = await reviewer.run("review_run", {"records": decided})
            queue = review_result.data if review_result.success else []
        else:
            queue = []
        queue_size = len(queue.get("queue", [])) if isinstance(queue, dict) else len(queue)
        self._emit(events, "review", "complete", f"Queued {queue_size} items for human review")

        total_elapsed = time.time() - t0
        self._emit(events, "done", "complete",
                   f"Pipeline complete in {total_elapsed:.2f}s over {rounds_run} evidence round(s)")

        # Summary
        statuses: Dict[str, int] = {}
        for r in decided:
            s = r.get("status", "uncertain") if isinstance(r, dict) else getattr(r, "status", "uncertain")
            statuses[s] = statuses.get(s, 0) + 1

        return {
            "events": events,
            "records": decided,
            "review_queue": queue,
            "summary": statuses,
            "total_evidence": len(evidence),
            "evidence_rounds": rounds_run,
            "agents_planned": selected,
            "elapsed_s": round(total_elapsed, 2),
        }
