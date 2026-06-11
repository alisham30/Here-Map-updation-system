# pyre-ignore-all-errors
# ============================================================================
# Agent 9 — Matching Agent
# ============================================================================
"""
Attaches fresh evidence to the correct baseline place.
Handles dense Singapore urban areas with multi-signal matching:
  - coordinate proximity (Haversine)
  - name similarity (token overlap + fuzzy)
  - address similarity
  - category consistency
  - brand/domain consistency
  - sign-text consistency
  - dense-cluster disambiguation
"""
import math
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from backend.agents.base_agent import BaseAgent
from backend.config import SEARCH_RADIUS_M, MATCH_STRONG, MATCH_MODERATE, MATCH_WEAK
from backend.schemas.models import MatchResult, MatchScore, MatchType

log = logging.getLogger("matching_agent")

EARTH_R = 6_371_000


def _haversine(lat1, lon1, lat2, lon2) -> float:
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dl, dg = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dl / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dg / 2) ** 2
    return EARTH_R * 2 * math.asin(math.sqrt(a))


def _name_similarity(a: str, b: str) -> float:
    """Hybrid: token overlap + SequenceMatcher + brand normalization."""
    if not a or not b:
        return 0.0
    a_clean = re.sub(r'[^\w\s]', '', a.lower()).strip()
    b_clean = re.sub(r'[^\w\s]', '', b.lower()).strip()
    if a_clean == b_clean:
        return 1.0

    # Token overlap
    ta, tb = set(a_clean.split()), set(b_clean.split())
    if ta and tb:
        token_sim = len(ta & tb) / max(len(ta), len(tb))
    else:
        token_sim = 0.0

    # Sequence similarity
    seq_sim = SequenceMatcher(None, a_clean, b_clean).ratio()

    return max(token_sim, seq_sim)


def _normalize_sg_address(addr: str) -> str:
    addr = addr.lower()
    replacements = {
        r'\bblk\b': 'block',
        r'\bst\b': 'street',
        r'\brd\b': 'road',
        r'\bave\b': 'avenue',
        r'\blor\b': 'lorong',
        r'\bjln\b': 'jalan',
        r'\bktg\b': 'katong',
        r'\bctrl\b': 'central',
        r'#': 'unit '
    }
    for pat, repl in replacements.items():
        addr = re.sub(pat, repl, addr)
    return re.sub(r'[^\w\s]', '', addr).strip()

def _address_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a_clean = _normalize_sg_address(a)
    b_clean = _normalize_sg_address(b)
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def _category_match(cat_a: str, cat_b: str) -> float:
    if not cat_a or not cat_b:
        return 0.0
    if cat_a == cat_b:
        return 1.0
    # Partial family matches
    families = {
        "food_beverage": ["cafe", "restaurant", "bakery", "coffee", "food"],
        "retail": ["pharmacy", "grocery", "department", "shopping", "mart"],
        "accommodation": ["hotel", "hostel", "resort"],
        "recreation_tourism": ["theme", "park", "attraction", "museum"],
    }
    for fam, keywords in families.items():
        if (cat_a == fam or any(k in cat_a for k in keywords)) and \
           (cat_b == fam or any(k in cat_b for k in keywords)):
            return 0.7
    return 0.0


