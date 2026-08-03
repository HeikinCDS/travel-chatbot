"""Natural-language processing components for the travel chatbot."""

from .entity_extractor import (
    TravelPreferences,
    extract_preferences,
    to_recommendation_filters,
)

__all__ = [
    "TravelPreferences",
    "extract_preferences",
    "to_recommendation_filters",
]
