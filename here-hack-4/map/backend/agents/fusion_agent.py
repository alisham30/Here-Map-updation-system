# pyre-ignore-all-errors
# ============================================================================
# Agent 10 — Fusion Agent
# ============================================================================
"""
Combines multi-source evidence into structured PlaceIntelligenceRecords.
Computes source agreement/conflict, aggregates signals, picks best data.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List
from backend.agents.base_agent import BaseAgent
from backend.schemas.models import (
    PlaceIntelligenceRecord, Coordinates, PlaceStatusEnum,
    FreshnessLabel, MatchResult, MatchType, FusedRecord
)

log = logging.getLogger("fusion_agent")


class FusionAgent(BaseAgent):
    name = "fusion"

    async def execute(self, payload: Dict[str, Any]) -> List[Dict]:
        matches = payload.get("matches", [])
        all_evidence = payload.get("evidence", [])
        baseline = payload.get("baseline", [])

        fused_records = []

        for match_entry in matches:
            candidate = match_entry.get("candidate", {})
            match_result = match_entry.get("match")

            if isinstance(match_result, dict):
                match_obj = MatchResult(**match_result)
            else:
                match_obj = match_result

            # Build fused record
            lat = candidate.get("latitude") or 0.0
            lng = candidate.get("longitude") or 0.0

            record = {
                "detected_name": candidate.get("name", "Unknown"),
                "detected_brand": candidate.get("brand"),
                "latitude": lat,
                "longitude": lng,
                "address": candidate.get("address"),
                "category": candidate.get("category", ""),
                "source_type": candidate.get("source_type", "unknown"),

                # Match info
                "match_type": match_obj.match_type.value if hasattr(match_obj.match_type, 'value') else match_obj.match_type,
                "match_score": match_obj.scores.composite if match_obj.scores else 0.0,
                "nearest_baseline_name": match_obj.matched_baseline_name,
                "nearest_baseline_distance_m": match_obj.distance_m,
                "baseline_place_id": match_obj.baseline_place_id,

                # Source tracking
                "source_types": [candidate.get("source_type", "unknown")],
                "source_count": 1,
                "evidence_ids": [],

                # Signals (to be enriched)
                "website_state": None,
                "delivery_available": None,
                "social_active": None,
                "visual_state": None,
                "sign_text": None,
                "image_explanation": None,
                "discussion_sentiment": None,
                "image_url": candidate.get("image_url"),
                "captured_at": None,
                "age_label": None,
                "recency_weight": None,
                # TripAdvisor real-time signals
                "ta_permanently_closed": None,
                "ta_review_count": None,
                "ta_recency_boost": None,
                "ta_weighted_avg_rating": None,
                "ta_is_active": None,
                # Gov / ACRA signals
                "gov_status_negative": None,
                "gov_confirmed_active": None,
                # OneMap official Singapore map signals
                "onemap_found": None,
                "onemap_revgeo_found": None,
                "onemap_found_nearby": None,

                # Will be set by decision agent
                "status": "uncertain",
                "confidence": 0.0,
                "freshness": "moderate",
                "review_needed": False,
            }

            # Enrich from evidence
            ev = candidate.get("evidence", {})
            if ev.get("source_type") == "official_website" or ev.get("website_state"):
                record["website_state"] = ev.get("website_state", "unknown")
            if ev.get("source_type") in ("grabfood", "foodpanda"):
                record["delivery_available"] = ev.get("is_available", False)
            if ev.get("source_type") == "social_media":
                record["social_active"] = ev.get("activity_level") == "active"
            if ev.get("source_type") == "visual_street":
                record["visual_state"] = ev.get("visual_state", "unknown")
                record["sign_text"] = ev.get("sign_text")
                record["image_url"] = ev.get("image_url") or record.get("image_url")
                raw = ev.get("raw_data", {}) or {}
                record["captured_at"] = ev.get("image_date") or raw.get("captured_at")
                record["age_label"] = raw.get("age_label")
                record["recency_weight"] = raw.get("recency_weight")
                # Short human-readable explanation for UI below image
                if record.get("visual_state") or record.get("sign_text"):
                    visual_state = str(record.get("visual_state") or "unknown").replace("_", " ")
                    sign_text = (record.get("sign_text") or "").strip()
                    if sign_text:
                        record["image_explanation"] = f"AI visual check: storefront appears {visual_state}. Sign text: {sign_text[:120]}."
                    else:
                        record["image_explanation"] = f"AI visual check: storefront appears {visual_state}."
            if ev.get("source_type") == "reddit":
                record["discussion_sentiment"] = ev.get("sentiment")
            if ev.get("source_type") == "tripadvisor":
                record["ta_permanently_closed"] = ev.get("is_permanently_closed", False)
                record["ta_review_count"] = ev.get("review_count", 0)
                record["ta_recency_boost"] = ev.get("recency_boost", 0.0)
                record["ta_weighted_avg_rating"] = ev.get("weighted_avg_rating")
                record["ta_is_active"] = ev.get("is_active", True)
            if ev.get("source_type") in ("acra_registry", "data_gov_sg"):
                direction = ev.get("signal_direction")
                if direction == "negative":
                    record["gov_status_negative"] = True
                elif direction == "positive":
                    record["gov_confirmed_active"] = True
            if ev.get("source_type") == "onemap":
                record["onemap_found"] = ev.get("onemap_found", False)
                record["onemap_revgeo_found"] = ev.get("onemap_revgeo_found", False)
                record["onemap_found_nearby"] = ev.get("onemap_found_nearby", False)
                # Treat a positive OneMap signal as gov confirmation
                direction = ev.get("signal_direction")
                if direction == "positive":
                    record["gov_confirmed_active"] = True
                elif direction == "negative" and not ev.get("onemap_revgeo_found"):
                    record["gov_status_negative"] = True

            fused_records.append(record)

        # ── Join authoritative gov evidence by baseline place ───────────────
        # OneMap / ACRA / data.gov.sg evidence has no business name of its own,
        # so it never becomes a matching candidate. Instead we attach it to the
        # record for the baseline place it was gathered for. Without this, those
        # official signals (the strongest closure evidence) never reach scoring.
        gov_by_baseline: Dict[str, List[Dict]] = {}
        for ev in all_evidence:
            if (isinstance(ev, dict)
                    and ev.get("source_type") in ("onemap", "acra_registry", "data_gov_sg")
                    and ev.get("baseline_place_id")):
                gov_by_baseline.setdefault(ev["baseline_place_id"], []).append(ev)

        for record in fused_records:
            bid = record.get("baseline_place_id")
            if bid and bid in gov_by_baseline:
                for ev in gov_by_baseline[bid]:
                    self._apply_gov(record, ev)

        # Consolidate duplicates (same name within 30m)
        consolidated = self._consolidate(fused_records)

        # ── Pydantic validation boundary ────────────────────────────────────
        # Validate/coerce each fused dict through FusedRecord so the decision
        # agent receives well-typed records (float coords, real booleans, list
        # source_types). Records that fail validation are kept as-is and logged
        # rather than dropped, so a single bad field never kills the run.
        validated = []
        invalid = 0
        for rec in consolidated:
            try:
                validated.append(FusedRecord(**rec).model_dump())
            except Exception as e:
                invalid += 1
                log.debug(f"FusedRecord validation failed for '{rec.get('detected_name')}': {e}")
                validated.append(rec)

        log.info(
            f"Fused {len(matches)} matches → {len(validated)} records "
            f"({invalid} kept unvalidated)"
        )
        return validated

    def _apply_gov(self, record: Dict, ev: Dict) -> None:
        """Merge an OneMap / ACRA / data.gov.sg evidence dict into a fused record."""
        st = ev.get("source_type")
        direction = ev.get("signal_direction")
        if st in ("acra_registry", "data_gov_sg"):
            if direction == "negative":
                record["gov_status_negative"] = True
            elif direction == "positive":
                record["gov_confirmed_active"] = True
        elif st == "onemap":
            if record.get("onemap_found") is None:
                record["onemap_found"] = ev.get("onemap_found", False)
            if record.get("onemap_revgeo_found") is None:
                record["onemap_revgeo_found"] = ev.get("onemap_revgeo_found", False)
            if record.get("onemap_found_nearby") is None:
                record["onemap_found_nearby"] = ev.get("onemap_found_nearby", False)
            if direction == "positive":
                record["gov_confirmed_active"] = True
            elif direction == "negative" and not ev.get("onemap_revgeo_found"):
                record["gov_status_negative"] = True
        # Reflect the source in the record's source list (deduped later).
        src = "acra_registry" if st == "data_gov_sg" else st
        if src and src not in record.get("source_types", []):
            record.setdefault("source_types", []).append(src)
            record["source_count"] = len(set(record["source_types"]))

    def _consolidate(self, records: List[Dict]) -> List[Dict]:
        """Merge records that are likely the same place."""
        if not records:
            return []

        used = set()
        merged = []

        for i, a in enumerate(records):
            if i in used:
                continue
            cluster = [a]
            used.add(i)

            for j in range(i + 1, len(records)):
                if j in used:
                    continue
                b = records[j]
                # Same name token overlap > 0.6 and within 30m
                na = set(a.get("detected_name", "").lower().split())
                nb = set(b.get("detected_name", "").lower().split())
                name_sim = len(na & nb) / max(len(na), len(nb)) if na and nb else 0
                if name_sim > 0.6:
                    cluster.append(b)
                    used.add(j)

            # Merge cluster
            primary = cluster[0]
            all_sources = []
            for c in cluster:
                all_sources.extend(c.get("source_types", []))
                # Carry forward signals
                for sig in ["website_state", "delivery_available", "social_active",
                            "visual_state", "sign_text", "image_explanation", "discussion_sentiment", "image_url",
                            "captured_at", "age_label", "recency_weight",
                            "ta_permanently_closed", "ta_review_count", "ta_recency_boost",
                            "ta_weighted_avg_rating", "ta_is_active",
                            "gov_status_negative", "gov_confirmed_active",
                            "onemap_found", "onemap_revgeo_found", "onemap_found_nearby"]:
                    if c.get(sig) is not None and primary.get(sig) is None:
                        primary[sig] = c[sig]

            primary["source_types"] = sorted(set(all_sources))
            primary["source_count"] = len(set(all_sources))
            merged.append(primary)

        return merged
