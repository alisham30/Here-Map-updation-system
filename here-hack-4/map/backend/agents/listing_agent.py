# pyre-ignore-all-errors
# ============================================================================
# Agent 5 — Public Listings / Directory Agent
# ============================================================================
"""
Gathers place evidence from Yelp-like business listings, directories,
tourism boards, and public merchant registries.
"""
import logging
from typing import Any, Dict, List
from backend.agents.base_agent import BaseAgent
from backend.schemas.models import ListingEvidence, SourceTypeEnum, FreshnessLabel

log = logging.getLogger("listing_agent")

YELP_LISTINGS = [
    {"id": "yelp-008", "name": "Punggol Coast Mall", "cat": "shopping, mall, retail", "lat": 1.415708, "lng": 103.9105519, "rating": 4.2, "reviews": 47, "addr": "88 Punggol Way Singapore 829913"},
    {"id": "yelp-001", "name": "Tiong Bahru Sourdough", "cat": "coffee, bakeries", "lat": 1.2845, "lng": 103.8316, "rating": 4.5, "reviews": 12, "addr": "56 Eng Hoon Street"},
    {"id": "yelp-002", "name": "Nasi Lemak Queen", "cat": "restaurants, malay", "lat": 1.2858, "lng": 103.8270, "rating": 4.8, "reviews": 28, "addr": "302 Tiong Bahru Road"},
    {"id": "yelp-003", "name": "Sunset Grill", "cat": "restaurants, seafood", "lat": 1.2490, "lng": 103.8267, "rating": 4.2, "reviews": 8, "addr": "8 Sentosa Gateway"},
    {"id": "yelp-004", "name": "East Coast Brew Lab", "cat": "coffee, specialty", "lat": 1.3054, "lng": 103.9058, "rating": 4.6, "reviews": 18, "addr": "212 East Coast Road"},
    {"id": "yelp-005", "name": "Fusion Kitchen @ Lau Pa Sat", "cat": "restaurants, fusion", "lat": 1.2806, "lng": 103.8505, "rating": 4.3, "reviews": 35, "addr": "18 Raffles Quay"},
    {"id": "yelp-006", "name": "Bukit Timah Taco Bar", "cat": "restaurants, mexican", "lat": 1.3394, "lng": 103.7764, "rating": 4.0, "reviews": 6, "addr": "587 Bukit Timah Road"},
    {"id": "yelp-007", "name": "Clementi Açaí Bowl", "cat": "coffee, healthfood", "lat": 1.3149, "lng": 103.7649, "rating": 4.7, "reviews": 22, "addr": "443 Clementi Ave 3"},
]

STB_LISTINGS = [
    {"id": "stb-001", "name": "Singapore VR Experience Centre", "lat": 1.2834, "lng": 103.8607, "cat": "entertainment", "desc": "VR attraction at Marina Bay"},
    {"id": "stb-002", "name": "Heritage Spice Garden", "lat": 1.2816, "lng": 103.8636, "cat": "garden", "desc": "Botanical spice garden near Gardens by the Bay"},
    {"id": "stb-003", "name": "Punggol Coast Mall", "lat": 1.415708, "lng": 103.9105519, "cat": "shopping_mall", "desc": "New integrated waterfront retail mall at 88 Punggol Way — not yet in OSM baseline"},
]

ACRA_BUSINESSES = [
    {"uen": "202600011K", "name": "Punggol Coast Mall Pte Ltd", "code": "4711", "addr": "88 PUNGGOL WAY 829913", "date": "2026-01-15"},
    {"uen": "202600001A", "name": "Tiong Bahru Sourdough Co.", "code": "5620", "addr": "56 ENG HOON ST 160056", "date": "2026-02-10"},
    {"uen": "202600002B", "name": "Nasi Lemak Queen Pte Ltd", "code": "5610", "addr": "302 TIONG BAHRU RD 168732", "date": "2026-01-25"},
    {"uen": "202600003C", "name": "Green Apothecary Pte Ltd", "code": "4773", "addr": "1 PASIR RIS DR 4 519457", "date": "2026-03-01"},
    {"uen": "202600004D", "name": "Jewel Fresh Market", "code": "4711", "addr": "78 AIRPORT BLVD 819666", "date": "2026-02-18"},
    {"uen": "202600005E", "name": "Cloud Nine Hotel & Suites", "code": "5510", "addr": "10 BAYFRONT AVE 018956", "date": "2026-01-05"},
    {"uen": "202600006F", "name": "Sunset Grill Singapore", "code": "5610", "addr": "8 SENTOSA GATEWAY 098269", "date": "2026-03-10"},
    {"uen": "202600007G", "name": "East Coast Brew Lab", "code": "5620", "addr": "212 EAST COAST RD 428911", "date": "2026-02-28"},
    {"uen": "202600008H", "name": "Orchard Wellness Pharmacy", "code": "4773", "addr": "290 ORCHARD RD 238859", "date": "2026-03-15"},
    {"uen": "202600009I", "name": "Lau Pa Sat Fusion Kitchen", "code": "5610", "addr": "18 RAFFLES QUAY 048582", "date": "2026-01-18"},
    {"uen": "202600010J", "name": "HarbourFront Mart Express", "code": "4711", "addr": "1 HARBOURFRONT WALK 098585", "date": "2026-02-05"},
]


class ListingEvidenceAgent(BaseAgent):
    name = "listing_evidence"

    async def execute(self, payload: Dict[str, Any]) -> List[ListingEvidence]:
        results = []

        # Yelp
        for r in YELP_LISTINGS:
            results.append(ListingEvidence(
                source_type=SourceTypeEnum.yelp,
                listing_name=r["name"],
                address=r["addr"],
                category=r["cat"],
                rating=r["rating"],
                review_count=r["reviews"],
                is_active=True,
                confidence=0.72,
                freshness=FreshnessLabel.recent,
                raw_data=r,
            ))

        # STB
        for r in STB_LISTINGS:
            results.append(ListingEvidence(
                source_type=SourceTypeEnum.stb_tourism,
                listing_name=r["name"],
                category=r["cat"],
                is_active=True,
                confidence=0.85,
                freshness=FreshnessLabel.recent,
                raw_data=r,
            ))

        # ACRA
        for r in ACRA_BUSINESSES:
            results.append(ListingEvidence(
                source_type=SourceTypeEnum.acra_registry,
                listing_name=r["name"],
                address=r["addr"],
                is_active=True,
                confidence=0.90,
                freshness=FreshnessLabel.very_recent,
                first_listed=r["date"],
                raw_data=r,
            ))

        log.info(f"Listing evidence: {len(results)} from Yelp + STB + ACRA")
        return results
