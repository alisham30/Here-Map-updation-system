# pyre-ignore-all-errors
# ============================================================================
# API Routes — Baseline / Map / Layers
# ============================================================================
from fastapi import APIRouter, Query
from typing import Optional
from backend.app_state import get_baseline_agent

router = APIRouter(prefix="/api", tags=["baseline"])


@router.get("/baseline/stats")
async def baseline_stats():
    agent = get_baseline_agent()
    places = agent.places
    layers = {}
    categories = {}
    for p in places:
        layers[p["source_layer"]] = layers.get(p["source_layer"], 0) + 1
        categories[p["category"]] = categories.get(p["category"], 0) + 1
    return {
        "total": len(places),
        "layers": layers,
        "categories": categories,
    }


@router.get("/baseline/places")
async def baseline_places(
    layer: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(500, le=5000),
    offset: int = 0,
):
    agent = get_baseline_agent()
    places = agent.places

    if layer:
        places = [p for p in places if p["source_layer"] == layer]
    if category:
        places = [p for p in places if p["category"] == category]
    if search:
        q = search.lower()
        places = [p for p in places if q in p.get("name", "").lower()]

    total = len(places)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "places": places[offset : offset + limit],
    }


@router.get("/baseline/nearby")
async def baseline_nearby(
    lat: float, lon: float, radius: float = Query(50, le=500)
):
    agent = get_baseline_agent()
    results = agent.find_nearby(lat, lon, radius)
    return {"count": len(results), "places": results}


@router.get("/layers")
async def get_layers():
    agent = get_baseline_agent()
    return agent.get_layers()


@router.get("/layers/{layer_name}")
async def get_layer(layer_name: str):
    agent = get_baseline_agent()
    data = agent.get_layers()
    layer = data["layers"].get(layer_name)
    if not layer:
        return {"error": f"Layer '{layer_name}' not found"}
    return layer
