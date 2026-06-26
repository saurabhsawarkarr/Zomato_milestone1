"""
Prompt service for LLM prompt construction.

Builds structured prompts for the Groq LLM from user preferences and
candidate restaurants. Handles edge cases L-09 through L-13.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.config import LLM_MAX_TOKENS
from src.models.restaurant import Restaurant
from src.models.user_preferences import UserPreferences

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token estimation (rough heuristic: ~4 chars per token for English)
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN = 4

# Reserve tokens for system prompt + output
SYSTEM_PROMPT_TOKEN_ESTIMATE = 300
OUTPUT_TOKEN_RESERVE = 800  # Reserve for the LLM's response
MAX_CANDIDATE_TOKENS = LLM_MAX_TOKENS - SYSTEM_PROMPT_TOKEN_ESTIMATE - OUTPUT_TOKEN_RESERVE


def _estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string."""
    return len(text) // CHARS_PER_TOKEN


# ---------------------------------------------------------------------------
# Prompt Injection Sanitization (edge case L-10)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+)?(previous\s+)?instructions|"
    r"forget\s+(everything|all|your)\b|"
    r"you\s+are\s+now\b|"
    r"system\s*:|"
    r"assistant\s*:|"
    r"\bpretend\s+to\s+be\b|"
    r"\bact\s+as\b|"
    r"do\s+not\s+follow)",
    re.IGNORECASE,
)


def _sanitize_user_input(text: str) -> str:
    """
    Sanitize user-provided text to prevent prompt injection.

    Edge case L-10: Strip meta-instructions that try to manipulate LLM behavior.
    """
    if not text:
        return ""

    # Remove injection-like patterns
    cleaned = _INJECTION_PATTERNS.sub("[filtered]", text)

    return cleaned.strip()


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert restaurant recommendation assistant specializing in Indian dining.

Your task is to analyze a list of candidate restaurants and rank the TOP choices that best match the user's preferences. For each recommendation, provide a thoughtful, personalized explanation of why that restaurant is a great fit.

RULES:
1. Only recommend restaurants from the provided candidate list. Do NOT invent or hallucinate restaurant names.
2. Rank based on how well each restaurant matches the user's stated preferences (cuisine, budget, rating, and any additional preferences).
3. For each recommendation, write a 2-3 sentence explanation that mentions specific attributes (cuisine, price point, rating, highlights) that make it a good match.
4. If the user's preferences couldn't be fully matched, briefly mention what was compromised.
5. Provide a short overall summary at the end.

RESPONSE FORMAT:
You MUST respond with valid JSON in exactly this schema:
{
  "recommendations": [
    {
      "rank": 1,
      "name": "Exact Restaurant Name",
      "explanation": "2-3 sentence personalized explanation"
    }
  ],
  "summary": "A brief 1-2 sentence overall summary of the recommendations"
}

