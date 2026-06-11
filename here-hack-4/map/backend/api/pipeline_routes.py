# pyre-ignore-all-errors
# ============================================================================
# API Routes — Pipeline / Intelligence / Places
# ============================================================================
import asyncio
import json
import time
import logging
import random
from copy import deepcopy
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from backend.app_state import get_orchestrator, get_baseline_agent, get_state
from backend.config import settings

router = APIRouter(prefix="/api", tags=["pipeline"])
log = logging.getLogger("pipeline_routes")

TARGET_STATUS_MIX = {
    "new_place": 5,
    "active": 3,
    "closed": 3,
    "rebranded": 2,
    "uncertain": 4,
}
# Output limits from config (tunable via ENV: PIPELINE_OUTPUT_LIMIT)
TARGET_RECORD_LIMIT = settings.pipeline_output_limit  # Default 200 from config
TARGET_IMAGE_MIN = 3
USE_PINNED_PRESET = False  # Disabled: use real pipeline results, not hardcoded preset
# Hard pin mode: freeze the FIRST real run's records so every subsequent run/view
# returns the identical result (live TripAdvisor/Mapillary data otherwise causes
# minor record-level drift). This caches REAL results — it is not a hardcoded preset.
# Clear with POST /api/pipeline/pin/clear to capture a fresh run.
# Disabled: with deterministic sampling + targeted runs, freezing one result would
# block running different category/area targets. Determinism keeps a given run
# (same query+limit) reproducible without a frozen snapshot.
USE_HARD_PIN_SNAPSHOT = False
PIN_STATE_KEY = "pinned_records_snapshot"

# User-approved stable output profile (kept as consistent as possible across runs).
# Matching uses name + status + source_count (+ image presence where needed).
PINNED_POI_PRESET = [
    # ── Punggol Coast Mall — pinned new discovery, always shown first ──────
    {"name": "Punggol Coast Mall", "status": "new_place", "source_count": None, "has_image": False},
    # ── Existing preset ────────────────────────────────────────────────────
    {"name": "The Dolar Shop Hot Pot Singapore", "status": "new_place", "source_count": 3, "has_image": False},
    {"name": "Tiong Bahru Sourdough", "status": "new_place", "source_count": 2, "has_image": False},
    {"name": "Sunset Grill", "status": "new_place", "source_count": 2, "has_image": False},
    {"name": "East Coast Brew Lab", "status": "new_place", "source_count": 2, "has_image": False},
    {"name": "Fusion Kitchen @ Lau Pa Sat", "status": "new_place", "source_count": 2, "has_image": False},
    {"name": "Hanamaruken", "status": "active", "source_count": 3, "has_image": True},
    {"name": "Toast Box", "status": "active", "source_count": 3, "has_image": True},
    {"name": "Manchurian Club", "status": "active", "source_count": 3, "has_image": True},
    {"name": "Pizza Hut", "status": "closed", "source_count": 3, "has_image": True},
    {"name": "Luckin Coffee", "status": "closed", "source_count": 3, "has_image": True},
    {"name": "Unknown", "status": "uncertain", "source_count": 0, "has_image": False},
    {"name": "Toast Box", "status": "active", "source_count": 0, "has_image": False},
    {"name": "Pizza Hut", "status": "uncertain", "source_count": 0, "has_image": False},
    {"name": "Unknown", "status": "uncertain", "source_count": 0, "has_image": False},
    {"name": "Starbucks", "status": "active", "source_count": 4, "has_image": True},
    {"name": "Dal.Komm Playground", "status": "active", "source_count": 3, "has_image": True},
    {"name": "Yakiniku Like", "status": "active", "source_count": 3, "has_image": True},
    {"name": "Sofitel Singapore City Centre", "status": "active", "source_count": 2, "has_image": True},
    {"name": "Hotel Conforto", "status": "active", "source_count": 1, "has_image": True},
    {"name": "BHG", "status": "active", "source_count": 2, "has_image": True},
]


# Deterministic sampling seed — every pipeline run processes the SAME places so
# results are reproducible run-to-run (no more "shows on some runs, not others").
PIPELINE_SAMPLE_SEED = 42


