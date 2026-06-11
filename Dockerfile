# syntax=docker/dockerfile:1
# ============================================================================
# PlaceIQ Singapore — single-image deploy (Hugging Face Spaces / Docker)
# Builds the React frontend, then runs the FastAPI server which serves BOTH the
# API and the built UI on port 7860.
# ============================================================================

# ── Stage 1: build the React frontend → dist/ ───────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /fe
COPY here-hack-4/map/frontend/package*.json ./
# --legacy-peer-deps: react-leaflet-cluster@4 lists a React 19 peer, but the app
# runs fine on React 18 (as it does locally). Ignore the strict peer check.
RUN npm install --legacy-peer-deps
COPY here-hack-4/map/frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ─────────────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# Slim dependencies (no torch/geopandas; GradCAM lazy-skips if absent)
COPY requirements-hf.txt ./
RUN pip install --no-cache-dir -r requirements-hf.txt

# Application code (here-hack-4 holds both map/ and agent/). node_modules, .env,
# caches and the 646MB ACRA CSVs are excluded via .dockerignore.
COPY here-hack-4/ ./here-hack-4/

# Drop in the production frontend build from stage 1, where the backend serves it.
COPY --from=frontend /fe/dist ./here-hack-4/map/frontend/dist

# Writable cache dir for Mapillary imagery (HF runs the container writable).
RUN mkdir -p ./here-hack-4/imagery_cache && chmod -R 777 ./here-hack-4/imagery_cache

WORKDIR /app/here-hack-4/map
EXPOSE 7860
# HF injects your keys as env vars (Settings → Secrets); pydantic-settings reads them.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7860"]
