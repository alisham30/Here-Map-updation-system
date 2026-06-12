# pyre-ignore-all-errors
# ============================================================================
# Agent — Gov Data Agent (Data.gov.sg + ACRA Business Registries)
# ============================================================================
"""
GovDataAgent fetches ground-truth evidence directly from official Singapore sources:
1. Local ACRA Business Registry CSVs (live or cancelled entities)
2. Live endpoints from data.gov.sg (e.g. Museums, Parks, Hawkers)
"""
import ssl
import csv
import math
import re
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from backend.agents.base_agent import BaseAgent
from backend.agents._util import extract_latlng, gather_bounded, key_present
from backend.schemas.models import Coordinates
from backend.config import settings

log = logging.getLogger("gov_agent")

ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
ONEMAP_REVGEO_URL = "https://www.onemap.gov.sg/api/public/revgeocode"

# ── ACRA via the data.gov.sg datastore API (public, no key required) ─────────
# Consolidated "Entities Registered with ACRA" dataset — covers every entity with
# entity_name + uen_status_desc, so we don't need the 646MB local CSVs.
ACRA_DATASTORE_URL = "https://data.gov.sg/api/action/datastore_search"
ACRA_DATASET_ID = "d_3f960c10fed6145404ca7b821f263b87"
# NEA "List of Licensed Eating Establishments" — 36k currently-licensed F&B
# premises with full addresses. A POI whose POSTAL CODE matches a licensed
# premises is an operating F&B location → authoritative "active" for food places.
NEA_DATASET_ID = "d_227473e811b09731e64725f140b77697"
ACRA_NAME_MATCH_THRESHOLD = 0.82
# uen_status_desc buckets (lowercased).
ACRA_LIVE_STATUSES = {"registered", "live", "live company"}
ACRA_DEAD_STATUSES = {
    "deregistered", "struck off", "struck-off", "cancelled", "dissolved",
    "wound up", "in liquidation", "ceased registration", "defunct",
}
# Generic words dropped when choosing the distinctive query token.
_ACRA_GENERIC_WORDS = {
    "seafood", "restaurant", "cafe", "coffee", "bar", "kitchen", "food", "house",
    "grill", "eating", "bistro", "eatery", "noodle", "noodles", "chicken", "rice",
    "bakery", "bbq", "hotpot", "steamboat", "dim", "sum", "tea", "shop", "store",
}

# Cap official-source lookups per run so we don't flood OneMap/data.gov.sg.
MAX_GOV_PLACES = 200


