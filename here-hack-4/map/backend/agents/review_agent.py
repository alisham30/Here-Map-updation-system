# pyre-ignore-all-errors
# ============================================================================
# Agent 12 — Review Agent
# ============================================================================
"""
Generates a prioritised review-queue for human validators.
Assigns priority (1–5), constructs context bundles, supports reviewer actions.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from backend.agents.base_agent import BaseAgent

log = logging.getLogger("review_agent")


class ReviewAgent(BaseAgent):
    name = "review"

    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        records: List[Dict] = payload.get("records", [])

        queue: List[Dict] = []
        auto_approved: int = 0

        for record in records:
            if record.get("review_needed"):
                item = self._build_review_item(record)
                queue.append(item)
            else:
                auto_approved += 1

        # Sort: higher priority first, then lower confidence
        queue.sort(key=lambda q: (-q["priority"], q["confidence"]))

        log.info(
            f"Review queue: {len(queue)} items | auto-approved: {auto_approved}"
        )
        return {
            "queue": queue,
            "auto_approved": auto_approved,
            "total": len(records),
        }

    def _build_review_item(self, record: Dict) -> Dict:
        status = record.get("status", "uncertain")
        confidence = record.get("confidence", 0.0)

        priority = self._compute_priority(status, confidence, record)

        return {
            "detected_name": record.get("detected_name", ""),
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "address": record.get("address"),
            "category": record.get("category"),
            "source_layer": record.get("source_layer"),
            "baseline_place_id": record.get("baseline_place_id"),
            "nearest_baseline_name": record.get("nearest_baseline_name"),
            "status": status,
            "confidence": confidence,
            "match_type": record.get("match_type"),
            "match_score": record.get("match_score"),
            "source_types": record.get("source_types", []),
            "source_count": record.get("source_count", 0),
            "review_reason": record.get("review_reason", ""),
            "priority": priority,
            "suggested_action": self._suggest_action(status, confidence),
            "evidence_summary": self._summarise_evidence(record),
            "reviewer_action": None,
            "reviewer_notes": None,
            "reviewed_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _compute_priority(status: str, confidence: float, record: Dict) -> int:
        """1 = highest, 5 = lowest."""
        if status == "rebranded":
            return 1  # rebrands always highest
        if status == "closed" and confidence >= 0.50:
            return 2
        if status == "new_place" and confidence < 0.55:
            return 2
        if status == "uncertain":
            return 3
        if status == "closed" and confidence < 0.50:
            return 3
        if status == "new_place":
            return 4
        return 5  # active edge cases

    @staticmethod
    def _suggest_action(status: str, confidence: float) -> str:
        if status == "new_place" and confidence >= 0.70:
            return "approve_new"
        if status == "closed" and confidence >= 0.60:
            return "approve_closed"
        if status == "rebranded":
            return "approve_rebrand"
        if status == "active":
            return "mark_active"
        return "need_more_evidence"

    @staticmethod
    def _summarise_evidence(record: Dict) -> str:
        parts = []
        if record.get("website_state"):
            parts.append(f"Website: {record['website_state']}")
        if record.get("delivery_available") is not None:
            parts.append(f"Delivery: {'yes' if record['delivery_available'] else 'no'}")
        if record.get("social_active") is not None:
            parts.append(f"Social: {'active' if record['social_active'] else 'inactive'}")
        if record.get("visual_state"):
            parts.append(f"Visual: {record['visual_state']}")
        if record.get("discussion_sentiment"):
            parts.append(f"Forums: {record['discussion_sentiment']}")
        return " | ".join(parts) if parts else "No evidence summary"
