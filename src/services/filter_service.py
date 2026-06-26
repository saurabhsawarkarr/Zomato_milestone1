"""
Filter service for restaurant candidate selection.

Applies cascading filters to the preprocessed dataset based on user
preferences and implements progressive filter relaxation when results
are too few. Handles edge cases F-01 through F-08.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.config import BUDGET_TIERS, MAX_CANDIDATES
from src.models.restaurant import Restaurant
from src.models.user_preferences import UserPreferences, BudgetTier
from src.data.preprocessor import SearchIndex, df_to_restaurants

logger = logging.getLogger(__name__)


# Minimum result count before triggering filter relaxation
MIN_RESULTS_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Filter Result
# ---------------------------------------------------------------------------

@dataclass
class FilterResult:
    """
    Encapsulates the output of the filtering pipeline.

    Attributes:
        restaurants: The list of matched Restaurant objects.
        total_matches: Total number of matches before capping to MAX_CANDIDATES.
        filters_relaxed: List of human-readable descriptions of relaxations applied.
        warnings: List of non-fatal warning messages for the user.
    """
    restaurants: list[Restaurant] = field(default_factory=list)
    total_matches: int = 0
    filters_relaxed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Individual Filter Functions
# ---------------------------------------------------------------------------

def _filter_by_location(df: pd.DataFrame, location: str) -> pd.DataFrame:
    """
    Filter restaurants by location (case-insensitive exact match).

    Edge case U-02: case-insensitive.
    """
    mask = df["location"].str.lower() == location.lower().strip()
    return df[mask]


def _filter_by_budget(
    df: pd.DataFrame,
    budget_tier: BudgetTier,
) -> pd.DataFrame:
    """
    Filter restaurants by budget tier using configured cost ranges.

    Edge cases:
      F-07: Restaurants with null cost_for_two are INCLUDED (not excluded).
      F-08: Inclusive boundaries (≤) for upper limit.
    """
    cost_range = BUDGET_TIERS.get(budget_tier.value)
    if cost_range is None:
        logger.warning("Unknown budget tier: %s. Skipping budget filter.", budget_tier)
        return df

    low, high = cost_range

    # Include restaurants where cost is within range OR cost is null (F-07)
    mask = (
        df["cost_for_two"].isna()
        | (
            (df["cost_for_two"] >= low) & (df["cost_for_two"] <= high)
        )
    )
    return df[mask]


def _filter_by_cuisine(
    df: pd.DataFrame,
    cuisines: list[str],
) -> pd.DataFrame:
    """
    Filter restaurants whose cuisines list contains ANY of the requested cuisines.

    Edge case U-14: OR logic for multiple cuisines.
    """
    if not cuisines:
        return df

    cuisines_lower = {c.lower() for c in cuisines}

    def _has_cuisine(restaurant_cuisines):
        if not isinstance(restaurant_cuisines, list):
            return False
        return any(c.lower() in cuisines_lower for c in restaurant_cuisines)

    mask = df["cuisines"].apply(_has_cuisine)
    return df[mask]


def _filter_by_rating(df: pd.DataFrame, min_rating: float) -> pd.DataFrame:
    """
    Filter restaurants with rating >= min_rating.

    Edge case U-21: min_rating=0.0 effectively passes everything.
    """
    if min_rating <= 0.0:
        return df
    return df[df["rating"] >= min_rating]


def _soft_match_preferences(
    df: pd.DataFrame,
    additional_preferences: Optional[str],
) -> pd.DataFrame:
    """
    Soft-match filter: boost/filter by keyword presence in highlights.

    If additional_preferences is provided, check if any keyword appears
    in the restaurant's highlights. This is a SOFT filter — if it removes
    too many results, it will be the first to be relaxed.

    Edge case U-25: If no highlights match, no boost but no crash.
    Edge case U-27: Empty string → skip.
    """
    if not additional_preferences or not additional_preferences.strip():
        return df

    keywords = [kw.strip().lower() for kw in additional_preferences.split() if kw.strip()]
    if not keywords:
        return df

    def _matches_keywords(highlights):
        if not isinstance(highlights, list) or not highlights:
            return False
        highlights_lower = " ".join(str(h).lower() for h in highlights)
        return any(kw in highlights_lower for kw in keywords)

    # Try the soft filter
    mask = df["highlights"].apply(_matches_keywords)
    matched = df[mask]

    # If soft match eliminates too many, return original (it's a soft filter)
    if len(matched) < MIN_RESULTS_THRESHOLD and len(df) >= MIN_RESULTS_THRESHOLD:
        logger.info(
            "Soft match too restrictive (%d results). Keeping all %d candidates.",
            len(matched),
            len(df),
        )
        return df

    return matched if len(matched) > 0 else df


# ---------------------------------------------------------------------------
# Budget Relaxation Helpers
# ---------------------------------------------------------------------------

_BUDGET_ORDER = [BudgetTier.LOW, BudgetTier.MEDIUM, BudgetTier.HIGH]


def _widen_budget(current_tier: BudgetTier) -> Optional[BudgetTier]:
    """
    Get the next wider budget tier.

    low → medium, medium → high, high → None (cannot widen further).
    """
    idx = _BUDGET_ORDER.index(current_tier)
    if idx < len(_BUDGET_ORDER) - 1:
        return _BUDGET_ORDER[idx + 1]
    return None


def _lower_budget(current_tier: BudgetTier) -> Optional[BudgetTier]:
    """
    Get the next lower budget tier.

    high → medium, medium → low, low → None.
    """
    idx = _BUDGET_ORDER.index(current_tier)
    if idx > 0:
        return _BUDGET_ORDER[idx - 1]
    return None


# ---------------------------------------------------------------------------
# Sort Logic
# ---------------------------------------------------------------------------

def _sort_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort candidates by rating descending, then votes descending, then name.

    Edge case F-04: Secondary sort by votes when ratings are equal.
    """
    return df.sort_values(
        by=["rating", "votes", "name"],
        ascending=[False, False, True],
    )


