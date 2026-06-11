# pyre-ignore-all-errors
# ============================================================================
# Shared agent utilities — coordinate extraction + bounded parallel fan-out
# ============================================================================
"""
Small helpers used across evidence agents so behaviour is consistent:

  * extract_latlng(place) — baseline places use flat latitude/longitude keys,
    but some records nest them under "coordinates". This reads both safely.
  * gather_bounded(...)   — run an async worker over many items concurrently
    with a concurrency cap (semaphore), so we get parallel API calls without
    hammering third-party rate limits.
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypeVar

log = logging.getLogger("agent_util")

T = TypeVar("T")
R = TypeVar("R")


def key_present(value: Optional[str]) -> bool:
    """
    True only if `value` looks like a real API key — not None, empty, or one of
    the placeholder strings left in .env templates (e.g. 'your_..._here').
    """
    if not value or not str(value).strip():
        return False
    v = str(value).strip().lower()
    if v.startswith("your_") or v.endswith("_here"):
        return False
    if v in {"none", "null", "changeme", "placeholder", "todo"}:
        return False
    return True


def extract_latlng(place: Any) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (lat, lng) from a place that may be a dict (flat or nested) or a
    Pydantic model. Returns (None, None) when coordinates are missing/invalid.
    """
    lat = lng = None
    if isinstance(place, dict):
        lat = place.get("latitude")
        lng = place.get("longitude")
        if lat is None or lng is None:
            coords = place.get("coordinates")
            if isinstance(coords, dict):
                lat = lat if lat is not None else coords.get("latitude")
                lng = lng if lng is not None else coords.get("longitude")
            elif coords is not None:
                lat = lat if lat is not None else getattr(coords, "latitude", None)
                lng = lng if lng is not None else getattr(coords, "longitude", None)
    else:
        lat = getattr(place, "latitude", None)
        lng = getattr(place, "longitude", None)
        coords = getattr(place, "coordinates", None)
        if (lat is None or lng is None) and coords is not None:
            lat = lat if lat is not None else getattr(coords, "latitude", None)
            lng = lng if lng is not None else getattr(coords, "longitude", None)

    try:
        return (float(lat), float(lng)) if lat is not None and lng is not None else (None, None)
    except (TypeError, ValueError):
        return (None, None)


async def gather_bounded(
    items: List[T],
    worker: Callable[[T], Awaitable[Optional[R]]],
    concurrency: int = 8,
) -> List[R]:
    """
    Apply `worker` to every item with at most `concurrency` running at once.
    Exceptions and None results are dropped; successful results are flattened
    if a worker returns a list. Order is not guaranteed.
    """
    if not items:
        return []
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _run(item: T):
        async with sem:
            try:
                return await worker(item)
            except Exception as e:  # fault isolation per item
                log.debug(f"worker failed for item: {e}")
                return None

    raw = await asyncio.gather(*[_run(i) for i in items])
    out: List[R] = []
    for r in raw:
        if r is None:
            continue
        if isinstance(r, list):
            out.extend(r)
        else:
            out.append(r)
    return out