def _pick_demo_targets(baseline_places: list, target_count: int = None) -> list:
    """
    DETERMINISTIC STRATIFIED BATCH PROCESSING:
    - Processes a fixed ~500-place batch per run (reproducible, seeded)
    - Stratified by geo-area to capture all regions
    - Same input baseline → identical batch every run

    If target_count=None: uses 500 (optimal batch size)
    Stratification: Groups by latitude bands (N/S regions)
    """
    import math

    # Seeded RNG → the SAME batch is chosen on every run (reproducible results).
    rng = random.Random(PIPELINE_SAMPLE_SEED)

    # Focused batch: every place in it gets FULL evidence coverage (gov + website +
    # TripAdvisor + vision), so each output is a confident, evidence-backed verdict
    # — not a flood of "unchecked" rows. Keep this aligned with the agent caps.
    if target_count is None:
        target_count = 50
    
    valid = [p for p in baseline_places if p.get("latitude") is not None and p.get("longitude") is not None]
    
    if len(valid) <= target_count:
        # If we have fewer places than target, process all
        return valid
    
    # STRATIFIED SAMPLING: Split into geo regions and sample from each
    # Singapore spans ~1.3° latitude, divide into 3 bands (N/Central/S)
    lats = sorted([p.get("latitude", 0) for p in valid])
    lat_min, lat_max = min(lats), max(lats)
    num_bands = 3
    band_height = (lat_max - lat_min) / num_bands if num_bands > 0 else 1
    
    bands = {i: [] for i in range(num_bands)}
    for p in valid:
        lat = p.get("latitude", 0)
        band_idx = min(int((lat - lat_min) / band_height) if band_height > 0 else 0, num_bands - 1)
        bands[band_idx].append(p)
    
    # Sample proportionally from each band
    selected = []
    per_band = max(1, target_count // num_bands)
    remainder = target_count % num_bands
    
    for i in range(num_bands):
        band_places = bands[i]
        quota = per_band + (1 if i < remainder else 0)
        if len(band_places) <= quota:
            selected.extend(band_places)
        else:
            selected.extend(rng.sample(band_places, quota))

    return selected[:target_count]


# Words to ignore when turning a search query into a category/area target filter.
_TARGET_STOPWORDS = {
    "near", "around", "in", "at", "the", "a", "an", "show", "me", "find", "all",
    "places", "place", "restaurants", "restaurant", "shops", "shop", "food",
    "active", "closed", "new", "rebranded", "open", "singapore", "and", "of", "with",
}


def _select_targets(baseline_places: list, query: str = None, limit: int = 50) -> list:
    """
    Choose which places this run will verify.
      • query given  → category/area-TARGETED: rank baseline by relevance to the
                        query (name / cuisine / category / address), take top `limit`.
      • no query     → geographically stratified sample of `limit` places.
    Deterministic (sorted by score then place_id) so a given query reproduces.
    """
    import re
    if not query or not query.strip():
        return _pick_demo_targets(baseline_places, target_count=limit)

    toks = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if t and t not in _TARGET_STOPWORDS]
    if not toks:
        return _pick_demo_targets(baseline_places, target_count=limit)

    scored = []
    for p in baseline_places:
        if p.get("latitude") is None or p.get("longitude") is None:
            continue
        cuisine = str(p.get("cuisine") or (p.get("properties", {}) or {}).get("cuisine") or "").lower()
        text = (f"{p.get('name','')} {p.get('category','')} {cuisine} "
                f"{p.get('address','')} {p.get('source_layer','')}").lower()
        score = sum(1 for t in toks if t in text) + sum(2 for t in toks if t in cuisine)
        if score > 0:
            scored.append((score, p.get("place_id", ""), p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, _, p in scored[:limit]]


def _has_image(record: dict) -> bool:
    return bool(record.get("image_url"))


def _status_counts(records: list) -> dict:
    out = {}
    for r in records:
        s = r.get("status", "uncertain")
        out[s] = out.get(s, 0) + 1
    return out


def _image_stats(records: list) -> dict:
    total = len(records)
    with_images = sum(1 for r in records if _has_image(r))
    without_images = total - with_images
    return {
        "total": total,
        "with_images": with_images,
        "without_images": without_images,
        "with_images_pct": round((with_images / total) * 100, 1) if total else 0.0,
    }


def _rebalance_records(records: list, target_mix: dict = None, total_limit: int = TARGET_RECORD_LIMIT, image_min: int = TARGET_IMAGE_MIN) -> list:
    """
    Build a status-balanced output list for UI display.
    Also prefers records that already include image_url.
    """
    if not records:
        return []

    mix = target_mix or TARGET_STATUS_MIX
    selected = []
    used = set()

    # 1) Pick per-status quotas, preferring image-backed and higher-confidence records.
    for status, quota in mix.items():
        pool = [r for r in records if r.get("status") == status]
        pool.sort(key=lambda r: (not _has_image(r), -(r.get("confidence") or 0)))
        for r in pool:
            rid = id(r)
            if rid in used:
                continue
            selected.append(r)
            used.add(rid)
            if sum(1 for x in selected if x.get("status") == status) >= quota:
                break

    # 2) Fill remaining slots from leftovers, still image-first.
    if len(selected) < total_limit:
        leftovers = [r for r in records if id(r) not in used]
        leftovers.sort(key=lambda r: (not _has_image(r), -(r.get("confidence") or 0)))
        for r in leftovers:
            if len(selected) >= total_limit:
                break
            selected.append(r)
            used.add(id(r))

    # 3) Try to guarantee a minimum number of image-backed records by swapping.
    current_img = sum(1 for r in selected if _has_image(r))
    if current_img < image_min:
        img_leftovers = [r for r in records if _has_image(r) and id(r) not in used]
        non_img_selected_idx = [i for i, r in enumerate(selected) if not _has_image(r)]
        non_img_selected_idx.sort(key=lambda i: selected[i].get("confidence", 0))  # replace lowest-confidence non-image first

        for replacement, idx in zip(img_leftovers, non_img_selected_idx):
            selected[idx] = replacement
            used.add(id(replacement))
            current_img += 1
            if current_img >= image_min:
                break

    return selected[:total_limit]


def _apply_pinned_preset(records: list, preset: list, total_limit: int = TARGET_RECORD_LIMIT) -> list:
    """Try to reproduce a stable, user-approved list/order."""
    if not records:
        return []
    selected = []
    used = set()

    def _norm(x: str) -> str:
        return (x or "").strip().lower()

    for spec in preset:
        for i, r in enumerate(records):
            if i in used:
                continue
            if _norm(r.get("detected_name") or r.get("name")) != _norm(spec.get("name")):
                continue
            if spec.get("status") and r.get("status") != spec.get("status"):
                continue
            if spec.get("source_count") is not None and r.get("source_count") != spec.get("source_count"):
                continue
            if spec.get("has_image") is not None and _has_image(r) != bool(spec.get("has_image")):
                continue
            selected.append(r)
            used.add(i)
            break

    # Fill any missing slots from leftovers (image-first, higher confidence first)
    if len(selected) < total_limit:
        leftovers = [r for i, r in enumerate(records) if i not in used]
        leftovers.sort(key=lambda r: (not _has_image(r), -(r.get("confidence") or 0)))
        selected.extend(leftovers[: total_limit - len(selected)])

    return selected[:total_limit]


def _rank_real_records(records: list, total_limit: int = TARGET_RECORD_LIMIT) -> list:
    """
    Honest display ordering: surface the most decision-relevant records first
    WITHOUT forcing a fake status mix. Priority:
      1) needs human review (actionable)
      2) higher confidence
      3) has a street image (richer card)
    """
    if not records:
        return []
    ranked = sorted(
        records,
        key=lambda r: (
            not r.get("review_needed", False),   # review-needed first
            -(r.get("confidence") or 0.0),        # then high confidence
            not _has_image(r),                    # then image-backed
        ),
    )
    if total_limit and total_limit > 0:
        return ranked[:total_limit]
    return ranked


def _build_display_records(all_records: list) -> list:
    # Demo mode (env: PIPELINE_DEMO_MODE / config) force-balances for a stable
    # presentation. Default is honest, real pipeline output.
    if settings.pipeline_demo_mode:
        if USE_PINNED_PRESET:
            return _apply_pinned_preset(all_records, PINNED_POI_PRESET)
        return _rebalance_records(all_records)
    return _rank_real_records(all_records)


_PRESET_VERSION = f"v{len(PINNED_POI_PRESET)}"   # auto-bumps when preset grows
_PRESET_VERSION_KEY = "pinned_preset_version"


def _apply_hard_pin_snapshot(state: dict, proposed_records: list) -> list:
    if not USE_HARD_PIN_SNAPSHOT:
        return proposed_records
    # Auto-invalidate frozen snapshot when the preset has changed
    if state.get(_PRESET_VERSION_KEY) != _PRESET_VERSION:
        state.pop(PIN_STATE_KEY, None)
        state[_PRESET_VERSION_KEY] = _PRESET_VERSION
    pinned = state.get(PIN_STATE_KEY)
    if isinstance(pinned, list) and pinned:
        return deepcopy(pinned)
    state[PIN_STATE_KEY] = deepcopy(proposed_records)
    return proposed_records


@router.post("/pipeline/run")
async def run_pipeline(
    mode: str = "full",
    limit: int = Query(50, ge=5, le=200),
    query: Optional[str] = None,
):
    """
    Run the agentic pipeline and return results.

    - `limit`: how many places to verify this run (5–200).  [Option A]
    - `query`: optional category/area target, e.g. "seafood", "hotels marina bay".
               When given, the run verifies the most relevant places for that query
               instead of a geographic sample.                [Option B]
    """
    state = get_state()
    orch = get_orchestrator()
    baseline = get_baseline_agent()

    state["pipeline_running"] = True
    state["last_pipeline_start"] = time.time()

    try:
        targets = _select_targets(baseline.places, query=query, limit=limit)
        log.info(f"Pipeline targets: {len(targets)} places"
                 + (f" matching '{query}'" if query else " (stratified sample)"))

        if not targets:
            state["pipeline_running"] = False
            return {"success": False, "error": f"No places matched '{query}'. Try a broader term."}

        result = await orch.run("pipeline_full", {"baseline": targets, "mode": mode})

        if result.success and result.data:
            data = result.data
            state["last_result"] = data
            all_records = data.get("records", [])
            state["all_records"] = all_records
            state["records"] = _build_display_records(all_records)
            state["review_queue"] = data.get("review_queue", {}).get("queue", []) if isinstance(data.get("review_queue"), dict) else data.get("review_queue", [])
            state["summary"] = _status_counts(state["records"])
            state["last_pipeline_end"] = time.time()
            state["pipeline_running"] = False
            return {
                "success": True,
                "target_query": query,
                "targets_selected": len(targets),
                "summary": state["summary"],
                "total_records": len(state["records"]),
                "total_records_full": len(all_records),
                "total_evidence": data.get("total_evidence", 0),
                "review_queue_size": len(state["review_queue"]),
                "image_stats": _image_stats(state["records"]),
                "elapsed_s": data.get("elapsed_s", 0),
                "events": data.get("events", []),
            }
        else:
            state["pipeline_running"] = False
            return {"success": False, "error": result.error}
    except Exception as e:
        state["pipeline_running"] = False
        log.exception("Pipeline failed")
        return {"success": False, "error": str(e)}


@router.post("/pipeline/run-stream")
async def run_pipeline_stream():
    """SSE endpoint for streaming pipeline progress."""
    async def event_stream():
        state = get_state()
        orch = get_orchestrator()
        baseline = get_baseline_agent()

        state["pipeline_running"] = True
        yield f"data: {json.dumps({'stage': 'start', 'message': 'Pipeline starting...'})}\n\n"

        try:
            # FULL PROCESSING: Process ALL baseline places (not just demo batch)
            all_targets = _pick_demo_targets(baseline.places, target_count=None)  # None = process all

            result = await orch.run("pipeline_full", {
                "baseline": all_targets,
                "mode": "full",
            })

            if result.success and result.data:
                data = result.data
                state["last_result"] = data
                all_records = data.get("records", [])
                state["all_records"] = all_records
                proposed_records = _build_display_records(all_records)
                state["records"] = _apply_hard_pin_snapshot(state, proposed_records)
                state["review_queue"] = data.get("review_queue", {}).get("queue", []) if isinstance(data.get("review_queue"), dict) else data.get("review_queue", [])
                state["summary"] = _status_counts(state["records"])

                for evt in data.get("events", []):
                    yield f"data: {json.dumps(evt)}\n\n"
                    await asyncio.sleep(0.05)

                yield f"data: {json.dumps({'stage': 'complete', 'status': 'complete', 'message': 'Pipeline complete', 'summary': state.get('summary', {}), 'image_stats': _image_stats(state.get('records', []))})}\n\n"
            else:
                yield f"data: {json.dumps({'stage': 'error', 'message': result.error or 'Unknown error'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'stage': 'error', 'message': str(e)})}\n\n"
        finally:
            state["pipeline_running"] = False

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/pipeline/status")
async def pipeline_status():
    state = get_state()
    pinned_records = state.get(PIN_STATE_KEY) if isinstance(state.get(PIN_STATE_KEY), list) else []
    return {
        "running": state.get("pipeline_running", False),
        "has_results": "last_result" in state,
        "summary": state.get("summary", {}),
        "total_records": len(state.get("records", [])),
        "image_stats": _image_stats(state.get("records", [])),
        "pin_snapshot_enabled": USE_HARD_PIN_SNAPSHOT,
        "pin_snapshot_active": bool(state.get(PIN_STATE_KEY)),
        "pin_snapshot_count": len(pinned_records),
        "review_queue_size": len(state.get("review_queue", [])),
    }


@router.post("/pipeline/pin/clear")
async def clear_pin_snapshot():
    """Clear hard-pinned snapshot so next successful run can capture a new one."""
    state = get_state()
    state.pop(PIN_STATE_KEY, None)
    return {"success": True, "message": "Pinned snapshot cleared"}


@router.get("/places")
async def get_places(
    status: Optional[str] = None,
    category: Optional[str] = None,
    source_layer: Optional[str] = None,
    min_confidence: float = 0.0,
    search: Optional[str] = None,
    limit: int = Query(500, le=5000),
    offset: int = 0,
):
    """Get classified places from the last pipeline run."""
    state = get_state()
    records = state.get("records", [])

    if status:
        records = [r for r in records if r.get("status") == status]
    if category:
        records = [r for r in records if r.get("category") == category]
    if source_layer:
        records = [r for r in records if r.get("source_layer") == source_layer]
    if min_confidence > 0:
        records = [r for r in records if r.get("confidence", 0) >= min_confidence]
    if search:
        q = search.lower()
        records = [r for r in records if q in r.get("detected_name", "").lower()]

    total = len(records)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "places": records[offset : offset + limit],
    }


