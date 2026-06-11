# pyre-ignore-all-errors
# ============================================================================
# API Routes — Place Detail with XAI Explanations
# ============================================================================
import logging
from fastapi import APIRouter, HTTPException
from backend.app_state import get_state
from backend.explainability.explanation_generator import generate_explanation

router = APIRouter(prefix="/api", tags=["place_detail"])
log = logging.getLogger("place_detail_routes")


@router.get("/places/{place_index}/explanation")
async def get_place_explanation(place_index: int):
    """Get full XAI explanation for a classified place."""
    state = get_state()
    records = state.get("records", [])

    if place_index < 0 or place_index >= len(records):
        raise HTTPException(status_code=404, detail="Place not found")

    record = records[place_index]
    explanation = generate_explanation(record)

    return {
        "place": record,
        "explanation": explanation,
    }


@router.get("/places/by-name/{name}/explanation")
async def get_place_explanation_by_name(name: str):
    """Get XAI explanation by place name (partial match)."""
    state = get_state()
    records = state.get("records", [])

    q = name.lower()
    for i, record in enumerate(records):
        rname = record.get("detected_name", "").lower()
        if q in rname or rname in q:
            explanation = generate_explanation(record)
            return {
                "index": i,
                "place": record,
                "explanation": explanation,
            }

    raise HTTPException(status_code=404, detail=f"No place matching '{name}' found")


@router.get("/places/all-with-explanations")
async def get_all_places_with_explanations(status: str = None, limit: int = 500):
    """Get all classified places with inline explanations."""
    state = get_state()
    records = state.get("records", [])

    if status:
        records = [r for r in records if r.get("status") == status]

    results = []
    for i, record in enumerate(records[:limit]):
        explanation = generate_explanation(record)
        results.append({
            **record,
            "_explanation": explanation,
        })

    return {"places": results, "total": len(results)}
