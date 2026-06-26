"""
Recommendation data models.

Defines the Recommendation and RecommendationResponse models for
structured LLM output parsing. Handles edge cases L-14 through L-22.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from src.models.restaurant import Restaurant

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content filter — basic offensive content check (edge case L-21)
# ---------------------------------------------------------------------------

_OFFENSIVE_PATTERNS = re.compile(
    r"\b(fuck|shit|damn|ass|bitch|crap|hell|dick|bastard|slut|whore)\b",
    re.IGNORECASE,
)

_GENERIC_EXPLANATION = (
    "This restaurant is a great match based on your preferences "
    "for location, budget, and cuisine."
)


def _filter_explanation(text: str) -> str:
    """
    Basic content filter for LLM explanations.

    Edge case L-21: Replace offensive content with generic explanation.
    """
    if not text:
        return _GENERIC_EXPLANATION

    if _OFFENSIVE_PATTERNS.search(text):
        logger.warning("Offensive content detected in LLM explanation. Replacing.")
        return _GENERIC_EXPLANATION

    return text.strip()


# ---------------------------------------------------------------------------
# Recommendation Model
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    """
    A single restaurant recommendation from the LLM.

    Attributes:
        rank: Position in the recommendation list (1-based).
        name: Restaurant name (cross-checked against candidates).
        cuisines: List of cuisines (from dataset, not LLM).
        rating: Rating (from dataset, not LLM — edge case L-20).
        cost_for_two: Cost for two (from dataset, not LLM — edge case L-20).
        explanation: AI-generated explanation of why this restaurant is recommended.
    """
    rank: int
    name: str
    cuisines: list[str] = field(default_factory=list)
    rating: float = 0.0
    cost_for_two: Optional[float] = None
    explanation: str = ""

    def to_dict(self) -> dict:
        """Convert to a plain dictionary for API serialization."""
        return {
            "rank": self.rank,
            "name": self.name,
            "cuisines": self.cuisines,
            "rating": self.rating,
            "cost_for_two": self.cost_for_two,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# RecommendationResponse Model
# ---------------------------------------------------------------------------

@dataclass
class RecommendationResponse:
    """
    Complete recommendation response including all recommendations and metadata.

    Attributes:
        recommendations: Ordered list of Recommendation objects.
        summary: AI-generated summary of the overall recommendations.
        filters_relaxed: List of filter relaxation descriptions (from filter service).
        is_fallback: Whether this response uses fallback (non-LLM) results.
    """
    recommendations: list[Recommendation] = field(default_factory=list)
    summary: str = ""
    filters_relaxed: list[str] = field(default_factory=list)
    is_fallback: bool = False

    def to_dict(self) -> dict:
        """Convert to a plain dictionary for API serialization."""
        return {
            "status": "success",
            "count": len(self.recommendations),
            "filters_relaxed": self.filters_relaxed,
            "is_fallback": self.is_fallback,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "summary": self.summary,
        }

    @classmethod
    def from_llm_response(
        cls,
        json_string: str,
        candidates: list[Restaurant],
        filters_relaxed: list[str] | None = None,
    ) -> RecommendationResponse:
        """
        Parse an LLM JSON response into a RecommendationResponse.

        Cross-checks recommendations against the candidate list to ensure
        factual accuracy (edge cases L-19, L-20).

        Args:
            json_string: Raw JSON string from the LLM.
            candidates: The original candidate restaurants sent to the LLM.
            filters_relaxed: Filter relaxation info from the filter service.

        Returns:
            A validated RecommendationResponse.
        """
        if filters_relaxed is None:
            filters_relaxed = []

        # --- Step 1: Clean the JSON string ---
        parsed = _parse_json_string(json_string)
        if parsed is None:
            logger.warning("Failed to parse LLM JSON response. Using fallback.")
            return cls._build_fallback(candidates, filters_relaxed)

        # --- Step 2: Extract recommendations ---
        raw_recs = _extract_recommendations(parsed)
        if not raw_recs:
            # Edge case L-18: 0 recommendations
            logger.warning("LLM returned 0 recommendations. Using fallback.")
            return cls._build_fallback(candidates, filters_relaxed)

        # --- Step 3: Build candidate lookup for cross-checking ---
        candidate_map = {r.name.lower().strip(): r for r in candidates}

        # --- Step 4: Validate each recommendation ---
        validated_recs: list[Recommendation] = []
        seen_names: set[str] = set()

        for i, raw in enumerate(raw_recs):
            rec_name = str(raw.get("name", "")).strip()
            if not rec_name:
                continue

            # Edge case L-22: Skip duplicates
            name_key = rec_name.lower()
            if name_key in seen_names:
                logger.debug("Skipping duplicate recommendation: %s", rec_name)
                continue
            seen_names.add(name_key)

            # Edge case L-19: Cross-check against candidates
            matched_candidate = candidate_map.get(name_key)
            if matched_candidate is None:
                # Try fuzzy match (restaurant name might be slightly different)
                matched_candidate = _fuzzy_match_candidate(rec_name, candidate_map)

            if matched_candidate is None:
                logger.warning(
                    "LLM hallucinated restaurant '%s' — not in candidates. Discarding.",
                    rec_name,
                )
                continue

            # Edge case L-20: Use dataset values for factual fields
            explanation = _filter_explanation(
                str(raw.get("explanation", raw.get("reason", "")))
            )

            validated_recs.append(
                Recommendation(
                    rank=len(validated_recs) + 1,
                    name=matched_candidate.name,  # Use exact dataset name
                    cuisines=matched_candidate.cuisines,  # From dataset
                    rating=matched_candidate.rating,  # From dataset
                    cost_for_two=matched_candidate.cost_for_two,  # From dataset
                    explanation=explanation,  # From LLM
                )
            )

        # Edge case L-17: Truncate to top 5
        validated_recs = validated_recs[:5]

        # Re-number ranks
        for i, rec in enumerate(validated_recs):
            rec.rank = i + 1

        if not validated_recs:
            logger.warning("No valid recommendations after cross-check. Using fallback.")
            return cls._build_fallback(candidates, filters_relaxed)

        # Extract summary
        summary = str(parsed.get("summary", "")).strip()
        if not summary:
            summary = _generate_default_summary(validated_recs)

        return cls(
            recommendations=validated_recs,
            summary=summary,
            filters_relaxed=filters_relaxed,
            is_fallback=False,
        )

    @classmethod
    def _build_fallback(
        cls,
        candidates: list[Restaurant],
        filters_relaxed: list[str],
    ) -> RecommendationResponse:
        """
        Build a fallback response from raw candidates without LLM explanations.

        Used when the LLM fails or returns unusable output.
        """
        # Sort by rating descending, take top 5
        sorted_candidates = sorted(
            candidates, key=lambda r: (r.rating, r.votes), reverse=True
        )[:5]

        recs = [
            Recommendation(
                rank=i + 1,
                name=r.name,
                cuisines=r.cuisines,
                rating=r.rating,
                cost_for_two=r.cost_for_two,
                explanation=_GENERIC_EXPLANATION,
            )
            for i, r in enumerate(sorted_candidates)
        ]

        summary = (
            "These recommendations are based on rating and popularity. "
            "AI-powered explanations were unavailable for this request."
        )

        return cls(
            recommendations=recs,
            summary=summary,
            filters_relaxed=filters_relaxed,
            is_fallback=True,
        )


# ---------------------------------------------------------------------------
# JSON Parsing Helpers
# ---------------------------------------------------------------------------

def _parse_json_string(text: str) -> dict | None:
    """
    Parse a JSON string from LLM output, handling common issues.

    Edge cases:
      L-15: Strip markdown code fences.
      L-16: Handle plain text (returns None).
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # Edge case L-15: Strip markdown code fences
    if cleaned.startswith("```"):
        # Remove opening fence (with optional language tag)
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        # Remove closing fence
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

    # Try to parse JSON
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
        logger.warning("LLM returned JSON but not an object (type: %s)", type(result).__name__)
        return None
    except json.JSONDecodeError as e:
        logger.warning("JSON parse error: %s", e)

        # Edge case L-07: Try to parse truncated JSON by finding the last complete object
        try:
            # Find the last valid closing brace
            last_brace = cleaned.rfind("}")
            if last_brace > 0:
                truncated = cleaned[: last_brace + 1]
                result = json.loads(truncated)
                if isinstance(result, dict):
                    logger.info("Successfully parsed truncated JSON response")
                    return result
        except json.JSONDecodeError:
            pass

        return None


