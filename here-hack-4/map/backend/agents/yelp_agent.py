# pyre-ignore-all-errors
# ============================================================================
# Agent — Yelp Fusion API Evidence Agent (Singapore)
# ============================================================================
"""
Gathers real restaurant/business evidence from Yelp Fusion API.
Detects operational status, reviews, ratings, and closure indicators.
"""
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from backend.agents.base_agent import BaseAgent
from backend.schemas.models import SourceTypeEnum, FreshnessLabel
from backend.config import settings

log = logging.getLogger("yelp_agent")

# ── Yelp Fusion API ──────────────────────────────────────────────────────────
YELP_BASE = "https://api.yelp.com/v3"
YELP_SEARCH_URL = f"{YELP_BASE}/businesses/search"
YELP_BUSINESS_URL = f"{YELP_BASE}/businesses"
SEARCH_RADIUS_M = 100
REQUEST_TIMEOUT = 12.0


class YelpAgent(BaseAgent):
    name = "yelp_evidence"

    def _api_key(self) -> Optional[str]:
        return (
            settings.yelp_api_key if hasattr(settings, "yelp_api_key") and settings.yelp_api_key else None
        )

    async def _search_businesses(
        self,
        client: httpx.AsyncClient,
        name: str,
        lat: float,
        lng: float,
        key: str
    ) -> List[Dict[str, Any]]:
        """Search Yelp for businesses matching name + coordinates."""
        try:
            headers = {"Authorization": f"Bearer {key}"}
            params = {
                "term": name,
                "latitude": lat,
                "longitude": lng,
                "radius": SEARCH_RADIUS_M,
                "limit": 5,
            }
            resp = await client.get(YELP_SEARCH_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("businesses", [])
            else:
                log.debug(f"Yelp search failed ({resp.status_code}): {resp.text}")
                return []
        except Exception as e:
            log.debug(f"Yelp search error for '{name}': {e}")
            return []

    async def _get_business_details(
        self,
        client: httpx.AsyncClient,
        business_id: str,
        key: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed business info from Yelp."""
        try:
            headers = {"Authorization": f"Bearer {key}"}
            url = f"{YELP_BUSINESS_URL}/{business_id}"
            resp = await client.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            else:
                log.debug(f"Yelp details failed ({resp.status_code})")
                return None
        except Exception as e:
            log.debug(f"Yelp details error: {e}")
            return None

    async def execute(self, payload: Dict[str, Any]) -> List[Dict]:
        key = self._api_key()
        if not key:
            log.warning("YELP_API_KEY not set — skipping Yelp agent")
            return []

        baseline = payload.get("baseline", [])
        results = []

        async with httpx.AsyncClient() as client:
            for place in baseline[:50]:  # Limit to avoid rate-limiting
                name = place.get("name", "")
                lat = place.get("latitude")
                lng = place.get("longitude")
                category = place.get("category", "")

                if not name or lat is None or lng is None:
                    continue

                # Search Yelp
                businesses = await self._search_businesses(client, name, float(lat), float(lng), key)
                if not businesses:
                    continue

                # Pick best match
                best_match = None
                best_sim = 0.0
                for biz in businesses:
                    sim = self._name_similarity(name, biz.get("name", ""))
                    if sim > best_sim:
                        best_sim = sim
                        best_match = biz

                if not best_match or best_sim < 0.40:
                    continue

                # Get full details
                biz_id = best_match.get("id")
                details = await self._get_business_details(client, biz_id, key)
                if not details:
                    details = best_match

                # Build evidence record
                yelp_evidence = {
                    "source_type": "yelp",
                    "source_name": "Yelp Fusion API",
                    "business_id": biz_id,
                    "business_name": details.get("name", ""),
                    "latitude": details.get("coordinates", {}).get("latitude", lat),
                    "longitude": details.get("coordinates", {}).get("longitude", lng),
                    "rating": details.get("rating"),
                    "review_count": details.get("review_count", 0),
                    "is_closed": details.get("is_closed", False),
                    "phone": details.get("phone"),
                    "website": details.get("url"),
                    "business_hours": details.get("hours"),
                    "categories": [c.get("title") for c in details.get("categories", [])],
                    "address": self._format_address(details.get("location", {})),
                    "confidence": min(best_sim + 0.2, 0.95),
                    "freshness": FreshnessLabel.very_recent,  # Yelp data is live
                    "match_score": best_sim,
                    "raw_data": details,
                }

                results.append(yelp_evidence)
                log.info(f"Yelp found: {details.get('name')} (rating: {details.get('rating')}, closed: {details.get('is_closed')})")

        log.info(f"Yelp evidence: Found {len(results)} businesses")
        return results

    def _name_similarity(self, a: str, b: str) -> float:
        """Simple token overlap similarity."""
        a_tokens = set(a.lower().split())
        b_tokens = set(b.lower().split())
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = a_tokens & b_tokens
        union = a_tokens | b_tokens
        return len(intersection) / len(union) if union else 0.0

    def _format_address(self, location: Dict) -> str:
        """Format address from Yelp location object."""
        parts = []
        if location.get("address1"):
            parts.append(location["address1"])
        if location.get("city"):
            parts.append(location["city"])
        if location.get("zip_code"):
            parts.append(location["zip_code"])
        if location.get("country"):
            parts.append(location["country"])
        return ", ".join(parts)