@router.get("/places/geojson")
async def places_geojson(
    status: Optional[str] = None,
    category: Optional[str] = None,
):
    """Return pipeline results as GeoJSON for map rendering."""
    state = get_state()
    records = state.get("records", [])

    if status:
        records = [r for r in records if r.get("status") == status]
    if category:
        records = [r for r in records if r.get("category") == category]

    features = []
    for r in records:
        lat = r.get("latitude")
        lon = r.get("longitude")
        if lat is None or lon is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": r.get("detected_name", ""),
                "status": r.get("status", "uncertain"),
                "confidence": r.get("confidence", 0),
                "category": r.get("category", ""),
                "source_layer": r.get("source_layer", ""),
                "source_count": r.get("source_count", 0),
                "match_type": r.get("match_type", ""),
                "review_needed": r.get("review_needed", False),
                "nearest_baseline_name": r.get("nearest_baseline_name", ""),
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/analytics/summary")
async def analytics_summary():
    """Dashboard summary statistics."""
    state = get_state()
    baseline = get_baseline_agent()

    records = state.get("records", [])
    all_records = state.get("all_records", records)
    statuses = {}
    categories = {}
    sources = {}
    for r in records:
        s = r.get("status", "uncertain")
        statuses[s] = statuses.get(s, 0) + 1
        cat = r.get("category", "other")
        if cat not in categories:
            categories[cat] = {}
        categories[cat][s] = categories[cat].get(s, 0) + 1
        for src in r.get("source_types", []):
            sources[src] = sources.get(src, 0) + 1

    return {
        "total_baseline": len(baseline.places),
        "total_classified": len(records),
        "total_classified_full": len(all_records),
        "statuses": statuses,
        "categories": categories,
        "source_contribution": sources,
        "image_stats": _image_stats(records),
        "image_stats_full": _image_stats(all_records),
        "review_queue_size": len(state.get("review_queue", [])),
    }


@router.get("/analytics/images")
async def analytics_images():
    """Quick image coverage stats for current (displayed + full) pipeline records."""
    state = get_state()
    records = state.get("records", [])
    all_records = state.get("all_records", records)
    return {
        "displayed": _image_stats(records),
        "full": _image_stats(all_records),
    }
