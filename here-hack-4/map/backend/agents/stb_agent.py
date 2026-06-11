# pyre-ignore-all-errors
# ============================================================================
# Agent — Singapore Tourism Board (STB) Real Data Agent
# ============================================================================
"""
Loads real tourist attractions from official STB dataset.
Source: /TouristAttractions/Tourist Attractions.geojson (data.gov.sg)
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from backend.agents.base_agent import BaseAgent
from backend.schemas.models import ListingEvidence, SourceTypeEnum, FreshnessLabel

log = logging.getLogger("stb_agent")

# Path to real STB dataset (from data.gov.sg)
STB_GEOJSON_PATH = Path(__file__).parent.parent.parent / "TouristAttractions" / "Tourist Attractions.geojson"


class STBAgent(BaseAgent):
    name = "stb_evidence"

    async def execute(self, payload: Dict[str, Any]) -> List[ListingEvidence]:
        """Load real tourist attractions from STB GeoJSON dataset."""
        results = []
        
        if not STB_GEOJSON_PATH.exists():
            log.warning(f"STB dataset not found at {STB_GEOJSON_PATH}")
            return results

        try:
            with open(STB_GEOJSON_PATH, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)

            features = geojson_data.get("features", [])
            log.info(f"STB agent loading {len(features)} attractions from real dataset")

            for feature in features:
                props = feature.get("properties", {})
                coords = feature.get("geometry", {}).get("coordinates", [None, None])
                
                name = props.get("PAGETITLE") or props.get("name")
                if not name:
                    continue

                address = props.get("ADDRESS", "")
                latitude = coords[1] if len(coords) > 1 else props.get("LATITUDE")
                longitude = coords[0] if len(coords) > 0 else props.get("LONGTITUDE")

                results.append(ListingEvidence(
                    source_type=SourceTypeEnum.stb_tourism,
                    listing_name=name,
                    address=address,
                    category="tourist_attraction",
                    is_active=True,  # STB dataset is current
                    confidence=0.95,  # Real official source
                    freshness=FreshnessLabel.very_recent,
                    raw_data={
                        "properties": props,
                        "url": props.get("EXTERNAL_LINK"),
                        "opening_hours": props.get("OPENING_HOURS"),
                        "overview": props.get("OVERVIEW"),
                    }
                ))

        except Exception as e:
            log.error(f"STB dataset loading error: {e}")

        log.info(f"STB evidence: Loaded {len(results)} real attractions from official dataset")
        return results