class MatchingAgent(BaseAgent):
    name = "matching"

    async def execute(self, payload: Dict[str, Any]) -> List[Dict]:
        baseline = payload.get("baseline", [])
        evidence_list = payload.get("evidence", [])

        # Group evidence by approximate location
        candidates = self._build_candidates(evidence_list)
        log.info(f"Matching {len(candidates)} evidence candidates against {len(baseline)} baseline places")

        results = []
        for cand in candidates:
            match = self._match_to_baseline(cand, baseline)
            results.append({
                "candidate": cand,
                "match": match,
            })

        # Summarize
        types = {}
        for r in results:
            mt = r["match"].match_type.value
            types[mt] = types.get(mt, 0) + 1
        log.info(f"Match results: {types}")

        return results

    def _build_candidates(self, evidence_list: List) -> List[Dict]:
        """Convert heterogeneous evidence objects into standardized candidates."""
        candidates = []
        for ev in evidence_list:
            if hasattr(ev, "model_dump"):
                d = ev.model_dump()
            elif isinstance(ev, dict):
                d = ev
            else:
                continue

            name = (d.get("merchant_name") or d.get("listing_name") or
                    d.get("business_name") or d.get("profile_name") or
                    d.get("extracted_name") or "")
            lat = d.get("lat") or d.get("latitude")
            lng = d.get("lng") or d.get("longitude")
            addr = d.get("address") or d.get("extracted_address") or ""
            cat = d.get("category") or d.get("extracted_category") or ""
            image_url = d.get("image_url")

            # Pull from raw_data if needed
            raw = d.get("raw_data", {})
            if not lat and "lat" in raw:
                lat = raw["lat"]
            if not lng and "lng" in raw:
                lng = raw["lng"]
            if not name and "name" in raw:
                name = raw["name"]
            if not image_url and "image_url" in raw:
                image_url = raw["image_url"]

            if name:
                candidates.append({
                    "name": name,
                    "latitude": lat,
                    "longitude": lng,
                    "address": addr,
                    "category": cat,
                    "source_type": d.get("source_type", "unknown"),
                    "brand": d.get("brand_name") or d.get("brand") or "",
                    "sign_text": d.get("sign_text") or "",
                    "image_url": image_url,
                    "evidence": d,
                })
        return candidates

    def _match_to_baseline(self, candidate: Dict, baseline: List[Dict]) -> MatchResult:
        """Find the best baseline match for a candidate."""
        clat = candidate.get("latitude")
        clon = candidate.get("longitude")

        # If no coordinates, skip spatial matching and do name-only search
        if clat is None or clon is None:
            return self._name_only_match(candidate, baseline)

        best_score = 0.0
        best_bp = None
        best_scores = MatchScore()
        best_dist = None

        for bp in baseline:
            blat, blon = bp.get("latitude"), bp.get("longitude")
            if blat is None or blon is None:
                continue

            # Quick bounding-box pre-filter (~0.001 deg ≈ 111m)
            if clat and clon:
                if abs(blat - clat) > 0.001 or abs(blon - clon) > 0.001:
                    continue
                dist = _haversine(clat, clon, blat, blon)
                if dist > SEARCH_RADIUS_M:
                    continue
                coord_score = max(0, 1.0 - (dist / SEARCH_RADIUS_M))
            else:
                dist = None
                coord_score = 0.0

            name_score = _name_similarity(candidate.get("name", ""), bp.get("name", ""))
            addr_score = _address_similarity(candidate.get("address", ""), bp.get("address", ""))
            cat_score = _category_match(candidate.get("category", ""), bp.get("category", ""))
            brand_score = _name_similarity(candidate.get("brand", ""), bp.get("brand", "")) if candidate.get("brand") and bp.get("brand") else 0.0
            sign_score = _name_similarity(candidate.get("sign_text", ""), bp.get("name", "")) if candidate.get("sign_text") else 0.0

            # Weighted composite
            composite = (
                coord_score * 0.25 +
                name_score * 0.30 +
                addr_score * 0.10 +
                cat_score * 0.15 +
                brand_score * 0.10 +
                sign_score * 0.10
            )

            if composite > best_score:
                best_score = composite
                best_bp = bp
                best_dist = dist
                best_scores = MatchScore(
                    coordinate_score=round(coord_score, 3),
                    name_score=round(name_score, 3),
                    address_score=round(addr_score, 3),
                    category_score=round(cat_score, 3),
                    brand_score=round(brand_score, 3),
                    sign_text_score=round(sign_score, 3),
                    composite=round(composite, 3),
                )

        # Classify match type.
        # Same spot + same name = same place: an exact-coordinate hit (≤~10m) with
        # a strong name match is a strong match even when the evidence lacks
        # category/address (which otherwise caps the weighted composite ~0.55).
        same_place = best_scores.coordinate_score >= 0.90 and best_scores.name_score >= 0.70
        if best_score >= MATCH_STRONG or same_place:
            match_type = MatchType.strong_match
        elif best_score >= MATCH_MODERATE:
            # Check if name is very different but location matches → potential rebrand
            if best_scores.name_score < 0.3 and best_scores.coordinate_score > 0.7:
                match_type = MatchType.possible_rebrand
            else:
                match_type = MatchType.ambiguous
        elif best_score >= MATCH_WEAK:
            match_type = MatchType.ambiguous
        else:
            match_type = MatchType.likely_new

        return MatchResult(
            candidate_id=candidate.get("name", "unknown"),
            baseline_place_id=best_bp.get("place_id") if best_bp else None,
            match_type=match_type,
            scores=best_scores,
            distance_m=round(best_dist, 1) if best_dist else None,
            matched_baseline_name=best_bp.get("name") if best_bp else None,
        )

    def _name_only_match(self, candidate: Dict, baseline: List[Dict]) -> MatchResult:
        """Fast name-only matching for candidates without coordinates."""
        cname = candidate.get("name", "").lower().split()
        if not cname:
            return MatchResult(
                candidate_id=candidate.get("name", "unknown"),
                match_type=MatchType.likely_new,
                scores=MatchScore(),
            )

        best_score = 0.0
        best_bp = None
        cname_set = set(cname)
        for bp in baseline:
            bname = bp.get("name", "").lower().split()
            if not bname:
                continue
            bname_set = set(bname)
            overlap = len(cname_set & bname_set) / max(len(cname_set), len(bname_set))
            if overlap > best_score:
                best_score = overlap
                best_bp = bp

        if best_score >= 0.8:
            match_type = MatchType.strong_match
        elif best_score >= 0.5:
            match_type = MatchType.ambiguous
        else:
            match_type = MatchType.likely_new

        # Use name_score directly as composite for name-only matches
        # (don't suppress by 0.3 — name is the only signal we have)
        return MatchResult(
            candidate_id=candidate.get("name", "unknown"),
            baseline_place_id=best_bp.get("place_id") if best_bp else None,
            match_type=match_type,
            scores=MatchScore(name_score=round(best_score, 3), composite=round(best_score, 3)),
            matched_baseline_name=best_bp.get("name") if best_bp else None,
        )
