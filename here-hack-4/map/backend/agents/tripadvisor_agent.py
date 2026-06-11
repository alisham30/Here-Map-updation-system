# pyre-ignore-all-errors
# ============================================================================
# Agent — TripAdvisor Real-Time Review Evidence Agent
# ============================================================================
"""
Queries the TripAdvisor Content API to gather real-time review evidence.

Key behaviours:
  • Searches TripAdvisor by name + lat/lng for each baseline place
  • Fuzzy-matches returned location names against the baseline name
    (difflib SequenceMatcher — no extra dependencies)
  • Fetches the latest reviews for every matched location
  • Applies recency weighting: the newer the review the higher the weight
  • Computes a final confidence score that blends:
      name_match_score × recency_boost × rating_signal
  • Permanently-closed flags from TripAdvisor immediately lower confidence
"""

import logging
import math
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
import httpx

from backend.agents.base_agent import BaseAgent
from backend.agents._util import extract_latlng, gather_bounded
from backend.schemas.models import (
    FreshnessLabel,
    SourceTypeEnum,
    TripAdvisorEvidence,
    TripAdvisorReview,
)
from backend.config import settings

log = logging.getLogger("tripadvisor_agent")

# ── TripAdvisor Content API base ─────────────────────────────────────────────
TA_BASE = "https://api.content.tripadvisor.com/api/v1"
SEARCH_RADIUS_M = 100          # metres around the baseline coordinate
MAX_REVIEWS_PER_LOCATION = 10  # TripAdvisor free tier returns up to 5; paid up to 10
REQUEST_TIMEOUT = 12.0

# ── Recency weight table (age in days → weight) ───────────────────────────────
# Reviews from the last 30 days are treated as "ground truth".
# Weight decays smoothly beyond that using a half-life of ~180 days.
def _recency_weight(age_days: int) -> float:
    """Exponential decay: weight = exp(-λ · age_days), λ = ln(2)/180."""
    if age_days <= 0:
        return 1.0
    half_life = 180.0
    lam = math.log(2) / half_life
    w = math.exp(-lam * age_days)
    return round(max(w, 0.05), 4)   # floor at 0.05 — even old reviews count a little


# ── Name fuzzy-match ──────────────────────────────────────────────────────────
def _fuzzy_score(a: str, b: str) -> float:
    """
    Symmetric token-sort fuzzy ratio (0–1).
    Sorts tokens before comparison so "Café ABC" ~ "ABC Café".
    """
    def _norm(s: str) -> str:
        return " ".join(sorted(s.lower().split()))

    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


# ── Freshness label from age ──────────────────────────────────────────────────
def _freshness(latest_review_date: Optional[str]) -> FreshnessLabel:
    if not latest_review_date:
        return FreshnessLabel.stale
    try:
        dt = datetime.fromisoformat(latest_review_date.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).days
        if age <= 30:
            return FreshnessLabel.very_recent
        if age <= 90:
            return FreshnessLabel.recent
        if age <= 365:
            return FreshnessLabel.moderate
        return FreshnessLabel.stale
    except Exception:
        return FreshnessLabel.stale


