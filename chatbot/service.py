"""Coordinate intent, preference, context and recommendation modules."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
import os
import re
from typing import Any, Mapping, Protocol

from dialogue.context_manager import ConversationContext, REPLACE_INTEREST_PATTERN
from nlp.entity_extractor import extract_preferences
from nlp.intent_classifier import IntentClassifier, IntentPrediction
from nlp.local_llm import (
    LLMInterpretation,
    LocalLLMInterpreter,
    merge_preferences,
)
from recommendation_engine.recommendation_engine import (
    find_attraction_by_name_in_text,
    get_attraction_by_id,
    recommend_attractions,
)
from web_discovery import OpenDataDiscovery
from chatbot.attraction_images import get_attraction_image


class IntentPredictor(Protocol):
    def predict(self, text: str) -> IntentPrediction:
        """Return an intent prediction for one message."""


class AttractionDiscovery(Protocol):
    def discover(
        self,
        preferences: Mapping[str, Any],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return current attraction candidates with supporting references."""

    def get_by_id(self, attraction_id: str) -> dict[str, Any] | None:
        """Retrieve one attraction that was returned earlier."""


class LanguageInterpreter(Protocol):
    def interpret(
        self,
        text: str,
        context: Mapping[str, Any],
    ) -> LLMInterpretation | None:
        """Return a validated local-model interpretation when available."""

    def generate_descriptions(
        self,
        attractions: list[Mapping[str, Any]],
    ) -> dict[str, str]:
        """Return grounded display descriptions keyed by attraction ID."""


class DisabledLanguageInterpreter:
    """No-op interpreter used when local language generation is switched off."""

    def interpret(
        self,
        text: str,
        context: Mapping[str, Any],
    ) -> None:
        return None

    def generate_descriptions(
        self,
        attractions: list[Mapping[str, Any]],
    ) -> dict[str, str]:
        return {}


EXPLICIT_RESET_PATTERN = re.compile(
    r"^\s*(?:reset|start\s+over|begin\s+again|new\s+search|"
    r"clear\s+(?:everything|all\s+preferences|my\s+preferences))"
    r"\s*(?:please)?[.!]?\s*$",
    re.IGNORECASE,
)

EXPLICIT_GOODBYE_PATTERN = re.compile(
    r"^\s*(?:goodbye|bye|see\s+you|talk\s+later|exit|quit|"
    r"that(?:'s|\s+is)\s+all|thanks?,?\s+bye)\s*[.!]?\s*$",
    re.IGNORECASE,
)

NO_CHANGE_PATTERN = re.compile(
    r"^\s*(?:no\s+changes?|nothing\s+to\s+change|keep\s+(?:it|them)\s+"
    r"(?:the\s+)?same|leave\s+(?:it|them)\s+(?:the\s+)?same|"
    r"never\s+mind|cancel)\s*[.!]?\s*$",
    re.IGNORECASE,
)

NO_SPECIAL_ACCESS_PATTERN = re.compile(
    r"^\s*(?:no\s+(?:special\s+)?(?:accessibility|mobility)\s+"
    r"(?:needs?|requirements?)|no\s+special\s+requirements?|"
    r"none\s+of\s+these)\s*[.!]?\s*$",
    re.IGNORECASE,
)

DIRECT_INFORMATION_PATTERN = re.compile(
    r"\b(?:tell\s+me\s+about|information\s+(?:about|on)|"
    r"what\s+(?:is|are)|describe|details?\s+(?:about|on))\b",
    re.IGNORECASE,
)

NEW_TRIP_REQUEST_PATTERN = re.compile(
    r"\b(?:i\s+(?:would|'d)\s+like\s+to\s+visit|"
    r"i\s+(?:want|plan)\s+to\s+(?:visit|travel\s+to|go\s+to)|"
    r"plan(?:ning)?\s+(?:a\s+)?(?:new\s+)?trip\s+to|"
    r"start(?:ing)?\s+(?:a\s+)?(?:new\s+)?trip\s+to)\b",
    re.IGNORECASE,
)

EXPLICIT_FRESH_TRIP_PATTERN = re.compile(
    r"\b(?:new\s+(?:trip|journey|search)|start\s+over|begin\s+again)\b",
    re.IGNORECASE,
)

STATE_SUGGESTIONS = (
    {"label": "Johor", "message": "Johor"},
    {"label": "Penang", "message": "Penang"},
    {"label": "Perak", "message": "Perak"},
    {"label": "Pahang", "message": "Pahang"},
    {"label": "Sabah", "message": "Sabah"},
    {"label": "Sarawak", "message": "Sarawak"},
)


