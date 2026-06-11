# pyre-ignore-all-errors
# ============================================================================
# XAI Explanation Generator — human-readable proof cards & natural language
# ============================================================================
"""
For every classified place, generates:
  - proof cards with per-source confidence contributions + rich narratives
  - flowing natural-language explanation (NOT a mechanical signal list)
  - headline, summary, baseline comparison, uncertainty reasons
"""
from typing import Any, Dict, List, Optional


def _round3(val: float) -> float:
    return int(val * 1000) / 1000


def _pct(val: float) -> str:
    return f"{int(val * 100)}%"


# ── Source metadata ──────────────────────────────────────────────────────────

SOURCE_RELIABILITY = {
    "analysis":         "medium",
    "acra_registry":    "very_high",
    "onemap":           "very_high",
    "official_website": "high",
    "tripadvisor":      "high",
    "grabfood":         "medium_high",
    "foodpanda":        "medium_high",
    "yelp":             "medium_high",
    "public_listing":   "medium_high",
    "stb_tourism":      "medium_high",
    "social_media":     "medium",
    "reddit":           "medium",
    "visual_street":    "low",          # image weight = 0; shown for context only
    "baseline_geojson": "very_high",
    "baseline_only":    "low",
}

SOURCE_DISPLAY_NAMES = {
    "analysis":         "Spatial / Source Analysis",
    "acra_registry":    "ACRA Business Registry",
    "onemap":           "OneMap Singapore",
    "official_website": "Official Website",
    "tripadvisor":      "TripAdvisor",
    "grabfood":         "GrabFood",
    "foodpanda":        "foodpanda",
    "yelp":             "Yelp",
    "public_listing":   "Public Directory",
    "stb_tourism":      "Singapore Tourism Board",
    "social_media":     "Social Media",
    "reddit":           "Community Discussion",
    "visual_street":    "Street-Level Image",
    "baseline_geojson": "Baseline (OSM/HERE)",
    "baseline_only":    "Baseline Only",
}

SOURCE_ICONS = {
    "analysis":         "🧮",
    "acra_registry":    "🏛️",
    "onemap":           "🗺️",
    "official_website": "🌐",
    "tripadvisor":      "✈️",
    "grabfood":         "🛵",
    "foodpanda":        "🐼",
    "yelp":             "⭐",
    "public_listing":   "📋",
    "stb_tourism":      "🏝️",
    "social_media":     "📱",
    "reddit":           "💬",
    "visual_street":    "📷",
    "baseline_geojson": "🗺️",
    "baseline_only":    "📂",
}


# ── Main entry point ─────────────────────────────────────────────────────────

def generate_explanation(record: Dict[str, Any]) -> Dict[str, Any]:
    status        = record.get("status", "uncertain")
    confidence    = record.get("confidence", 0.0)
    name          = record.get("detected_name", "Unknown")
    source_types  = record.get("source_types", [])
    source_count  = record.get("source_count", 0)
    match_type    = record.get("match_type", "")
    match_score   = record.get("match_score", 0.0)
    nearest_baseline  = record.get("nearest_baseline_name")
    nearest_distance  = record.get("nearest_baseline_distance_m")
    website_state     = record.get("website_state")
    delivery_available = record.get("delivery_available")
    social_active     = record.get("social_active")
    visual_state      = record.get("visual_state")
    discussion_sentiment = record.get("discussion_sentiment")

    proof_cards = _build_proof_cards(record)

    natural_explanation = _build_natural_explanation(
        status=status,
        name=name,
        confidence=confidence,
        proof_cards=proof_cards,
        record=record,
    )

    headline = _generate_headline(status, name, confidence)
    summary  = _generate_summary(
        status, name, confidence, source_count,
        nearest_baseline, nearest_distance,
        match_type, match_score, source_types,
        website_state, delivery_available, social_active, visual_state,
        record,
    )

    baseline_comparison = None
    if nearest_baseline:
        baseline_comparison = {
            "nearest_name": nearest_baseline,
            "distance_m":   nearest_distance,
            "match_score":  _round3(match_score) if match_score else 0,
            "match_type":   match_type,
            "why_not_same": _why_not_same(status, match_type, match_score,
                                          name, nearest_baseline, nearest_distance),
        }

    uncertainty_reasons = _get_uncertainty_reasons(record)

    net = _round3(sum(p["confidence_contribution"] for p in proof_cards))
    return {
        "headline":            headline,
        "summary":             summary,
        "natural_explanation": natural_explanation,
        "proof_cards":         proof_cards,
        "baseline_comparison": baseline_comparison,
        "uncertainty_reasons": uncertainty_reasons,
        "total_proof_confidence": net,
        # Faithfulness metadata: which model decided this and its raw score, so the
        # proof cards (which sum to net) can be reconciled against the real verdict.
        "model":               record.get("model"),
        "model_score":         record.get("model_score"),
        "net_signal_score":    net,
        "is_faithful":         bool(record.get("signal_breakdown")),
        "recommendation":      _get_recommendation(status, confidence),
    }