IMPORTANT:
- The "name" field MUST exactly match a restaurant name from the candidate list.
- Do NOT include rating, cuisines, or cost_for_two in your JSON — those will be filled from the dataset.
- Respond ONLY with the JSON object, no markdown fences or extra text."""


# ---------------------------------------------------------------------------
# Prompt Building
# ---------------------------------------------------------------------------

def _format_preferences(prefs: UserPreferences) -> str:
    """Format user preferences as a readable text block for the prompt."""
    parts = [
        f"- Location: {prefs.location}",
        f"- Budget: {prefs.budget}",
    ]

    if prefs.cuisines_list:
        parts.append(f"- Preferred Cuisine(s): {', '.join(prefs.cuisines_list)}")
    else:
        parts.append("- Preferred Cuisine(s): No preference (any cuisine)")

    if prefs.min_rating > 0:
        parts.append(f"- Minimum Rating: {prefs.min_rating}/5.0")

    if prefs.additional_preferences:
        sanitized = _sanitize_user_input(prefs.additional_preferences)
        if sanitized:
            parts.append(f"- Additional Preferences: {sanitized}")

    return "\n".join(parts)


def _format_candidate(restaurant: Restaurant, index: int) -> str:
    """
    Format a single restaurant as a concise text block for the prompt.

    Edge case L-13: Escape special characters that could break JSON.
    """
    # Escape JSON-special characters in text fields
    name = restaurant.name.replace('"', '\\"')
    cuisines_str = ", ".join(restaurant.cuisines)

    parts = [f"{index}. {name}"]
    parts.append(f"   Cuisine: {cuisines_str}")
    parts.append(f"   Rating: {restaurant.rating}/5.0 ({restaurant.votes} votes)")

    if restaurant.cost_for_two is not None:
        parts.append(f"   Cost for Two: ₹{int(restaurant.cost_for_two)}")
    else:
        parts.append("   Cost for Two: Not available")

    if restaurant.restaurant_type:
        parts.append(f"   Type: {restaurant.restaurant_type}")

    if restaurant.highlights:
        # Limit highlights to keep prompt concise
        highlights = restaurant.highlights[:5]
        parts.append(f"   Highlights: {', '.join(highlights)}")

    return "\n".join(parts)


def _trim_candidates(
    candidates: list[Restaurant],
    max_tokens: int,
) -> list[Restaurant]:
    """
    Trim the candidate list to fit within the token budget.

    Edge case L-09: If too many candidates, reduce to fit token limit.
    Prioritizes candidates by rating (highest first).

    Args:
        candidates: Full list of candidate restaurants.
        max_tokens: Maximum token budget for the candidate section.

    Returns:
        Trimmed list of candidates that fits within the token budget.
    """
    if not candidates:
        return []

    # Sort by rating (highest first) to keep the best candidates
    sorted_candidates = sorted(
        candidates, key=lambda r: (r.rating, r.votes), reverse=True
    )

    selected: list[Restaurant] = []
    total_chars = 0

    for candidate in sorted_candidates:
        candidate_text = _format_candidate(candidate, len(selected) + 1)
        candidate_chars = len(candidate_text)

        if total_chars + candidate_chars > max_tokens * CHARS_PER_TOKEN:
            logger.info(
                "Token limit reached. Trimmed candidates from %d to %d.",
                len(candidates),
                len(selected),
            )
            break

        selected.append(candidate)
        total_chars += candidate_chars

    # Ensure at least some candidates
    if not selected and sorted_candidates:
        selected = sorted_candidates[:3]
        logger.warning("Forced inclusion of top 3 candidates despite token limit.")

    return selected


def build_prompt(
    prefs: UserPreferences,
    candidates: list[Restaurant],
) -> tuple[str, str, list[Restaurant]]:
    """
    Build the system and user prompts for the LLM.

    Args:
        prefs: Validated user preferences.
        candidates: List of candidate restaurants from the filter service.

    Returns:
        Tuple of (system_prompt, user_prompt, trimmed_candidates).
        The trimmed_candidates list reflects which restaurants were actually
        included in the prompt (for cross-checking the response).
    """
    # Trim candidates to fit token budget
    trimmed = _trim_candidates(candidates, MAX_CANDIDATE_TOKENS)

    # Format preferences
    prefs_text = _format_preferences(prefs)

    # Format candidates
    candidate_texts = [
        _format_candidate(r, i + 1) for i, r in enumerate(trimmed)
    ]
    candidates_text = "\n\n".join(candidate_texts)

    # Edge case L-12: Adjust prompt for single candidate
    if len(trimmed) == 1:
        instruction = (
            "There is only 1 candidate restaurant. Evaluate whether it matches "
            "the user's preferences and provide your assessment."
        )
        rank_instruction = "Rank 1 restaurant."
    elif len(trimmed) <= 5:
        instruction = (
            f"There are {len(trimmed)} candidate restaurants. "
            f"Rank all of them from best to least suitable match."
        )
        rank_instruction = f"Rank all {len(trimmed)} restaurants."
    else:
        instruction = (
            f"There are {len(trimmed)} candidate restaurants. "
            f"Select and rank the TOP 5 that best match the user's preferences."
        )
        rank_instruction = "Rank the top 5 restaurants."

    user_prompt = f"""USER PREFERENCES:
{prefs_text}

CANDIDATE RESTAURANTS ({len(trimmed)} total):
{candidates_text}

TASK:
{instruction}
{rank_instruction}
Provide a personalized explanation for each recommendation.
Respond with valid JSON only."""

    # Log token estimates
    total_tokens = (
        _estimate_tokens(SYSTEM_PROMPT)
        + _estimate_tokens(user_prompt)
    )
    logger.info(
        "Prompt built: %d candidates, ~%d tokens (system + user)",
        len(trimmed),
        total_tokens,
    )

    return SYSTEM_PROMPT, user_prompt, trimmed
