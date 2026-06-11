# pyre-ignore-all-errors
# ============================================================================
# Agent 2 — Baseline Map Agent
# ============================================================================
"""
Manages the baseline POI dataset.  Loads GeoJSON from the here/ directory,
builds a spatial index, and serves baseline context to other agents.
"""
import json
import math
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.agents.base_agent import BaseAgent
from backend.config import HERE_DIR

log = logging.getLogger("baseline_agent")

EARTH_R = 6_371_000

LAYER_CATEGORY = {
    "cafes": "food_beverage", "restaurants": "food_beverage",
    "hotels": "accommodation", "pharmacies": "retail",
    "grocery stores": "retail", "department_stores": "retail",
    "shopping_malls": "retail", "fuel_station": "fuel_energy",
    "theme_parks": "recreation_tourism", "tourism attraction": "recreation_tourism",
}


def _haversine(lat1, lon1, lat2, lon2):
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lat2 - lat1)
    dg = math.radians(lon2 - lon1)
    a = math.sin(dl / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dg / 2) ** 2
    return EARTH_R * 2 * math.asin(math.sqrt(a))


class BaselineAgent(BaseAgent):
    name = "baseline"

    def __init__(self):
        self._places: List[Dict] = []
        self._loaded = False

    @property
    def places(self) -> List[Dict]:
        if not self._loaded:
            self._load()
        return self._places

    def _load(self):
        """Load all GeoJSON files from here/ directory."""
        here = Path(HERE_DIR)
        pid = 0
        for fp in sorted(here.glob("*.geojson")):
            layer_name = fp.stem
            with open(fp, "r", encoding="utf-8") as f:
                gj = json.load(f)
            for feat in gj.get("features", []):
                props = feat.get("properties", {})
                coords = feat.get("geometry", {}).get("coordinates", [])
                if len(coords) < 2:
                    continue
                self._places.append({
                    "place_id": f"bl_{pid}",
                    "osm_id": props.get("@id", ""),
                    "name": props.get("name", ""),
                    "brand": props.get("brand"),
                    "category": LAYER_CATEGORY.get(layer_name, "other"),
                    "amenity": props.get("amenity"),
                    "tourism": props.get("tourism"),
                    "source_layer": layer_name,
                    "latitude": coords[1],
                    "longitude": coords[0],
                    "address": props.get("addr:street", ""),
                    "postal_code": props.get("addr:postcode"),
                    "phone": props.get("phone"),
                    "website": props.get("website"),
                    "opening_hours": props.get("opening_hours"),
                    "cuisine": props.get("cuisine"),
                    "properties": props,
                })
                pid += 1
        self._loaded = True
        log.info(f"Loaded {len(self._places)} baseline places from {here}")

    def find_nearby(self, lat: float, lon: float, radius_m: float = 50) -> List[Dict]:
        """Return baseline places within radius_m of (lat, lon)."""
        return [
            {**p, "distance_m": _haversine(lat, lon, p["latitude"], p["longitude"])}
            for p in self.places
            if _haversine(lat, lon, p["latitude"], p["longitude"]) <= radius_m
        ]

    def find_by_name(self, name: str, threshold: float = 0.4) -> List[Dict]:
        """Simple token-overlap search."""
        tokens = set(name.lower().split())
        results = []
        for p in self.places:
            ptokens = set(p["name"].lower().split())
            if not tokens or not ptokens:
                continue
            sim = len(tokens & ptokens) / max(len(tokens), len(ptokens))
            if sim >= threshold:
                results.append({**p, "name_sim": sim})
        return sorted(results, key=lambda x: -x["name_sim"])[:20]

    def get_layers(self) -> Dict[str, Any]:
        """Return raw GeoJSON per layer for the frontend."""
        here = Path(HERE_DIR)
        layers = {}
        total = 0
        for fp in sorted(here.glob("*.geojson")):
            with open(fp, "r", encoding="utf-8") as f:
                gj = json.load(f)
            layers[fp.stem] = gj
            total += len(gj.get("features", []))
        return {"layers": layers, "total_features": total}

    async def execute(self, payload: Dict[str, Any]) -> Any:
        """Load baseline and return summary."""
        if not self._loaded:
            self._load()
        return {
            "count": len(self._places),
            "layers": list({p["source_layer"] for p in self._places}),
            "categories": list({p["category"] for p in self._places}),
        }
