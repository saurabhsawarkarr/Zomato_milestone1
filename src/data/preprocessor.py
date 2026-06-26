"""
Data preprocessor for the Zomato restaurant dataset.

Cleans, normalizes, and indexes the raw dataset into a query-ready
format. Handles edge cases D-08 through D-19 from edge-cases.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from src.models.restaurant import Restaurant

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column name mapping — handles variations in dataset column names
# ---------------------------------------------------------------------------
# Maps our internal field names to possible column names in the dataset
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["name", "restaurant_name", "restaurant name", "res_name"],
    "location": ["location", "city", "locality", "address", "area"],
    "cuisines": ["cuisines", "cuisine", "cuisine_type"],
    "cost_for_two": [
        "cost_for_two",
        "cost for two",
        "average_cost_for_two",
        "avg_cost",
        "approx_cost(for two people)",
        "approx_cost",
        "cost",
    ],
    "rating": [
        "rating",
        "aggregate_rating",
        "rate",
        "avg_rating",
        "ratings",
    ],
    "votes": ["votes", "num_votes", "review_count", "reviews"],
    "restaurant_type": [
        "restaurant_type",
        "type",
        "rest_type",
        "listed_in(type)",
        "online_order",
    ],
    "highlights": [
        "highlights",
        "features",
        "amenities",
        "dish_liked",
        "cuisines_offered",
    ],
}


def _resolve_column(df: pd.DataFrame, field_name: str) -> str | None:
    """
    Find the actual column name in the DataFrame that matches our expected field.

    Args:
        df: The DataFrame to search.
        field_name: Our internal field name (e.g., 'name', 'location').

    Returns:
        The actual column name found in the DataFrame, or None.
    """
    aliases = COLUMN_ALIASES.get(field_name, [field_name])
    df_columns_lower = {col.lower().strip(): col for col in df.columns}

    for alias in aliases:
        if alias.lower() in df_columns_lower:
            return df_columns_lower[alias.lower()]

    return None


def _clean_cost(value: Any) -> float | None:
    """
    Parse cost_for_two from various formats to a numeric value.

    Handles edge cases D-12, D-13:
      - Currency symbols: "₹500", "$25" → 500, 25
      - Comma-separated: "1,200" → 1200
      - Non-numeric: "N/A", "-" → None
      - Zero/negative → None
    """
    if pd.isna(value) or value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None

    # String cleanup
    text = str(value).strip()

    # Remove currency symbols and commas
    text = re.sub(r"[₹$€£,\s]", "", text)

    # Remove any remaining non-numeric characters except dot
    text = re.sub(r"[^\d.]", "", text)

    if not text:
        return None

    try:
        cost = float(text)
        return cost if cost > 0 else None
    except ValueError:
        return None


def _clean_rating(value: Any) -> float:
    """
    Parse rating to a float in the range [0.0, 5.0].

    Handles edge cases D-10, D-11:
      - Non-numeric values ("NEW", "-", "N/A") → 0.0
      - Out of range → clamped to [0.0, 5.0]
    """
    if pd.isna(value) or value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return max(0.0, min(5.0, float(value)))

    text = str(value).strip()

    # Common non-numeric placeholders
    if text.lower() in ("new", "-", "n/a", "", "nan", "none", "--"):
        return 0.0

    # Extract first numeric value from string
    match = re.search(r"(\d+\.?\d*)", text)
    if match:
        return max(0.0, min(5.0, float(match.group(1))))

    return 0.0


def _parse_cuisines(value: Any) -> list[str]:
    """
    Parse cuisines field into a list of title-cased cuisine strings.

    Handles edge cases D-14, D-15, D-16:
      - Comma-separated string → list
      - Empty/null → ["Unknown"]
      - Inconsistent casing → title case
    """
    if pd.isna(value) or value is None:
        return ["Unknown"]

    if isinstance(value, list):
        items = value
    else:
        # Split by comma and clean
        items = [c.strip() for c in str(value).split(",")]

    # Normalize to title case and remove empties
    cleaned = [c.strip().title() for c in items if c.strip()]

    return cleaned if cleaned else ["Unknown"]


def _parse_list_field(value: Any) -> list[str]:
    """
    Parse a generic list field (e.g., highlights) from various formats.

    Handles edge case D-18: missing highlights → empty list.
    """
    if pd.isna(value) or value is None:
        return []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    # Try comma-separated string
    items = [c.strip() for c in str(value).split(",")]
    return [item for item in items if item and item.lower() not in ("nan", "none", "")]


def _clean_votes(value: Any) -> int:
    """Parse votes to an integer, defaulting to 0."""
    if pd.isna(value) or value is None:
        return 0

    if isinstance(value, (int, float)):
        return max(0, int(value))

    text = re.sub(r"[^\d]", "", str(value))
    return int(text) if text else 0


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and normalize the raw dataset DataFrame.

    Steps:
      1. Map column names to standard field names
      2. Clean individual fields (cost, rating, cuisines, etc.)
      3. Drop rows with missing critical fields (name, location)
      4. Deduplicate
      5. Sort by rating descending

    Args:
        df: Raw DataFrame from the loader.

    Returns:
        Cleaned and normalized DataFrame.
    """
    logger.info("Preprocessing dataset (%d rows)...", len(df))
    original_count = len(df)

    # --- Step 1: Resolve and rename columns ---
    column_map: dict[str, str] = {}
    for field_name in COLUMN_ALIASES:
        actual_col = _resolve_column(df, field_name)
        if actual_col:
            column_map[actual_col] = field_name
            logger.debug("Mapped column '%s' → '%s'", actual_col, field_name)
        else:
            logger.debug("No column found for field '%s'", field_name)

    df = df.rename(columns=column_map)

    # --- Step 2: Ensure required columns exist ---
    if "name" not in df.columns:
        raise RuntimeError(
            f"Cannot find a 'name' column in the dataset. "
            f"Available columns: {list(df.columns)}"
        )

    if "location" not in df.columns:
        # Try to use any address-like column
        logger.warning("No 'location' column found. Checking alternatives...")
        for col in df.columns:
            if any(
                kw in col.lower()
                for kw in ("city", "location", "area", "locality", "address")
            ):
                df = df.rename(columns={col: "location"})
                logger.info("Using '%s' as location column", col)
                break
        else:
            raise RuntimeError(
                f"Cannot find a 'location' column in the dataset. "
                f"Available columns: {list(df.columns)}"
            )

    # --- Step 3: Clean individual fields ---

    # Edge case D-08: Drop rows with missing name
    df = df.dropna(subset=["name"])
    df = df[df["name"].astype(str).str.strip() != ""]

    # Edge case D-09: Drop rows with missing location
    df = df.dropna(subset=["location"])
    df = df[df["location"].astype(str).str.strip() != ""]

    # Normalize location: strip whitespace, title case
    df["location"] = df["location"].astype(str).str.strip().str.title()

    # Normalize name: strip whitespace, preserve original casing (edge case D-19)
    df["name"] = df["name"].astype(str).str.strip()

    # Clean cost (edge cases D-12, D-13)
    if "cost_for_two" in df.columns:
        df["cost_for_two"] = df["cost_for_two"].apply(_clean_cost)
    else:
        df["cost_for_two"] = None

    # Clean rating (edge cases D-10, D-11)
    if "rating" in df.columns:
        df["rating"] = df["rating"].apply(_clean_rating)
    else:
        df["rating"] = 0.0

    # Parse cuisines (edge cases D-14, D-15, D-16)
    if "cuisines" in df.columns:
        df["cuisines"] = df["cuisines"].apply(_parse_cuisines)
    else:
        df["cuisines"] = [["Unknown"]] * len(df)

    # Clean votes
    if "votes" in df.columns:
        df["votes"] = df["votes"].apply(_clean_votes)
    else:
        df["votes"] = 0

    # Parse restaurant type
    if "restaurant_type" in df.columns:
        df["restaurant_type"] = df["restaurant_type"].astype(str).str.strip()
    else:
        df["restaurant_type"] = ""

    # Parse highlights (edge case D-18)
    if "highlights" in df.columns:
        df["highlights"] = df["highlights"].apply(_parse_list_field)
    else:
        df["highlights"] = [[] for _ in range(len(df))]

    # --- Step 4: Deduplicate (edge case D-17) ---
    before_dedup = len(df)
    df = df.sort_values("votes", ascending=False).drop_duplicates(
        subset=["name", "location"], keep="first"
    )
    dedup_removed = before_dedup - len(df)
    if dedup_removed > 0:
        logger.info("Removed %d duplicate entries", dedup_removed)

    # --- Step 5: Sort by rating descending ---
    df = df.sort_values("rating", ascending=False).reset_index(drop=True)

    # Keep only the columns we need
    keep_cols = [
        "name", "location", "cuisines", "cost_for_two",
        "rating", "votes", "restaurant_type", "highlights",
    ]
    available_cols = [c for c in keep_cols if c in df.columns]
    df = df[available_cols]

    logger.info(
        "Preprocessing complete: %d → %d rows (%d removed)",
        original_count,
        len(df),
        original_count - len(df),
    )

    return df


