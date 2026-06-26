"""
User preferences model for restaurant recommendation requests.

Defines the UserPreferences dataclass and BudgetTier enum used to capture,
validate, and normalize user input. Handles edge cases U-01 through U-27.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Budget Tier Enum
# ---------------------------------------------------------------------------

class BudgetTier(Enum):
    """
    Budget tier enum.

    The actual cost ranges are configured in config.py via BUDGET_TIERS.
    This enum represents the symbolic tier names.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def from_string(cls, value: str) -> BudgetTier:
        """
        Parse a budget string to a BudgetTier, case-insensitively.

        Handles edge case U-10: case-insensitive matching.

        Args:
            value: The budget string (e.g., "low", "LOW", "Medium").

        Returns:
            The matching BudgetTier.

        Raises:
            ValueError: If the value is not a valid budget tier.
        """
        if not value or not value.strip():
            # Edge case U-09
            raise ValueError("Budget is required. Choose from: 'low', 'medium', or 'high'.")

        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            raise ValueError(
                f"Budget must be 'low', 'medium', or 'high'. "
                f"Got: '{value}'."
            )


# ---------------------------------------------------------------------------
# Common cuisine aliases (edge case U-15)
# ---------------------------------------------------------------------------

CUISINE_ALIASES: dict[str, str] = {
    "bbq": "Barbecue",
    "barbeque": "Barbecue",
    "barbecue": "Barbecue",
    "bar-b-que": "Barbecue",
    "north indian": "North Indian",
    "south indian": "South Indian",
    "indo-chinese": "Chinese",
    "indo chinese": "Chinese",
    "continental": "Continental",
    "cafe": "Cafe",
    "café": "Cafe",
    "pizza": "Pizza",
    "burger": "Burger",
    "biryani": "Biryani",
    "biriyani": "Biryani",
    "briyani": "Biryani",
    "desserts": "Desserts",
    "dessert": "Desserts",
    "ice cream": "Ice Cream",
    "icecream": "Ice Cream",
    "sea food": "Seafood",
    "sea-food": "Seafood",
    "seafood": "Seafood",
    "thai": "Thai",
    "mexican": "Mexican",
    "italian": "Italian",
    "chinese": "Chinese",
    "japanese": "Japanese",
    "korean": "Korean",
    "french": "French",
    "american": "American",
    "mediterranean": "Mediterranean",
    "lebanese": "Lebanese",
    "mughlai": "Mughlai",
    "street food": "Street Food",
    "streetfood": "Street Food",
    "fast food": "Fast Food",
    "fastfood": "Fast Food",
}


def _normalize_cuisine(cuisine: str) -> str:
    """
    Normalize a cuisine string using alias mapping and title-casing.

    Edge case U-15: Handle variant spellings.
    """
    stripped = cuisine.strip()
    lower = stripped.lower()

    # Check alias map first
    if lower in CUISINE_ALIASES:
        return CUISINE_ALIASES[lower]

    # Fall back to title case
    return stripped.title()


# ---------------------------------------------------------------------------
# Input Sanitization (edge case U-23, U-24)
# ---------------------------------------------------------------------------

# Patterns that look like injection attempts
_INJECTION_PATTERNS = re.compile(
    r"(--|;|'|\"|\b(DROP|DELETE|INSERT|UPDATE|SELECT|EXEC|UNION|ALTER)\b)",
    re.IGNORECASE,
)

MAX_ADDITIONAL_PREFS_LENGTH = 500


def _sanitize_text(text: str) -> str:
    """
    Sanitize free-text input by stripping injection patterns and truncating.

    Edge cases:
      U-23: Strip SQL/script injection patterns.
      U-24: Truncate to MAX_ADDITIONAL_PREFS_LENGTH chars.
    """
    if not text:
        return ""

    # Strip injection patterns
    cleaned = _INJECTION_PATTERNS.sub("", text)

    # Remove any HTML/script tags
    cleaned = re.sub(r"<[^>]*>", "", cleaned)

    # Truncate
    if len(cleaned) > MAX_ADDITIONAL_PREFS_LENGTH:
        logger.warning(
            "Additional preferences truncated from %d to %d chars",
            len(cleaned),
            MAX_ADDITIONAL_PREFS_LENGTH,
        )
        cleaned = cleaned[:MAX_ADDITIONAL_PREFS_LENGTH]

    return cleaned.strip()


