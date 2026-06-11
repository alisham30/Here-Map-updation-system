# Deploying PlaceIQ to Hugging Face Spaces

This repo is ready to deploy as a **Docker Space**. The `Dockerfile` builds the
React frontend and runs the FastAPI server (API + UI) on port **7860**.

## 1. Create the Space
1. Go to https://huggingface.co/new-space
2. **Owner**: your account · **Space name**: `placeiq-singapore`
3. **SDK**: choose **Docker** → **Blank**
4. **Hardware**: `CPU basic` (free) is enough — the server needs no GPU.
5. Create the Space.

## 2. Add your API keys as Secrets (NOT a committed .env)
In the Space → **Settings → Variables and secrets → New secret**, add each:

| Secret name | Needed for |
|---|---|
| `OPENAI_API_KEY` | XAI, NLP search, GPT-4o vision |
| `TRIPADVISOR_API_KEY` | closure flags + review recency |
| `ONE_MAP_TOKEN` | official SG existence check |
| `DATA_GOV_SG_API_KEY` | gov datasets |
| `MAPILLARY_ACCESS_TOKEN` | street imagery for vision |
| `MAPBOX_ACCESS_TOKEN` | map tiles |
| `FETCHLAYER_API_KEY` | Reddit discussion (optional) |

Any you omit → that agent skips cleanly.

## 3. Push the code to the Space
A Space is its own git repo. From this project folder:

```bash
# Log in once (use an HF access token from huggingface.co/settings/tokens)
pip install huggingface_hub
huggingface-cli login

# Add the Space as a remote and push
git remote add hf https://huggingface.co/spaces/<your-username>/placeiq-singapore
git push hf main
```

(If the Space was created with an initial commit, use `git push hf main --force`
the first time.)

HF will build the Docker image and start the app. Open the Space URL → you'll see
the PlaceIQ UI. Click **Run Pipeline**.

## Notes
- **ACRA CSVs (646MB)** are not shipped (too large). Without them, ACRA-registry
  closure signals are skipped; OneMap + TripAdvisor + website closures still work.
  To enable ACRA, attach persistent storage and upload the CSVs to
  `here-hack-4/map/data/`.
- **State is in-memory** — a Space restart clears pipeline results (just re-run).
- The image is **slim** (no torch); the on-demand GradCAM overlay is disabled in
  this build but the core vision (Mapillary + GPT-4o sign reading) runs fully.
- The app listens on **7860** (set via `app_port` in `README.md`).