class TripAdvisorAgent(BaseAgent):
    name = "tripadvisor_evidence"

    # ── helpers ───────────────────────────────────────────────────────────────

    def _api_key(self) -> Optional[str]:
        # Prefer runtime env-var override, fall back to config/settings
        return (
            os.environ.get("TRIPADVISOR_API_KEY")
            or (settings.tripadvisor_api_key if hasattr(settings, "tripadvisor_api_key") else None)
        )

    async def _search_location(
        self,
        client: httpx.AsyncClient,
        name: str,
        lat: float,
        lng: float,
        category: str,
        key: str,
    ) -> List[Dict]:
        """Search TripAdvisor for a location near lat/lng by name."""
        # Map internal categories to TripAdvisor category filter
        ta_cat = _map_category(category)
        params: Dict[str, Any] = {
            "key": key,
            "searchQuery": name,
            "latLong": f"{lat},{lng}",
            "radius": SEARCH_RADIUS_M,
            "radiusUnit": "m",
            "language": "en",
        }
        if ta_cat:
            params["category"] = ta_cat

        try:
            resp = await client.get(f"{TA_BASE}/location/search", params=params,
                                    timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except httpx.HTTPStatusError as e:
            log.warning(f"TA search HTTP {e.response.status_code} for '{name}'")
            return []
        except Exception as e:
            log.warning(f"TA search error for '{name}': {e}")
            return []

    async def _fetch_reviews(
        self,
        client: httpx.AsyncClient,
        location_id: str,
        key: str,
    ) -> List[Dict]:
        """Fetch the most recent reviews for a location."""
        params = {"key": key, "language": "en"}
        try:
            resp = await client.get(
                f"{TA_BASE}/location/{location_id}/reviews",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])[:MAX_REVIEWS_PER_LOCATION]
        except Exception as e:
            log.warning(f"TA reviews error for location {location_id}: {e}")
            return []

    async def _fetch_details(
        self,
        client: httpx.AsyncClient,
        location_id: str,
        key: str,
    ) -> Dict:
        """Fetch full details (address, rating, closed status) for a location."""
        params = {"key": key, "language": "en", "currency": "SGD"}
        try:
            resp = await client.get(
                f"{TA_BASE}/location/{location_id}/details",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.warning(f"TA details error for location {location_id}: {e}")
            return {}

    # ── core logic ────────────────────────────────────────────────────────────

    def _build_evidence(
        self,
        baseline_name: str,
        ta_location: Dict,
        details: Dict,
        raw_reviews: List[Dict],
        lat: float = None,
        lng: float = None,
    ) -> TripAdvisorEvidence:
        """
        Convert TripAdvisor API data → TripAdvisorEvidence with:
          - name fuzzy match score
          - per-review recency weighting
          - blended confidence
        """
        ta_name = ta_location.get("name", "")
        location_id = ta_location.get("location_id", "")

        # ── Name fuzzy match ──
        name_match = _fuzzy_score(baseline_name, ta_name)

        # ── Parse reviews with recency weights ──
        today = datetime.now(timezone.utc)
        parsed_reviews: List[TripAdvisorReview] = []
        for rv in raw_reviews:
            pub = rv.get("published_date") or rv.get("created_time") or ""
            age_days = 9999
            if pub:
                try:
                    dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    age_days = max((today - dt).days, 0)
                except Exception:
                    pass
            w = _recency_weight(age_days)
            parsed_reviews.append(TripAdvisorReview(
                review_id=str(rv.get("id", "")),
                title=rv.get("title"),
                text=rv.get("text"),
                rating=int(rv.get("rating", 0)),
                published_date=pub or None,
                age_days=age_days,
                recency_weight=w,
            ))

        # Sort newest-first
        parsed_reviews.sort(key=lambda r: r.age_days)

        # ── Weighted average rating ──
        weighted_avg: Optional[float] = None
        if parsed_reviews:
            total_w = sum(r.recency_weight for r in parsed_reviews)
            if total_w > 0:
                weighted_avg = round(
                    sum(r.rating * r.recency_weight for r in parsed_reviews) / total_w, 2
                )

        # ── Recency boost: fraction of reviews from last 90 days ──
        recent_90 = [r for r in parsed_reviews if r.age_days <= 90]
        recency_boost = round(len(recent_90) / max(len(parsed_reviews), 1), 3)

        # ── Latest review date ──
        latest_date = parsed_reviews[0].published_date if parsed_reviews else None

        # ── Freshness label ──
        freshness = _freshness(latest_date)

        # ── Closed / active status ──
        is_permanently_closed = bool(details.get("is_permanently_closed", False))
        is_active = not is_permanently_closed

        # ── Overall rating from details ──
        ta_rating = None
        raw_rating = details.get("rating") or ta_location.get("rating")
        if raw_rating is not None:
            try:
                ta_rating = float(raw_rating)
            except (TypeError, ValueError):
                pass

        review_count = int(details.get("num_reviews") or ta_location.get("num_reviews") or 0)

        # ── Composite confidence ─────────────────────────────────────────────
        # Base: name match (0–1)
        # Recency boost adds up to +0.15 if lots of fresh reviews
        # Rating signal: 0.8–1.0 normalised from 1–5
        # Permanently closed immediately drops to 0.05
        if is_permanently_closed:
            confidence = 0.05
        else:
            rating_signal = ((ta_rating or 3.0) - 1.0) / 4.0 * 0.2 + 0.8  # 0.8–1.0
            confidence = round(
                min(name_match * (0.85 + recency_boost * 0.15) * rating_signal, 0.98),
                3,
            )

        # ── Address ──
        address = (
            details.get("address_obj", {}).get("address_string")
            or ta_location.get("address_obj", {}).get("address_string")
        )
        category = (
            details.get("category", {}).get("name")
            or ta_location.get("category", {}).get("name")
        )

        return TripAdvisorEvidence(
            source_type=SourceTypeEnum.tripadvisor,
            source_url=f"https://www.tripadvisor.com/Restaurant_Review-d{location_id}",
            confidence=confidence,
            freshness=freshness,
            location_id=location_id,
            listing_name=ta_name,
            address=address,
            category=category,
            rating=ta_rating,
            review_count=review_count,
            is_permanently_closed=is_permanently_closed,
            is_active=is_active,
            name_match_score=round(name_match, 4),
            weighted_avg_rating=weighted_avg,
            latest_review_date=latest_date,
            recency_boost=recency_boost,
            reviews=parsed_reviews,
            raw_data={
                "ta_location": ta_location,
                "details": details,
                # Carry the searched coordinates so matching can place this
                # evidence spatially (not name-only) and the fused record has
                # real coordinates for the map / fly-to.
                "lat": lat,
                "lng": lng,
                "name": baseline_name,
            },
        )

    # ── execute ───────────────────────────────────────────────────────────────

    async def execute(self, payload: Dict[str, Any]) -> List[TripAdvisorEvidence]:
        key = self._api_key()
        if not key:
            log.warning("TRIPADVISOR_API_KEY not set — skipping TripAdvisor agent")
            return []

        baseline_places = payload.get("baseline", [])

        # Process the whole focused batch so every place gets a TripAdvisor check.
        sample = baseline_places[:200]

        async with httpx.AsyncClient() as client:

            async def _process(place) -> Optional[TripAdvisorEvidence]:
                # Coordinates: baseline uses flat latitude/longitude; tolerate nested too.
                lat, lng = extract_latlng(place)
                name = place.get("name", "") if isinstance(place, dict) else getattr(place, "name", "")
                category = place.get("category", "") if isinstance(place, dict) else getattr(place, "category", "")
                if not name or lat is None or lng is None:
                    return None

                # 1. Search TripAdvisor
                candidates = await self._search_location(client, name, lat, lng, category, key)
                if not candidates:
                    log.debug(f"No TA results for '{name}'")
                    return None

                # 2. Pick best fuzzy-matched candidate (score ≥ 0.40 threshold)
                best_candidate, best_score = _best_match(name, candidates)
                if best_candidate is None or best_score < 0.40:
                    log.debug(f"No good TA match for '{name}' (best={best_score:.2f})")
                    return None

                location_id = best_candidate.get("location_id", "")
                log.info(
                    f"TA match '{name}' → '{best_candidate.get('name')}' "
                    f"(fuzzy={best_score:.2f}, id={location_id})"
                )

                # 3. Fetch details + reviews in parallel
                details, raw_reviews = await _parallel_fetch(
                    client, location_id, key, self._fetch_details, self._fetch_reviews
                )

                # 4. Build evidence record (carry search coords for spatial matching)
                return self._build_evidence(name, best_candidate, details, raw_reviews, lat, lng)

            # Fan out across places concurrently (bounded to respect TA rate limits)
            results = await gather_bounded(sample, _process, concurrency=6)

        log.info(f"TripAdvisor evidence: {len(results)} matched locations")
        return results


# ── Module-level helpers ──────────────────────────────────────────────────────

def _map_category(internal_cat: str) -> str:
    """Map internal category strings to TripAdvisor category filter values."""
    cat = internal_cat.lower()
    if any(k in cat for k in ("restaurant", "food", "cafe", "hawker", "kopitiam", "bar")):
        return "restaurants"
    if any(k in cat for k in ("hotel", "hostel", "resort", "accommodation")):
        return "hotels"
    if any(k in cat for k in ("attraction", "museum", "park", "theme")):
        return "attractions"
    return ""  # No filter — broadest search


def _best_match(name: str, candidates: List[Dict]) -> Tuple[Optional[Dict], float]:
    """Return the candidate with the highest fuzzy name score."""
    best: Optional[Dict] = None
    best_score = 0.0
    for c in candidates:
        score = _fuzzy_score(name, c.get("name", ""))
        if score > best_score:
            best_score = score
            best = c
    return best, best_score


async def _parallel_fetch(
    client: httpx.AsyncClient,
    location_id: str,
    key: str,
    fetch_details_fn,
    fetch_reviews_fn,
) -> Tuple[Dict, List[Dict]]:
    """Fetch details and reviews concurrently."""
    import asyncio
    details_task = asyncio.create_task(fetch_details_fn(client, location_id, key))
    reviews_task = asyncio.create_task(fetch_reviews_fn(client, location_id, key))
    details, reviews = await asyncio.gather(details_task, reviews_task)
    return details, reviews
