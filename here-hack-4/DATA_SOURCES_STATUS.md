# PlaceIQ Data Sources Status

## ❌ CURRENTLY USING SIMULATED/FAKE DATA

| Agent | Source | Status | Issue |
|-------|--------|--------|-------|
| **Delivery** | GrabFood, foodpanda | ❌ FAKE | Using `random.random()` (70% chance, not real API) |
| **Social** | Instagram, Facebook | ❌ FAKE | Hardcoded entries + simulated followers |
| **Discussion** | Reddit, Google Maps Reviews | ❌ LIKELY FAKE | Simulated sentiment |
| **Listing** | Google Shopping | ❌ Unknown | Check listing_agent.py |

## ✅ REAL DATA (With proper config)

| Agent | Source | Status | Requires |
|-------|--------|--------|----------|
| **Gov** | ACRA + data.gov.sg | ✅ REAL | Local CSV files (included) |
| **TripAdvisor** | TripAdvisor API | ⚠️ CONFIGURED? | `TRIPADVISOR_API_KEY` in .env |
| **Visual** | Street View | ⚠️ CONFIGURED? | `OPENAI_API_KEY` for vision analysis |
| **Website** | Website Extraction | ⚠️ CONFIGURED? | OpenAI or Groq API key |

## 🔴 MISSING / NOT INTEGRATED

| Source | Why Missing |
|--------|------------|
| **Google Places API** | Not coded |
| **Yelp API** | Not coded |
| **Facebook Graph API** | Not coded |
| **Instagram Graph API** | Not coded |
| **Google Maps Reviews** | Not coded |

---

## What You Need to Set Up

Create `.env` file in `map/backend/` with:

```bash
# Required for real TripAdvisor data
TRIPADVISOR_API_KEY=your_key_here

# Required for real vision analysis (street view photos)
OPENAI_API_KEY=your_key_here

# Optional: Alternative LLM
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Optional: Real social/review scraping
# (Currently not implemented but can be added)
GOOGLE_MAPS_API_KEY=your_key_here
YELP_API_KEY=your_key_here

# Map rendering
MAPBOX_ACCESS_TOKEN=your_token_here
```

## How to Enable Real Data

### Step 1: Set up API Keys
Configure `.env` file with actual API credentials

### Step 2: Replace Simulated Agents
Remove `random.random()` calls and use real APIs:

**Before (delivery_agent.py):**
```python
if random.random() < 0.70:  # FAKE - 70% chance
    results.append(DeliveryEvidence(...))
```

**After (needs real GrabFood/foodpanda scraping):**
```python
response = await httpx.get("https://sg.search.grab.com/search?q=" + name)
# Parse real results
```

### Step 3: Add Missing Sources
Need to create new agents for:
- Google Places API
- Yelp API  
- Facebook/Instagram Graph APIs

---

## Quick Fix: Enable Available Real Sources Only

For NOW, focus on **REAL data** available:
1. ✅ **Gov Agent** - Already working (ACRA + data.gov.sg)
2. ⚠️ **TripAdvisor** - Works if you add API key
3. ⚠️ **Visual** - Works if you add OPENAI_API_KEY
4. ⚠️ **Website** - Works if you add API key

These 4 sources will give you **real evidence** without fakes.

---

**Want me to:**
1. Replace fake agents with no-op (skip simulation)?
2. Add real Yelp/Google Maps integration?
3. Set up proper config system for API keys?