def _extract_recommendations(parsed: dict) -> list[dict]:
    """
    Extract the recommendations list from parsed JSON.

    Edge case L-14: Handle different possible keys.
    """
    # Try standard key
    recs = parsed.get("recommendations")
    if isinstance(recs, list):
        return recs

    # Try alternative keys
    for key in ("results", "restaurants", "picks", "top_picks", "data"):
        recs = parsed.get(key)
        if isinstance(recs, list):
            logger.info("Found recommendations under key '%s'", key)
            return recs

    # If the parsed dict itself looks like a single recommendation
    if "name" in parsed and "explanation" in parsed:
        return [parsed]

    logger.warning(
        "Cannot find recommendations in LLM response. Keys: %s",
        list(parsed.keys()),
    )
    return []


def _fuzzy_match_candidate(
    name: str,
    candidate_map: dict[str, Restaurant],
) -> Restaurant | None:
    """
    Try to match a recommendation name to a candidate using fuzzy matching.

    Handles minor differences in naming (extra whitespace, punctuation, etc.).
    """
    name_lower = name.lower().strip()

    # Try partial matching
    for key, candidate in candidate_map.items():
        # Check if one contains the other
        if name_lower in key or key in name_lower:
            logger.debug("Fuzzy matched '%s' → '%s'", name, candidate.name)
            return candidate

    return None


def _generate_default_summary(recommendations: list[Recommendation]) -> str:
    """Generate a default summary when the LLM doesn't provide one."""
    count = len(recommendations)
    if count == 1:
        return f"We found 1 restaurant that matches your preferences: {recommendations[0].name}."
    top_name = recommendations[0].name if recommendations else "various options"
    return (
        f"Here are the top {count} restaurant recommendations based on your preferences. "
        f"Our top pick is {top_name}."
    )