# ---------------------------------------------------------------------------
# Validation Errors
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when user input fails validation."""

    def __init__(self, message: str, field: str = ""):
        self.field = field
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# UserPreferences Model
# ---------------------------------------------------------------------------

@dataclass
class UserPreferences:
    """
    Captures and validates user preferences for restaurant recommendations.

    Attributes:
        location: Required. The location/city to search in.
        budget: Required. Budget tier as string ('low', 'medium', 'high').
        cuisine: Optional. Preferred cuisine type(s), comma-separated.
        min_rating: Optional. Minimum rating filter (0.0–5.0, default 0.0).
        additional_preferences: Optional. Free-text preferences for soft matching.
    """

    location: str
    budget: str
    cuisine: Optional[str] = None
    min_rating: float = 0.0
    additional_preferences: Optional[str] = None

    # Parsed/normalized fields (set during validation)
    _budget_tier: Optional[BudgetTier] = field(default=None, repr=False)
    _cuisines_list: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Normalize inputs immediately on creation."""
        self._normalize()

    def _normalize(self) -> None:
        """Normalize all input fields to standard format."""
        # --- Location ---
        # Edge case U-03: strip whitespace
        if self.location:
            self.location = self.location.strip().title()

        # --- Budget ---
        # Edge case U-10: normalize casing
        if self.budget:
            self.budget = self.budget.strip().lower()

        # Parse budget tier
        self._budget_tier = BudgetTier.from_string(self.budget)

        # --- Cuisine ---
        # Edge case U-13: None/empty → skip
        # Edge case U-14: support comma-separated multiple cuisines
        if self.cuisine and self.cuisine.strip():
            raw_cuisines = [c.strip() for c in self.cuisine.split(",")]
            self._cuisines_list = [
                _normalize_cuisine(c) for c in raw_cuisines if c
            ]
        else:
            self._cuisines_list = []

        # --- Min Rating ---
        # Edge case U-17, U-18: clamp to [0.0, 5.0]
        # Edge case U-22: default to 0.0 if not provided
        if self.min_rating is None:
            self.min_rating = 0.0
        self.min_rating = max(0.0, min(5.0, float(self.min_rating)))

        # --- Additional Preferences ---
        # Edge case U-23, U-24, U-27
        if self.additional_preferences:
            self.additional_preferences = _sanitize_text(
                self.additional_preferences
            )
            if not self.additional_preferences:
                self.additional_preferences = None

    @property
    def budget_tier(self) -> BudgetTier:
        """Get the parsed BudgetTier enum value."""
        if self._budget_tier is None:
            self._budget_tier = BudgetTier.from_string(self.budget)
        return self._budget_tier

    @property
    def cuisines_list(self) -> list[str]:
        """Get the parsed list of cuisine strings."""
        return self._cuisines_list

    def validate(self, available_locations: list[str], available_cuisines: list[str]) -> list[str]:
        """
        Validate user preferences against the actual dataset values.

        Args:
            available_locations: List of valid locations from the dataset.
            available_cuisines: List of valid cuisines from the dataset.

        Returns:
            List of warning messages (non-fatal issues). Empty if all is clean.

        Raises:
            ValidationError: If a required field is invalid (location not found, etc.).
        """
        warnings: list[str] = []

        # --- Validate location ---
        # Edge case U-05: empty location
        if not self.location or not self.location.strip():
            raise ValidationError("Location is required.", field="location")

        # Edge case U-06: numeric or special character only
        if re.match(r"^[\d\W]+$", self.location):
            raise ValidationError(
                f"Invalid location format: '{self.location}'. "
                f"Please enter a valid city or area name.",
                field="location",
            )

        # Edge case U-01, U-02: location not found (case-insensitive)
        location_lower = self.location.lower()
        location_map = {loc.lower(): loc for loc in available_locations}

        if location_lower not in location_map:
            # Try partial matching for helpful error message
            close_matches = [
                loc for loc in available_locations
                if location_lower in loc.lower() or loc.lower() in location_lower
            ]
            suggestion = ""
            if close_matches:
                suggestion = f" Did you mean: {', '.join(close_matches[:5])}?"

            raise ValidationError(
                f"Location '{self.location}' not found in the dataset.{suggestion} "
                f"Available locations include: {', '.join(available_locations[:10])}...",
                field="location",
            )

        # Normalize to the exact casing from the dataset
        self.location = location_map[location_lower]

        # --- Validate budget ---
        # Edge case U-08, U-09: already handled in BudgetTier.from_string()

        # --- Validate cuisine ---
        # Edge case U-12, U-16: cuisine not in dataset
        if self._cuisines_list:
            cuisine_lower_map = {c.lower(): c for c in available_cuisines}
            validated_cuisines = []

            for cuisine in self._cuisines_list:
                if cuisine.lower() in cuisine_lower_map:
                    validated_cuisines.append(cuisine_lower_map[cuisine.lower()])
                else:
                    warnings.append(
                        f"Cuisine '{cuisine}' not found in the dataset. "
                        f"It will be skipped."
                    )

            self._cuisines_list = validated_cuisines

            if not self._cuisines_list and self.cuisine:
                warnings.append(
                    "None of the requested cuisines were found. "
                    "Showing results for all cuisines."
                )

        # --- Validate min_rating ---
        # Edge case U-19: handled by type coercion in _normalize
        # Edge case U-20: warn if very high
        if self.min_rating >= 4.5:
            warnings.append(
                f"Minimum rating of {self.min_rating} is very high. "
                f"This may significantly limit results."
            )

        return warnings

    def to_dict(self) -> dict:
        """Convert to a plain dictionary for API serialization."""
        return {
            "location": self.location,
            "budget": self.budget,
            "cuisine": self.cuisine,
            "min_rating": self.min_rating,
            "additional_preferences": self.additional_preferences,
        }

    def __repr__(self) -> str:
        parts = [f"location='{self.location}'", f"budget='{self.budget}'"]
        if self._cuisines_list:
            parts.append(f"cuisines={self._cuisines_list}")
        if self.min_rating > 0:
            parts.append(f"min_rating={self.min_rating}")
        if self.additional_preferences:
            parts.append(f"prefs='{self.additional_preferences[:30]}...'")
        return f"UserPreferences({', '.join(parts)})"
