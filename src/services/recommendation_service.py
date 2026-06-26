"""
Recommendation orchestrator service.

Wires together the filter service, prompt service, and LLM service to
produce end-to-end restaurant recommendations. This is the main entry
point for generating recommendations from user preferences.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd

from src.data.preprocessor import SearchIndex
from src.models.recommendation import RecommendationResponse
from src.models.restaurant import Restaurant
from src.models.user_preferences import UserPreferences
from src.services.filter_service import filter_restaurants, FilterResult
from src.services.prompt_service import build_prompt
from src.services.llm_service import call_llm, check_api_key

logger = logging.getLogger(__name__)


def get_recommendations(
    prefs: UserPreferences,
    df: Optional[pd.DataFrame] = None,
    index: Optional[SearchIndex] = None,
) -> RecommendationResponse:
    """
    Generate restaurant recommendations end-to-end.

    Flow: validate → filter → build prompt → call LLM → parse → return.

    Args:
        prefs: Validated user preferences.
        df: The preprocessed DataFrame. If None, loads from global state.
        index: The SearchIndex. If None, builds from df.

    Returns:
        A RecommendationResponse with ranked recommendations and explanations.
    """
    total_start = time.time()

    # -----------------------------------------------------------------------
    # Step 1: Filter candidates
    # -----------------------------------------------------------------------
    logger.info("Step 1/4: Filtering candidates for %s", prefs)

    filter_start = time.time()
    filter_result = filter_restaurants(prefs, df, index)
    filter_time = time.time() - filter_start

    logger.info(
        "Filtered to %d candidates in %.2fs (relaxations: %s)",
        len(filter_result.restaurants),
        filter_time,
        filter_result.filters_relaxed or "none",
    )

    # Handle no candidates
    if not filter_result.restaurants:
        logger.warning("No candidates found after filtering. Returning empty response.")
        return RecommendationResponse(
            recommendations=[],
            summary="No restaurants found matching your criteria. "
                    "Try broadening your search with a different location or budget.",
            filters_relaxed=filter_result.filters_relaxed,
            is_fallback=True,
        )

    # -----------------------------------------------------------------------
    # Step 2: Check API key before building prompt
    # -----------------------------------------------------------------------
    if not check_api_key():
        logger.warning(
            "Groq API key not configured. Returning fallback recommendations."
        )
        return RecommendationResponse._build_fallback(
            filter_result.restaurants,
            filter_result.filters_relaxed,
        )

    # -----------------------------------------------------------------------
    # Step 3: Build prompt
    # -----------------------------------------------------------------------
    logger.info("Step 2/4: Building LLM prompt...")

    prompt_start = time.time()
    system_prompt, user_prompt, trimmed_candidates = build_prompt(
        prefs, filter_result.restaurants
    )
    prompt_time = time.time() - prompt_start

    logger.info(
        "Prompt built in %.2fs (%d candidates included)",
        prompt_time,
        len(trimmed_candidates),
    )

    # -----------------------------------------------------------------------
    # Step 4: Call LLM
    # -----------------------------------------------------------------------
    logger.info("Step 3/4: Calling Groq LLM...")

    llm_start = time.time()
    try:
        llm_response = call_llm(system_prompt, user_prompt)
        llm_time = time.time() - llm_start
        logger.info("LLM responded in %.2fs", llm_time)

    except RuntimeError as e:
        llm_time = time.time() - llm_start
        logger.error("LLM call failed after %.2fs: %s", llm_time, e)

        # Return fallback recommendations
        return RecommendationResponse._build_fallback(
            trimmed_candidates,
            filter_result.filters_relaxed,
        )

    # -----------------------------------------------------------------------
    # Step 5: Parse response
    # -----------------------------------------------------------------------
    logger.info("Step 4/4: Parsing LLM response...")

    parse_start = time.time()
    result = RecommendationResponse.from_llm_response(
        json_string=llm_response,
        candidates=trimmed_candidates,
        filters_relaxed=filter_result.filters_relaxed,
    )
    parse_time = time.time() - parse_start

    logger.info(
        "Parsed %d recommendations in %.2fs (fallback: %s)",
        len(result.recommendations),
        parse_time,
        result.is_fallback,
    )

    # If parsing resulted in fallback (bad LLM output), try once more
    if result.is_fallback and llm_response:
        logger.info("First LLM response unusable. Retrying with stricter prompt...")

        try:
            retry_response = call_llm(system_prompt, user_prompt)
            retry_result = RecommendationResponse.from_llm_response(
                json_string=retry_response,
                candidates=trimmed_candidates,
                filters_relaxed=filter_result.filters_relaxed,
            )

            if not retry_result.is_fallback:
                result = retry_result
                logger.info("Retry succeeded: %d recommendations", len(result.recommendations))
            else:
                logger.warning("Retry also produced fallback results.")

        except RuntimeError as e:
            logger.warning("Retry LLM call also failed: %s", e)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total_time = time.time() - total_start
    logger.info(
        "Recommendation pipeline complete in %.2fs "
        "(filter: %.2fs, prompt: %.2fs, llm: %.2fs, parse: %.2fs)",
        total_time,
        filter_time,
        prompt_time,
        llm_time,
        parse_time,
    )

    return result