def _environment_flag(name: str, *, default: bool = False) -> bool:
    """Read a predictable true/false feature flag from the environment."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


INTEREST_SUGGESTIONS = (
    {"label": "Nature", "message": "Nature"},
    {"label": "Beach", "message": "Beach"},
    {"label": "History", "message": "History"},
    {"label": "Wildlife", "message": "Wildlife"},
    {"label": "Relaxation", "message": "Relaxation"},
)

ELDERLY_TRIP_SUGGESTION = {
    "label": "Switch to elderly-friendly trip",
    "message": "I am planning a comfortable trip for an elderly traveller",
}

ACCESSIBILITY_SUGGESTIONS = (
    {"label": "Minimal walking", "message": "The traveller needs minimal walking"},
    {"label": "Wheelchair access", "message": "The traveller needs wheelchair access"},
    {"label": "Nearby seats", "message": "The traveller needs benches and places to rest"},
    {"label": "Accessible toilet", "message": "The traveller needs an accessible toilet"},
    {"label": "No special requirements", "message": "No special accessibility requirements"},
)

PREFERENCE_CHANGE_SUGGESTIONS = (
    {"label": "Location", "message": "Change my location"},
    {"label": "Interest", "message": "Change my interest"},
    {"label": "Accessibility", "message": "Change my accessibility needs"},
)

BUDGET_SUGGESTIONS = (
    {"label": "Up to RM20", "message": "Change my budget to RM20"},
    {"label": "Up to RM50", "message": "Change my budget to RM50"},
    {"label": "Up to RM100", "message": "Change my budget to RM100"},
)

PREFERENCE_FIELD_PATTERN = re.compile(
    r"^\s*(?:(?:change|update|edit)(?:\s+my)?\s+)?"
    r"(?P<field>location|state|destination|interest|budget|cost|fee|"
    r"accessibility(?:\s+needs?)?|mobility(?:\s+needs?)?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

SELECTION_PATTERNS = (
    (0, re.compile(r"\b(?:first|1st|option\s*1|number\s*1)\b", re.IGNORECASE)),
    (1, re.compile(r"\b(?:second|2nd|option\s*2|number\s*2)\b", re.IGNORECASE)),
    (2, re.compile(r"\b(?:third|3rd|option\s*3|number\s*3)\b", re.IGNORECASE)),
)

SELECTION_CUE_PATTERN = re.compile(
    r"\b(?:choose|chose|select|pick|take|go\s+with|let'?s\s+go\s+with|"
    r"tell\s+me\s+about|information\s+(?:about|on)|details?\s+(?:about|on))\b",
    re.IGNORECASE,
)

AFFIRMATIVE_CONFIRMATION_PATTERN = re.compile(
    r"^\s*(?:yes|yeah|yep|correct|that'?s\s+right|yes\s+please)\s*[.!]?\s*$",
    re.IGNORECASE,
)

NEGATIVE_CONFIRMATION_PATTERN = re.compile(
    r"^\s*(?:no|nope|not\s+that\s+one|that'?s\s+not\s+it)\s*[.!]?\s*$",
    re.IGNORECASE,
)

ACCESS_COMPARISON_PATTERN = re.compile(
    r"\b(?:most accessible|easiest access|easy walking|least walking|"
    r"best for (?:an? )?(?:elderly|senior)|wheelchair)\b",
    re.IGNORECASE,
)
CHEAPEST_COMPARISON_PATTERN = re.compile(
    r"\b(?:cheapest|lowest cost|lowest price|most affordable|budget option)\b",
    re.IGNORECASE,
)
SHORTEST_COMPARISON_PATTERN = re.compile(
    r"\b(?:shortest|quickest|least time|short visit)\b",
    re.IGNORECASE,
)

SHOW_PREVIOUS_OPTIONS_PATTERN = re.compile(
    r"\b(?:go\s+back|back\s+to\s+(?:the\s+)?(?:options?|choices?|results?)|"
    r"previous\s+(?:options?|choices?|recommendations?|results?)|"
    r"(?:show|see|reopen|return\s+to|take\s+me\s+back\s+to)\s+"
    r"(?:me\s+)?(?:the\s+)?(?:previous|last|earlier|old)?\s*"
    r"(?:options?|choices?|recommendations?|results?)|"
    r"show\s+(?:me\s+)?(?:the\s+)?(?:options?|choices?|results?)\s+again|"
    r"what(?:'?s|\s+is|\s+are)?\s+(?:the\s+)?other\s+(?:choices?|options?|places?)|"
    r"what\s+were\s+(?:my|the)\s+(?:choices?|options?|results?)|"
    r"what\s+else\s+did\s+you\s+(?:suggest|recommend)|"
    r"other\s+(?:choices?|options?)\s+from\s+before)\b",
    re.IGNORECASE,
)

SHOW_MORE_OPTIONS_PATTERN = re.compile(
    r"\b(?:show|give|find|see)\s+(?:me\s+)?(?:some\s+)?"
    r"(?:more|additional|different)\s+"
    r"(?:options?|choices?|recommendations?|results?|places?)\b|"
    r"\b(?:more|additional|different)\s+"
    r"(?:options?|choices?|recommendations?|results?|places?)\b|"
    r"\b(?:show|give)\s+(?:me\s+)?(?:the\s+)?next\s+"
    r"(?:three|3|few|options?|choices?|results?|places?)\b|"
    r"\bwhat\s+else\s+(?:is\s+there|can\s+you\s+(?:show|recommend))\b",
    re.IGNORECASE,
)


def _ranking_criterion(text: str) -> str | None:
    if ACCESS_COMPARISON_PATTERN.search(text):
        return "accessibility"
    if CHEAPEST_COMPARISON_PATTERN.search(text):
        return "cost"
    if SHORTEST_COMPARISON_PATTERN.search(text):
        return "duration"
    return None


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _yes_partial_score(value: Any) -> int:
    return {"yes": 2, "partial": 1}.get(str(value).casefold(), 0)


def _fee_summary(attraction: Mapping[str, Any]) -> str | None:
    minimum = attraction.get("min_fee_myr")
    maximum = attraction.get("max_fee_myr")
    status = str(attraction.get("entrance_fee_status") or "").casefold()
    if status == "free" or (minimum == 0 and maximum == 0):
        return "Free entry is recorded"
    if minimum is not None and maximum is not None:
        if float(minimum) == float(maximum):
            return f"Recorded entrance fee: RM{float(minimum):g}"
        return f"Recorded entrance-fee range: RM{float(minimum):g}-RM{float(maximum):g}"
    if minimum is not None:
        return f"Recorded entrance fee starts from RM{float(minimum):g}"
    return None


def _duration_summary(attraction: Mapping[str, Any]) -> str | None:
    hours = attraction.get("recommended_duration_hours")
    if hours is None:
        return None
    return f"Suggested visit duration: about {float(hours):g} hour(s)"


def _access_summary(attraction: Mapping[str, Any]) -> str | None:
    elderly = str(attraction.get("elderly_friendly") or "").strip().casefold()
    wheelchair = str(
        attraction.get("wheelchair_accessible") or ""
    ).strip().casefold()
    details = []
    if elderly in {"yes", "partial", "no"}:
        details.append(f"Elderly-friendly: {elderly.title()}")
    if wheelchair in {"yes", "partial", "no"}:
        details.append(f"wheelchair access: {wheelchair.title()}")
    walking = str(attraction.get("walking_difficulty") or "").strip().casefold()
    if walking in {"low", "moderate", "high"}:
        details.append(f"walking difficulty: {walking}")
    feature_labels = {
        "step_free_access": "step-free access",
        "resting_seats_available": "resting seats",
        "accessible_toilet": "accessible toilet",
        "shelter_available": "shelter",
    }
    for field_name, label in feature_labels.items():
        value = str(attraction.get(field_name) or "").strip().casefold()
        if value in {"yes", "partial", "no"}:
            details.append(f"{label}: {value.title()}")
    parking = str(attraction.get("parking_proximity") or "").strip().casefold()
    if parking in {"near", "moderate", "far"}:
        details.append(f"parking: {parking}")
    return "; ".join(details) or None


def _accessibility_detail(attraction: Mapping[str, Any]) -> str | None:
    """Describe missing structured facts without a generic verification warning."""

    missing = []
    elderly = str(
        attraction.get("elderly_friendly") or ""
    ).strip().casefold()
    wheelchair = str(
        attraction.get("wheelchair_accessible") or ""
    ).strip().casefold()
    known_values = {"yes", "partial", "no"}
    if elderly not in known_values:
        missing.append("elderly suitability")
    if wheelchair not in known_values:
        missing.append("wheelchair access")

    elderly_note = str(
        attraction.get("elderly_accessibility_notes") or ""
    ).strip()
    note = elderly_note or str(attraction.get("accessibility_notes") or "").strip()
    generic_markers = (
        "not been verified",
        "not been confirmed",
        "information is not available",
        "information has not been verified",
        "information has not been confirmed",
        "confirmed via independent research pass",
    )
    note_is_specific = note and not any(
        marker in note.casefold() for marker in generic_markers
    )

    if note_is_specific:
        return f"Accessibility notes: {note}"
    if missing:
        return "Accessibility details not recorded: " + " and ".join(missing)
    return None


def _accessibility_features(
    attraction: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Return consistent, readable accessibility rows for result cards."""

    overall = str(attraction.get("elderly_suitability") or "").strip()
    if overall.casefold() not in {
        "suitable",
        "suitable with assistance",
        "not recommended",
    }:
        legacy = str(attraction.get("elderly_friendly") or "").strip().casefold()
        overall = {
            "yes": "Suitable",
            "partial": "Suitable with assistance",
            "no": "Not recommended",
        }.get(legacy, "Not recorded")

    fields = (
        ("Walking difficulty", attraction.get("walking_difficulty")),
        ("Step-free access", attraction.get("step_free_access")),
        ("Resting seats", attraction.get("resting_seats_available")),
        ("Accessible toilet", attraction.get("accessible_toilet")),
        ("Parking proximity", attraction.get("parking_proximity")),
        ("Shelter", attraction.get("shelter_available")),
        ("Overall elderly suitability", overall),
    )
    positive = {"low", "yes", "near", "suitable"}
    caution = {"moderate", "partial", "suitable with assistance"}
    negative = {"high", "no", "far", "not recommended"}
    features = []
    for label, raw_value in fields:
        value = str(raw_value or "").strip()
        if not value or value.casefold() == "unknown":
            value = "Not recorded"
        normalised = value.casefold()
        status = (
            "positive" if normalised in positive else
            "caution" if normalised in caution else
            "negative" if normalised in negative else
            "unknown"
        )
        features.append({"label": label, "value": value, "status": status})
    return tuple(features)


