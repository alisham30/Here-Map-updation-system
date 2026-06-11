"""
Scoring utilities for MapFreshness pipeline.
Computes weighted freshness scores from multi-source signals.
"""

# ─── Weight sets for different evidence availability scenarios ───

WEIGHT_SETS = {
    "base": {
        # No vision, no crowdsource — external + temporal signals only
        "external_score":   0.38,   # was 0.40
        "temporal_score":   0.15,
        "anomaly_score":    0.10,
        "behavioral_score": 0.12,   # was 0.15
        "density_score":    0.05,   # NEW — human density (Mapillary + OSM traces)
        "location_score":   0.20,
    },
    "vision_only": {
        # Vision available but no crowdsource data
        "external_score":   0.33,   # was 0.35
        "vision_score":     0.25,
        "temporal_score":   0.10,
        "anomaly_score":    0.05,
        "behavioral_score": 0.07,   # was 0.10
        "density_score":    0.05,   # NEW — human density
        "location_score":   0.15,
    },
    "full": {
        # All signals available: vision + crowdsource + external
        "external_score":    0.28,  # was 0.30
        "vision_score":      0.25,
        "crowdsource_score": 0.10,
        "temporal_score":    0.10,
        "anomaly_score":     0.05,
        "behavioral_score":  0.07,  # was 0.10
        "density_score":     0.05,  # NEW — human density
        "location_score":    0.10,
    },
}


def calculate_freshness(scores: dict, weight_set: str = "base") -> float:
    """
    Compute a weighted freshness score from individual signal scores.

    Args:
        scores: dict mapping score keys (e.g. "external_score") to float values 0-100
        weight_set: one of "base", "vision_only", "full"

    Returns:
        Weighted freshness score as a float 0-100
    """
    weights = WEIGHT_SETS.get(weight_set, WEIGHT_SETS["base"])
    total_weight = 0.0
    weighted_sum = 0.0

    for key, weight in weights.items():
        value = scores.get(key)
        if value is not None:
            weighted_sum += weight * float(value)
            total_weight += weight

    if total_weight == 0:
        return 50.0

    # Normalise in case some keys were missing
    return round(weighted_sum / total_weight, 2)


def determine_status(freshness_score: float, confidence: float = 1.0) -> str:
    """
    Map a freshness score to a human-readable status label.

    Args:
        freshness_score: 0-100 composite score
        confidence: 0-1 confidence multiplier

    Returns:
        One of: "fresh", "moderate", "stale", "uncertain"
    """
    effective = freshness_score * confidence

    if confidence < 0.4:
        return "uncertain"
    if effective >= 70:
        return "fresh"
    if effective >= 40:
        return "moderate"
    return "stale"