# ── Proof cards ──────────────────────────────────────────────────────────────

def _build_proof_cards(record: Dict) -> List[Dict]:
    """
    Build evidence proof cards.

    Preferred path: if the decision agent attached a `signal_breakdown` (the
    actual signed weights it scored with), build cards directly from it so each
    `confidence_contribution` is the REAL number that drove the verdict. This is
    what makes the explanation faithful. Falls back to the legacy source-based
    cards only when no breakdown is present (e.g. baseline-only placeholders).
    """
    breakdown = record.get("signal_breakdown")
    if breakdown:
        return _build_proof_cards_from_breakdown(record, breakdown)
    return _build_legacy_proof_cards(record)


def _build_proof_cards_from_breakdown(record: Dict, breakdown: List[Dict]) -> List[Dict]:
    """Faithful cards: one per signal that actually fired, with its true weight."""
    status = record.get("status", "uncertain")
    cards: List[Dict] = []
    for sig in breakdown:
        src = sig.get("source") or "analysis"
        weight = float(sig.get("weight", 0.0))
        # Direction is relative to the place being OPEN/operational:
        #   closure model: weight>0 → toward closed (negative); weight<0 → open (positive)
        #   new_place model: every signal supports the 'new_place' verdict (positive)
        if sig.get("direction") == "support":
            direction = "positive"
        else:
            direction = "negative" if weight > 0 else "positive"

        cards.append({
            "source_type": src,
            "source_name": SOURCE_DISPLAY_NAMES.get(src, src.replace("_", " ").title()),
            "source_icon": SOURCE_ICONS.get(src, "📡"),
            "reliability": sig.get("reliability") or SOURCE_RELIABILITY.get(src, "medium"),
            "freshness": "recent",
            "signal_direction": direction,
            "supports_status": status,
            "finding": sig.get("label", ""),
            "reasoning": sig.get("detail", ""),
            "narrative": sig.get("detail", sig.get("label", "")),
            # The real weight from the model — signed so the UI can show ±.
            "confidence_contribution": _round3(weight),
            "signal_key": sig.get("key"),
        })

    # Strongest predictors first (by absolute real weight).
    cards.sort(key=lambda c: abs(c.get("confidence_contribution", 0.0)), reverse=True)
    return cards


