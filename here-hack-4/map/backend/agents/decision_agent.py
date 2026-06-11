# pyre-ignore-all-errors
# ============================================================================
# Agent 11 — Decision Agent
# ============================================================================
"""
Classifies each fused record into:
  - Active         (confirmed existing, evidence consistent)
  - New Place      (not in baseline, strong new evidence)
  - Closed         (baseline exists, no operational evidence)
  - Rebranded      (same location, different name/brand)
  - Uncertain      (conflicting or insufficient evidence)

Also computes confidence and decides if human review is needed.
"""
import logging
import math
from typing import Any, Dict, List
from backend.agents.base_agent import BaseAgent
from backend.config import MATCH_STRONG, MATCH_MODERATE


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    r1, r2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))

log = logging.getLogger("decision_agent")

# Closure decision thresholds (on the weighted closure score, 0..1).
# CLOSED_THRESHOLD is intentionally below 0.75 so that a real cluster of agreeing
# signals (e.g. ACRA struck-off + dead website + absent from OneMap = 0.65) is
# surfaced as "closed" for review, instead of being buried as "uncertain".
CLOSED_THRESHOLD = 0.60
UNCERTAIN_CLOSURE = 0.40

# When False, baseline places with no fresh evidence are NOT emitted as "uncertain"
# placeholders — the platform only outputs evidence-backed predictions.
EMIT_UNASSESSED = False


def _closure_reason(record: Dict) -> str:
    """Build a human-readable reason string from whichever closure signals fired."""
    reasons = []
    if record.get("ta_permanently_closed"):
        reasons.append("TripAdvisor marks permanently closed")
    if record.get("gov_status_negative"):
        reasons.append("ACRA/Gov registry shows cancelled entity")
    ta_recency = record.get("ta_recency_boost")
    ta_count = record.get("ta_review_count") or 0
    if ta_recency is not None and ta_count > 0 and ta_recency < 0.15:
        reasons.append("TripAdvisor reviews have dried up (no recent activity)")
    if record.get("onemap_found") is False and record.get("onemap_revgeo_found") is False:
        reasons.append("OneMap finds no record at this location")
    if record.get("website_state") in ("inactive", "parked"):
        reasons.append("website inactive")
    if record.get("discussion_sentiment") == "negative":
        reasons.append("negative community discussion")
    if not reasons:
        reasons.append("multiple weak signals suggest permanent closure")
    return "; ".join(reasons)


