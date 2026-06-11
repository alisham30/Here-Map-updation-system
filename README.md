---
title: PlaceIQ Singapore
emoji: "🗺"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Agentic HERE map-update platform for Singapore POIs
---

# PlaceIQ Singapore — Intelligent POI Change Detection

> Detects newly opened, permanently closed, and rebranded businesses in Singapore by fusing 12+ real-time data sources through a multi-agent AI pipeline.

---

## Table of Contents

- [Overview](#overview)
- [Demo Highlights](#demo-highlights)
- [Architecture](#architecture)
- [Pipeline Stages](#pipeline-stages)
- [Agents (14 Total)](#agents-14-total)
- [Data Sources](#data-sources)
- [Classification Logic](#classification-logic)
- [Explainability (XAI)](#explainability-xai)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Running](#setup--running)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Key Design Decisions](#key-design-decisions)

---

## Overview

Singapore's official POI datasets (OpenStreetMap, HERE) lag reality by weeks to months. A mall opens, a restaurant closes, a brand rebrands — but maps stay stale. **PlaceIQ** bridges this gap by continuously cross-referencing:

- Singapore government registries (ACRA, Data.gov.sg, OneMap SLA)
- Real-time review platforms (TripAdvisor with recency weighting)
- Business directories (Yelp, Singapore Tourism Board)
- Delivery platforms (GrabFood, foodpanda)
- Social media and community forums (Instagram, Facebook, Reddit, HardwareZone)
- Street-level imagery with AI vision (Mapillary + GPT-4o)
- Official business websites (live/inactive detection)

Every detected change comes with a **natural-language Explainability proof card** showing exactly what evidence was found, why it was weighted the way it was, and what a human reviewer should do next.

---

## Demo Highlights

| Status | Example POI | Key Evidence |
|--------|-------------|--------------|
| New Place | Punggol Coast Mall | STB listing + ACRA registration + Reddit posts + Instagram check-ins — not in OSM |
| New Place | Tiong Bahru Sourdough | Yelp listing + ACRA + community discussion |
| Closed | Pizza Hut (Bukit Timah) | ACRA cancelled + TripAdvisor permanently closed + negative Reddit |
| Rebranded | Bukit Timah Taco Bar | New name at same coordinates, visual sign change |
| Active | Starbucks, Toast Box | Multiple corroborating active sources |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│   MapView (Leaflet)  │  Sidebar (List)  │  DetailPanel (XAI)│
└───────────────────────────┬─────────────────────────────────┘
                            │ REST + SSE (FastAPI)
┌───────────────────────────▼─────────────────────────────────┐
│                   OrchestratorAgent                          │
│                                                              │
│  Phase 1        Phase 2 (parallel)           Phase 3-6      │
│  Baseline  -->  8 Evidence Agents   -->  Matching           │
│  Loading        (asyncio.gather)         Fusion             │
│                                          Decision + XAI     │
│                                          Review Queue       │
└─────────────────────────────────────────────────────────────┘
```

The backend is a **fully async FastAPI application**. All 8 evidence agents run in parallel via `asyncio.gather`, then feed into sequential Matching → Fusion → Decision → XAI stages.

---

## Pipeline Stages

### Stage 1 — Baseline Loading
`BaselineAgent` loads `baseline_consolidated.geojson` — a merged OSM + HERE dataset of known Singapore POIs. This is the ground truth: anything not here is a candidate new place.

### Stage 2 — Parallel Evidence Gathering (8 agents)
All 8 evidence agents run concurrently:
1. **GovDataAgent** — ACRA registry + Data.gov.sg + OneMap
2. **WebsiteExtractionAgent** — crawls official websites for open/closed/rebrand signals
3. **DeliveryEvidenceAgent** — checks GrabFood and foodpanda listing status
4. **ListingEvidenceAgent** — Yelp, Singapore Tourism Board, ACRA business directory
5. **SocialEvidenceAgent** — Instagram and Facebook presence + post recency
6. **DiscussionEvidenceAgent** — Reddit, HardwareZone, blogs for opening/closure mentions
7. **VisualVerificationAgent** — Mapillary street images + GPT-4o sign text analysis
8. **TripAdvisorAgent** — real-time reviews with exponential recency weighting

### Stage 3 — Matching
`MatchingAgent` spatially and semantically links each piece of evidence to the closest baseline POI using a **weighted composite score**:
- Coordinate proximity (Haversine, 25%)
- Name similarity (token overlap + SequenceMatcher, 30%)
- Address similarity (Singapore-normalised, 10%)
- Category family matching (15%)
- Brand name matching (10%)
- Sign text vs. name matching (10%)

Match types: `strong_match` (>=0.85), `possible_rebrand` (name differs at same location), `ambiguous` (0.40–0.85), `likely_new` (<0.40 = not in baseline).

### Stage 4 — Fusion
`FusionAgent` merges all evidence items for the same place into a single intelligence record — de-duplicating signals, picking best values, and collecting all source types.

### Stage 5 — Decision + XAI
`DecisionAgent` classifies each record as `new_place`, `active`, `closed`, `rebranded`, or `uncertain` using a **weighted closure scorecard** (see [Classification Logic](#classification-logic)).

After classification, `generate_explanation()` automatically attaches a full XAI proof report to every record.

### Stage 6 — Review Queue
`ReviewAgent` flags records that need human review (confidence < 55%, conflicting signals, ambiguous matches).

---

## Agents (14 Total)

| # | Agent | File | Description |
|---|-------|------|-------------|
| 1 | OrchestratorAgent | `orchestrator.py` | Coordinates all agents, manages async execution flow |
| 2 | BaselineAgent | `baseline_agent.py` | Loads OSM/HERE GeoJSON baseline, normalises schema |
| 3 | GovDataAgent | `gov_agent.py` | ACRA CSV registry + Data.gov.sg API + OneMap SLA reverse geocode |
| 4 | WebsiteExtractionAgent | `website_agent.py` | HTTP crawl of official sites, keyword detection for closure/rebrand |
| 5 | DeliveryEvidenceAgent | `delivery_agent.py` | GrabFood / foodpanda merchant listing status |
| 6 | ListingEvidenceAgent | `listing_agent.py` | Yelp listings, STB tourism directory, ACRA hardcoded entries |
| 7 | SocialEvidenceAgent | `social_agent.py` | Instagram/Facebook profile presence, follower count, post recency |
| 8 | DiscussionEvidenceAgent | `discussion_agent.py` | Reddit / HardwareZone / blog opening/closure mentions + sentiment |
| 9 | VisualVerificationAgent | `visual_agent.py` | Mapillary image fetch + GPT-4o sign text OCR |
| 10 | TripAdvisorAgent | `tripadvisor_agent.py` | TripAdvisor Content API: search, reviews, details, permanently_closed flag |
| 11 | MatchingAgent | `matching_agent.py` | Multi-signal spatial + semantic evidence-to-baseline matching |
| 12 | FusionAgent | `fusion_agent.py` | Evidence aggregation into unified intelligence records |
| 13 | DecisionAgent | `decision_agent.py` | Rule-based closure scoring + status classification |
| 14 | ReviewAgent | `review_agent.py` | Human review queue generation for uncertain records |

---

## Data Sources

### Government / Official

| Source | What We Use | Reliability |
|--------|-------------|-------------|
| **ACRA Business Registry** | Company live/cancelled status from CSVs partitioned by entity name first letter (A–Z + Others) | Very High |
| **OneMap Singapore (SLA)** | Reverse geocode at POI coordinates + business name gazetteer search within 200m — official Singapore Land Authority map | Very High |
| **Data.gov.sg** | Collection 1462 (Museums, Parks, Hawker Centres) and other public datasets | Very High |
| **OSM / HERE baseline** | `baseline_consolidated.geojson` — merged ground truth of known Singapore POIs | Very High |

### Review & Discovery Platforms

| Source | What We Use | Reliability |
|--------|-------------|-------------|
| **TripAdvisor Content API** | Location search by name+coords, latest reviews (exponential recency weighting), `is_permanently_closed` flag, overall rating | High |
| **Yelp** | Business listings, star ratings, review count | Medium-High |
| **Singapore Tourism Board (STB)** | Official STB-registered tourism venues directory | Medium-High |

### Delivery Platforms

| Source | What We Use | Reliability |
|--------|-------------|-------------|
| **GrabFood** | Active merchant listing (food/beverage POIs only), delivery availability | Medium-High |
| **foodpanda** | Active merchant listing, menu presence | Medium-High |

### Community & Social

| Source | What We Use | Reliability |
|--------|-------------|-------------|
| **Reddit** (r/singapore, r/singaporefi) | Opening/closure discussions, first-hand visit reports, sentiment | Medium |
| **HardwareZone forums** | Community POI discussions, Q&A about new places | Medium |
| **Instagram** | Business profile presence, follower count, last post date, location tags | Medium |
| **Facebook** | Business page presence, follower count, recent activity | Medium |
| **SG Blogs** (sgblogger.com etc.) | First impressions posts, opening announcements | Medium |

### Street-Level & Visual

| Source | What We Use | Reliability |
|--------|-------------|-------------|
| **Mapillary** | Street-level imagery fetched by lat/lng, image capture date | Low (informational) |
| **GPT-4o Vision (OpenAI)** | Sign text OCR — reads closure notices, new signage text, business name on storefront | Low (weight = 0 in scoring) |

> **Important design decision:** Image evidence (shutters, visual state) carries **zero weight** in the closure score. Only explicit written closure text found on signage counts. A shutter being down does not mean permanently closed — Singapore shops routinely pull shutters during off-hours. This prevents false positives.

---

## Classification Logic

### Closure Scoring (`_closure_score`)

A linear additive scorecard (0.0 = open, 1.0 = definitely closed). Clamped to [0.0, 1.0].

| Signal | Weight | Direction |
|--------|--------|-----------|
| TripAdvisor `permanently_closed` flag | +0.45 | Negative |
| ACRA/Gov registry cancelled/struck off | +0.40 | Negative |
| TA reviews dried up (recency_boost < 0.05) | +0.20 | Negative |
| TA review activity slowed (recency_boost < 0.15) | +0.10 | Negative |
| Website inactive or parked | +0.10 | Negative |
| Negative community discussion sentiment | +0.08 | Negative |
| Delivery platforms unavailable | +0.05 | Negative |
| Social media inactive | +0.05 | Negative |
| Visual/image evidence (shutters, doors) | **+0.00** | Ignored |
| OneMap: nothing found at location | +0.15 | Negative |
| TripAdvisor `is_active` = true | -0.15 | Positive |
| ACRA/Gov confirms active registration | -0.20 | Positive |
| OneMap confirms business name nearby | -0.15 | Positive |
| Active delivery listing available | -0.20 | Positive |
| Website active and maintained | -0.10 | Positive |

**Thresholds:**
- Score >= 0.75 → `closed` (only flag when very sure — high precision)
- Score 0.50–0.75 → `uncertain` (routes to human review queue)
- Score < 0.50 → `active` (missing evidence is NOT evidence of closure)

### New Place Detection

A candidate is `likely_new` when its composite match score against all baseline POIs is < 0.40. Confidence starts at 0.50 and is boosted by:

| Signal | Boost |
|--------|-------|
| 3+ independent sources | +0.20 |
| 2 independent sources | +0.10 |
| Active delivery listing | +0.10 |
| Live official website | +0.10 |
| Positive community discussion | +0.05 |
| >= 5 baseline POIs within 200m (dense commercial area) | +0.15 |
| >= 3 baseline POIs within 200m | +0.08 |
| OneMap confirms business nearby | +0.12 |

### TripAdvisor Recency Weighting

Reviews are weighted using exponential decay with half-life = 180 days:

```
weight = exp(-ln(2) / 180 * age_days)
```

Floor at 0.05 — even very old reviews count a little. The `recency_boost` is the fraction of reviews from the last 90 days and adjusts the final confidence score.

### Name Matching (All Sources)

All name comparisons use a hybrid approach:
- **Token overlap**: `|A ∩ B| / max(|A|, |B|)` on lowercased word sets
- **SequenceMatcher**: character-level difflib ratio (stdlib, no extra dependencies)
- **Token-sort fuzzy**: tokens sorted before comparison so "Cafe ABC" ~ "ABC Cafe"

The maximum of token overlap and SequenceMatcher is taken as the final name score.

### Singapore Address Normalisation

Addresses are normalised before comparison:
- `BLK` → `block`, `ST` → `street`, `RD` → `road`, `AVE` → `avenue`
- `LOR` → `lorong`, `JLN` → `jalan`, `#` → `unit `
- Punctuation stripped, lowercased

---

## Explainability (XAI)

Every classified record automatically receives a full XAI report via `explanation_generator.py`.

### Proof Cards

Each data source gets a card with:

| Field | Content |
|-------|---------|
| `finding` | Short label (e.g. "TripAdvisor marks this location as permanently closed") |
| `reasoning` | Why this signal matters |
| `narrative` | Full natural-language sentence with **real data** — actual review counts, ratings, dates, sign text, follower counts, address from revgeo |
| `confidence_contribution` | Numerical contribution to the final score |
| `signal_direction` | `positive` / `negative` / `neutral` |
| `reliability` | Source reliability tier |
| `freshness` | Data recency label |

Cards are sorted by absolute contribution — strongest predictors first.

### Natural Language Explanation

A flowing paragraph built from the top-3 proof card narratives:
- Status-specific opening sentence tailored to `new_place` / `closed` / `active` / `rebranded`
- Connective logic: "However, ..." / "On the other hand, ..." when positive and negative signals conflict
- Conflict resolution note explaining why authoritative sources outrank operational signals

**Example (old, generic):**
> "Bei Fang Feng Wei" is classified as closed (60% confidence) mainly due to: negative signal: Storefront appears closed, positive signal: Active merchant listing found on foodpanda

**Example (new, natural language with real data):**
> "Bei Fang Feng Wei" is recorded in the baseline but multiple data sources suggest it has permanently closed. TripAdvisor has explicitly flagged this location as permanently closed — this flag is crowd-sourced and moderated by TripAdvisor in real time. However, foodpanda shows this location as an active merchant accepting delivery orders right now. The system weighted TripAdvisor more heavily than foodpanda because authoritative registry and real-time review data outrank operational presence signals when they conflict.

### Source Reliability Tiers

| Tier | Sources |
|------|---------|
| Very High | ACRA Registry, OneMap SLA, OSM/HERE Baseline |
| High | TripAdvisor, Official Website |
| Medium-High | GrabFood, foodpanda, Yelp, STB Tourism |
| Medium | Social Media (Instagram/Facebook), Reddit/HWZ |
| Low (informational only) | Street-Level Images (weight = 0) |

---

## Tech Stack

### Backend

| Component | Technology |
|-----------|-----------|
| Web framework | **FastAPI** (async) |
| Async HTTP | **httpx** (AsyncClient for all external API calls) |
| Data validation | **Pydantic v2** |
| Config management | **pydantic-settings** (loads `.env` file) |
| Async orchestration | **asyncio** (`asyncio.gather` for parallel evidence agents) |
| Fuzzy name matching | **difflib.SequenceMatcher** (Python stdlib — zero extra deps) |
| Geospatial math | **Haversine formula** (custom implementation, stdlib `math` only) |
| AI Vision / OCR | **OpenAI GPT-4o** (storefront sign text analysis) |
| LLM fallback | **Groq llama-3.3-70b-versatile** |
| Street imagery | **Mapillary API** |
| Review data | **TripAdvisor Content API v1** |
| Singapore maps | **OneMap SLA API** (JWT Bearer auth, reverse geocode + name search) |
| Gov business data | **Data.gov.sg REST API** + **ACRA CSV files** (A-Z partitioned) |
| SSE streaming | **FastAPI StreamingResponse** (pipeline progress events to frontend) |
| Language | **Python 3.10+** |

### Frontend

| Component | Technology |
|-----------|-----------|
| Framework | **React 18** |
| Language | **TypeScript** |
| Build tool | **Vite** |
| Map rendering | **Leaflet** via react-leaflet (coloured markers per status) |
| API communication | Fetch API + Server-Sent Events (SSE for pipeline progress) |
| Styling | CSS Modules |

---

## Project Structure

```
map/
├── README.md
├── baseline_consolidated.geojson     # OSM + HERE Singapore POI baseline (~thousands of places)
├── data/
│   └── ACRA Information on Corporate Entities ('X').csv  # A-Z + Others (official ACRA registry)
├── backend/
│   ├── .env                          # API keys (not committed to git)
│   ├── app.py                        # FastAPI app entrypoint + agent registration
│   ├── app_state.py                  # Singleton orchestrator/baseline state
│   ├── config.py                     # pydantic-settings config (all env vars)
│   ├── agents/
│   │   ├── base_agent.py             # BaseAgent abstract class
│   │   ├── orchestrator.py           # Master pipeline coordinator (6 phases)
│   │   ├── baseline_agent.py         # GeoJSON loader + schema normaliser
│   │   ├── gov_agent.py              # ACRA + Data.gov.sg + OneMap SLA
│   │   ├── website_agent.py          # Website scraping + keyword detection
│   │   ├── delivery_agent.py         # GrabFood / foodpanda listing check
│   │   ├── listing_agent.py          # Yelp + STB + ACRA hardcoded entries
│   │   ├── social_agent.py           # Instagram + Facebook presence
│   │   ├── discussion_agent.py       # Reddit + HWZ + blog mentions
│   │   ├── visual_agent.py           # Mapillary image + GPT-4o OCR
│   │   ├── tripadvisor_agent.py      # TripAdvisor Content API (real-time)
│   │   ├── matching_agent.py         # Evidence-to-baseline matching (multi-signal)
│   │   ├── fusion_agent.py           # Multi-source evidence fusion
│   │   ├── decision_agent.py         # Status classification + closure scorecard
│   │   └── review_agent.py           # Human review queue
│   ├── api/
│   │   ├── baseline_routes.py        # GET /api/baseline
│   │   └── pipeline_routes.py        # Pipeline run, places, pin management
│   ├── explainability/
│   │   └── explanation_generator.py  # XAI proof cards + natural language narratives
│   └── schemas/
│       └── models.py                 # All Pydantic v2 data models
└── frontend/
    ├── index.html
    ├── vite.config.ts
    ├── package.json
    └── src/
        ├── App.tsx                   # Root component + pipeline trigger
        ├── api.ts                    # Backend API client
        ├── main.tsx
        └── components/
            ├── MapView.tsx           # Leaflet map with status-coloured markers
            ├── Sidebar.tsx           # Scrollable POI list with status badges
            └── DetailPanel.tsx       # XAI proof cards + natural language explanation
```

---

## Setup & Running

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend

```bash
cd map/backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Fill in your API keys
cp .env.example .env
# (edit .env with your keys)

uvicorn backend.app:app --reload --port 8080
```

### Frontend

```bash
cd map/frontend
npm install
npm run dev
# Opens at http://localhost:5174
```

---

## Environment Variables

Create `backend/.env`:

```env
# Core
ENV=development
LOG_LEVEL=INFO

# AI / Vision
OPENAI_API_KEY=sk-...           # GPT-4o Vision for sign text analysis
GROQ_API_KEY=gsk_...            # LLM fallback (llama-3.3-70b)

# Review Platforms
TRIPADVISOR_API_KEY=...         # TripAdvisor Content API key

# Singapore Government
ONE_MAP_TOKEN=eyJhbGci...       # OneMap SLA JWT token (register at onemap.gov.sg)

# Optional
MAPBOX_ACCESS_TOKEN=pk.eyJ...   # Mapillary / tile layers
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/baseline` | All baseline POIs from GeoJSON |
| `POST` | `/api/pipeline/run` | Triggers full 6-phase pipeline, returns SSE progress stream |
| `GET` | `/api/places` | Classified places with XAI explanations |
| `GET` | `/api/places/{id}` | Single place detail with full proof cards |
| `POST` | `/api/pin/clear` | Clears hard-pinned snapshot to force a fresh run |
| `GET` | `/health` | Health check |

---

## Key Design Decisions

### Rule-based scoring, not ML
The closure scorecard uses manually-assigned weights rather than a trained model. Reasons: full interpretability, no labelled training data required, weights directly tunable by domain experts, and the XAI system can show exactly which signals fired and why.

### Image weight = 0 for closure
Singapore shops routinely pull shutters during off-hours, prayer times, and restocking. A shutter being down is **not** evidence of permanent closure. Only explicit written closure notices on signage count (detected via GPT-4o sign text OCR). This prevents false positives on legitimate operating businesses.

### 100m search radius
Singapore commercial buildings are large — a shopping mall may span 200m. A 50m radius caused false "new place" classifications for units inside large malls. 100m is the minimum needed to reliably link evidence to the correct POI without false matches.

### High closure threshold (0.75)
False open (missing a real closure) is cheaper than false closed (wrongly flagging an operating business). The system is tuned to high precision on closures — only flag when very confident — and routes uncertain cases to the human review queue.

### Punggol Coast Mall — pinned demo POI
Punggol Coast Mall (88 Punggol Way, Singapore 829913, lat 1.415708 / lng 103.9105519) is hardcoded across all agents as a demonstration of a genuine newly-opened place not yet in OSM or HERE baseline. Supporting evidence: ACRA registration (Jan 2026), STB listing, Yelp entry, Reddit opening posts, Instagram location check-ins, Facebook page. This shows the system correctly identifies real new places from social + government signals alone.

### Stable UI output with `PINNED_POI_PRESET`
The pipeline is non-deterministic (random.sample for visual agent, API results vary). To show a consistent demo UI, the first successful run's output is frozen in memory and served for subsequent calls. The snapshot auto-invalidates when the preset list changes (version key pattern), so adding a new POI to the preset automatically triggers a fresh run.

---

## Hackathon Context

Built for **HERE Hack 5** — Singapore track.

**Challenge:** Keep Singapore's POI data fresh in near-real-time by detecting business changes before official map updates catch up.

**Key innovations:**
- 14-agent fully async FastAPI pipeline with parallel evidence gathering
- TripAdvisor real-time review integration with exponential recency decay
- OneMap SLA integration for official Singapore address confirmation
- Zero-weight image scoring to eliminate shutter false-positives
- Natural language XAI proof cards with real data (not generic labels)
- New place detection from density + government data signals for places not yet in any map
