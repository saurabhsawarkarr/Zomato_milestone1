"""
FastAPI routes for the Nextleap Zomato recommendation API.

Endpoints:
  GET  /health                 → Server health + dataset info
  GET  /metadata/locations     → Available locations list
  GET  /metadata/cuisines      → Available cuisines list
  GET  /metadata/budget-tiers  → Budget tier definitions
  POST /recommend              → AI-powered recommendations
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────────

class RecommendRequest(BaseModel):
    location: str = Field(..., description="City or area name (required)")
    budget: str = Field(..., description="Budget tier: 'low' | 'medium' | 'high'")
    cuisine: Optional[str] = Field(None, description="Comma-separated cuisine types (optional)")
    min_rating: float = Field(0.0, ge=0.0, le=5.0, description="Minimum rating 0.0–5.0")
    additional_preferences: Optional[str] = Field(None, max_length=500, description="Free-text preferences")

    @validator("budget")
    def validate_budget(cls, v: str) -> str:
        allowed = {"low", "medium", "high"}
        if v.lower() not in allowed:
            raise ValueError(f"budget must be one of: {', '.join(allowed)}")
        return v.lower()

    @validator("location")
    def validate_location(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("location cannot be empty")
        return v


# ─────────────────────────────────────────────────────────────────
# Helper: get app state (df + index)
# ─────────────────────────────────────────────────────────────────

def _get_state(request: Request):
    """Return (df, index) from FastAPI app state."""
    df    = getattr(request.app.state, "df",    None)
    index = getattr(request.app.state, "index", None)
    if df is None or index is None:
        raise HTTPException(
            status_code=503,
            detail="Dataset not yet loaded. Please wait and try again.",
        )
    return df, index


# ─────────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────────

@router.get("/health", tags=["System"])
async def health_check(request: Request) -> dict[str, Any]:
    """Returns server health status and basic dataset statistics."""
    uptime = time.time() - getattr(request.app.state, "start_time", time.time())
    df = getattr(request.app.state, "df", None)

    return {
        "status": "ok",
        "dataset_loaded": df is not None,
        "dataset_rows": int(len(df)) if df is not None else 0,
        "uptime_seconds": round(uptime, 1),
    }


# ─────────────────────────────────────────────────────────────────
# GET /metadata/locations
# ─────────────────────────────────────────────────────────────────

@router.get("/metadata/locations", tags=["Metadata"])
async def get_locations(request: Request) -> dict[str, list[str]]:
    """Returns sorted list of unique locations available in the dataset."""
    _, index = _get_state(request)
    locations = sorted(index.locations)
    logger.debug("Returning %d locations", len(locations))
    return {"locations": locations}


# ─────────────────────────────────────────────────────────────────
# GET /metadata/cuisines
# ─────────────────────────────────────────────────────────────────

@router.get("/metadata/cuisines", tags=["Metadata"])
async def get_cuisines(request: Request) -> dict[str, list[str]]:
    """Returns sorted list of unique cuisines available in the dataset."""
    _, index = _get_state(request)
    cuisines = sorted(index.cuisines)
    logger.debug("Returning %d cuisines", len(cuisines))
    return {"cuisines": cuisines}


# ─────────────────────────────────────────────────────────────────
# GET /metadata/budget-tiers
# ─────────────────────────────────────────────────────────────────

@router.get("/metadata/budget-tiers", tags=["Metadata"])
async def get_budget_tiers() -> dict[str, Any]:
    """Returns budget tier definitions with cost ranges (INR)."""
    from src.config import settings
    return {
        "tiers": {
            "low":    {"label": "Low",    "max_cost": settings.budget_low_max,    "description": f"Up to ₹{settings.budget_low_max} for two"},
            "medium": {"label": "Medium", "max_cost": settings.budget_medium_max, "description": f"₹{settings.budget_low_max + 1}–₹{settings.budget_medium_max} for two"},
            "high":   {"label": "High",   "max_cost": None,                       "description": f"Above ₹{settings.budget_medium_max} for two"},
        }
    }


# ─────────────────────────────────────────────────────────────────
# POST /recommend
# ─────────────────────────────────────────────────────────────────

@router.post("/recommend", tags=["Recommendations"])
async def recommend(body: RecommendRequest, request: Request) -> dict[str, Any]:
    """
    Generate AI-powered restaurant recommendations.

    Accepts user preferences and returns top-5 restaurants ranked and
    explained by the Groq LLM.
    """
    df, index = _get_state(request)

    from src.models.user_preferences import UserPreferences, ValidationError
    from src.services.recommendation_service import get_recommendations

    # ── Build UserPreferences ──
    try:
        prefs = UserPreferences(
            location=body.location,
            budget=body.budget,
            cuisine=body.cuisine,
            min_rating=body.min_rating,
            additional_preferences=body.additional_preferences,
        )
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Validate against dataset ──
    try:
        warnings = prefs.validate(index.locations, index.cuisines)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    logger.info(
        "Recommend request: location=%s budget=%s cuisine=%s rating=%.1f",
        prefs.location, prefs.budget, prefs.cuisine, prefs.min_rating,
    )

    # ── Run recommendation pipeline ──
    try:
        result = get_recommendations(prefs, df, index)
    except Exception as e:
        logger.exception("Recommendation pipeline failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Recommendation engine error: {e}")

    # ── Serialize response ──
    recs_out = []
    for rec in result.recommendations:
        recs_out.append({
            "rank":          rec.rank,
            "name":          rec.name,
            "cuisines":      rec.cuisines,
            "rating":        rec.rating,
            "cost_for_two":  rec.cost_for_two,
            "explanation":   rec.explanation,
        })

    return {
        "status":          "success",
        "count":           len(recs_out),
        "filters_relaxed": result.filters_relaxed,
        "is_fallback":     result.is_fallback,
        "summary":         result.summary,
        "recommendations": recs_out,
        "warnings":        warnings,
    }