def _elderly_suitability_reason(attraction: Mapping[str, Any]) -> str | None:
    """Summarise the attraction's recorded support without inventing claims."""

    documented = str(
        attraction.get("documented_accessibility_features") or ""
    ).strip().rstrip(".")
    if documented:
        return f"Recorded accessibility features: {documented}."

    screening_note = str(
        attraction.get("accessibility_screening_notes") or ""
    ).strip()
    generic_prefixes = (
        "recorded because the source",
        "recorded because the sources",
    )
    if screening_note and not screening_note.casefold().startswith(generic_prefixes):
        return screening_note
    return None


def _display_description(attraction: Mapping[str, Any]) -> str:
    description = str(attraction.get("short_description") or "").strip()
    if description and not description.casefold().startswith("ai-generated candidate"):
        return description

    name = attraction.get("attraction_name") or "This attraction"
    category = str(attraction.get("primary_category") or "travel").casefold()
    city = attraction.get("city_district")
    state = attraction.get("state_territory")
    location = ", ".join(str(value) for value in (city, state) if value)
    tags = [
        tag.strip().casefold()
        for tag in re.split(r"[;,]", str(attraction.get("interests_tags") or ""))
        if tag.strip()
    ][:3]
    interests = ", ".join(tags)
    result = f"{name} is a {category} attraction"
    if location:
        result += f" in {location}"
    result += "."
    if interests:
        result += f" It may appeal to visitors interested in {interests}."
    return result


