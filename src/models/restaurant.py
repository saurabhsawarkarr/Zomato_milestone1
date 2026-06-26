"""
Restaurant data model.

Defines the Restaurant dataclass used throughout the application for
type-safe restaurant data handling, serialization, and prompt generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Restaurant:
    """Represents a single restaurant from the Zomato dataset."""

    name: str
    location: str
    cuisines: list[str] = field(default_factory=list)
    cost_for_two: Optional[float] = None
    rating: float = 0.0
    votes: int = 0
    restaurant_type: str = ""
    highlights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a plain dictionary for JSON serialization."""
        return asdict(self)

    def to_prompt_string(self) -> str:
        """
        Format the restaurant as a concise text block for inclusion
        in an LLM prompt. Only includes available information.
        """
        parts = [f"- **{self.name}**"]

        if self.cuisines:
            parts.append(f"  Cuisine: {', '.join(self.cuisines)}")

        parts.append(f"  Location: {self.location}")

        if self.cost_for_two is not None:
            parts.append(f"  Cost for Two: ₹{int(self.cost_for_two)}")
        else:
            parts.append("  Cost for Two: Not available")

        parts.append(f"  Rating: {self.rating}/5.0 ({self.votes} votes)")

        if self.restaurant_type:
            parts.append(f"  Type: {self.restaurant_type}")

        if self.highlights:
            parts.append(f"  Highlights: {', '.join(self.highlights)}")

        return "\n".join(parts)

    def __repr__(self) -> str:
        cuisines_str = ", ".join(self.cuisines[:3])
        cost_str = f"₹{int(self.cost_for_two)}" if self.cost_for_two else "N/A"
        return (
            f"Restaurant('{self.name}' | {self.location} | "
            f"{cuisines_str} | {self.rating}★ | {cost_str})"
        )