# ---------------------------------------------------------------------------
# Main Filter Pipeline
# ---------------------------------------------------------------------------

def filter_restaurants(
    prefs: UserPreferences,
    df: pd.DataFrame,
    index: SearchIndex,
    max_candidates: Optional[int] = None,
) -> FilterResult:
    """
    Apply cascading filters to produce a shortlist of candidate restaurants.

    Filter order: location → budget → cuisine → rating → soft match.
    Applies progressive relaxation if fewer than MIN_RESULTS_THRESHOLD results.

    Args:
        prefs: Validated UserPreferences instance.
        df: The preprocessed DataFrame.
        index: The SearchIndex (used for validation, not primary filtering here).
        max_candidates: Override for MAX_CANDIDATES. Defaults to config value.

    Returns:
        FilterResult with matched restaurants, relaxation info, and warnings.
    """
    if max_candidates is None:
        max_candidates = MAX_CANDIDATES

    result = FilterResult()

    # -----------------------------------------------------------------------
    # Step 1: Location filter (required, never relaxed)
    # -----------------------------------------------------------------------
    candidates = _filter_by_location(df, prefs.location)
    logger.info(
        "After location filter ('%s'): %d restaurants",
        prefs.location,
        len(candidates),
    )

    if candidates.empty:
        # Edge case: location has zero restaurants (should be caught by validation)
        result.warnings.append(
            f"No restaurants found in '{prefs.location}'."
        )
        return result

    # -----------------------------------------------------------------------
    # Step 2: Budget filter
    # -----------------------------------------------------------------------
    budget_tier = prefs.budget_tier
    budget_filtered = _filter_by_budget(candidates, budget_tier)
    logger.info(
        "After budget filter ('%s'): %d restaurants",
        budget_tier.value,
        len(budget_filtered),
    )

    # -----------------------------------------------------------------------
    # Step 3: Cuisine filter
    # -----------------------------------------------------------------------
    cuisine_filtered = _filter_by_cuisine(budget_filtered, prefs.cuisines_list)
    if prefs.cuisines_list:
        logger.info(
            "After cuisine filter (%s): %d restaurants",
            prefs.cuisines_list,
            len(cuisine_filtered),
        )

    # -----------------------------------------------------------------------
    # Step 4: Rating filter
    # -----------------------------------------------------------------------
    rating_filtered = _filter_by_rating(cuisine_filtered, prefs.min_rating)
    if prefs.min_rating > 0:
        logger.info(
            "After rating filter (>= %.1f): %d restaurants",
            prefs.min_rating,
            len(rating_filtered),
        )

    # -----------------------------------------------------------------------
    # Step 5: Soft match on additional preferences
    # -----------------------------------------------------------------------
    final = _soft_match_preferences(rating_filtered, prefs.additional_preferences)
    if prefs.additional_preferences:
        logger.info(
            "After soft match: %d restaurants",
            len(final),
        )

    # -----------------------------------------------------------------------
    # Step 6: Progressive relaxation if too few results (edge case F-01)
    # -----------------------------------------------------------------------
    if len(final) < MIN_RESULTS_THRESHOLD:
        final, relaxations = _progressive_relaxation(
            location_df=candidates,
            prefs=prefs,
            current_count=len(final),
        )
        result.filters_relaxed = relaxations

    # -----------------------------------------------------------------------
    # Step 7: Sort and cap
    # -----------------------------------------------------------------------
    final = _sort_candidates(final)

    result.total_matches = len(final)

    # Edge case F-03: Cap at max_candidates
    if len(final) > max_candidates:
        logger.info(
            "Capping results from %d to %d",
            len(final),
            max_candidates,
        )
        final = final.head(max_candidates)

    # Edge case F-02: Inform if very few results
    if 0 < result.total_matches <= 2:
        result.warnings.append(
            f"Only {result.total_matches} restaurant(s) matched your criteria."
        )

    # Edge case U-07: Location with very few restaurants total
    location_total = len(candidates)
    if location_total <= 2:
        result.warnings.append(
            f"Note: '{prefs.location}' only has {location_total} restaurant(s) "
            f"in the dataset."
        )

    # Convert to Restaurant objects
    result.restaurants = df_to_restaurants(final)

    logger.info(
        "Filter pipeline complete: %d results (relaxations: %s)",
        len(result.restaurants),
        result.filters_relaxed or "none",
    )

    return result