def _build_legacy_proof_cards(record: Dict) -> List[Dict]:
    """
    Legacy heuristic cards (used only when no faithful breakdown exists).
      finding   — short label
      reasoning — why it matters
      narrative — a full natural-language sentence using REAL data from the record
    """
    cards = []
    source_types = record.get("source_types", [])
    status       = record.get("status", "uncertain")
    confidence   = record.get("confidence", 0.0)

    base = confidence / max(len(source_types), 1)

    for src in source_types:
        card: Dict[str, Any] = {
            "source_type":  src,
            "source_name":  SOURCE_DISPLAY_NAMES.get(src, src.replace("_", " ").title()),
            "source_icon":  SOURCE_ICONS.get(src, "📡"),
            "reliability":  SOURCE_RELIABILITY.get(src, "medium"),
            "freshness":    "recent",
            "signal_direction": "positive",
            "supports_status":  status,
            "narrative":    "",   # filled below
        }

        # ── Official Website ─────────────────────────────────────────────
        if src == "official_website":
            ws = record.get("website_state", "unknown")
            if ws == "active":
                extras = []
                if record.get("has_booking"):
                    extras.append("active booking system")
                if record.get("has_menu"):
                    extras.append("published menu")
                extra_str = f" It also has {' and '.join(extras)}." if extras else ""
                card["finding"]   = "Official website is live and active"
                card["reasoning"] = "A live website with current content is strong evidence of an operational business"
                card["narrative"] = (
                    f"The official website for '{record.get('detected_name', 'this place')}' "
                    f"is live and actively maintained.{extra_str} "
                    f"This is a reliable signal that the business is currently operating."
                )
                card["confidence_contribution"] = _round3(base * 1.2)
            elif ws in ("inactive", "error", "parked"):
                card["finding"]   = f"Official website is {ws}"
                card["reasoning"] = "An inactive or error-state website suggests the business may no longer be operating"
                card["narrative"] = (
                    f"The official website returns a '{ws}' status — it is no longer being maintained. "
                    f"Businesses that are still operating typically keep their web presence active."
                )
                card["confidence_contribution"] = _round3(-base * 0.8)
                card["signal_direction"] = "negative"
            else:
                card["finding"]   = f"Website state: {ws}"
                card["reasoning"] = "Website state provides limited evidence"
                card["narrative"] = f"The website state is reported as '{ws}', which provides inconclusive evidence."
                card["confidence_contribution"] = _round3(base * 0.4)

        # ── Delivery platforms ───────────────────────────────────────────
        elif src in ("grabfood", "foodpanda"):
            platform = "GrabFood" if src == "grabfood" else "foodpanda"
            if record.get("delivery_available"):
                card["finding"]   = f"Active merchant listing on {platform} with delivery available"
                card["reasoning"] = f"Only operational businesses maintain active delivery listings on {platform}"
                card["narrative"] = (
                    f"{platform} shows this location as an active merchant accepting delivery orders right now. "
                    f"Delivery platforms remove or deactivate listings within days of a closure, "
                    f"so an active listing is strong real-time evidence of operation."
                )
                card["confidence_contribution"] = _round3(base * 1.1)
            else:
                card["finding"]   = f"No active listing found on {platform}"
                card["reasoning"] = f"Not all businesses use {platform} — absence is a weak signal only"
                card["narrative"] = (
                    f"This place does not appear as an active merchant on {platform}. "
                    f"This is a weak signal — many businesses operate without delivery apps, "
                    f"especially non-food categories."
                )
                card["confidence_contribution"] = _round3(-base * 0.2)
                card["signal_direction"] = "neutral"

        # ── Yelp ─────────────────────────────────────────────────────────
        elif src == "yelp":
            rating = record.get("rating") or record.get("ta_weighted_avg_rating")
            r_count = record.get("review_count") or 0
            if rating and r_count:
                card["finding"]   = f"Yelp listing: {r_count} reviews, rated {rating:.1f}★"
                card["reasoning"] = "An active Yelp listing with reviews confirms the place is known and operational"
                card["narrative"] = (
                    f"Yelp lists this place with {r_count} review{'s' if r_count != 1 else ''} "
                    f"and an average rating of {rating:.1f} out of 5 ⭐. "
                    f"A business with reviews is actively frequented by customers."
                )
            else:
                card["finding"]   = "Business listing found on Yelp"
                card["reasoning"] = "An active Yelp listing suggests the business is known and operational"
                card["narrative"] = (
                    "This place is listed on Yelp, indicating it is a known business "
                    "that has been visited and reviewed by the public."
                )
            card["confidence_contribution"] = _round3(base * 1.0)

        # ── ACRA Registry ────────────────────────────────────────────────
        elif src == "acra_registry":
            gov_neg = record.get("gov_status_negative")
            gov_ok  = record.get("gov_confirmed_active")
            if gov_neg:
                card["finding"]   = "ACRA registry shows entity as cancelled or struck off"
                card["reasoning"] = "Official government deregistration is authoritative evidence of closure"
                card["narrative"] = (
                    "Singapore's ACRA business registry shows this entity has been cancelled or struck off. "
                    "ACRA deregistration is the most authoritative signal of permanent business closure — "
                    "it means the company no longer has a legal right to operate."
                )
                card["confidence_contribution"] = _round3(base * 1.4)
                card["signal_direction"] = "negative"
                card["reliability"] = "very_high"
            else:
                card["finding"]   = "ACRA registry confirms active business registration"
                card["reasoning"] = "Official government registration is the strongest evidence of a legitimate operating business"
                card["narrative"] = (
                    "Singapore's ACRA business registry confirms this entity holds a valid, active registration. "
                    "This is a legally mandated record — businesses must maintain this to operate. "
                    "It is the most authoritative signal of legitimacy available in Singapore."
                )
                card["confidence_contribution"] = _round3(base * 1.4)
                card["reliability"] = "very_high"

        # ── TripAdvisor ──────────────────────────────────────────────────
        elif src == "tripadvisor":
            ta_closed   = record.get("ta_permanently_closed")
            ta_count    = record.get("ta_review_count") or 0
            ta_rating   = record.get("ta_weighted_avg_rating")
            ta_recency  = record.get("ta_recency_boost")
            ta_latest   = record.get("ta_latest_review_date")

            if ta_closed:
                card["finding"]   = "TripAdvisor marks this location as permanently closed"
                card["reasoning"] = "TripAdvisor's permanent closure flag is updated from real-time user reports"
                card["narrative"] = (
                    "TripAdvisor has explicitly flagged this location as permanently closed. "
                    "This flag is crowd-sourced and moderated by TripAdvisor in real time — "
                    "it is one of the strongest available signals of a permanent closure."
                )
                card["confidence_contribution"] = _round3(base * 1.5)
                card["signal_direction"] = "negative"
            elif ta_count > 0 and ta_recency is not None:
                recency_desc = (
                    "with very recent reviews in the last 90 days" if ta_recency >= 0.5
                    else "but review activity has slowed recently" if ta_recency >= 0.15
                    else "but no new reviews in the last 3 months — activity may have dropped"
                )
                rating_str = f", rated {ta_rating:.1f} ⭐" if ta_rating else ""
                date_str   = f" Most recent review: {ta_latest}." if ta_latest else ""
                card["finding"]   = f"TripAdvisor: {ta_count} reviews{rating_str}"
                card["reasoning"] = "Review volume and recency indicate how actively visited a place is"
                card["narrative"] = (
                    f"TripAdvisor shows {ta_count} review{'s' if ta_count != 1 else ''}{rating_str}, "
                    f"{recency_desc}.{date_str} "
                    f"A place that is genuinely closed stops receiving new reviews quickly."
                )
                card["confidence_contribution"] = (
                    _round3(base * 1.2) if ta_recency >= 0.3
                    else _round3(base * 0.4)
                )
                card["signal_direction"] = "positive" if ta_recency >= 0.15 else "neutral"
            else:
                card["finding"]   = "No TripAdvisor listing found"
                card["reasoning"] = "Absence from TripAdvisor may indicate a new or unlisted business"
                card["narrative"] = (
                    "This location does not appear in TripAdvisor's database. "
                    "For a newly opened place this is expected — TripAdvisor listings lag reality by weeks to months."
                )
                card["confidence_contribution"] = _round3(base * 0.3)
                card["signal_direction"] = "neutral"

        # ── OneMap Singapore ─────────────────────────────────────────────
        elif src == "onemap":
            revgeo  = record.get("onemap_revgeo_found")
            nearby  = record.get("onemap_found_nearby")
            onemap_found = record.get("onemap_found")
            address = record.get("onemap_address") or ""

            if nearby:
                addr_str = f" The confirmed address is: {address}." if address else ""
                card["finding"]   = "OneMap confirms building and business at this location"
                card["reasoning"] = "Singapore's official government map service confirms the physical address and listing"
                card["narrative"] = (
                    f"Singapore's official OneMap database confirms a building at these coordinates "
                    f"and finds this business name within 200m of the recorded location.{addr_str} "
                    f"OneMap is maintained by SLA (Singapore Land Authority) and is authoritative for Singapore addresses."
                )
                card["confidence_contribution"] = _round3(base * 1.3)
            elif revgeo and not onemap_found:
                addr_str = f" Address at coordinates: {address}." if address else ""
                card["finding"]   = "OneMap confirms building exists but business name not in gazetteer"
                card["reasoning"] = "The physical building exists but the business may not be officially listed yet"
                card["narrative"] = (
                    f"OneMap's reverse geocode confirms a building/address at these coordinates.{addr_str} "
                    f"However, this business name does not appear in OneMap's business gazetteer — "
                    f"consistent with a newly opened place not yet registered in official directories."
                )
                card["confidence_contribution"] = _round3(base * 0.6)
                card["signal_direction"] = "neutral"
            elif not revgeo and not onemap_found:
                card["finding"]   = "OneMap finds no record at this location"
                card["reasoning"] = "Singapore's official map shows nothing at these coordinates — unusual for an active business"
                card["narrative"] = (
                    "OneMap's reverse geocode finds no registered address or business at these coordinates, "
                    "and the business name does not appear in the gazetteer. "
                    "This is unusual in dense Singapore — it may indicate the location data is incorrect "
                    "or the business no longer operates at this address."
                )
                card["confidence_contribution"] = _round3(-base * 0.5)
                card["signal_direction"] = "negative"
            else:
                card["finding"]   = "Partial OneMap match"
                card["reasoning"] = "OneMap data is inconclusive for this location"
                card["narrative"] = "OneMap data provides partial information about this location."
                card["confidence_contribution"] = _round3(base * 0.3)
                card["signal_direction"] = "neutral"

        # ── Social Media ─────────────────────────────────────────────────
        elif src == "social_media":
            last_post  = record.get("last_post_date") or ""
            followers  = record.get("follower_count") or 0
            platform   = record.get("social_platform") or "social media"
            if record.get("social_active"):
                follower_str = f" with {followers:,} followers" if followers else ""
                post_str     = f", last active on {last_post}" if last_post else ""
                card["finding"]   = f"Active social media presence{follower_str}{post_str}"
                card["reasoning"] = "A business actively posting on social media is engaging with customers and is operational"
                card["narrative"] = (
                    f"The business has an active {platform} presence{follower_str}{post_str}. "
                    f"Regular social media activity — especially recent posts — shows the business "
                    f"is engaging with customers and is open."
                )
                card["confidence_contribution"] = _round3(base * 0.9)
            else:
                card["finding"]   = "Social media account found but has gone dormant"
                card["reasoning"] = "Dormant social media may indicate the business has stopped operating"
                card["narrative"] = (
                    f"A {platform} account exists for this business but has not posted recently. "
                    f"While not conclusive, a sudden stop in social activity after previous regular posts "
                    f"can be an early indicator of closure."
                )
                card["confidence_contribution"] = _round3(base * 0.3)
                card["signal_direction"] = "neutral"

        # ── Community Discussion (Reddit / HWZ / blogs) ──────────────────
        elif src == "reddit":
            sent    = record.get("discussion_sentiment", "neutral")
            snippet = record.get("discussion_snippet") or record.get("snippet") or ""
            sent_map = {"positive": "positive", "negative": "negative", "neutral": "mixed"}
            sent_label = sent_map.get(sent, sent)
            snippet_str = f' For example: "{snippet[:120]}..."' if snippet else ""
            card["finding"]   = f"Community mentions found with {sent_label} sentiment"
            card["reasoning"] = "Real people discussing a place on public forums reflects its current relevance"
            card["narrative"] = (
                f"Public forums and community platforms are discussing this place with {sent_label} sentiment.{snippet_str} "
                f"Community discussion — especially recent opening mentions or closure reports — is "
                f"valuable ground-truth evidence from people who have visited in person."
            )
            card["confidence_contribution"] = _round3(base * (0.9 if sent == "positive" else 0.5 if sent == "neutral" else 0.6))
            card["signal_direction"] = "positive" if sent == "positive" else "neutral" if sent == "neutral" else "negative"

        # ── Street-Level Image ────────────────────────────────────────────
        elif src == "visual_street":
            vs        = record.get("visual_state", "unknown")
            sign_text = (record.get("sign_text") or "").strip()
            img_note  = record.get("image_explanation") or ""

            # Image has weight=0 in closure scoring — label that clearly
            if vs == "open" and sign_text:
                card["finding"]   = f"Sign reads: '{sign_text}' — storefront appears open"
                card["reasoning"] = "Sign text matches business name, suggesting the place is operating"
                card["narrative"] = (
                    f"A street-level photo of this location shows the sign reading '{sign_text}'. "
                    f"The storefront appears open and operational. "
                    f"Note: image evidence has zero weight in the closure score — "
                    f"only explicit written closure notices in the sign count."
                )
                card["confidence_contribution"] = _round3(base * 0.05)
                card["signal_direction"] = "positive"
            elif vs == "closed" and sign_text:
                card["finding"]   = f"Sign text detected: '{sign_text[:80]}'"
                card["reasoning"] = "Written closure notice found on the sign — this is explicit text evidence, not just a shutter"
                card["narrative"] = (
                    f"The street-level photo shows a sign reading: '{sign_text[:120]}'. "
                    f"This is an explicit written closure notice visible on the premises. "
                    f"Unlike a pulled-down shutter (which just means 'closed today'), "
                    f"written notices like this are strong evidence of permanent closure."
                )
                card["confidence_contribution"] = _round3(base * 0.05)   # weight kept at 0 as designed
                card["signal_direction"] = "negative"
            elif vs == "changed":
                sign_str = f" The sign now reads: '{sign_text}'." if sign_text else ""
                card["finding"]   = f"Storefront has changed since baseline{' — new signage detected' if sign_text else ''}"
                card["reasoning"] = "Visual change at the location may indicate a new business or rebrand"
                card["narrative"] = (
                    f"Street imagery shows the storefront has changed from what was recorded in the baseline.{sign_str} "
                    f"This visual change supports the hypothesis of a new business or rebrand at this location."
                )
                card["confidence_contribution"] = _round3(base * 0.05)
                card["signal_direction"] = "neutral"
            elif vs == "unknown":
                note_str = f" AI note: {img_note}" if img_note else ""
                card["finding"]   = "Street image captured — shutters down, no closure text visible"
                card["reasoning"] = "Shutters being down means the shop is closed right now, not permanently closed"
                card["narrative"] = (
                    f"A street-level photo was captured at this location showing shutters down, "
                    f"but no written closure notice was found on the signage.{note_str} "
                    f"Shutters being down is not evidence of permanent closure — "
                    f"Singapore shops routinely pull shutters during off-hours. "
                    f"This image carries zero weight in the closure score."
                )
                card["confidence_contribution"] = 0.0
                card["signal_direction"] = "neutral"
            else:
                card["finding"]   = f"Street image: visual state is '{vs}'"
                card["reasoning"] = "Street-level image provides context but carries zero weight in closure scoring"
                card["narrative"] = (
                    f"A street-level photo shows the storefront in a '{vs}' state. "
                    f"Image evidence is shown here for context only — it is not used in the confidence score."
                )
                card["confidence_contribution"] = 0.0
                card["signal_direction"] = "neutral"
            card["reliability"] = "low"
            card["freshness"]   = "informational"

        # ── STB Tourism ─────────────────────────────────────────────────
        elif src == "stb_tourism":
            card["finding"]   = "Listed in Singapore Tourism Board directory"
            card["reasoning"] = "STB registration confirms the place is recognised as a tourism-relevant establishment"
            card["narrative"] = (
                "This place is listed in the Singapore Tourism Board's official directory. "
                "STB approval means the establishment has met the government's criteria for a legitimate tourism venue."
            )
            card["confidence_contribution"] = _round3(base * 1.0)

        # ── Baseline only ────────────────────────────────────────────────
        elif src == "baseline_only":
            card["finding"]   = "Present in baseline dataset but no fresh evidence found"
            card["reasoning"] = "Absence of fresh evidence warrants investigation but does not confirm closure"
            card["narrative"] = (
                "This place exists in Singapore's official baseline map dataset (OSM/HERE) "
                "but no fresh evidence was gathered from any active data source during this pipeline run. "
                "This could mean the place is closed, or simply that it wasn't covered in this run's sample."
            )
            card["confidence_contribution"] = _round3(base * 0.2)
            card["signal_direction"] = "neutral"
            card["freshness"] = "stale"

        # ── Fallback ────────────────────────────────────────────────────
        else:
            card["finding"]   = f"Evidence from {src.replace('_', ' ')}"
            card["reasoning"] = "Supporting evidence from this source"
            card["narrative"] = f"Data from {SOURCE_DISPLAY_NAMES.get(src, src)} provides additional context."
            card["confidence_contribution"] = _round3(base * 0.5)

        cards.append(card)

    # Sort by absolute contribution descending (strongest predictors first)
    cards.sort(key=lambda c: abs(c.get("confidence_contribution", 0.0)), reverse=True)
    return cards