# ---------------------------------------------------------------------------
# Search Index
# ---------------------------------------------------------------------------

class SearchIndex:
    """
    In-memory search index for O(1) lookups by location and cuisine.

    Attributes:
        by_location: Dict mapping lowercase location → list of DataFrame indices.
        by_cuisine: Dict mapping lowercase cuisine → list of DataFrame indices.
        locations: Sorted list of unique locations (title case).
        cuisines: Sorted list of unique cuisines (title case).
    """

    def __init__(self, df: pd.DataFrame):
        """Build the search index from a preprocessed DataFrame."""
        logger.info("Building search index...")

        self.by_location: dict[str, list[int]] = {}
        self.by_cuisine: dict[str, list[int]] = {}

        for idx, row in df.iterrows():
            # Index by location
            loc_key = str(row["location"]).lower().strip()
            if loc_key not in self.by_location:
                self.by_location[loc_key] = []
            self.by_location[loc_key].append(idx)

            # Index by each cuisine
            cuisines = row.get("cuisines", [])
            if isinstance(cuisines, list):
                for cuisine in cuisines:
                    c_key = cuisine.lower().strip()
                    if c_key not in self.by_cuisine:
                        self.by_cuisine[c_key] = []
                    self.by_cuisine[c_key].append(idx)

        # Build sorted lists for display/validation
        self.locations: list[str] = sorted(
            set(str(row["location"]) for _, row in df.iterrows())
        )
        self.cuisines: list[str] = sorted(
            set(
                cuisine
                for _, row in df.iterrows()
                for cuisine in (row.get("cuisines", []) if isinstance(row.get("cuisines"), list) else [])
                if cuisine.lower() != "unknown"
            )
        )

        logger.info(
            "Search index built: %d locations, %d cuisines",
            len(self.locations),
            len(self.cuisines),
        )

    def get_by_location(self, location: str) -> list[int]:
        """Get row indices for a given location (case-insensitive)."""
        return self.by_location.get(location.lower().strip(), [])

    def get_by_cuisine(self, cuisine: str) -> list[int]:
        """Get row indices for a given cuisine (case-insensitive)."""
        return self.by_cuisine.get(cuisine.lower().strip(), [])

    def has_location(self, location: str) -> bool:
        """Check if a location exists in the index."""
        return location.lower().strip() in self.by_location

    def has_cuisine(self, cuisine: str) -> bool:
        """Check if a cuisine exists in the index."""
        return cuisine.lower().strip() in self.by_cuisine


def build_index(df: pd.DataFrame) -> SearchIndex:
    """Build and return a SearchIndex from a preprocessed DataFrame."""
    return SearchIndex(df)


def df_to_restaurants(df: pd.DataFrame) -> list[Restaurant]:
    """
    Convert a DataFrame (or subset) to a list of Restaurant objects.

    Args:
        df: A preprocessed DataFrame or filtered subset.

    Returns:
        List of Restaurant instances.
    """
    restaurants = []
    for _, row in df.iterrows():
        restaurants.append(
            Restaurant(
                name=str(row.get("name", "")),
                location=str(row.get("location", "")),
                cuisines=row.get("cuisines", []) if isinstance(row.get("cuisines"), list) else [],
                cost_for_two=row.get("cost_for_two"),
                rating=float(row.get("rating", 0.0)),
                votes=int(row.get("votes", 0)),
                restaurant_type=str(row.get("restaurant_type", "")),
                highlights=row.get("highlights", []) if isinstance(row.get("highlights"), list) else [],
            )
        )
    return restaurants