class DecisionAgent(BaseAgent):
    name = "decision"

    async def execute(self, payload: Dict[str, Any]) -> List[Dict]:
        records = payload.get("records", [])
        baseline = payload.get("baseline", [])
        results = []

        for record in records:
            classified = self._classify(record, baseline)
            results.append(classified)

        # Baseline places with NO fresh evidence are "not assessed", not predictions.
        # A map-update platform should only output verdicts it has evidence for, so
        # by default we do NOT flood the output with unchecked "uncertain" rows.
        evidenced_baselines = {r.get("baseline_place_id") for r in records if r.get("baseline_place_id")}

        closure_candidates = []
        for bp in (baseline if EMIT_UNASSESSED else []):
            if bp.get("place_id") not in evidenced_baselines:
                # No fresh evidence for this baseline place → high closure probability
                bp_lat = bp.get("latitude")
                bp_lng = bp.get("longitude")
                
                # Compute area density to assess if silence is suspicious
                nearby_count = self._area_density(bp_lat, bp_lng, baseline, radius_m=300.0) if bp_lat and bp_lng else 0
                
                # ── Absence of evidence is NOT evidence of closure ──────────────
                # A baseline place with no fresh signal in THIS run is always
                # classified "uncertain" and queued for review — never auto-closed.
                # Area density only sets review PRIORITY (how suspicious the silence
                # is), not a closure verdict. This prevents fabricating closures from
                # places that simply weren't covered by the evidence sample.
                if nearby_count >= 8:
                    review_priority_score = 0.45  # dense area, silence is notable
                    review_reason = (f"No fresh evidence for '{bp.get('name', '')}' in a dense commercial area "
                                     f"({nearby_count} places within 300m) — verify whether it has closed.")
                elif nearby_count >= 4:
                    review_priority_score = 0.35
                    review_reason = (f"No operational signals detected for '{bp.get('name', '')}' "
                                     f"({nearby_count} places within 300m) — possible closure or coverage gap.")
                else:
                    review_priority_score = 0.25
                    review_reason = (f"No fresh evidence found for '{bp.get('name', '')}' — "
                                     f"likely a coverage gap in this run; closure not established.")

                closure_candidates.append({
                    "detected_name": bp.get("name", ""),
                    "latitude": bp_lat,
                    "longitude": bp_lng,
                    "address": bp.get("address"),
                    "category": bp.get("category"),
                    "source_layer": bp.get("source_layer"),
                    "baseline_place_id": bp.get("place_id"),
                    "match_type": "strong_match",
                    "match_score": 1.0,
                    "nearest_baseline_name": bp.get("name"),
                    "source_types": ["baseline_only"],
                    "source_count": 0,
                    "status": "uncertain",          # never auto-"closed" from silence
                    "confidence": review_priority_score,
                    "freshness": "stale",
                    "review_needed": True,
                    "review_reason": review_reason,
                    "website_state": None,
                    "delivery_available": None,
                    "social_active": None,
                    "visual_state": None,
                    "discussion_sentiment": None,
                })

        # Rank by how suspicious the silence is (dense-area gaps first) for review.
        closure_candidates.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        from backend.explainability.explanation_generator import generate_explanation
        for cc in closure_candidates:
            try:
                cc["xai_explanation"] = generate_explanation(cc)
            except Exception as e:
                log.debug(f"XAI for baseline-only '{cc.get('detected_name')}' failed: {e}")
                cc["xai_explanation"] = None
        results.extend(closure_candidates)

        # Summary
        statuses = {}
        for r in results:
            s = r.get("status", "uncertain")
            statuses[s] = statuses.get(s, 0) + 1
        log.info(f"Decision results: {statuses}")

        return results

    def _closure_signals(self, record: Dict) -> List[Dict[str, Any]]:
        """
        Single source of truth for the closure model. Returns the list of signals
        that ACTUALLY fired, each with its signed weight. The XAI layer reads this
        same list, so every explanation is faithful to the score by construction.

        weight > 0 pushes toward CLOSED, weight < 0 pushes toward OPEN.

        Street-level vision now carries MEASURED weight, but only on explicit
        signage: a written "Permanently Closed / For Rent" notice counts toward
        closure (+0.15); a clearly operating shopfront counts weakly toward open
        (-0.05). A merely pulled-down shutter still scores 0 (the visual_agent
        only sets visual_state='closed' when it reads explicit closure text).
        A DIFFERENT business name on the sign is handled as a REBRAND, not here.
        """
        signals: List[Dict[str, Any]] = []

        def add(key, label, weight, source, reliability, detail):
            signals.append({
                "key": key, "label": label, "weight": round(weight, 3),
                "direction": "closure" if weight > 0 else "open",
                "source": source, "reliability": reliability, "detail": detail,
            })

        # ── Authoritative closure ──────────────────────────────────────────
        if record.get("ta_permanently_closed") is True:
            add("ta_permanently_closed", "TripAdvisor marks permanently closed",
                0.45, "tripadvisor", "very_high",
                "TripAdvisor's crowd-moderated permanent-closure flag is set.")
        if record.get("gov_status_negative") is True:
            add("gov_cancelled", "ACRA/Gov registry shows entity cancelled",
                0.40, "acra_registry", "very_high",
                "Official Singapore registry lists this entity as struck off / cancelled.")

        # ── Review activity decay ──────────────────────────────────────────
        ta_recency = record.get("ta_recency_boost")
        ta_count = record.get("ta_review_count") or 0
        if ta_recency is not None and ta_count > 0:
            if ta_recency < 0.05:
                add("ta_no_recent", "TripAdvisor reviews have dried up",
                    0.20, "tripadvisor", "high",
                    f"{ta_count} reviews exist but none are recent (recency={ta_recency}).")
            elif ta_recency < 0.15:
                add("ta_low_recent", "TripAdvisor review activity has slowed",
                    0.10, "tripadvisor", "high",
                    f"Only a small fraction of {ta_count} reviews are recent (recency={ta_recency}).")

        if record.get("website_state") in ("inactive", "parked"):
            add("website_down", f"Official website is {record.get('website_state')}",
                0.10, "official_website", "high",
                "The official site is no longer served / has been parked.")
        if record.get("discussion_sentiment") == "negative":
            add("forum_negative", "Negative community discussion",
                0.08, "reddit", "medium",
                "Recent Reddit chatter about this place is negative / closure-leaning.")
        if record.get("delivery_available") is False:
            add("delivery_absent", "Not listed on delivery platforms",
                0.05, "grabfood", "low",
                "No active delivery listing (weak — many places skip delivery apps).")
        if record.get("social_active") is False:
            add("social_dormant", "Social media dormant",
                0.05, "social_media", "low",
                "Social account exists but has gone quiet.")

        # ── Street-level vision (explicit signage only) ────────────────────
        vs = record.get("visual_state")
        if vs == "closed":  # set only on explicit written closure text, not shutters
            add("visual_closure_text", "Storefront sign shows an explicit closure notice",
                0.15, "visual_street", "medium",
                "GPT-4o read a written closure / 'For Rent' notice on the storefront sign.")
        elif vs == "open":
            add("visual_open", "Street photo shows the shopfront operating",
                -0.05, "visual_street", "low",
                "Street imagery shows the named business open and operating.")

        # ── OneMap official map ────────────────────────────────────────────
        onemap_found = record.get("onemap_found")
        onemap_revgeo = record.get("onemap_revgeo_found")
        onemap_nearby = record.get("onemap_found_nearby")
        if onemap_found is False and onemap_revgeo is False:
            add("onemap_absent", "OneMap finds nothing at this location",
                0.15, "onemap", "high",
                "Neither reverse-geocode nor name search returns a record in official SG data.")

        # ── OPEN signals (subtract) ────────────────────────────────────────
        if record.get("ta_is_active") is True and record.get("ta_permanently_closed") is not True:
            add("ta_active", "TripAdvisor listing is active",
                -0.15, "tripadvisor", "high",
                "TripAdvisor shows the location as operating.")
        if record.get("gov_confirmed_active") is True:
            add("gov_active", "ACRA/Gov confirms active registration",
                -0.20, "acra_registry", "very_high",
                "Official registry confirms a live, valid registration.")
        if onemap_nearby is True:
            add("onemap_nearby", "OneMap confirms business at this location",
                -0.15, "onemap", "very_high",
                "OneMap finds this name within 200m of the recorded coordinates.")
        if record.get("delivery_available") is True:
            add("delivery_active", "Active delivery listing",
                -0.20, "grabfood", "medium_high",
                "An active delivery merchant listing is strong real-time proof of operation.")
        if record.get("website_state") == "active":
            add("website_active", "Official website is live",
                -0.10, "official_website", "high",
                "The official site is live and being served.")

        return signals

    def _closure_score(self, record: Dict) -> float:
        """Weighted closure probability (0.0 = open, 1.0 = closed), clamped."""
        score = sum(s["weight"] for s in self._closure_signals(record))
        return max(0.0, min(1.0, round(score, 3)))

    def _newplace_signals(self, record: Dict, nearby_count: int) -> List[Dict[str, Any]]:
        """Faithful breakdown of the new-place confidence build-up (all support 'new_place')."""
        signals: List[Dict[str, Any]] = []

        def add(key, label, weight, source, reliability, detail):
            signals.append({
                "key": key, "label": label, "weight": round(weight, 3),
                "direction": "support", "source": source,
                "reliability": reliability, "detail": detail,
            })

        add("base_new", "Not found in OSM/HERE baseline", 0.50, "baseline_geojson", "high",
            "No strong baseline match — consistent with a newly opened place.")
        sc = record.get("source_count", 0)
        if sc >= 3:
            add("multi_source", f"{sc} independent sources confirm existence", 0.20, "", "high",
                f"{sc} distinct evidence sources corroborate this location.")
        elif sc >= 2:
            add("two_source", f"{sc} independent sources confirm existence", 0.10, "", "medium_high",
                f"{sc} distinct evidence sources corroborate this location.")
        if record.get("delivery_available"):
            add("delivery_active", "Active delivery listing", 0.10, "grabfood", "medium_high",
                "Listed and accepting orders on a delivery platform.")
        if record.get("website_state") == "active":
            add("website_active", "Official website is live", 0.10, "official_website", "high",
                "A live official site backs the new listing.")
        if record.get("discussion_sentiment") == "positive":
            add("forum_positive", "Positive community discussion", 0.05, "reddit", "medium",
                "Recent Reddit chatter is positive / opening-related.")
        if record.get("visual_state") == "open":
            add("visual_open", "Storefront photo appears open", 0.05, "visual_street", "low",
                "Street imagery shows an operating storefront (informational).")
        if nearby_count >= 5:
            add("dense_area", f"High-density commercial area ({nearby_count} within 200m)", 0.15, "", "medium",
                "Surrounded by active POIs — a real new place is likely.")
        elif nearby_count >= 3:
            add("moderate_area", f"Moderate-density area ({nearby_count} within 200m)", 0.08, "", "medium",
                "Some commercial activity nearby.")
        if record.get("onemap_found_nearby") is True:
            add("onemap_nearby", "OneMap confirms location", 0.12, "onemap", "very_high",
                "Official SG map confirms this name near the coordinates.")
        return signals

    def _rebrand_signals(self, record: Dict) -> List[Dict[str, Any]]:
        """Faithful breakdown for a REBRAND verdict (all support 'rebranded')."""
        signals: List[Dict[str, Any]] = []

        def add(key, label, weight, source, reliability, detail):
            signals.append({
                "key": key, "label": label, "weight": round(weight, 3),
                "direction": "support", "source": source,
                "reliability": reliability, "detail": detail,
            })

        if record.get("visual_state") == "changed":
            add("visual_changed", "Street photo shows a different business name", 0.40,
                "visual_street", "medium",
                "GPT-4o read a business name on the storefront that differs from the map record.")
        ms = record.get("match_score") or 0.0
        if ms > 0:
            add("location_match", "Same coordinates as a known baseline place",
                round(min(ms, 0.6), 3), "baseline_geojson", "high",
                "Location strongly matches an existing baseline place, but the name differs.")
        sign = (record.get("sign_text") or "").strip()
        if sign:
            add("new_signage", "New signage text detected", 0.10, "visual_street", "low",
                f"Sign reads: '{sign[:60]}'.")
        return signals

    def _area_density(self, lat: float, lng: float, baseline: List[Dict], radius_m: float = 200.0) -> int:
        """Count how many baseline places exist within radius_m of (lat, lng)."""
        if not lat or not lng:
            return 0
        count = 0
        for bp in baseline:
            blat = bp.get("latitude") or bp.get("coordinates", {}).get("latitude") if isinstance(bp.get("coordinates"), dict) else None
            blng = bp.get("longitude") or bp.get("coordinates", {}).get("longitude") if isinstance(bp.get("coordinates"), dict) else None
            if blat is None or blng is None:
                continue
            try:
                if _haversine_m(lat, lng, float(blat), float(blng)) <= radius_m:
                    count += 1
            except Exception:
                continue
        return count

    def _classify(self, record: Dict, baseline: List[Dict] = None) -> Dict:
        """Core classification logic."""
        match_type = record.get("match_type", "likely_new")
        match_score = record.get("match_score", 0.0)
        source_count = record.get("source_count", 0)
        website_state = record.get("website_state")
        delivery_avail = record.get("delivery_available")
        social_active = record.get("social_active")
        visual_state = record.get("visual_state")
        discussion = record.get("discussion_sentiment")

        confidence = 0.0
        status = "uncertain"
        review_needed = False
        review_reason = ""

        # ── Compute closure model once (faithful signals for XAI) ──
        closure_signals = self._closure_signals(record)
        closure = max(0.0, min(1.0, round(sum(s["weight"] for s in closure_signals), 3)))
        nearby_baseline_count = 0  # set in new_place branch, reused for breakdown

        # ── NEW PLACE ──
        if match_type == "likely_new":
            status = "new_place"
            confidence = 0.5

            # Boost confidence with corroborating evidence
            if source_count >= 3:
                confidence += 0.20
            elif source_count >= 2:
                confidence += 0.10

            if delivery_avail:
                confidence += 0.10
            if website_state == "active":
                confidence += 0.10
            if discussion == "positive":
                confidence += 0.05
            if visual_state == "open":
                confidence += 0.05  # image is informational only, small boost

            # ── Density + not-in-OSM boost ──────────────────────────────────
            # If the candidate is NOT in the OSM/HERE baseline but IS in external
            # data sources (gov, delivery, reviews) AND the surrounding area has
            # high POI density (≥3 baseline places within 200m), the area is
            # commercially active — this strongly suggests a genuine new place.
            clat = record.get("latitude")
            clng = record.get("longitude")
            nearby_baseline_count = 0
            if baseline and clat and clng:
                nearby_baseline_count = self._area_density(float(clat), float(clng), baseline, radius_m=200.0)

            if nearby_baseline_count >= 5:
                # Dense commercial area — high chance new place is real
                confidence += 0.15
                review_reason = f"High-density area ({nearby_baseline_count} places within 200m) — new POI likely genuine"
            elif nearby_baseline_count >= 3:
                confidence += 0.08
                review_reason = f"Moderate-density area ({nearby_baseline_count} places within 200m)"

            # OneMap confirms the place exists in official SG data but not in OSM
            if record.get("onemap_found_nearby") is True:
                confidence += 0.12
                review_reason = (review_reason or "") + "; OneMap confirms location"

            confidence = min(confidence, 0.98)

            if confidence < 0.55:
                review_needed = True
                review_reason = review_reason or "New place but low confidence — needs verification"

        # ── REBRANDED ──
        elif match_type == "possible_rebrand":
            status = "rebranded"
            confidence = 0.55

            if visual_state == "changed":
                confidence += 0.15
            if source_count >= 2:
                confidence += 0.10
            if delivery_avail:
                confidence += 0.05

            confidence = min(confidence, 0.95)
            review_needed = True
            review_reason = f"Possible rebrand of '{record.get('nearest_baseline_name', '?')}' — needs human confirmation"

        # ── STRONG MATCH ──
        elif match_type == "strong_match":
            status = "active"
            confidence = max(match_score, 0.70)

            # Vision-driven REBRAND: a known location whose storefront now shows a
            # DIFFERENT business name is a rebrand, not a closure. This takes
            # priority over the closure score.
            if visual_state == "changed":
                status = "rebranded"
                confidence = 0.70 if record.get("sign_text") else 0.60
                review_needed = True
                review_reason = (
                    f"Street imagery shows a different business at the location of "
                    f"'{record.get('nearest_baseline_name') or record.get('detected_name')}' — likely rebrand"
                )
            # An explicit authoritative closure flag is decisive on its own.
            elif record.get("ta_permanently_closed") is True:
                status = "closed"
                confidence = 0.92
                review_needed = True
                review_reason = _closure_reason(record)
            # Otherwise: multiple independent closure signals must agree. 0.60 is
            # reached e.g. by ACRA struck-off (0.40) + dead website (0.10) + absent
            # from OneMap (0.15). Always queued for human review.
            elif closure >= CLOSED_THRESHOLD:
                status = "closed"
                # Scale confidence: ~0.62 at threshold → 0.95 at closure=1.0
                confidence = round(min(0.62 + (closure - CLOSED_THRESHOLD) * 0.8, 0.95), 3)
                review_needed = True
                review_reason = _closure_reason(record)
            elif closure >= UNCERTAIN_CLOSURE:
                status = "uncertain"
                confidence = round(0.35 + closure * 0.30, 3)
                review_needed = True
                review_reason = "Partial closure signals detected — needs human verification"
            # Below the uncertain bar: missing evidence is NOT negative evidence — keep active

        # ── AMBIGUOUS ──
        elif match_type == "ambiguous":
            if match_score >= 0.55:
                status = "active"
                confidence = match_score
            elif match_score >= 0.45:
                status = "active"
                confidence = match_score
                review_needed = True
                review_reason = "Moderate match — may need verification"
            else:
                status = "uncertain"
                confidence = 0.40
                review_needed = True
                review_reason = "Ambiguous match — dense area or conflicting signals"

            # Override: strong multi-source new evidence
            if source_count >= 3 and delivery_avail:
                status = "new_place"
                confidence = 0.60
                review_reason = "Possibly new, multiple sources confirm but baseline conflict exists"

            # Ambiguous + meaningful closure evidence → uncertain for review (never
            # silently "active"). We still don't auto-CLOSE on an ambiguous match —
            # the weak match means we can't be sure it's the same place — but we must
            # not bury real closure signals under a default-active verdict.
            if closure >= 0.50 and status != "new_place":
                status = "uncertain"
                confidence = round(0.40 + closure * 0.20, 3)
                review_needed = True
                review_reason = f"Closure signals present but baseline match is ambiguous — {_closure_reason(record)}"

        # ── NO MATCH / FALLBACK ──
        else:
            if record.get("ta_permanently_closed") is True or closure >= CLOSED_THRESHOLD:
                status = "closed"
                confidence = round(min(0.58 + (closure - CLOSED_THRESHOLD), 0.90), 3)
                review_needed = True
                review_reason = _closure_reason(record)
            elif closure >= UNCERTAIN_CLOSURE:
                status = "uncertain"
                confidence = 0.35
                review_needed = True
                review_reason = "Partial closure signals — insufficient for confident closed classification"
            elif source_count == 0:
                status = "uncertain"
                confidence = 0.30
                review_needed = True
                review_reason = "No fresh evidence found"

        from backend.explainability.explanation_generator import generate_explanation

        record["status"] = status
        record["confidence"] = round(confidence, 3)
        record["review_needed"] = review_needed
        record["review_reason"] = review_reason

        # ── Faithful signal breakdown for XAI ───────────────────────────────
        # Attach the exact signals/weights that drove THIS verdict so the proof
        # cards report real contributions, not re-derived approximations.
        record["closure_score"] = closure
        if status == "new_place":
            breakdown = self._newplace_signals(record, nearby_baseline_count)
            record["model"] = "new_place_confidence"
            record["model_score"] = round(confidence, 3)
        elif status == "rebranded":
            breakdown = self._rebrand_signals(record)
            record["model"] = "rebrand_confidence"
            record["model_score"] = round(confidence, 3)
        else:
            breakdown = closure_signals
            record["model"] = "closure_score"
            record["model_score"] = closure
        record["signal_breakdown"] = breakdown

        # Attach XAI explanation automatically
        try:
            record["xai_explanation"] = generate_explanation(record)
        except Exception as e:
            log.warning(f"Failed to generate XAI for {record.get('detected_name')}: {e}")
            record["xai_explanation"] = None

        return record