# ── Natural-language explanation ──────────────────────────────────────────────

def _build_natural_explanation(
    status: str,
    name: str,
    confidence: float,
    proof_cards: List[Dict[str, Any]],
    record: Dict[str, Any],
    max_predictors: int = 3,
) -> str:
    """
    Build a genuinely conversational explanation based on top predictors.
    Uses each card's 'narrative' (full sentence with real data) rather than
    mechanical "positive signal: X, negative signal: Y" labelling.
    """
    pct = int(confidence * 100)

    if not proof_cards:
        return f'"{name}" is classified as {status} ({pct}% confidence) but supporting evidence is limited.'

    # Top predictors by absolute contribution
    top = sorted(proof_cards, key=lambda c: abs(float(c.get("confidence_contribution", 0))), reverse=True)[:max_predictors]

    positives = [c for c in top if c.get("signal_direction") == "positive"]
    negatives = [c for c in top if c.get("signal_direction") == "negative"]

    # Pull full narratives from each top card
    narratives = [c.get("narrative", c.get("finding", "")).strip() for c in top if c.get("narrative") or c.get("finding")]
    narratives = [n for n in narratives if n]

    if not narratives:
        return f'"{name}" is classified as {status} ({pct}% confidence).'

    # Status-specific opening sentence
    if status == "new_place":
        source_count = record.get("source_count", 0)
        intro = (
            f'"{name}" does not appear in Singapore\'s official POI baseline '
            f'(OSM/HERE datasets), suggesting it is a newly opened place. '
            f'{source_count} independent source{"s" if source_count != 1 else ""} confirm its existence at this location.'
        )
    elif status == "closed":
        intro = (
            f'"{name}" is recorded in the baseline but multiple data sources '
            f'suggest it has permanently closed.'
        )
    elif status == "active":
        intro = (
            f'"{name}" matches a known baseline place and shows clear signals '
            f'of active operation.'
        )
    elif status == "rebranded":
        nearest = record.get("nearest_baseline_name", "an existing baseline place")
        intro = (
            f'The location previously recorded as "{nearest}" '
            f'now appears to have a new business identity: "{name}".'
        )
    else:
        intro = f'"{name}" has uncertain status ({pct}% confidence) — evidence is conflicting or incomplete.'

    # Weave narratives into flowing paragraphs
    if len(narratives) == 1:
        body = narratives[0]
    elif len(narratives) == 2:
        # Decide connective based on whether signals agree or conflict
        if positives and negatives:
            body = f"{narratives[0]} However, {narratives[1][0].lower()}{narratives[1][1:]}"
        else:
            body = f"{narratives[0]} Additionally, {narratives[1][0].lower()}{narratives[1][1:]}"
    else:
        if positives and negatives:
            # Conflict: lead with the strongest, then contrast
            body = (
                f"{narratives[0]} "
                f"On the other hand, {narratives[1][0].lower()}{narratives[1][1:]} "
                f"Furthermore, {narratives[2][0].lower()}{narratives[2][1:]}"
            )
        else:
            body = f"{narratives[0]} {narratives[1]} {narratives[2]}"

    # Conflict resolution note
    if positives and negatives and status in ("closed", "uncertain"):
        pos_names = ", ".join(c["source_name"] for c in positives[:2])
        neg_names = ", ".join(c["source_name"] for c in negatives[:2])
        body += (
            f" The system weighted {neg_names} more heavily than {pos_names} "
            f"because authoritative registry and real-time review data outrank "
            f"operational presence signals when they conflict."
        )
    elif positives and negatives and status == "active":
        neg_names = ", ".join(c["source_name"] for c in negatives[:1])
        body += (
            f" Despite {neg_names} showing a weak negative signal, "
            f"the overall balance of evidence strongly supports active status."
        )

    return f"{intro} {body}"


