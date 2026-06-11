# pyre-ignore-all-errors
# ============================================================================
# API Routes — Review Queue + Human Validation
# ============================================================================
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timezone
from backend.app_state import get_state

router = APIRouter(prefix="/api", tags=["review"])


@router.get("/review/queue")
async def review_queue(
    priority: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    state = get_state()
    queue = state.get("review_queue", [])

    if priority is not None:
        queue = [q for q in queue if q.get("priority") == priority]
    if status:
        queue = [q for q in queue if q.get("status") == status]

    total = len(queue)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": queue[offset : offset + limit],
    }


@router.get("/review/queue/{item_index}")
async def review_item(item_index: int):
    state = get_state()
    queue = state.get("review_queue", [])
    if 0 <= item_index < len(queue):
        return queue[item_index]
    return {"error": "Item not found"}


@router.post("/review/action")
async def submit_review(item_index: int, action: str, notes: str = ""):
    """Apply a reviewer action to a queue item."""
    valid_actions = [
        "approve_new", "approve_closed", "approve_rebrand",
        "mark_active", "reject", "need_more_evidence",
    ]
    if action not in valid_actions:
        return {"error": f"Invalid action. Valid: {valid_actions}"}

    state = get_state()
    queue = state.get("review_queue", [])
    if item_index < 0 or item_index >= len(queue):
        return {"error": "Item not found"}

    item = queue[item_index]
    item["reviewer_action"] = action
    item["reviewer_notes"] = notes
    item["reviewed_at"] = datetime.now(timezone.utc).isoformat()

    # Also update the corresponding record in the main records list
    records = state.get("records", [])
    detected_name = item.get("detected_name", "")
    lat = item.get("latitude")
    lon = item.get("longitude")

    new_status_map = {
        "approve_new": "new_place",
        "approve_closed": "closed",
        "approve_rebrand": "rebranded",
        "mark_active": "active",
        "reject": "active",
    }

    if action in new_status_map:
        for r in records:
            if (r.get("detected_name") == detected_name
                    and r.get("latitude") == lat
                    and r.get("longitude") == lon):
                r["status"] = new_status_map[action]
                r["review_needed"] = False
                r["confidence"] = max(r.get("confidence", 0), 0.90)
                break

    return {"success": True, "action": action, "item": item}


@router.get("/review/stats")
async def review_stats():
    state = get_state()
    queue = state.get("review_queue", [])
    total = len(queue)
    reviewed = sum(1 for q in queue if q.get("reviewer_action"))
    pending = total - reviewed

    by_priority = {}
    by_status = {}
    by_action = {}
    for q in queue:
        p = q.get("priority", 0)
        by_priority[p] = by_priority.get(p, 0) + 1
        s = q.get("status", "uncertain")
        by_status[s] = by_status.get(s, 0) + 1
        a = q.get("reviewer_action")
        if a:
            by_action[a] = by_action.get(a, 0) + 1

    return {
        "total": total,
        "reviewed": reviewed,
        "pending": pending,
        "by_priority": by_priority,
        "by_status": by_status,
        "by_action": by_action,
    }
