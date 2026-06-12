# pyre-ignore-all-errors
# ============================================================================
# Agent — New-Place Discovery (NEA licensed establishments vs the baseline map)
# ============================================================================
"""
Finds NEW places: food establishments that are CURRENTLY LICENSED by NEA but are
not represented on the baseline OSM/HERE map.

Approach (real, authoritative — no guessing):
  1. Pull a sample of NEA Licensed Eating Establishments (each has a full address
     incl. 6-digit postal code).
  2. De-duplicate by premises address (a coffeeshop has many licences at one spot).
  3. Geocode each address (OneMap) → lat/lng.
  4. If NO baseline POI exists within ~60m of that point, the licensed premises is
     missing from the map → emit it as a `new_place` candidate for review.
"""
import logging
import math
import random
import re
import ssl
from typing import Any, Dict, List, Optional
import httpx

from backend.agents.base_agent import BaseAgent
from backend.agents._util import gather_bounded
from backend.config import settings

log = logging.getLogger("discovery_agent")

DATASTORE_URL = "https://data.gov.sg/api/action/datastore_search"
NEA_DATASET_ID = "d_227473e811b09731e64725f140b77697"
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

NEA_FETCH = 250          # how many licence rows to pull per run
MAX_GEOCODE = 60         # unique addresses to geocode (bounded API usage)
MAX_NEW_PLACES = 15      # cap discovered new places per run
NEARBY_RADIUS_M = 90.0   # generous: if ANY baseline POI is this close, treat as mapped
SEED = 42                # (larger radius = fewer false "new" — precision over recall)


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    r1, r2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(r1) * math.cos(r2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _clean_name(premises: str, licensee: str) -> str:
    """
    A clear LOCATION label from the premises address (the NEA trade name isn't in
    the data; the licensee is usually a person's name, which reads as junk).
    e.g. "24 SIN MING ROAD #01-51 SINGAPORE 570024" -> "24 Sin Ming Road #01-51".
    """
    p = re.sub(r"\bSINGAPORE\s+\d{6}\b", "", premises or "", flags=re.IGNORECASE)
    p = re.sub(r"\s+", " ", p).strip(" ,")
    return p.title()[:64] if p else "Licensed food premises"


class NewPlaceDiscoveryAgent(BaseAgent):
    name = "discovery"

    def __init__(self):
        super().__init__()
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def execute(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        baseline = payload.get("full_baseline") or payload.get("baseline", [])
        if not baseline:
            return []

        async with httpx.AsyncClient(verify=self.ssl_context, timeout=12.0) as client:
            # 1) Pull a (deterministic) sample of NEA licences.
            offset = random.Random(SEED).randint(0, 30000)
            try:
                resp = await client.get(DATASTORE_URL, params={
                    "resource_id": NEA_DATASET_ID, "limit": NEA_FETCH, "offset": offset,
                })
                records = resp.json().get("result", {}).get("records", []) if resp.status_code == 200 else []
            except Exception as e:
                log.warning(f"NEA fetch failed: {e}")
                return []

            # 2) De-duplicate by premises address (skip suspended licences).
            seen, uniques = set(), []
            for r in records:
                addr = (r.get("premises_address") or "").strip()
                postal_m = re.search(r"\b(\d{6})\b", addr)
                if not addr or not postal_m:
                    continue
                key = re.sub(r"\s+", " ", addr.upper())
                if key in seen:
                    continue
                seen.add(key)
                uniques.append({
                    "address": addr,
                    "postal": postal_m.group(1),
                    "name": _clean_name(addr, r.get("licensee_name", "")),
                })
                if len(uniques) >= MAX_GEOCODE:
                    break

            # 3) Geocode each unique address and 4) check baseline proximity.
            async def _check(u: Dict) -> Optional[Dict]:
                lat, lng = await self._geocode(client, u["postal"], u["address"])
                if lat is None:
                    return None
                # Already on the map?
                for bp in baseline:
                    blat, blng = bp.get("latitude"), bp.get("longitude")
                    if blat is None or blng is None:
                        continue
                    if abs(blat - lat) > 0.001 or abs(blng - lng) > 0.001:
                        continue
                    if _haversine_m(lat, lng, blat, blng) <= NEARBY_RADIUS_M:
                        return None  # a baseline POI is right here → not new
                return {
                    "detected_name": u["name"],
                    "latitude": lat,
                    "longitude": lng,
                    "address": u["address"],
                    "category": "food_beverage",
                    "source_layer": "nea_licensed",
                    "match_type": "likely_new",
                    "match_score": 0.0,
                    "source_types": ["data_gov_sg"],
                    "source_count": 1,
                    "status": "new_place",
                    "confidence": 0.7,
                    "freshness": "very_recent",
                    "review_needed": True,
                    "review_reason": (f"NEA-licensed food premises at '{u['address']}' has no POI "
                                      f"on the baseline map — candidate new place to add."),
                    "gov_confirmed_active": True,
                    "model": "new_place_confidence",
                    "model_score": 0.7,
                    "signal_breakdown": [{
                        "key": "nea_unmapped", "label": "NEA-licensed food premises missing from the map",
                        "weight": 0.5, "direction": "support", "source": "data_gov_sg",
                        "reliability": "very_high",
                        "detail": f"Official NEA licence active at '{u['address']}', but no POI exists here on the baseline map.",
                    }],
                }

            found = await gather_bounded(uniques, _check, concurrency=6)

        found = found[:MAX_NEW_PLACES]
        # Attach faithful XAI to each discovered place.
        from backend.explainability.explanation_generator import generate_explanation
        for rec in found:
            try:
                rec["xai_explanation"] = generate_explanation(rec)
            except Exception as e:
                log.debug(f"XAI for discovered '{rec.get('detected_name')}' failed: {e}")
                rec["xai_explanation"] = None
        log.info(f"Discovery: {len(found)} NEA-licensed premises missing from the baseline map")
        return found

    async def _geocode(self, client: httpx.AsyncClient, postal: str, address: str):
        """Postal → lat/lng via OneMap search."""
        token = settings.one_map_token
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            resp = await client.get(ONEMAP_SEARCH_URL, params={
                "searchVal": postal, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1,
            }, headers=headers)
            if resp.status_code != 200:
                return (None, None)
            for r in resp.json().get("results", [])[:1]:
                lat = float(r.get("LATITUDE") or 0)
                lng = float(r.get("LONGITUDE") or 0)
                if lat and lng:
                    return (lat, lng)
        except Exception as e:
            log.debug(f"OneMap geocode failed for {postal}: {e}")
        return (None, None)