# ── Headline ─────────────────────────────────────────────────────────────────

def _generate_headline(status: str, name: str, confidence: float) -> str:
    pct = int(confidence * 100)
    headlines = {
        "new_place":  f'"{name}" is likely a NEW place ({pct}% confidence)',
        "closed":     f'"{name}" is likely PERMANENTLY CLOSED ({pct}% confidence)',
        "rebranded":  f'"{name}" appears to be REBRANDED ({pct}% confidence)',
        "active":     f'"{name}" is confirmed ACTIVE ({pct}% confidence)',
        "uncertain":  f'"{name}" — status UNCERTAIN ({pct}% confidence)',
    }
    return headlines.get(status, f'"{name}" — status: {status}')


# ── Summary ───────────────────────────────────────────────────────────────────

def _generate_summary(
    status, name, confidence, source_count,
    nearest_baseline, nearest_distance,
    match_type, match_score, source_types,
    website_state, delivery_available, social_active, visual_state,
    record: Dict,
) -> str:
    parts = []

    if status == "new_place":
        parts.append(f'"{name}" was not found in the baseline dataset of Singapore POIs.')
        if source_count >= 2:
            parts.append(f"{source_count} independent sources confirm its existence at this location.")
        if nearest_baseline:
            dist_str = f"{nearest_distance:.0f}m" if nearest_distance else "nearby"
            parts.append(
                f'The nearest baseline entry is "{nearest_baseline}" ({dist_str} away), '
                f"but the match score is only {match_score:.0%} — these are different places."
            )
        signals = []
        if website_state == "active":      signals.append("website is live")
        if delivery_available:             signals.append("delivery is available")
        if social_active:                  signals.append("social media is active")
        ta_count = record.get("ta_review_count") or 0
        if ta_count > 0:                   signals.append(f"TripAdvisor shows {ta_count} reviews")
        if signals:
            parts.append(f"Supporting evidence: {', '.join(signals)}.")

    elif status == "closed":
        parts.append(f'"{name}" exists in the baseline but shows strong closure signals.')
        negatives = []
        if record.get("ta_permanently_closed"):  negatives.append("TripAdvisor marks permanently closed")
        if record.get("gov_status_negative"):     negatives.append("ACRA registration cancelled")
        ta_recency = record.get("ta_recency_boost")
        ta_count   = record.get("ta_review_count") or 0
        if ta_recency is not None and ta_count > 0 and ta_recency < 0.15:
            negatives.append("TripAdvisor reviews have dried up")
        if website_state in ("inactive", "error", "parked"): negatives.append("website is inactive")
        if delivery_available is False:           negatives.append("not on delivery platforms")
        if negatives:
            parts.append(f"Closure signals: {'; '.join(negatives)}.")

    elif status == "rebranded":
        parts.append(
            f'The location previously occupied by "{nearest_baseline or "unknown"}" '
            f'now appears to be "{name}".'
        )
        if match_score:
            parts.append(
                f"Spatial overlap is strong but name similarity is low ({match_score:.0%}), "
                "suggesting a rebrand rather than the same business."
            )

    elif status == "active":
        parts.append(f'"{name}" matches a baseline place and shows active operational signals.')
        positives = []
        if website_state == "active":   positives.append("website is live")
        if delivery_available:          positives.append("delivery is available")
        if social_active:               positives.append("social media is active")
        ta_count = record.get("ta_review_count") or 0
        ta_recency = record.get("ta_recency_boost")
        if ta_count > 0 and ta_recency and ta_recency >= 0.3:
            positives.append(f"TripAdvisor shows {ta_count} recent reviews")
        if record.get("onemap_found_nearby"):
            positives.append("confirmed on OneMap")
        if positives:
            parts.append(f"Confirmed by: {', '.join(positives)}.")

    elif status == "uncertain":
        parts.append(f'"{name}" has conflicting or insufficient evidence.')
        parts.append("Human review is recommended to resolve this case.")

    return " ".join(parts)


