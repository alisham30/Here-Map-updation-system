# PlaceIQ Singapore — Complete Data Source Audit

## 📊 Executive Summary
Your project has **MANY real data sources ALREADY AVAILABLE** but agents are using **hardcoded fake data** instead!

---

## 🔍 REAL DATA SOURCES AVAILABLE (In Workspace)

### ✅ **STB Tourist Attractions** (Available but NOT being used)
- **Location:** `/TouristAttractions/Tourist Attractions.geojson`
- **Format:** GeoJSON + KML + Shapefile
- **Records:** 100+ tourist attractions (museums, temples, gardens, heritage sites, etc.)
- **Fields:** NAME, ADDRESS, LAT/LONG, OVERVIEW, OPENING_HOURS, EXTERNAL_LINK, IMAGE_PATH, RATINGS
- **Example:** National Gallery, Sultan Mosque, Gardens by the Bay
- **Status:** ❌ **AGENT IGNORING THIS** — stb_agent.py calls fake API instead

### ✅ **HERE Category Files** (Available but NOT being used)
**Location:** `/map/here/` — 11 pre-extracted category geojsons:
- `tourism attraction.geojson` — attractions
- `shopping_malls.geojson` — 100+ malls  
- `restaurants.geojson` — 1000+ restaurants
- `hotels.geojson` — 300+ hotels
- `pharmacies.geojson` — pharmacies
- `theme_parks.geojson` — theme parks
- `cafes.geojson` — cafe listings
- `fuel_station.geojson` — gas stations
- `grocery stores.geojson` — supermarkets
- `department_stores.geojson` — department stores
- **Status:** ✅ Available but NO agents reference these

### ✅ **ACRA Business Registry** (Being used, but partial)
- **Location:** `/map/data/ACRA Information on Corporate Entities ('A-U').csv`
- **Records:** 26 CSV files (by first letter of entity name)
- **Fields:** UEN, Company Name, Address, Business Code, Registration Date
- **Coverage:** Complete Singapore business registry
- **Status:** ✅ USED by gov_agent.py (for closure detection)
- **UPDATE:** listing_agent.py also has hardcoded 11 ACRA entries that are static test data

### ✅ **Baseline Consolidated Geodata** (Primary source)
- **Location:** `/map/baseline_consolidated.geojson`
- **Records:** 10,570 places (consolidated from OSM + HERE)
- **Loaded by:** backend/config.py + backend/app_state.py
- **Coverage:** Complete Singapore baseline
- **Status:** ✅ ACTIVE (master data source)

### ✅ **Parks Data**
- **Location:** `/map/data/Parks.geojson`
- **Records:** Park locations and boundaries in Singapore
- **Status:** ✅ Available but NO agents reference

### ✅ **Discovery Outputs** (Pipeline results)
- `/map/discovery_output/NEW_DETECTIONS_not_on_OSM.geojson` — New places found
- `/map/discovery_output/UNCERTAIN_needs_review.geojson` — Uncertain classifications
- `/map/discovery_output/existing_OSM_baseline.geojson` — Baseline subset

### ✅ **data.gov.sg APIs** (Real endpoints)
- **OneMap API** — Address lookup, reverse geocoding
- **Historical datasets** — Multi-year records
- **Status:** ✅ USED by gov_agent.py for verification

---

## ❌ AGENTS IGNORING REAL DATA (Using Hardcoded/Fake Instead)

### 1. **STB Agent** — ❌ FAKE API
**File:** `backend/agents/stb_agent.py`
```python
STB_API_BASE = "https://api.stb.gov.sg/v1"  # FAKE ENDPOINT — doesn't exist
# Calling endpoints that don't exist:
- GET /attractions
- GET /dining_venues
```
**Problem:** Agent waits for STB_API_KEY in config, but endpoint is fictional
**What it SHOULD do:** Load from `/TouristAttractions/Tourist Attractions.geojson` ✅ (available locally)

---

### 2. **Listing Agent** — ❌ 100% HARDCODED
**File:** `backend/agents/listing_agent.py`
```python
YELP_LISTINGS = [8 hardcoded businesses] — Same 8 every run
STB_LISTINGS = [3 hardcoded attractions] — Same 3 every run  
ACRA_BUSINESSES = [11 hardcoded companies] — Same 11 every run
```
**Problem:** 
- Returns identical data every execution
- **Yelp entries:** Punggol Coast Mall, Tiong Bahru Sourdough, Nasi Lemak Queen, etc. (STATIC)
- **STB entries:** Singapore VR Experience, Heritage Spice Garden (STATIC)
- Never calls real APIs
- Duplicate with yelp_agent.py (TWO Yelp agents!)

**What it SHOULD do:** 
- Option A: Remove this agent (yelp_agent.py already does Yelp properly)
- Option B: Convert to load from real sources (HERE geojsons, ACRA CSVs, STB geojson)

---

### 3. **Delivery Agent** — ❌ PARTIALLY FAKE
**File:** `backend/agents/delivery_agent.py`
```python
# Tries real API calls BUT:
FOODPANDA_API_URL = "https://api.foodpanda.sg/v1"  # ✅ Real endpoint
DELIVEROO_API_URL = "https://api.deliveroo.sg/v1"  # ✅ Real endpoint
# BUT no API keys configured — fallback returns random data
```
**Status:** Waiting for FOODPANDA_API_KEY & DELIVEROO_API_KEY in .env