def _present_attraction(attraction: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(attraction)
    for key, value in get_attraction_image(
        attraction.get("attraction_id")
    ).items():
        if not result.get(key):
            result[key] = value
    result["display_description"] = _display_description(attraction)
    result["cost_summary"] = _fee_summary(attraction)
    result["duration_summary"] = _duration_summary(attraction)
    result["accessibility_summary"] = _access_summary(attraction)
    result["accessibility_notes"] = _accessibility_detail(attraction)
    result["accessibility_features"] = list(_accessibility_features(attraction))
    eligibility = str(
        attraction.get("elderly_recommendation_eligibility") or ""
    ).strip().casefold()
    if eligibility == "eligible":
        # Keep evidence available under Sources without adding a prominent
        # badge that competes with the attraction image and title.
        result["accessibility_evidence_badge"] = None
        evidence_urls = re.findall(
            r"https?://[^\s;]+",
            str(attraction.get("accessibility_evidence_source") or ""),
        )
        unique_evidence_urls = list(dict.fromkeys(evidence_urls))
        result["accessibility_evidence_links"] = (
            [{
                "title": "Accessibility information",
                "url": unique_evidence_urls[0],
            }]
            if unique_evidence_urls
            else []
        )
        result["accessibility_reason"] = _elderly_suitability_reason(attraction)
    else:
        result["accessibility_evidence_badge"] = None
        result["accessibility_evidence_links"] = []
        result["accessibility_reason"] = None
    # Source links remain visible on the card. Missing facts are omitted instead
    # of repeatedly warning travellers that each individual field is unverified.
    result["verification_note"] = None
    return result


@dataclass
class ChatSession:
    """Serializable state belonging to one user, not the global application."""

    context: ConversationContext = field(default_factory=ConversationContext)
    shown_attraction_ids: list[str] = field(default_factory=list)
    shown_destination_group_ids: list[str] = field(default_factory=list)
    latest_recommendation_ids: list[str] = field(default_factory=list)
    ranking_preference: str | None = None
    retrieval_query: str | None = None
    accessibility_clarified: bool = False
    pending_attraction_id: str | None = None
    pending_preference_field: str | None = None

    @classmethod
    def from_dict(cls, values: Mapping[str, Any] | None) -> "ChatSession":
        if values is None:
            return cls()
        if not isinstance(values, Mapping):
            raise TypeError("values must be a mapping or None")
        return cls(
            context=ConversationContext.from_dict(values.get("context")),
            shown_attraction_ids=list(values.get("shown_attraction_ids", [])),
            shown_destination_group_ids=list(
                values.get("shown_destination_group_ids", [])
            ),
            latest_recommendation_ids=list(
                values.get("latest_recommendation_ids", [])
            ),
            ranking_preference=values.get("ranking_preference"),
            retrieval_query=values.get("retrieval_query"),
            accessibility_clarified=bool(
                values.get("accessibility_clarified", False)
            ),
            pending_attraction_id=values.get("pending_attraction_id"),
            pending_preference_field=values.get("pending_preference_field"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "shown_attraction_ids": list(self.shown_attraction_ids),
            "shown_destination_group_ids": list(
                self.shown_destination_group_ids
            ),
            "latest_recommendation_ids": list(self.latest_recommendation_ids),
            "ranking_preference": self.ranking_preference,
            "retrieval_query": self.retrieval_query,
            "accessibility_clarified": self.accessibility_clarified,
            "pending_attraction_id": self.pending_attraction_id,
            "pending_preference_field": self.pending_preference_field,
        }

    def reset(self) -> None:
        self.context.reset()
        self.shown_attraction_ids.clear()
        self.shown_destination_group_ids.clear()
        self.latest_recommendation_ids.clear()
        self.ranking_preference = None
        self.retrieval_query = None
        self.accessibility_clarified = False
        self.pending_attraction_id = None
        self.pending_preference_field = None


@dataclass(frozen=True)
class ChatbotResponse:
    """Controller result that a web or mobile interface can render."""

    reply: str
    action: str
    intent: str
    confidence: float
    context: Mapping[str, Any]
    recommendations: tuple[Mapping[str, Any], ...] = ()
    suggestions: tuple[Mapping[str, str], ...] = ()
    unchanged_preferences: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "action": self.action,
            "intent": self.intent,
            "confidence": self.confidence,
            "context": dict(self.context),
            "recommendations": [dict(item) for item in self.recommendations],
            "suggestions": [dict(item) for item in self.suggestions],
            "unchanged_preferences": dict(self.unchanged_preferences),
        }


class ChatbotService:
    """Process a message without storing one user's state globally."""

    TRAVEL_INTENTS = {
        "request_recommendation",
        "refine_preferences",
        "request_alternative",
    }

    def __init__(
        self,
        classifier: IntentPredictor | None = None,
        *,
        confidence_threshold: float = 0.45,
        recommendation_limit: int = 3,
        web_discovery: AttractionDiscovery | None = None,
        language_interpreter: LanguageInterpreter | None = None,
        enable_local_llm: bool | None = None,
        enable_live_discovery: bool | None = None,
    ):
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if recommendation_limit < 1:
            raise ValueError("recommendation_limit must be at least 1")
        self.classifier = classifier or IntentClassifier()
        self.confidence_threshold = confidence_threshold
        self.recommendation_limit = recommendation_limit
        self.enable_local_llm = (
            _environment_flag("ENABLE_LOCAL_LLM")
            if enable_local_llm is None
            else bool(enable_local_llm)
        )
        self.enable_live_discovery = (
            _environment_flag("ENABLE_LIVE_DISCOVERY")
            if enable_live_discovery is None
            else bool(enable_live_discovery)
        )
        disabled_interpreter = DisabledLanguageInterpreter()
        self.language_interpreter = language_interpreter or (
            LocalLLMInterpreter()
            if self.enable_local_llm
            else disabled_interpreter
        )
        self.web_discovery = web_discovery or OpenDataDiscovery(
            language_model=(
                self.language_interpreter
                if self.enable_local_llm
                else disabled_interpreter
            )
        )

    def process_message(
        self,
        text: str,
        session: ChatSession | None = None,
    ) -> ChatbotResponse:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")

        session = session or ChatSession()
        prediction = self.classifier.predict(text)
        rule_preferences = extract_preferences(text)
        message_preferences = rule_preferences

        explicit_reset = bool(EXPLICIT_RESET_PATTERN.fullmatch(text))
        explicit_goodbye = bool(EXPLICIT_GOODBYE_PATTERN.fullmatch(text))
        interpretation = None
        use_local_model = (
            not rule_preferences.to_dict()
            and (
                prediction.confidence < self.confidence_threshold
                or prediction.label == "out_of_scope"
            )
        )
        if (
            self.enable_local_llm
            and not explicit_reset
            and not explicit_goodbye
            and use_local_model
        ):
            interpretation = self.language_interpreter.interpret(
                text,
                session.context.to_dict(),
            )
        if interpretation is not None:
            message_preferences = merge_preferences(
                rule_preferences,
                interpretation.preferences,
            )
            minimum_confidence = (
                0.85 if interpretation.intent == "out_of_scope" else 0.65
            )
            if interpretation.confidence >= minimum_confidence:
                prediction = IntentPrediction(
                    label=interpretation.intent,
                    confidence=interpretation.confidence,
                    scores={interpretation.intent: interpretation.confidence},
                )

        starts_new_trip = bool(
            message_preferences.state
            and NEW_TRIP_REQUEST_PATTERN.search(text)
        )
        has_previous_destination = session.context.state is not None
        changes_destination = bool(
            has_previous_destination
            and message_preferences.state != session.context.state
        )
        explicitly_requests_fresh_trip = bool(
            EXPLICIT_FRESH_TRIP_PATTERN.search(text)
        )
        if (
            starts_new_trip
            and session.context.to_dict()
            and (changes_destination or explicitly_requests_fresh_trip)
        ):
            # Reset an established itinerary, but do not erase accessibility
            # needs merely because the user phrases their first destination as
            # "I would like to visit Penang".
            session.reset()

        intent = prediction.label
        state_changed = (
            message_preferences.state is not None
            and message_preferences.state != session.context.state
        )
        requested_ranking = _ranking_criterion(text)

        if intent == "reset_conversation" and explicit_reset:
            session.reset()
            return self._response(
                "Your travel preferences have been cleared. Where would you like to go?",
                "reset",
                prediction,
                session,
                suggestions=STATE_SUGGESTIONS,
            )

        if intent == "goodbye" and explicit_goodbye:
            return self._response(
                "Goodbye. I hope you enjoy planning your trip in Malaysia.",
                "goodbye",
                prediction,
                session,
            )

        if session.pending_attraction_id:
            pending_attraction_id = session.pending_attraction_id
            session.pending_attraction_id = None
            if AFFIRMATIVE_CONFIRMATION_PATTERN.fullmatch(text):
                return self._information_response(
                    prediction,
                    session,
                    attraction_id=pending_attraction_id,
                )
            if NEGATIVE_CONFIRMATION_PATTERN.fullmatch(text):
                return self._previous_options_response(prediction, session)

        # A direct question about a saved attraction must be resolved before
        # state extraction starts a broad search. For example, "Tell me about
        # Penang Hill" contains the state name Penang, but names one specific
        # attraction rather than requesting any attraction in that state.
        named_attraction = None
        if intent == "request_information" or DIRECT_INFORMATION_PATTERN.search(text):
            named_attraction = find_attraction_by_name_in_text(text)
        if named_attraction is not None:
            attraction_id = str(named_attraction["attraction_id"])
            state = str(named_attraction.get("state_territory") or "").strip()
            if state:
                session.context.state = state
            if not session.latest_recommendation_ids:
                session.latest_recommendation_ids = [attraction_id]
            if attraction_id not in session.shown_attraction_ids:
                session.shown_attraction_ids.append(attraction_id)
            return self._information_response(
                prediction,
                session,
                attraction_id=attraction_id,
            )

        # A newly named state starts a search in that state. It must take
        # priority over comparisons with the previous state's result cards.
        if not state_changed:
            if SHOW_PREVIOUS_OPTIONS_PATTERN.search(text):
                return self._previous_options_response(prediction, session)

            selected_id = self._match_latest_selection(text, session)
            if selected_id is not None:
                return self._information_response(
                    prediction,
                    session,
                    attraction_id=selected_id,
                )

            fuzzy_selection = self._fuzzy_latest_selection(text, session)
            if fuzzy_selection is not None:
                attraction_id, attraction_name = fuzzy_selection
                session.pending_attraction_id = attraction_id
                return self._response(
                    f"I may not have heard the place name correctly. Do you "
                    f"mean {attraction_name}?",
                    "confirm_attraction",
                    prediction,
                    session,
                    suggestions=(
                        {
                            "label": f"Yes, {attraction_name}",
                            "message": f"Tell me about {attraction_name}",
                        },
                        {
                            "label": "Show options again",
                            "message": "Show the previous options",
                        },
                    ),
                )

            comparison = self._comparison_request(text, session)
            if comparison is not None:
                return comparison
        else:
            # A ranking word in the same message, for example "cheapest in
            # Kuala Lumpur", belongs to the new search and can survive a
            # clarification turn if the user still needs to provide interest.
            session.ranking_preference = requested_ranking

        if requested_ranking and not session.latest_recommendation_ids:
            session.ranking_preference = requested_ranking

        # Extract recognised travel details before trusting the classifier.
        # A short answer such as "Relaxation" can otherwise be mistaken for
        # "reset conversation" and unexpectedly erase the user's choices.
        pending_preference_field = session.pending_preference_field
        replace_interests = (
            bool(REPLACE_INTEREST_PATTERN.search(text))
            or bool(message_preferences.state and message_preferences.interests)
            or bool(
                pending_preference_field == "interest"
                and message_preferences.interests
            )
        )
        no_special_access = bool(NO_SPECIAL_ACCESS_PATTERN.fullmatch(text))
        replace_accessibility_needs = bool(
            pending_preference_field == "accessibility"
            and (
                message_preferences.wheelchair_accessible
                or message_preferences.accessibility_needs
                or no_special_access
            )
        )
        if (
            message_preferences.elderly_friendly
            and not message_preferences.wheelchair_accessible
            and not message_preferences.accessibility_needs
        ):
            session.accessibility_clarified = False
        if (
            message_preferences.wheelchair_accessible
            or message_preferences.accessibility_needs
            or no_special_access
        ):
            session.accessibility_clarified = True
        changes = session.context.update(
            message_preferences,
            replace_interests=replace_interests,
            replace_accessibility_needs=replace_accessibility_needs,
        )
        resolved_pending_field = bool(
            (pending_preference_field == "location" and message_preferences.state)
            or (
                pending_preference_field == "interest"
                and message_preferences.interests
            )
            or (
                pending_preference_field == "budget"
                and message_preferences.maximum_fee is not None
            )
            or (
                pending_preference_field == "accessibility"
                and (
                    message_preferences.wheelchair_accessible
                    or message_preferences.accessibility_needs
                    or no_special_access
                )
            )
        )
        if resolved_pending_field:
            session.pending_preference_field = None
        if changes:
            session.shown_attraction_ids.clear()
            session.shown_destination_group_ids.clear()
            session.latest_recommendation_ids.clear()
            if state_changed or message_preferences.interests:
                session.retrieval_query = text
            else:
                session.retrieval_query = " ".join(
                    part
                    for part in (session.retrieval_query, text)
                    if part
                )[-500:]

        # An explicit update is still meaningful when the value is already saved.
        # Do not mistake an empty change set for an absence of recognised values.
        recognised_refinement = bool(message_preferences.to_dict()) and (
            intent == "refine_preferences"
            or bool(REPLACE_INTEREST_PATTERN.search(text))
        )
        if changes or recognised_refinement:
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            if self._needs_accessibility_clarification(session):
                return self._accessibility_clarification_response(
                    prediction,
                    session,
                )
            response = self._recommendation_response(
                prediction,
                session,
                sort_by=session.ranking_preference,
            )
            if not changes:
                supplied = message_preferences.to_dict()
                acknowledgement = "Those preferences are already saved. "
                if set(supplied) == {"interests"}:
                    acknowledgement = (
                        "Your interest is already set to "
                        + ", ".join(session.context.interests) + ". "
                    )
                response = replace(
                    response,
                    reply=acknowledgement + response.reply,
                    unchanged_preferences=supplied,
                )
            return response

        if no_special_access:
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            return self._recommendation_response(
                prediction,
                session,
                sort_by=session.ranking_preference,
            )

        preference_field_match = PREFERENCE_FIELD_PATTERN.fullmatch(text)
        if preference_field_match:
            field = preference_field_match.group("field").casefold()
            if field in {"location", "state", "destination"}:
                session.pending_preference_field = "location"
                return self._response(
                    "Which Malaysian state or federal territory would you like "
                    "to visit instead?",
                    "change_location",
                    prediction,
                    session,
                    suggestions=STATE_SUGGESTIONS,
                )
            if field == "interest":
                session.pending_preference_field = "interest"
                return self._response(
                    "What type of attraction would you prefer instead?",
                    "change_interest",
                    prediction,
                    session,
                    suggestions=INTEREST_SUGGESTIONS,
                )
            if field in {"budget", "cost", "fee"}:
                session.pending_preference_field = "budget"
                return self._response(
                    "What is your new maximum entrance-fee budget? Choose an "
                    "amount below or type another amount in RM.",
                    "change_budget",
                    prediction,
                    session,
                    suggestions=BUDGET_SUGGESTIONS,
                )
            session.pending_preference_field = "accessibility"
            return self._response(
                "What accessibility or mobility support is most important?",
                "change_accessibility",
                prediction,
                session,
                suggestions=ACCESSIBILITY_SUGGESTIONS,
            )

        # Recommendation pagination is a direct conversational command.  It
        # should remain reliable even when the statistical intent classifier
        # assigns a weak or unrelated label to a short phrase such as
        # "show me more options".
        if SHOW_MORE_OPTIONS_PATTERN.search(text):
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            return self._recommendation_response(
                prediction,
                session,
                alternative=True,
                sort_by=session.ranking_preference,
            )

        if NO_CHANGE_PATTERN.fullmatch(text):
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            return self._response(
                "Okay, I have kept your current travel preferences. You can "
                "ask me to show the recommendations again or tell me what you "
                "would like to do next.",
                "preferences_unchanged",
                prediction,
                session,
            )

        if intent == "request_information":
            if (
                session.context.to_dict()
                and not session.context.is_ready_for_recommendation()
            ):
                return self._clarification_response(prediction, session)
            return self._information_response(prediction, session)

        if intent == "out_of_scope":
            return self._response(
                "I am designed to help with travel planning and attractions "
                "in Malaysia. Please enter a travel-related message, such as "
                "a state you want to visit, an attraction type, budget or "
                "accessibility need.",
                "out_of_scope",
                prediction,
                session,
                suggestions=STATE_SUGGESTIONS,
            )

        if prediction.confidence < self.confidence_threshold:
            return self._response(
                "I could not understand that as a travel request. Please ask "
                "about travel in Malaysia, such as a state and the type of "
                "attraction you prefer.",
                "low_confidence",
                prediction,
                session,
            )

        if intent == "greeting":
            return self._response(
                "Hello! Tell me which Malaysian state you would like to visit.",
                "greeting",
                prediction,
                session,
                suggestions=STATE_SUGGESTIONS,
            )

        if intent == "help":
            return self._response(
                "You can tell me a state, interest, entrance-fee budget and any "
                "family, elderly or wheelchair-accessibility requirements.",
                "help",
                prediction,
                session,
            )

        if intent == "request_alternative":
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            return self._recommendation_response(
                prediction,
                session,
                alternative=True,
                sort_by=session.ranking_preference,
            )

        if intent == "refine_preferences":
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            return self._response(
                "Which preference would you like to change: location, interest "
                "or accessibility?",
                "request_refinement",
                prediction,
                session,
                suggestions=PREFERENCE_CHANGE_SUGGESTIONS,
            )

        if intent == "request_recommendation":
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            session.shown_attraction_ids.clear()
            session.shown_destination_group_ids.clear()
            session.retrieval_query = " ".join(
                part
                for part in (session.retrieval_query, text)
                if part
            )[-500:]
            return self._recommendation_response(
                prediction,
                session,
                sort_by=session.ranking_preference,
            )

        return self._response(
            "Please tell me where in Malaysia you want to visit and what type "
            "of attraction you enjoy.",
            "clarify_intent",
            prediction,
            session,
        )

    def _clarification_response(
        self,
        prediction: IntentPrediction,
        session: ChatSession,
    ) -> ChatbotResponse:
        question = session.context.next_clarification_question()
        suggestions = (
            STATE_SUGGESTIONS
            if not session.context.state
            else INTEREST_SUGGESTIONS
        )
        return self._response(
            question or "Please provide another travel preference.",
            "clarify_preferences",
            prediction,
            session,
            suggestions=suggestions,
        )

    @staticmethod
    def _needs_accessibility_clarification(session: ChatSession) -> bool:
        return bool(
            session.context.elderly_friendly
            and not session.context.wheelchair_accessible
            and not session.context.accessibility_needs
            and not session.accessibility_clarified
        )

    def _accessibility_clarification_response(
        self,
        prediction: IntentPrediction,
        session: ChatSession,
    ) -> ChatbotResponse:
        return self._response(
            "To find a comfortable option, what is the traveller's most "
            "important accessibility need? Choose one below, or type several "
            "needs in your own words.",
            "clarify_accessibility",
            prediction,
            session,
            suggestions=ACCESSIBILITY_SUGGESTIONS,
        )

    def _recommendation_response(
        self,
        prediction: IntentPrediction,
        session: ChatSession,
        *,
        alternative: bool = False,
        sort_by: str | None = None,
    ) -> ChatbotResponse:
        local_candidates = recommend_attractions(
            **session.context.recommendation_filters(),
            query_text=session.retrieval_query,
            limit=50,
        )
        web_candidates = (
            self.web_discovery.discover(
                session.context.to_dict(),
                limit=max(self.recommendation_limit * 2, 6),
            )
            if self.enable_live_discovery
            else []
        )
        candidates = self._merge_candidates(local_candidates, web_candidates)
        candidates = self._sort_candidates(candidates, sort_by)

        if not candidates:
            session.latest_recommendation_ids.clear()
            state = session.context.state or "that location"
            interest = ", ".join(session.context.interests) or "selected"
            search_scope = (
                "the saved collection or live open-data sources"
                if self.enable_live_discovery
                else "the saved collection"
            )
            requirements = []
            if session.context.wheelchair_accessible:
                requirements.append("recorded wheelchair access")
            if session.context.elderly_friendly:
                requirements.append("recorded elderly suitability")
            if session.context.family_friendly:
                requirements.append("family-friendly places")
            if session.context.maximum_fee is not None:
                requirements.append(
                    f"an entrance fee of at most RM{session.context.maximum_fee:g}"
                )
            need_labels = {
                "low_walking": "minimal walking", "step_free": "step-free access",
                "seating": "resting seats", "accessible_toilet": "accessible toilets",
                "nearby_parking": "nearby parking", "shelter": "shelter or shade",
            }
            requirements.extend(
                need_labels.get(need, need.replace("_", " "))
                for need in session.context.accessibility_needs
            )
            requirement_text = (
                " matching your saved requirements (" + "; ".join(requirements) + ")"
                if requirements else ""
            )
            return self._response(
                f"I could not find an exact match for {interest} attractions "
                f"in {state}{requirement_text} in {search_scope}. "
                "This does not mean that no such places exist. "
                "Your preferences are still saved. Which preference would you "
                "like to change: location, interest or accessibility?",
                "no_results",
                prediction,
                session,
                suggestions=PREFERENCE_CHANGE_SUGGESTIONS,
            )

        shown_groups = set(session.shown_destination_group_ids)
        unseen = [
            item
            for item in candidates
            if item["attraction_id"] not in session.shown_attraction_ids
            and self._destination_group_id(item) not in shown_groups
        ]
        if alternative and not unseen:
            result_scope = (
                "saved or live" if self.enable_live_discovery else "saved"
            )
            return self._response(
                f"There are no more matching alternatives in the {result_scope} "
                "results. Which preference would you like to change: location, "
                "interest or accessibility?",
                "no_alternatives",
                prediction,
                session,
                suggestions=PREFERENCE_CHANGE_SUGGESTIONS,
            )

        selected = (unseen or candidates)[: self.recommendation_limit]
        selected_ids = [item["attraction_id"] for item in selected]
        for attraction_id in selected_ids:
            if attraction_id not in session.shown_attraction_ids:
                session.shown_attraction_ids.append(attraction_id)
        for item in selected:
            group_id = self._destination_group_id(item)
            if group_id not in session.shown_destination_group_ids:
                session.shown_destination_group_ids.append(group_id)
        session.latest_recommendation_ids = selected_ids

        presented = [_present_attraction(item) for item in selected]
        names = ", ".join(item["attraction_name"] for item in presented)
        if alternative:
            prefix = (
                "Here is another option"
                if len(presented) == 1
                else "Here are more options"
            )
        else:
            prefix = "I found"
        accessibility_requested = bool(
            session.context.elderly_friendly
            or session.context.wheelchair_accessible
        )
        accessibility_unknown = accessibility_requested and any(
            (
                session.context.elderly_friendly
                and str(item.get("elderly_friendly") or "").casefold()
                not in {"yes", "partial"}
            )
            or (
                session.context.wheelchair_accessible
                and str(item.get("wheelchair_accessible") or "").casefold()
                not in {"yes", "partial"}
            )
            for item in presented
        )
        reply = (
            f"{prefix}: {names}. I have compared their recorded cost, visit "
            "duration and accessibility below. Which option suits you best? "
            "Choose a place by name, or ask for the easiest access, lowest "
            "cost or shortest visit."
        )
        requested_accessibility_need_count = (
            len(session.context.accessibility_needs)
            + int(bool(session.context.wheelchair_accessible))
        )
        if requested_accessibility_need_count > 1:
            reply += (
                " Each place matches at least one of your selected accessibility "
                "needs, and places matching more needs are ranked first."
            )
        if accessibility_unknown:
            reply += (
                " Some accessibility details are not recorded in the saved "
                "collection, so Maya has not labelled those details as "
                "confirmed."
            )
        suggestions = self._result_suggestions(presented) + ({
            "label": "Show me more options",
            "message": "Show me more options",
        },)
        general_recommendation = not (
            session.context.elderly_friendly
            or session.context.wheelchair_accessible
            or session.context.accessibility_needs
        )
        if general_recommendation:
            suggestions += (ELDERLY_TRIP_SUGGESTION,)
        return self._response(
            reply,
            "alternative" if alternative else "recommend",
            prediction,
            session,
            presented,
            suggestions,
        )

    @staticmethod
    def _destination_group_id(item: Mapping[str, Any]) -> str:
        """Return the stable place group used to avoid repeated venues."""
        state = _normalise_name(str(item.get("state_territory") or ""))
        identifier = str(
            item.get("related_site_id")
            or item.get("canonical_id")
            or item.get("attraction_id")
            or item.get("attraction_name")
            or ""
        )
        return f"{state}:{_normalise_name(identifier)}"

    @staticmethod
    def _merge_candidates(
        local: list[Mapping[str, Any]],
        web: list[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        """Combine sources without repeating aliases or one destination group."""
        merged: list[Mapping[str, Any]] = []
        seen_names: set[tuple[str, str]] = set()
        seen_groups: set[tuple[str, str]] = set()
        for item in [*web, *local]:
            name_key = (
                _normalise_name(str(item.get("attraction_name") or "")),
                _normalise_name(str(item.get("state_territory") or "")),
            )
            group_key = ChatbotService._destination_group_id(item)
            if (
                name_key in seen_names
                or group_key in seen_groups
            ):
                continue
            seen_names.add(name_key)
            seen_groups.add(group_key)
            merged.append(item)
        return merged

    @staticmethod
    def _sort_candidates(
        candidates: list[Mapping[str, Any]],
        criterion: str | None,
    ) -> list[Mapping[str, Any]]:
        if criterion == "cost":
            known = [item for item in candidates if item.get("min_fee_myr") is not None]
            unknown = [item for item in candidates if item.get("min_fee_myr") is None]
            return sorted(known, key=lambda item: float(item["min_fee_myr"])) + unknown
        if criterion == "duration":
            known = [
                item for item in candidates
                if item.get("recommended_duration_hours") is not None
            ]
            unknown = [
                item for item in candidates
                if item.get("recommended_duration_hours") is None
            ]
            return sorted(
                known,
                key=lambda item: float(item["recommended_duration_hours"]),
            ) + unknown
        if criterion == "accessibility":
            return sorted(
                candidates,
                key=lambda item: (
                    _yes_partial_score(item.get("elderly_friendly"))
                    + _yes_partial_score(item.get("wheelchair_accessible"))
                ),
                reverse=True,
            )
        return candidates

    def _previous_options_response(
        self,
        prediction: IntentPrediction,
        session: ChatSession,
    ) -> ChatbotResponse:
        attractions = self._latest_attractions(session)
        if not attractions:
            return self._response(
                "I do not have an earlier set of recommendations in this "
                "conversation yet. Tell me a Malaysian state and the type of "
                "place you enjoy.",
                "previous_options_unavailable",
                prediction,
                session,
                suggestions=STATE_SUGGESTIONS,
            )

        presented = [_present_attraction(item) for item in attractions]
        return self._response(
            "Of course. Here are the previous options again. You can choose "
            "one by name, say first, second or third, or ask me to compare them.",
            "show_previous_options",
            prediction,
            session,
            presented,
            self._result_suggestions(presented),
        )

    def _information_response(
        self,
        prediction: IntentPrediction,
        session: ChatSession,
        *,
        attraction_id: str | None = None,
    ) -> ChatbotResponse:
        if not session.latest_recommendation_ids:
            return self._response(
                "Please ask for a recommendation first, then I can explain "
                "one of the suggested attractions.",
                "information_unavailable",
                prediction,
                session,
            )

        if attraction_id is None and len(session.latest_recommendation_ids) > 1:
            attractions = [
                self._get_attraction(item_id)
                for item_id in session.latest_recommendation_ids
            ]
            presented = [
                _present_attraction(item)
                for item in attractions
                if item is not None
            ]
            return self._response(
                "Which suggested place would you like me to explain? Choose "
                "one of the place names below.",
                "choose_recommendation",
                prediction,
                session,
                presented,
                self._result_suggestions(presented, include_refinements=False),
            )

        attraction_id = attraction_id or session.latest_recommendation_ids[0]
        attraction = self._get_attraction(attraction_id)
        if attraction is None:
            return self._response(
                "I could not retrieve that attraction's details.",
                "information_unavailable",
                prediction,
                session,
            )

        attraction = _present_attraction(attraction)
        details = [
            attraction.get("display_description"),
            attraction.get("cost_summary"),
            attraction.get("duration_summary"),
            attraction.get("accessibility_summary"),
        ]
        reason = attraction.get("accessibility_reason")
        if reason:
            details.append(f"Why it may suit elderly visitors: {reason}")
        access = attraction.get("accessibility_notes")
        if access:
            details.append(access)
        reply = f"{attraction['attraction_name']}: " + " ".join(
            f"{str(detail).rstrip('.')}." for detail in details if detail
        )
        previous = self._latest_attractions(session)
        suggestions = self._result_suggestions(
            previous,
            include_refinements=False,
        )
        if len(previous) > 1:
            suggestions += ({
                "label": "Back to recommendations",
                "message": "Show the previous options",
            },)
        return self._response(
            reply,
            "information",
            prediction,
            session,
            [attraction],
            suggestions,
        )

    @staticmethod
    def _result_suggestions(
        attractions: list[Mapping[str, Any]],
        *,
        include_refinements: bool = True,
    ) -> tuple[Mapping[str, str], ...]:
        suggestions: list[Mapping[str, str]] = [
            {
                "label": str(item["attraction_name"]),
                "message": f"Tell me about {item['attraction_name']}",
            }
            for item in attractions
        ]
        if include_refinements and len(attractions) > 1:
            suggestions.extend((
                {"label": "Easiest access", "message": "Which option has the easiest access?"},
                {"label": "Lowest cost", "message": "Which option has the lowest cost?"},
                {"label": "Shortest visit", "message": "Which option has the shortest visit?"},
            ))
        return tuple(suggestions)

    def _get_attraction(self, attraction_id: str) -> dict[str, Any] | None:
        attraction = get_attraction_by_id(attraction_id)
        if attraction is not None or not self.enable_live_discovery:
            return attraction
        return self.web_discovery.get_by_id(attraction_id)

    def _latest_attractions(self, session: ChatSession) -> list[dict[str, Any]]:
        return [
            attraction
            for attraction_id in session.latest_recommendation_ids
            if (attraction := self._get_attraction(attraction_id)) is not None
        ]

    def _match_latest_selection(
        self,
        text: str,
        session: ChatSession,
    ) -> str | None:
        if not session.latest_recommendation_ids:
            return None
        normalised_text = _normalise_name(text)
        for attraction in self._latest_attractions(session):
            name = _normalise_name(str(attraction["attraction_name"]))
            if name and name in normalised_text:
                return str(attraction["attraction_id"])
        for index, pattern in SELECTION_PATTERNS:
            if pattern.search(text) and index < len(session.latest_recommendation_ids):
                return session.latest_recommendation_ids[index]
        return None

    def _fuzzy_latest_selection(
        self,
        text: str,
        session: ChatSession,
    ) -> tuple[str, str] | None:
        """Offer a correction for a likely misheard recommendation name."""

        if (
            not session.latest_recommendation_ids
            or not SELECTION_CUE_PATTERN.search(text)
        ):
            return None
        normalised_text = _normalise_name(text)
        message_tokens = normalised_text.split()
        scored: list[tuple[float, str, str]] = []
        for attraction in self._latest_attractions(session):
            attraction_id = str(attraction["attraction_id"])
            attraction_name = str(attraction["attraction_name"])
            normalised_name = _normalise_name(attraction_name)
            name_length = len(normalised_name.split())
            window_scores = []
            for size in range(max(1, name_length - 1), name_length + 2):
                for start in range(0, max(0, len(message_tokens) - size) + 1):
                    phrase = " ".join(message_tokens[start:start + size])
                    window_scores.append(
                        SequenceMatcher(None, phrase, normalised_name).ratio()
                    )
            if window_scores:
                scored.append((max(window_scores), attraction_id, attraction_name))

        if not scored:
            return None
        scored.sort(reverse=True)
        best_score, attraction_id, attraction_name = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best_score < 0.68 or best_score - second_score < 0.08:
            return None
        return attraction_id, attraction_name

    def _comparison_request(
        self,
        text: str,
        session: ChatSession,
    ) -> ChatbotResponse | None:
        if len(session.latest_recommendation_ids) < 2:
            return None
        candidates = self._latest_attractions(session)
        criterion = None
        known: list[dict[str, Any]] = []

        if ACCESS_COMPARISON_PATTERN.search(text):
            criterion = "accessibility"
            known = [
                item for item in candidates
                if _yes_partial_score(item.get("elderly_friendly"))
                or _yes_partial_score(item.get("wheelchair_accessible"))
            ]
            key = lambda item: (
                _yes_partial_score(item.get("elderly_friendly"))
                + _yes_partial_score(item.get("wheelchair_accessible"))
            )
            best = max(known, key=key) if known else None
        elif CHEAPEST_COMPARISON_PATTERN.search(text):
            criterion = "entrance cost"
            known = [item for item in candidates if item.get("min_fee_myr") is not None]
            best = min(known, key=lambda item: float(item["min_fee_myr"])) if known else None
        elif SHORTEST_COMPARISON_PATTERN.search(text):
            criterion = "visit duration"
            known = [
                item for item in candidates
                if item.get("recommended_duration_hours") is not None
            ]
            best = min(
                known,
                key=lambda item: float(item["recommended_duration_hours"]),
            ) if known else None
        else:
            return None

        prediction = self.classifier.predict(text)
        presented = [_present_attraction(item) for item in candidates]
        if best is None:
            return self._response(
                f"I do not have enough information to compare these places "
                f"by {criterion}. Choose a place by name or ask for another "
                "type of comparison.",
                "comparison_unavailable",
                prediction,
                session,
                presented,
                self._result_suggestions(presented, include_refinements=False),
            )

        best = _present_attraction(best)
        return self._response(
            f"Based on the currently recorded {criterion}, "
            f"{best['attraction_name']} is the strongest match. Here are its "
            "details so you can decide whether it suits you.",
            "comparison",
            prediction,
            session,
            [best],
            ({
                "label": f"Choose {best['attraction_name']}",
                "message": f"Tell me about {best['attraction_name']}",
            },),
        )

    @staticmethod
    def _response(
        reply: str,
        action: str,
        prediction: IntentPrediction,
        session: ChatSession,
        recommendations: list[Mapping[str, Any]] | None = None,
        suggestions: tuple[Mapping[str, str], ...] | None = None,
    ) -> ChatbotResponse:
        return ChatbotResponse(
            reply=reply,
            action=action,
            intent=prediction.label,
            confidence=prediction.confidence,
            context=session.context.to_dict(),
            recommendations=tuple(recommendations or []),
            suggestions=tuple(suggestions or ()),
        )