def _norm_entity(s: str) -> str:
    """Normalize a business/entity name for matching (drop punctuation + legal suffixes)."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b(pte|ltd|llp|llc|private|limited|co|company|the|and)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lat2 - lat1)
    dg = math.radians(lon2 - lon1)
    a = math.sin(dl / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dg / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))

ACRA_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

class GovDataAgent(BaseAgent):
    """Fetches high-confidence ground truth from Singapore open-data sources."""
    name = "gov_data"

    def __init__(self):
        super().__init__()
        # Ensure httpx allows standard connections
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def execute(self, payload: Dict[str, Any]) -> Any:
        """Standard Agent execution entrypoint — fans out across places in parallel."""
        baseline = payload.get("baseline", [])
        sample = [b for b in baseline if b.get("name")][:MAX_GOV_PLACES]

        # One shared client for all OneMap / data.gov.sg calls in this run.
        async with httpx.AsyncClient(verify=self.ssl_context, timeout=10.0) as client:
            evidence_list = await gather_bounded(
                sample,
                lambda b: self.gather_evidence(client, b.get("name", ""), b),
                concurrency=8,
            )
        return evidence_list

    async def gather_evidence(self, client: httpx.AsyncClient, name: str, baseline_record: dict = None) -> List[Dict[str, Any]]:
        proofs = []

        # 1. ACRA registry — prefer the live data.gov.sg API; fall back to local CSVs.
        acra_evidence = await self._check_acra_api(client, name, baseline_record)
        if acra_evidence is None:
            acra_evidence = self._check_acra_registry(name)
        if acra_evidence:
            proofs.append(acra_evidence)

        # Postal code: from the baseline record, else from OneMap reverse-geocode.
        postal = re.sub(r"\D", "", str((baseline_record or {}).get("postal_code") or ""))

        # 2. OneMap — official Singapore map authority
        #    Reverse geocode the baseline coordinates to confirm what's at the location,
        #    then name-search to check if the business appears in OneMap data.
        lat, lng = extract_latlng(baseline_record) if baseline_record else (None, None)
        if lat is not None and lng is not None:
            onemap_evidence = await self._check_onemap(client, name, lat, lng)
            if onemap_evidence:
                proofs.append(onemap_evidence)
                if len(postal) != 6:
                    postal = re.sub(r"\D", "", str(onemap_evidence.get("onemap_postal") or ""))

        # 3. NEA licensed-eating-establishments — authoritative "operating" check for
        #    F&B by postal code. Confirms the place is a live licensed food premises.
        category = (baseline_record or {}).get("category", "")
        is_fb = "food" in str(category).lower() or "restaurant" in str(category).lower()
        if len(postal) == 6 and is_fb:
            nea_evidence = await self._check_nea_licence(client, name, postal)
            if nea_evidence:
                proofs.append(nea_evidence)

        # Stamp target metadata so downstream matching can attach to the baseline place.
        for p in proofs:
            p["target_place"] = name
            if baseline_record:
                p["baseline_place_id"] = baseline_record.get("place_id")
        return proofs

    async def _check_acra_api(self, client: httpx.AsyncClient, name: str,
                              baseline_record: dict = None) -> Optional[Dict[str, Any]]:
        """
        Credible ACRA lookup via the data.gov.sg datastore API.

        ACRA stores LEGAL entity names + a registered address, which often differ
        from a shop's trade name — so a name-only match is unreliable (it caused the
        earlier false closures). We make it trustworthy by corroborating with the
        registered ADDRESS:

          match_strength = name_similarity (0–1)  +  location_bonus
            • +0.30 if the POI postal code == the entity's reg_postal_code (decisive)
            • +0.12 if the registered street name appears in the POI address
          A record only counts as a confident match at strength ≥ 0.85, so we either
          match the name very closely OR match a decent name AND the location.

        Among confident matches: any LIVE entity → active; only if all are
        struck-off/deregistered → closed. Confidence reflects the match strength,
        and reliability is "very_high" only when the address corroborates.
        """
        name = (name or "").strip()
        if len(name) < 3:
            return None

        target = _norm_entity(name)
        if not target:
            return None
        target_tokens = set(target.split())

        # data.gov.sg ACRA only supports loose full-text search, so multi-word
        # queries get diluted. Query the most DISTINCTIVE token (longest non-generic
        # word) — e.g. "TungLok Seafood" → "tunglok" — which reliably surfaces the
        # entity, then fuzzy-match the full name against the results.
        non_generic = [t for t in target.split() if t not in _ACRA_GENERIC_WORDS and len(t) >= 3]
        pool = non_generic or [t for t in target.split() if len(t) >= 3] or list(target_tokens)
        query_term = max(pool, key=len) if pool else target

        headers = {}
        if key_present(settings.data_gov_sg_api_key):
            headers["x-api-key"] = settings.data_gov_sg_api_key  # used if the endpoint supports it

        try:
            resp = await client.get(
                ACRA_DATASTORE_URL,
                params={"resource_id": ACRA_DATASET_ID, "q": query_term, "limit": 100},
                headers=headers,
            )
            if resp.status_code != 200:
                return None
            records = resp.json().get("result", {}).get("records", [])
        except Exception as e:
            log.debug(f"ACRA API error for '{name}': {e}")
            return None

        target_nospace = target.replace(" ", "")

        bp = baseline_record or {}
        poi_postal = re.sub(r"\D", "", str(bp.get("postal_code") or ""))
        poi_addr = _norm_entity(bp.get("address") or "")

        confident = []
        for rec in records:
            entity = rec.get("entity_name") or ""
            ne = _norm_entity(entity)
            if not ne:
                continue
            name_score = max(
                SequenceMatcher(None, target, ne).ratio(),
                SequenceMatcher(None, target_nospace, ne.replace(" ", "")).ratio(),  # "tunglok" ~ "tung lok"
            )
            if target_tokens and target_tokens <= set(ne.split()):
                name_score = max(name_score, 0.92)
            if name_score < 0.60:
                continue  # not even plausibly the same name

            loc_bonus = 0.0
            rec_postal = re.sub(r"\D", "", str(rec.get("reg_postal_code") or ""))
            rec_street = _norm_entity(rec.get("reg_street_name") or "")
            if poi_postal and rec_postal and poi_postal == rec_postal:
                loc_bonus = 0.30
            elif poi_addr and rec_street and rec_street in poi_addr:
                loc_bonus = 0.12

            strength = name_score + loc_bonus
            if strength >= 0.85:
                confident.append({
                    "strength": round(strength, 3),
                    "name_score": round(name_score, 3),
                    "addr_matched": loc_bonus > 0,
                    "uen": rec.get("uen"),
                    "entity_name": entity,
                    "status": (rec.get("uen_status_desc") or "").strip(),
                    "postal": rec.get("reg_postal_code"),
                })

        if not confident:
            return None  # nothing we can stand behind → emit no ACRA signal

        confident.sort(key=lambda c: -c["strength"])
        live = [c for c in confident if c["status"].lower() in ACRA_LIVE_STATUSES]
        dead = [c for c in confident if c["status"].lower() in ACRA_DEAD_STATUSES]
        # A struck-off entity only counts as a CLOSURE signal when the registered
        # address also matches — a name-only struck-off match is unreliable (the
        # brand often operates under a different entity, e.g. Jumbo Seafood).
        dead_confirmed = [c for c in dead if c["addr_matched"]]

        if live:
            chosen, direction = live[0], "positive"
        elif dead_confirmed:
            chosen, direction = dead_confirmed[0], "negative"
        else:
            # Either no match, or a name-only struck-off match we won't trust.
            return None

        addr_note = " (address-confirmed)" if chosen["addr_matched"] else ""
        finding = f"ACRA registry: '{chosen['entity_name']}' — {chosen['status']}{addr_note}"
        return {
            "source_type": "acra_registry",
            # Only claim very_high when the registered address corroborates.
            "reliability": "very_high" if chosen["addr_matched"] else "high",
            "signal_direction": direction,
            "finding": finding,
            "match_confidence": chosen["strength"],
            "raw_data": {
                "source": "data.gov.sg ACRA datastore API",
                "match": chosen,
                "confident_matches": len(confident),
                "live_matches": len(live),
                "dead_matches": len(dead),
            },
        }

    async def _check_nea_licence(self, client: httpx.AsyncClient, name: str, postal: str) -> Optional[Dict[str, Any]]:
        """
        Check the NEA Licensed Eating Establishments list by POSTAL CODE. A licensed
        food premises at this address means the location is currently operating — an
        authoritative "active" signal for F&B that doesn't depend on the trade name
        (which is unreliable to match). Name match, when present, raises confidence.
        """
        try:
            resp = await client.get(
                ACRA_DATASTORE_URL,  # same datastore_search endpoint
                params={"resource_id": NEA_DATASET_ID, "q": postal, "limit": 50},
            )
            if resp.status_code != 200:
                return None
            records = resp.json().get("result", {}).get("records", [])
        except Exception as e:
            log.debug(f"NEA API error for postal {postal}: {e}")
            return None

        matched = [r for r in records
                   if postal in re.sub(r"\D", "", r.get("premises_address", "") or "")]
        if not matched:
            return None  # no licensed F&B premises at this postal code

        # Name corroboration (bonus): do the DISTINCTIVE name tokens appear in any
        # premises/licensee text? (ignore generic words like "restaurant").
        name_tokens = set(t for t in _norm_entity(name).split()
                          if t not in _ACRA_GENERIC_WORDS and len(t) >= 3)
        name_hit = False
        for r in matched:
            blob = _norm_entity(f"{r.get('premises_address','')} {r.get('licensee_name','')}")
            if name_tokens and len(name_tokens & set(blob.split())) >= max(1, len(name_tokens) // 2):
                name_hit = True
                break

        return {
            "source_type": "data_gov_sg",
            "reliability": "very_high" if name_hit else "high",
            "signal_direction": "positive",
            "finding": (f"NEA: {len(matched)} active food licence(s) at this address"
                        + (" (name matched)" if name_hit else "")),
            "raw_data": {
                "source": "NEA Licensed Eating Establishments (data.gov.sg)",
                "licences_at_postal": len(matched),
                "postal": postal,
                "name_matched": name_hit,
            },
        }

    async def _check_onemap(self, client: httpx.AsyncClient, name: str, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """
        Queries OneMap Singapore for two things:
          A) Reverse geocode at the baseline coordinates → confirms a building/address exists there.
          B) Name search → checks if this business appears in OneMap's gazetteer.

        Signal interpretation:
          • Address found nearby (revgeo) + name found     → strong positive (place exists)
          • Address found nearby but name NOT found        → neutral (building there, biz may not be listed)
          • Name found but NOT near our coordinates        → weak positive (wrong location or relocated)
          • Neither found                                  → weak closure signal (nothing at this location)
        """
        token = settings.one_map_token
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        revgeo_found = False
        revgeo_address: Optional[str] = None
        revgeo_postal: Optional[str] = None
        name_search_found = False
        name_found_nearby = False

        # ── A: Reverse geocode ──────────────────────────────────────────
        try:
            resp = await client.get(
                ONEMAP_REVGEO_URL,
                params={"location": f"{lat},{lng}", "buffer": 100, "addressType": "All", "otherFeatures": "N"},
                headers=headers,
            )
            if resp.status_code == 200:
                geo_info = resp.json().get("GeocodeInfo", [])
                if geo_info:
                    revgeo_found = True
                    g = geo_info[0]
                    revgeo_postal = g.get("POSTALCODE", "")
                    revgeo_address = f"{g.get('BLOCK', '')} {g.get('ROAD', '')} Singapore {g.get('POSTALCODE', '')}".strip()
                    log.debug(f"OneMap revgeo for ({lat},{lng}): {revgeo_address}")
        except Exception as e:
            log.debug(f"OneMap revgeo failed ({lat},{lng}): {e}")

        # ── B: Name search ──────────────────────────────────────────────
        try:
            resp = await client.get(
                ONEMAP_SEARCH_URL,
                params={"searchVal": name, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("found", 0) > 0:
                    name_search_found = True
                    # Check if any result is within 200m of our coordinates
                    for r in data.get("results", [])[:5]:
                        try:
                            r_lat = float(r.get("LATITUDE") or 0)
                            r_lng = float(r.get("LONGITUDE") or 0)
                            if r_lat and r_lng:
                                if _haversine_m(lat, lng, r_lat, r_lng) <= 200:
                                    name_found_nearby = True
                                    break
                        except Exception:
                            continue
                    log.debug(f"OneMap name search '{name}': found={name_search_found}, nearby={name_found_nearby}")
        except Exception as e:
            log.debug(f"OneMap name search failed '{name}': {e}")

        # ── Determine signal direction ──────────────────────────────────────
        if revgeo_found and name_found_nearby:
            direction = "positive"
            finding = f"OneMap confirms building exists and '{name}' found within 200m"
            reliability = "very_high"
        elif revgeo_found and name_search_found:
            direction = "positive"
            finding = f"OneMap confirms building at coordinates; '{name}' found in gazetteer (different location)"
            reliability = "high"
        elif revgeo_found and not name_search_found:
            direction = "neutral"
            finding = f"OneMap: building/address confirmed at coordinates but '{name}' not in gazetteer"
            reliability = "medium"
        elif not revgeo_found and name_search_found:
            direction = "neutral"
            finding = f"OneMap: '{name}' found in gazetteer but nothing at given coordinates"
            reliability = "medium"
        else:
            direction = "negative"
            finding = f"OneMap: nothing found at coordinates or in gazetteer for '{name}'"
            reliability = "high"

        return {
            "source_type": "onemap",
            "reliability": reliability,
            "signal_direction": direction,
            "finding": finding,
            "onemap_found": name_search_found,
            "onemap_revgeo_found": revgeo_found,
            "onemap_found_nearby": name_found_nearby,
            "onemap_address": revgeo_address,
            "onemap_postal": revgeo_postal,
            "raw_data": {
                "revgeo_found": revgeo_found,
                "name_search_found": name_search_found,
                "name_found_nearby": name_found_nearby,
                "revgeo_address": revgeo_address,
            },
        }

    def _check_acra_registry(self, name: str) -> Dict[str, Any] | None:
        """Searches local ACRA CSVs for the entity name."""
        if not ACRA_DATA_DIR.exists():
            return None

        # Determine which file to search based on first letter to be efficient
        first_letter = name.strip()[0].upper() if name.strip() else ""
        if not first_letter.isalpha():
            first_letter = "Others"

        file_path = ACRA_DATA_DIR / f"ACRA Information on Corporate Entities ('{first_letter}').csv"
        
        # Fallback if first letter file doesn't exist
        if not file_path.exists():
            file_path = ACRA_DATA_DIR / "ACRA Information on Corporate Entities ('Others').csv"
        
        if not file_path.exists():
            return None

        try:
            name_lower = name.lower()
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    return None
                
                # find indices
                name_idx = -1
                status_idx = -1
                for i, col in enumerate(header):
                    col_lower = col.lower()
                    if "entity_name" in col_lower:
                        name_idx = i
                    elif "status" in col_lower:
                        status_idx = i

                if name_idx == -1:
                    return None

                # Search through the file
                for row in reader:
                    if len(row) > name_idx:
                        row_name = row[name_idx].lower()
                        # Strict match (exact or very close)
                        if name_lower == row_name or f"{name_lower} pte" in row_name or f"{name_lower} ltd" in row_name:
                            status = row[status_idx] if status_idx != -1 and len(row) > status_idx else "Unknown"
                            
                            is_active = status.lower() in ("live", "registered")
                            
                            return {
                                "source_type": "acra_registry",
                                "reliability": "very_high",
                                "signal_direction": "positive" if is_active else "negative",
                                "finding": "ACRA Entity Match",
                                "raw_data": {"uen": row[0], "matched_name": row[name_idx], "status": status},
                            }
        except Exception as e:
            log.warning(f"Failed to read ACRA registry for {name}: {e}")
            
        return None

    async def _check_data_gov_sg(self, client: httpx.AsyncClient, name: str) -> Dict[str, Any] | None:
        """Queries Data.gov.sg API collections."""
        try:
            # Query the datasets metadata as an example (e.g. collection 1462)
            url = "https://api-production.data.gov.sg/v2/public/api/collections/1462/metadata"
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                collection_name = data.get("data", {}).get("collectionMetadata", {}).get("name", "")

                # Very simple check: if it's a museum and we're looking up a museum, add to confidence
                if "museum" in name.lower() and "Museums" in collection_name:
                    return {
                        "source_type": "data_gov_sg",
                        "reliability": "very_high",
                        "signal_direction": "positive",
                        "finding": "Verified as Official Museum in Data.gov.sg registry",
                        "raw_data": {"collection": collection_name},
                    }
        except Exception as e:
            log.warning(f"Data.gov.sg API failed for {name}: {e}")
        return None
