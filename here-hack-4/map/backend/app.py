# pyre-ignore-all-errors
# ============================================================================
# PlaceIQ Singapore — FastAPI Main Application
# ============================================================================
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ── Agents ──
from backend.agents.orchestrator import OrchestratorAgent
from backend.agents.baseline_agent import BaselineAgent
from backend.agents.gov_agent import GovDataAgent
from backend.agents.website_agent import WebsiteExtractionAgent
from backend.agents.discussion_agent import DiscussionEvidenceAgent
from backend.agents.discovery_agent import NewPlaceDiscoveryAgent
from backend.agents.visual_agent import VisualVerificationAgent
from backend.agents.matching_agent import MatchingAgent
from backend.agents.fusion_agent import FusionAgent
from backend.agents.decision_agent import DecisionAgent
from backend.agents.review_agent import ReviewAgent
from backend.agents.tripadvisor_agent import TripAdvisorAgent

# Dropped agents (no usable public developer API / fabricated data):
#   social_agent  — Instagram Graph API can't search arbitrary businesses
#   delivery_agent— foodpanda/Deliveroo have no public dev API (Deliveroo left SG)
#   yelp_agent    — POI competitor to HERE; weak Singapore coverage
#   stb_agent     — STB/TIH Open API was discontinued 31 Jul 2025

# ── Routes ──
from backend.api.baseline_routes import router as baseline_router
from backend.api.pipeline_routes import router as pipeline_router
from backend.api.review_routes import router as review_router
from backend.api.place_detail_routes import router as place_detail_router
from backend.api.vision_routes import router as vision_router
from backend.api.nlp_routes import router as nlp_router

# ── State ──
from backend.app_state import set_baseline_agent, set_orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("placeiq")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== PlaceIQ Singapore — Starting ===")

    # Build agent graph
    baseline_agent = BaselineAgent()
    _ = baseline_agent.places  # Force load

    orchestrator = OrchestratorAgent()
    orchestrator.register(baseline_agent)
    # Evidence agents (real Singapore sources)
    orchestrator.register(GovDataAgent())
    orchestrator.register(WebsiteExtractionAgent())
    orchestrator.register(DiscussionEvidenceAgent())
    orchestrator.register(VisualVerificationAgent())
    orchestrator.register(TripAdvisorAgent())
    # Discovery (new places not on the map)
    orchestrator.register(NewPlaceDiscoveryAgent())
    # Reasoning agents
    orchestrator.register(MatchingAgent())
    orchestrator.register(FusionAgent())
    orchestrator.register(DecisionAgent())
    orchestrator.register(ReviewAgent())

    set_baseline_agent(baseline_agent)
    set_orchestrator(orchestrator)

    log.info(f"Baseline loaded: {len(baseline_agent.places)} places")
    log.info(f"Agents registered: {list(orchestrator._agents.keys())}")

    yield

    log.info("=== PlaceIQ Singapore — Shutting down ===")


app = FastAPI(
    title="PlaceIQ Singapore",
    description="Agentic Place Intelligence Platform for Singapore",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration
app.include_router(baseline_router)
app.include_router(pipeline_router)
app.include_router(review_router)
app.include_router(place_detail_router)
app.include_router(vision_router)
app.include_router(nlp_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "PlaceIQ Singapore"}


# Serve frontend static build if it exists
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