# ---------------------------------------------------------------------------
# Progressive Filter Relaxation
# ---------------------------------------------------------------------------

def _progressive_relaxation(
    location_df: pd.DataFrame,
    prefs: UserPreferences,
    current_count: int,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Progressively relax filters to get at least MIN_RESULTS_THRESHOLD results.

    Relaxation order (edge case F-01):
      1. Drop additional_preferences (soft match)
      2. Widen budget by one tier (up)
      3. Also widen budget down (if applicable)
      4. Drop cuisine filter
      5. Lower min_rating by 0.5 (repeatedly)
      6. Remove budget filter entirely

    Edge case F-05: If all filters dropped, return whatever location has.

    Args:
        location_df: DataFrame already filtered by location.
        prefs: The original user preferences.
        current_count: The current number of matches.

    Returns:
        Tuple of (relaxed DataFrame, list of relaxation descriptions).
    """
    relaxations: list[str] = []
    budget_tier = prefs.budget_tier
    cuisines = prefs.cuisines_list.copy()
    min_rating = prefs.min_rating
    use_additional = bool(prefs.additional_preferences)

    def _apply_filters(
        df: pd.DataFrame,
        tier: BudgetTier,
        cuiss: list[str],
        rating: float,
        addl: bool,
    ) -> pd.DataFrame:
        """Apply the filter chain with current parameters."""
        result = _filter_by_budget(df, tier)
        result = _filter_by_cuisine(result, cuiss)
        result = _filter_by_rating(result, rating)
        if addl and prefs.additional_preferences:
            result = _soft_match_preferences(result, prefs.additional_preferences)
        return result

    # --- Relaxation 1: Drop additional preferences ---
    if use_additional:
        use_additional = False
        candidates = _apply_filters(location_df, budget_tier, cuisines, min_rating, False)
        if len(candidates) >= MIN_RESULTS_THRESHOLD:
            relaxations.append("Dropped additional preference keywords")
            logger.info("Relaxation: dropped additional prefs → %d results", len(candidates))
            return candidates, relaxations
        relaxations.append("Dropped additional preference keywords")

    # --- Relaxation 2: Widen budget up ---
    wider_tier = _widen_budget(budget_tier)
    if wider_tier:
        candidates = _apply_filters(location_df, wider_tier, cuisines, min_rating, False)
        if len(candidates) >= MIN_RESULTS_THRESHOLD:
            relaxations.append(
                f"Widened budget from '{budget_tier.value}' to '{wider_tier.value}'"
            )
            logger.info(
                "Relaxation: budget %s → %s → %d results",
                budget_tier.value, wider_tier.value, len(candidates),
            )
            return candidates, relaxations

    # --- Relaxation 3: Widen budget down ---
    lower_tier = _lower_budget(budget_tier)
    if lower_tier:
        # Combine: try both lower and upper tiers
        candidates_up = _apply_filters(location_df, wider_tier, cuisines, min_rating, False) if wider_tier else pd.DataFrame()
        candidates_down = _apply_filters(location_df, lower_tier, cuisines, min_rating, False)
        # Also include original tier
        candidates_orig = _apply_filters(location_df, budget_tier, cuisines, min_rating, False)

        combined = pd.concat([candidates_orig, candidates_up, candidates_down]).drop_duplicates(
            subset=["name", "location"], keep="first"
        )
        if len(combined) >= MIN_RESULTS_THRESHOLD:
            relaxations.append(
                f"Expanded budget to include nearby tiers"
            )
            logger.info("Relaxation: expanded budget range → %d results", len(combined))
            return combined, relaxations

    # --- Relaxation 4: Drop cuisine filter ---
    if cuisines:
        cuisines = []
        candidates = _filter_by_budget(location_df, budget_tier)
        candidates = _filter_by_rating(candidates, min_rating)
        if len(candidates) >= MIN_RESULTS_THRESHOLD:
            relaxations.append("Dropped cuisine filter")
            logger.info("Relaxation: dropped cuisine → %d results", len(candidates))
            return candidates, relaxations
        relaxations.append("Dropped cuisine filter")

    # --- Relaxation 5: Lower min_rating progressively ---
    while min_rating > 0.0:
        min_rating = max(0.0, min_rating - 0.5)
        candidates = _filter_by_budget(location_df, budget_tier)
        candidates = _filter_by_rating(candidates, min_rating)
        if len(candidates) >= MIN_RESULTS_THRESHOLD:
            relaxations.append(
                f"Lowered minimum rating to {min_rating:.1f}"
            )
            logger.info("Relaxation: min_rating → %.1f → %d results", min_rating, len(candidates))
            return candidates, relaxations

    # --- Relaxation 6: Remove budget filter entirely (edge case F-05, F-06) ---
    candidates = _filter_by_rating(location_df, 0.0)
    if len(candidates) >= MIN_RESULTS_THRESHOLD:
        relaxations.append("Removed budget filter")
        logger.info("Relaxation: removed budget → %d results", len(candidates))
        return candidates, relaxations

    # --- Final fallback: return everything in the location ---
    relaxations.append(
        f"Showing all restaurants in '{prefs.location}' (all filters relaxed)"
    )
    logger.info(
        "Relaxation: all filters dropped → %d results",
        len(location_df),
    )
    return location_df, relaxations
