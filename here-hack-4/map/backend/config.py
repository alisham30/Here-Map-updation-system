# pyre-ignore-all-errors
# ============================================================================
# Application Configuration & Environment Variables
# ============================================================================
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure absolute paths resolve relative to this file
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """
    Centralized configuration managed by pydantic-settings.
    Validates and loads environment variables from backend/.env
    """
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Context & Environment
    env: str = "development"
    log_level: str = "INFO"

    # Ports
    backend_port: int = 8080
    frontend_port: int = 5174

    # Core Paths
    baseline_geojson_path: str = str(PROJECT_ROOT / "baseline_consolidated.geojson")
    
    # Optional 3rd Party API Keys (Agent integration)
    openai_api_key: str | None = None
    mapbox_access_token: str | None = None
    mapillary_access_token: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    tripadvisor_api_key: str | None = None
    one_map_token: str | None = None
    
    # Singapore-specific APIs (NEW)
    yelp_api_key: str | None = None
    foodpanda_client_id: str | None = None
    foodpanda_client_secret: str | None = None
    deliveroo_api_key: str | None = None
    stb_api_key: str | None = None
    data_gov_sg_api_key: str | None = None
    instagram_app_id: str | None = None
    instagram_app_secret: str | None = None
    instagram_client_token: str | None = None

    # Community discussion (Reddit). Primary path: fetchlayer.dev Reddit search.
    # Optional official path: Reddit OAuth "script" app credentials.
    fetchlayer_api_key: str | None = None
    fetchlayer_base_url: str = "https://fetchlayer.dev/api"
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "placeiq-singapore/1.0"

    # Extraction Settings
    request_timeout_seconds: int = 15
    max_retries: int = 2
    
    # Pipeline Processing Settings
    # BATCH_SIZE: Places processed per run (500 = ~3-5 min, 1000 = ~6-10 min, 10+ min = >1000)
    # Stratified by geography to ensure all Singapore regions covered
    pipeline_batch_size: int = 500  # Optimal for fast parallel evidence gathering
    # Return output limit (set to -1 for all records, or specify max records to display)
    pipeline_output_limit: int = 200  # Balance: enough for UI, not overwhelming

    # Demo mode: when True, the UI list is force-balanced to a fixed status mix /
    # pinned preset for a stable presentation. Default False → show REAL pipeline
    # results (honest, varies run-to-run). Flip via PIPELINE_DEMO_MODE=true.
    pipeline_demo_mode: bool = False

# Constants mapped directly from previous versions
HERE_DIR = str(PROJECT_ROOT / "here")
MATCH_STRONG = 0.85
MATCH_MODERATE = 0.55
MATCH_WEAK = 0.40
SEARCH_RADIUS_M = 100.0   # Singapore buildings are large; 100m avoids false-closed

# PIPELINE PROCESSING NOTES:
# ==============================
# Stratified Batch Processing: Divides Singapore into 3 geo-bands (N/Central/S)
# and samples proportionally from each to ensure geographic diversity.
#
# Processing time estimates (with 8 parallel agents):
# - 500 places  → ~3-5 min (RECOMMENDED for demo/testing)
# - 1000 places → ~6-10 min (fuller detection)
# - 2000+ places → 10+ min (comprehensive, but long wait time)
#
# To get COMPLETE closure inventory across all of Singapore:
# Option A: Run pipeline 20x with stratified 500-place batches (covers all areas)
# Option B: Increase BATCH_SIZE but accept longer runtime
# Option C: Run custom endpoint with explicit lat/lng region bounds


# Singleton Settings Instance
settings = Settings()

# Setup logging automatically based on config
import logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
