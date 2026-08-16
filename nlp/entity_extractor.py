"""Extract structured travel preferences from a user's message.

The intent classifier determines *what* the user wants to do. This module
extracts the preference values needed by the recommendation engine. It uses a
transparent rule-based approach for the first prototype so each extracted
value can be explained and tested.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass(frozen=True)
class TravelPreferences:
    """Preference values recognised in one user message."""

    state: str | None = None
    interests: tuple[str, ...] = ()
    maximum_fee: float | None = None
    duration_days: int | None = None
    duration_hours: float | None = None
    family_friendly: bool | None = None
    elderly_friendly: bool | None = None
    wheelchair_accessible: bool | None = None
    accessibility_needs: tuple[str, ...] = ()

    def to_dict(self, omit_empty: bool = True) -> dict[str, Any]:
        """Return a JSON-friendly representation of the extracted values."""
        result = asdict(self)
        result["interests"] = list(self.interests)
        result["accessibility_needs"] = list(self.accessibility_needs)
        if omit_empty:
            result = {
                key: value
                for key, value in result.items()
                if value is not None and value != []
            }
        return result


# Canonical names match the values stored in the current SQLite database.
STATE_ALIASES = {
    "w.p. kuala lumpur": "Kuala Lumpur",
    "wp kuala lumpur": "Kuala Lumpur",
    "kuala lumpur": "Kuala Lumpur",
    "kl": "Kuala Lumpur",
    "w.p. putrajaya": "W.P. Putrajaya",
    "wp putrajaya": "W.P. Putrajaya",
    "putrajaya": "W.P. Putrajaya",
    "w.p. labuan": "W.P. Labuan",
    "wp labuan": "W.P. Labuan",
    "labuan": "W.P. Labuan",
    "negeri sembilan": "Negeri Sembilan",
    "pulau pinang": "Penang",
    "penang": "Penang",
    "malacca": "Melaka",
    "melaka": "Melaka",
    "terengganu": "Terengganu",
    "selangor": "Selangor",
    "sarawak": "Sarawak",
    "sabah": "Sabah",
    "perlis": "Perlis",
    "perak": "Perak",
    "pahang": "Pahang",
    "kelantan": "Kelantan",
    "kedah": "Kedah",
    "johor": "Johor",
}


# Terms are mapped to words already present in the attraction categories/tags.
INTEREST_ALIASES = {
    "hot springs": "hot spring",
    "hot spring": "hot spring",
    "theme parks": "theme park",
    "theme park": "theme park",
    "water park": "water park",
    "bird watching": "birdwatching",
    "birdwatching": "birdwatching",
    "jungle trekking": "hiking",
    "trekking": "hiking",
    "hiking": "hiking",
    "rainforest": "nature",
    "forest": "nature",
    "gardens": "nature",
    "garden": "nature",
    "scenery": "nature",
    "scenic": "nature",
    "nature": "nature",
    "seaside": "beach",
    "coast": "beach",
    "beaches": "beach",
    "beach": "beach",
    "islands": "island",
    "island": "island",
    "animals": "wildlife",
    "zoo": "wildlife",
    "wildlife": "wildlife",
    "heritage": "heritage",
    "historical": "history",
    "history": "history",
    "museum": "history",
    "cultural": "culture",
    "culture": "culture",
    "temple": "culture",
    "mosque": "culture",
    "adventurous": "adventure",
    "adventure": "adventure",
    "snorkelling": "snorkelling",
    "snorkeling": "snorkelling",
    "scuba diving": "scuba diving",
    "diving": "scuba diving",
    "shopping": "shopping",
    "local food": "food",
    "seafood": "food",
    "food": "food",
    "wellness": "relaxation",
    "peaceful": "relaxation",
    "relaxing": "relaxation",
    "relaxation": "relaxation",
}


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


STATE_PATTERNS = [
    (_phrase_pattern(alias), canonical)
    for alias, canonical in sorted(STATE_ALIASES.items(), key=lambda item: -len(item[0]))
]
INTEREST_PATTERNS = [
    (_phrase_pattern(alias), canonical)
    for alias, canonical in sorted(INTEREST_ALIASES.items(), key=lambda item: -len(item[0]))
]

BUDGET_PATTERNS = [
    re.compile(
        r"(?:under|below|less\s+than|no\s+more\s+than|up\s+to|maximum|max|within)"
        r"\s*(?:a\s+budget\s+of\s*)?(?:rm|myr)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"budget(?:\s+of|\s+is|\s+around)?\s*(?:rm|myr)?\s*"
        r"([0-9][0-9,]*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:rm|myr)\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:budget|or\s+less)",
        re.IGNORECASE,
    ),
]

DURATION_PATTERN = re.compile(
    r"(?<!\d)(\d+(?:\.\d+)?)\s*[- ]?\s*(day|days|hour|hours)\b",
    re.IGNORECASE,
)


def _extract_state(text: str) -> str | None:
    matches: list[tuple[int, str]] = []
    for pattern, state in STATE_PATTERNS:
        match = pattern.search(text)
        if match:
            matches.append((match.start(), state))
    return min(matches, default=(0, None), key=lambda item: item[0])[1]


def _extract_interests(text: str) -> tuple[str, ...]:
    matches: list[tuple[int, str]] = []
    for pattern, interest in INTEREST_PATTERNS:
        match = pattern.search(text)
        if match:
            matches.append((match.start(), interest))

    ordered: list[str] = []
    for _, interest in sorted(matches):
        if interest not in ordered:
            ordered.append(interest)
    return tuple(ordered)


def _extract_budget(text: str) -> float | None:
    if re.search(r"\b(?:free|no\s+entrance\s+fee|free\s+entry)\b", text, re.IGNORECASE):
        return 0.0
    for pattern in BUDGET_PATTERNS:
        match = pattern.search(text)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _extract_duration(text: str) -> tuple[int | None, float | None]:
    match = DURATION_PATTERN.search(text)
    if not match:
        return None, None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("day"):
        return int(value) if value.is_integer() else None, None
    return None, value


def extract_preferences(text: str) -> TravelPreferences:
    """Extract all supported preference values from ``text``.

    The function returns ``None`` for a Boolean preference that was not
    mentioned. This distinction is important when a later dialogue manager
    merges new values into an existing conversation context.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    duration_days, duration_hours = _extract_duration(text)
    family = bool(
        re.search(r"\b(?:family|families|children|child|kids|kid)\b", text, re.IGNORECASE)
    ) or None
    elderly = bool(
        re.search(
            r"\b(?:elderly|senior(?:s)?|older\s+(?:adult|adults|people|person|parent|parents)|"
            r"aged\s+parent|aged\s+parents|my\s+parents)\b",
            text,
            re.IGNORECASE,
        )
    ) or None
    wheelchair = bool(
        re.search(
            r"\b(?:wheelchair(?:[- ]accessible|[- ]friendly|\s+access)?|mobility\s+(?:aid|needs))\b",
            text,
            re.IGNORECASE,
        )
    ) or None
    accessibility_patterns = {
        "low_walking": (
            r"\b(?:cannot|can't|can not|unable to|difficulty|struggle(?:s)? to)\s+walk\b|"
            r"\b(?:little|less|minimal|short|limited)\s+walking\b|"
            r"\b(?:cannot|can't|can not)\s+walk\s+far\b"
        ),
        "step_free": (
            r"\b(?:no|avoid)\s+(?:stairs|steps)\b|"
            r"\b(?:step[- ]free|ramp|lift|elevator)\b|"
            r"\b(?:cannot|can't|can not|unable to|difficulty|struggle(?:s)? to)\b"
            r"[^.!?]{0,40}\bclimb\b"
        ),
        "seating": (
            r"\b(?:bench(?:es)?|resting\s+(?:seat|seats|area|areas)|"
            r"places?\s+to\s+(?:sit|rest)|need(?:s)?\s+to\s+rest)\b"
        ),
        "accessible_toilet": (
            r"\b(?:accessible|disabled|wheelchair)[- ](?:toilet|toilets|restroom|restrooms)\b|"
            r"\b(?:toilet|toilets|restroom|restrooms)\s+(?:nearby|access)\b"
        ),
        "nearby_parking": (
            r"\b(?:nearby|close|convenient|easy)[- ]parking\b|"
            r"\bparking\s+(?:nearby|close|near|access)\b|"
            r"\b(?:short|minimal)\s+walk\s+from\s+parking\b"
        ),
        "shelter": (
            r"\b(?:shelter(?:ed)?|shade(?:d)?|covered\s+(?:area|areas|walkway|walkways)|"
            r"avoid(?:ing)?\s+(?:heat|sun|rain))\b"
        ),
    }
    accessibility_needs = tuple(
        need
        for need, pattern in accessibility_patterns.items()
        if re.search(pattern, text, re.IGNORECASE)
    )

    return TravelPreferences(
        state=_extract_state(text),
        interests=_extract_interests(text),
        maximum_fee=_extract_budget(text),
        duration_days=duration_days,
        duration_hours=duration_hours,
        family_friendly=family,
        elderly_friendly=elderly,
        wheelchair_accessible=wheelchair,
        accessibility_needs=accessibility_needs,
    )


def to_recommendation_filters(preferences: TravelPreferences) -> dict[str, Any]:
    """Convert extracted values into current recommendation-engine arguments."""
    filters: dict[str, Any] = {}
    if preferences.state:
        filters["state"] = preferences.state
    if preferences.interests:
        # The current engine supports one interest. Preserve all interests in
        # TravelPreferences so multi-interest scoring can be added later.
        filters["interest"] = preferences.interests[0]
    if preferences.maximum_fee is not None:
        filters["maximum_fee"] = preferences.maximum_fee
    if preferences.family_friendly:
        filters["family_friendly"] = True
    if preferences.elderly_friendly:
        filters["elderly_friendly"] = True
    if preferences.wheelchair_accessible:
        filters["wheelchair_accessible"] = True
    if preferences.accessibility_needs:
        filters["accessibility_needs"] = preferences.accessibility_needs
    return filters
