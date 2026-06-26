"""
Nextleap Zomato — Application Entry Point

Serves as both a FastAPI web server (default) and an interactive CLI.

Usage:
    # Web server (default)
    uvicorn src.main:app --reload --port 8000

    # Interactive CLI
    python src/main.py --cli
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
# Logging (configured before all imports)
# ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ─────────────────────────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    """Load dataset and build search index on startup; clean up on shutdown."""
    from src.config import print_config_summary
    from src.data.loader import load_data
    from src.data.preprocessor import preprocess, build_index

    logger.info("=" * 55)
    logger.info("  Nextleap Zomato — Starting Server")
    logger.info("=" * 55)

    print_config_summary()

    # Step 1: Load
    logger.info("Step 1/3: Loading dataset...")
    t = time.time()
    try:
        raw_df = load_data()
    except RuntimeError as e:
        logger.error("Dataset load failed: %s", e)
        raise RuntimeError(f"Cannot start server: {e}") from e
    logger.info("Dataset loaded in %.2fs (%d rows)", time.time() - t, len(raw_df))

    # Step 2: Preprocess
    logger.info("Step 2/3: Preprocessing...")
    t = time.time()
    clean_df = preprocess(raw_df)
    logger.info("Preprocessing done in %.2fs", time.time() - t)

    # Step 3: Build index
    logger.info("Step 3/3: Building search index...")
    t = time.time()
    index = build_index(clean_df)
    logger.info(
        "Index built in %.2fs — %d locations, %d cuisines",
        time.time() - t, len(index.locations), len(index.cuisines),
    )

    # Store in app state
    app.state.df         = clean_df
    app.state.index      = index
    app.state.start_time = time.time()

    logger.info("=" * 55)
    logger.info("  Server ready!  →  http://localhost:8000")
    logger.info("  API Docs       →  http://localhost:8000/docs")
    logger.info("=" * 55)

    yield  # ← application runs here

    logger.info("Server shutting down.")


# ── Create FastAPI app ──
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(
    title="Nextleap Zomato — AI Restaurant Recommendations",
    description=(
        "AI-powered restaurant recommendation service built with "
        "Groq LLM and the Zomato dataset. Filter by location, budget, "
        "cuisine, and rating — then let the LLM explain why each pick is perfect."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS (allow all origins for dev) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ──
from src.api.routes import router as api_router
app.include_router(api_router)

# ── Serve static frontend ──
STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        """Serve the Cinder AI web frontend."""
        return FileResponse(str(STATIC_DIR / "index.html"))

    # Also serve JS/CSS directly from root for convenience
    @app.get("/{filename:path}", include_in_schema=False)
    async def serve_static_file(filename: str):
        file_path = STATIC_DIR / filename
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Fall through to the frontend (SPA routing)
        return FileResponse(str(STATIC_DIR / "index.html"))
else:
    logger.warning("static/ directory not found at %s — frontend not served", STATIC_DIR)

    @app.get("/", include_in_schema=False)
    async def root_no_frontend():
        return {"message": "Nextleap Zomato API", "docs": "/docs"}


# ─────────────────────────────────────────────────────────────────
# CLI Mode (unchanged from Phase 1–3)
# ─────────────────────────────────────────────────────────────────

def _load_and_prepare():
    """Load dataset, preprocess, build index. Returns (clean_df, index)."""
    from src.config import print_config_summary
    from src.data.loader import load_data
    from src.data.preprocessor import preprocess, build_index

    print()
    print_config_summary()
    print()

    logger.info("Step 1/3: Loading dataset...")
    t = time.time()
    try:
        raw_df = load_data()
    except RuntimeError as e:
        logger.error("Failed to load dataset: %s", e)
        sys.exit(1)
    logger.info("Dataset loaded in %.2fs (%d rows)", time.time() - t, len(raw_df))

    logger.info("Step 2/3: Preprocessing...")
    t = time.time()
    clean_df = preprocess(raw_df)
    logger.info("Preprocessing complete in %.2fs", time.time() - t)

    logger.info("Step 3/3: Building search index...")
    t = time.time()
    index = build_index(clean_df)
    logger.info("Index built in %.2fs", time.time() - t)

    print()
    print("=" * 60)
    print("  Dataset Summary")
    print("=" * 60)
    print(f"  Total restaurants : {len(clean_df):,}")
    print(f"  Unique locations  : {len(index.locations):,}")
    print(f"  Unique cuisines   : {len(index.cuisines):,}")
    print(f"  Rating range      : {clean_df['rating'].min():.1f} – {clean_df['rating'].max():.1f}")
    print("=" * 60)
    print()

    return clean_df, index


def _collect_preferences(index):
    from src.models.user_preferences import UserPreferences, ValidationError
    print()
    print("=" * 60)
    print("  Restaurant Recommendation — Enter Your Preferences")
    print("=" * 60)
    print()

    # Location
    print("  Type 'list' to see locations, 'quit' to exit.")
    while True:
        location = input("  Location: ").strip()
        if location.lower() == "quit":   return None
        if location.lower() == "list":
            print("  Locations:", ", ".join(index.locations[:20]), "...")
            continue
        if location:                     break
        print("  Location is required.")

    # Budget
    while True:
        budget = input("  Budget (low/medium/high): ").strip().lower()
        if budget == "quit":             return None
        if budget in ("low","medium","high"): break
        print("  Must be low, medium, or high.")

    # Cuisine
    cuisine_input = input("  Cuisine (optional, Enter to skip): ").strip()
    cuisine = cuisine_input or None

    # Rating
    while True:
        r = input("  Min Rating (0–5, Enter to skip): ").strip()
        if r.lower() == "quit":          return None
        if not r:                        min_rating = 0.0; break
        try:
            min_rating = float(r)
            if 0 <= min_rating <= 5:     break
        except ValueError:               pass
        print("  Enter a number 0.0–5.0.")

    additional = input("  Additional notes (Enter to skip): ").strip() or None

    try:
        prefs = UserPreferences(location=location, budget=budget,
                                cuisine=cuisine, min_rating=min_rating,
                                additional_preferences=additional)
    except ValueError as e:
        print(f"  Invalid input: {e}")
        return None

    try:
        warnings = prefs.validate(index.locations, index.cuisines)
        for w in warnings: print(f"  Warning: {w}")
    except ValidationError as e:
        print(f"  Error: {e.message}")
        return None

    return prefs


def _print_recommendations(response):
    if response.filters_relaxed:
        print("\n  Filters were relaxed:", ", ".join(response.filters_relaxed))
    if response.is_fallback:
        print("  AI explanations unavailable — showing data-based results.")
    if not response.recommendations:
        print("  No restaurants found. Try different criteria.")
        return
    if response.summary:
        print(f"\n  {response.summary}\n")
    for rec in response.recommendations:
        cuisines_str = ", ".join(rec.cuisines[:3])
        cost_str = f"Rs.{int(rec.cost_for_two):,}" if rec.cost_for_two else "N/A"
        print(f"\n  #{rec.rank}  {rec.name}")
        print(f"      {rec.rating}/5.0  |  {cost_str}  |  {cuisines_str}")
        if rec.explanation:
            print(f"      {rec.explanation}")
        print("  " + "-" * 56)


def run_cli(clean_df, index):
    """Run interactive CLI loop."""
    from src.services.recommendation_service import get_recommendations
    from src.services.llm_service import check_api_key

    print("\n" + "=" * 60)
    print("  Nextleap Zomato — AI Restaurant Recommendation CLI")
    if check_api_key():
        print("  Groq API key configured — AI explanations enabled")
    else:
        print("  No Groq API key — using data-based recommendations")
    print("=" * 60)

    while True:
        prefs = _collect_preferences(index)
        if prefs is None:
            print("\n  Goodbye!\n")
            break

        print("\n  Generating AI-powered recommendations...\n")
        response = get_recommendations(prefs, clean_df, index)
        _print_recommendations(response)

        again = input("\n  Search again? (yes/no): ").strip().lower()
        if again not in ("yes", "y", ""):
            print("\n  Goodbye!\n")
            break


def main() -> None:
    """Main entry point: runs CLI if --cli flag present, otherwise prints usage."""
    if "--cli" in sys.argv:
        clean_df, index = _load_and_prepare()
        run_cli(clean_df, index)
    else:
        print()
        print("  Nextleap Zomato — use uvicorn to start the web server:")
        print()
        print("    uvicorn src.main:app --reload --port 8000")
        print()
        print("  Or run in CLI mode:")
        print("    python src/main.py --cli")
        print()


if __name__ == "__main__":
    main()