---

## 🔧 RECOMMENDATION: Data Source Consolidation

### **PHASE 1: Fix STB Agent** (QUICK WIN)
Replace fake API calls with real GeoJSON loading:
```python
import json
from pathlib import Path

STB_GEOJSON_PATH = Path(__file__).parent.parent.parent / "TouristAttractions" / "Tourist Attractions.geojson"

# Load STB data from geojson
with open(STB_GEOJSON_PATH) as f:
    stb_data = json.load(f)
    for feature in stb_data['features']:
        props = feature['properties']
        # Extract: name, address, coords, opening hours, etc.
```

### **PHASE 2: Fix Listing Agent** (IMMEDIATE)
Either:
- **Option A:** DELETE listing_agent.py (yelp_agent.py + stb_agent.py already cover this)
- **Option B:** Rename to category_agent.py and load from HERE geojsons:
```python
HERE_GEOJSON_PATH = Path(__file__).parent.parent / "here"
# Load: restaurants.geojson, shopping_malls.geojson, hotels.geojson, etc.
```

### **PHASE 3: Delivery Agent** (Pending API keys)
- Get foodpanda API credentials
- Get Deliveroo API credentials  
- Add to .env file
- Agent code already written ✅

---

## 📋 Data Source Mapping Table

| Data Source | Format | Records | Location | Status | Agent Using | Issue |
|---|---|---|---|---|---|---|
| **STB (Tourist Attractions)** | GeoJSON/KML/SHP | 100+ | `/TouristAttractions/` | ✅ Loaded | stb_agent.py | ❌ Using fake API instead |
| **HERE Categories** | GeoJSON × 11 | 5000+ | `/map/here/` | ✅ Loaded | None | ❌ No agent references |
| **ACRA Registry** | CSV × 26 | 500K+ | `/map/data/` | ✅ Loaded | gov_agent.py | ✅ Used for verification |
| **Baseline Places** | GeoJSON | 10,570 | `baseline_consolidated.geojson` | ✅ Loaded | orchestrator.py | ✅ Primary source |
| **Parks** | GeoJSON | 300+ | `/map/data/Parks.geojson` | ✅ Loaded | None | ❌ No agent references |
| **data.gov.sg APIs** | REST API | Live | https://www.odata.gov.sg | ✅ Live | gov_agent.py | ✅ Used for verification |
| **OneMap** | REST API | Live | https://www.onemap.gov.sg | ✅ Live | gov_agent.py | ✅ Used for geocoding |
| **Yelp API** | REST API | Live | api.yelp.com | ⏳ Ready | yelp_agent.py | ⏳ Needs API key |
| **TripAdvisor API** | REST API | Live | api.content.tripadvisor.com | ✅ Configured | tripadvisor_agent.py | ✅ Ready to use |
| **OpenAI Vision** | REST API | Live | api.openai.com | ✅ Configured | visual_agent.py | ✅ Street view analysis |
| **foodpanda** | REST API | Live | api.foodpanda.sg | ⏳ Ready | delivery_agent.py | ⏳ Needs API key |
| **Deliveroo** | REST API | Live | api.deliveroo.sg | ⏳ Ready | delivery_agent.py | ⏳ Needs API key |

---

## 🚀 Quick Wins (In Order)

1. **STB Agent Fix** — Replace 20 lines to use real `.geojson`
2. **Remove listing_agent.py** — Delete 100 lines (duplicate Yelp agent)
3. **Get Foodpanda/Deliveroo Keys** — Add to .env
4. **Test Pipeline** — Verify all real APIs working

---

## 📁 File Organization Summary

```
/TouristAttractions/              ← STB DATA (unused!)
  Tourist Attractions.geojson     ← 100+ attractions
  Tourist Attractions (KML).kml   
  Tourist Attractions (SHP)/

/map/here/                        ← HERE CATEGORIES (unused!)
  shopping_malls.geojson          ← 100+ malls
  restaurants.geojson             ← 1000+ restaurants
  hotels.geojson                  ← 300+ hotels
  tourism_attraction.geojson      ← attractions
  (+ 7 more category files)

/map/data/                        ← ACRA REGISTRY (partially used)
  ACRA Information...('A').csv    ← A-companies
  ACRA Information...('B').csv    ← B-companies
  ... ('C'-'U')
  Parks.geojson                   ← Park locations

/map/baseline_consolidated.geojson ← MAIN SOURCE (10,570 places)

/map/backend/agents/
  stb_agent.py                    ← ❌ Calls fake API
  listing_agent.py                ← ❌ 100% hardcoded
  delivery_agent.py               ← ⏳ Ready for real keys
  yelp_agent.py                   ← ✅ Real API (duplicate with listing_agent)
```

---

## 💡 Next Actions
1. Update stb_agent.py to load geojson locally
2. Remove listing_agent.py (duplicate)
3. Configure foodpanda/deliveroo keys
4. Test full pipeline