# ── Baseline comparison ───────────────────────────────────────────────────────

def _why_not_same(status, match_type, match_score, name, nearest_baseline, nearest_distance) -> str:
    if status == "new_place":
        reasons = []
        if match_score and match_score < 0.4:
            reasons.append(f"Match score is only {match_score:.0%} (strong match threshold is 85%)")
        if nearest_distance and nearest_distance > 100:
            reasons.append(f"Distance of {nearest_distance:.0f}m exceeds the 100m proximity threshold")
        if name and nearest_baseline:
            name_tokens     = set(name.lower().split())
            baseline_tokens = set(nearest_baseline.lower().split())
            overlap = len(name_tokens & baseline_tokens) / max(len(name_tokens), len(baseline_tokens)) if name_tokens and baseline_tokens else 0
            if overlap < 0.5:
                reasons.append(f'Name similarity is low — "{name}" vs "{nearest_baseline}"')
        if not reasons:
            reasons.append("No strong match found in the baseline dataset")
        return ". ".join(reasons) + "."
    elif status == "rebranded":
        return (
            f'Same coordinates as "{nearest_baseline}" but a different name/brand. '
            "The system interprets this as a rebrand rather than the same business."
        )
    return "Match analysis did not find a definitive relationship."


# ── Uncertainty reasons ───────────────────────────────────────────────────────

