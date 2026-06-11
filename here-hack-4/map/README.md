# PlaceIQ Singapore 🇸🇬 — Agentic Geospatial Intelligence

PlaceIQ is a production-grade, Google-free spatial intelligence platform for Singapore. It automatically detects new places, closed businesses, and rebranded storefronts by cross-referencing official Singapore datasets (`data.gov.sg`, ACRA registries) and scraping alternative aggregator signals (foodpanda, GrabFood).

A native **Multi-Source Decision Engine** uses Generative AI (GPT-4o Vision) and XAI (Explainable AI) to generate human-readable confidence scores and "Proof Cards" for every flagged change.

## 🚀 Architecture overview
1. **Frontend**: React + Vite (Port 5174). Features Leaflet Marker Clustering, Map `flyTo` tracking, and zero-latency XAI side-panels.
2. **Backend**: FastAPI (Port 8080). Coordinates 8+ parallel Evidence Agents (`GovDataAgent`, `VisionAgent`, `DeliveryAggregationAgent`) and fuses the signals.

## 💻 How to Run Locally

### 1. Requirements
* NodeJS (`npm`)
* Python 3.10+
* An OpenAI API Key (For the Vision & Decision Agents)
* A Mapbox API Token (For the Map visual tiles)

### 2. Setup the Backend
Open a terminal in the root directory:
```bash
# Optional: Create a virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate # Mac/Linux

# Install dependencies
pip install "fastapi[all]" httpx openai pydantic pydantic-settings

# Setup your Environment Variables
cp backend/.env.example backend/.env
# EDIT backend/.env and add your OPENAI_API_KEY and MAPBOX_ACCESS_TOKEN

# Start the server (runs on http://localhost:8080)
python -m uvicorn backend.app:app --reload --port 8080
```

### 3. Setup the Frontend
Open a *second* terminal window in the `frontend/` directory:
```bash
cd frontend
npm install

# Start the frontend dev server (runs on http://localhost:5174)
npm run dev
```

## 🗺️ How to Use the App
1. Open the app at `http://localhost:5174`.
2. Click **Run Pipeline** in the dashboard.
   * *Note: The system is configured to process a fast "demo batch" of ~15 places so it completes quickly without rate-limiting the data.gov.sg endpoints.*
3. When places load on the left sidebar, **click on a place** (e.g., "Tiong Bahru Bakery").
4. Watch the map dynamically fly to the location, and explore the **XAI Proof Cards** in the detail panel explaining *why* the place was flagged!
