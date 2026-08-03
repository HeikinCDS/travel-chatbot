"""Maintain travel preferences across multiple chatbot messages."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from nlp.entity_extractor import (
    TravelPreferences,
    extract_preferences,
    to_recommendation_filters,
)


REPLACE_INTEREST_PATTERN = re.compile(
    r"\b(?:actually|instead|rather|change|replace|switch)\b",
    re.IGNORECASE,
)

REQUIRED_RECOMMENDATION_FIELDS = ("state", "interests")

CLARIFICATION_QUESTIONS = {
    "state": "Which Malaysian state or federal territory would you like to visit?",
    "interests": (
        "What type of attraction interests you, such as nature, beach, "
        "history, wildlife or relaxation?"
    ),
}


@dataclass
class ConversationContext:
    """Serializable preference state for one user conversation.

    ``None`` means a preference has not been provided. Interests are stored as
    a list because one user can mention several activities. The class contains
    no Flask-specific code, so it can be tested independently and later stored
    in a Flask session.
    """

    state: str | None = None
    interests: list[str] = field(default_factory=list)
    maximum_fee: float | None = None
    duration_days: int | None = None
    duration_hours: float | None = None
    family_friendly: bool | None = None
    elderly_friendly: bool | None = None
    wheelchair_accessible: bool | None = None

    @classmethod
    def from_dict(cls, values: Mapping[str, Any] | None) -> "ConversationContext":
        """Restore a context previously saved by :meth:`to_dict`."""
        if values is None:
            return cls()
        if not isinstance(values, Mapping):
            raise TypeError("values must be a mapping or None")

        allowed = {
            "state",
            "interests",
            "maximum_fee",
            "duration_days",
            "duration_hours",
            "family_friendly",
            "elderly_friendly",
            "wheelchair_accessible",
        }
        unexpected = set(values) - allowed
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(f"Unsupported context field(s): {names}")

        interests = values.get("interests", [])
        if not isinstance(interests, (list, tuple)):
            raise TypeError("interests must be a list or tuple")

        return cls(
            state=values.get("state"),
            interests=list(interests),
            maximum_fee=values.get("maximum_fee"),
            duration_days=values.get("duration_days"),
            duration_hours=values.get("duration_hours"),
            family_friendly=values.get("family_friendly"),
            elderly_friendly=values.get("elderly_friendly"),
            wheelchair_accessible=values.get("wheelchair_accessible"),
        )

    def to_dict(self, omit_empty: bool = True) -> dict[str, Any]:
        """Return data that can be safely stored in a Flask session."""
        result = {
            "state": self.state,
            "interests": list(self.interests),
            "maximum_fee": self.maximum_fee,
            "duration_days": self.duration_days,
            "duration_hours": self.duration_hours,
            "family_friendly": self.family_friendly,
            "elderly_friendly": self.elderly_friendly,
            "wheelchair_accessible": self.wheelchair_accessible,
        }
        if omit_empty:
            return {
                key: value
                for key, value in result.items()
                if value is not None and value != []
            }
        return result

    def reset(self) -> None:
        """Clear every stored preference."""
        self.state = None
        self.interests.clear()
        self.maximum_fee = None
        self.duration_days = None
        self.duration_hours = None
        self.family_friendly = None
        self.elderly_friendly = None
        self.wheelchair_accessible = None

    def update(
        self,
        preferences: TravelPreferences,
        *,
        replace_interests: bool = False,
    ) -> dict[str, Any]:
        """Merge recognised values and return only the fields that changed."""
        if not isinstance(preferences, TravelPreferences):
            raise TypeError("preferences must be a TravelPreferences instance")

        before = self.to_dict(omit_empty=False)

        if preferences.state is not None:
            self.state = preferences.state

        if preferences.interests:
            if replace_interests:
                self.interests = list(preferences.interests)
            else:
                for interest in preferences.interests:
                    if interest not in self.interests:
                        self.interests.append(interest)

        for field_name in (
            "maximum_fee",
            "duration_days",
            "duration_hours",
            "family_friendly",
            "elderly_friendly",
            "wheelchair_accessible",
        ):
            value = getattr(preferences, field_name)
            if value is not None:
                setattr(self, field_name, value)

        after = self.to_dict(omit_empty=False)
        return {
            key: value
            for key, value in after.items()
            if value != before[key]
        }

    def update_from_text(self, text: str) -> dict[str, Any]:
        """Extract values from a message and merge them into the context."""
        preferences = extract_preferences(text)
        replace_interests = bool(REPLACE_INTEREST_PATTERN.search(text))
        return self.update(
            preferences,
            replace_interests=replace_interests,
        )

    def clear_preference(self, field_name: str) -> None:
        """Clear one supported field without resetting the full conversation."""
        if field_name not in self.to_dict(omit_empty=False):
            raise ValueError(f"Unsupported context field: {field_name}")
        if field_name == "interests":
            self.interests.clear()
        else:
            setattr(self, field_name, None)

    def missing_required_preferences(self) -> list[str]:
        """Return the minimum missing fields needed for recommendation."""
        missing: list[str] = []
        if not self.state:
            missing.append("state")
        if not self.interests:
            missing.append("interests")
        return missing

    def is_ready_for_recommendation(self) -> bool:
        return not self.missing_required_preferences()

    def next_clarification_question(self) -> str | None:
        """Ask for the first missing required preference, if any."""
        missing = self.missing_required_preferences()
        return CLARIFICATION_QUESTIONS[missing[0]] if missing else None

    def recommendation_filters(self) -> dict[str, Any]:
        """Convert the current state to recommendation-engine arguments."""
        preferences = TravelPreferences(
            state=self.state,
            interests=tuple(self.interests),
            maximum_fee=self.maximum_fee,
            duration_days=self.duration_days,
            duration_hours=self.duration_hours,
            family_friendly=self.family_friendly,
            elderly_friendly=self.elderly_friendly,
            wheelchair_accessible=self.wheelchair_accessible,
        )
        return to_recommendation_filters(preferences)

    def preference_summary(self) -> str:
        """Create a short confirmation suitable for a later response layer."""
        parts: list[str] = []
        if self.state:
            parts.append(f"location: {self.state}")
        if self.interests:
            parts.append(f"interests: {', '.join(self.interests)}")
        if self.maximum_fee is not None:
            parts.append(f"maximum entrance fee: RM{self.maximum_fee:g}")
        if self.duration_days is not None:
            parts.append(f"duration: {self.duration_days} day(s)")
        elif self.duration_hours is not None:
            parts.append(f"duration: {self.duration_hours:g} hour(s)")
        if self.family_friendly:
            parts.append("family-friendly")
        if self.elderly_friendly:
            parts.append("elderly-friendly")
        if self.wheelchair_accessible:
            parts.append("wheelchair-accessible")
        return "; ".join(parts) if parts else "No travel preferences recorded."