def _get_uncertainty_reasons(record: Dict) -> List[str]:
    reasons = []
    source_count = record.get("source_count", 0)
    confidence   = record.get("confidence", 0.0)

    if source_count < 2:
        reasons.append("Only 1 evidence source — more independent confirmation needed")
    if confidence < 0.5:
        reasons.append(f"Low overall confidence ({int(confidence * 100)}%) — evidence is weak or conflicting")
    if record.get("website_state") is None:
        reasons.append("No website evidence gathered during this run")
    if record.get("delivery_available") is None:
        reasons.append("No delivery platform check performed")
    if record.get("ta_review_count") is None:
        reasons.append("TripAdvisor data was not retrieved for this location")
    if record.get("match_type") == "ambiguous":
        reasons.append("Baseline matching was ambiguous — dense area or partial name overlap")
    return reasons


# ── Recommendation ────────────────────────────────────────────────────────────

def _get_recommendation(status: str, confidence: float) -> str:
    if confidence >= 0.85:
        return "Very high confidence — can be auto-approved without review"
    elif confidence >= 0.70:
        return "High confidence — quick sanity check recommended before approval"
    elif confidence >= 0.55:
        return "Moderate confidence — review recommended, check top 2 proof cards"
    elif confidence >= 0.40:
        return "Low confidence — detailed manual review needed before any action"
    else:
        return "Very low confidence — needs manual investigation; do not auto-approve"
