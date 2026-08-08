"""Coordinate intent, preference, context and recommendation modules."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping, Protocol

from dialogue.context_manager import ConversationContext
from nlp.entity_extractor import extract_preferences
from nlp.intent_classifier import IntentClassifier, IntentPrediction
from recommendation_engine.recommendation_engine import (
    get_attraction_by_id,
    recommend_attractions,
)
from web_discovery import OpenDataDiscovery


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
        """Return current, source-backed attraction candidates."""

    def get_by_id(self, attraction_id: str) -> dict[str, Any] | None:
        """Retrieve one attraction that was returned earlier."""


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

STATE_SUGGESTIONS = (
    {"label": "Johor", "message": "Johor"},
    {"label": "Penang", "message": "Penang"},
    {"label": "Perak", "message": "Perak"},
    {"label": "Pahang", "message": "Pahang"},
    {"label": "Sabah", "message": "Sabah"},
    {"label": "Sarawak", "message": "Sarawak"},
)

INTEREST_SUGGESTIONS = (
    {"label": "Nature", "message": "Nature"},
    {"label": "Beach", "message": "Beach"},
    {"label": "History", "message": "History"},
    {"label": "Wildlife", "message": "Wildlife"},
    {"label": "Relaxation", "message": "Relaxation"},
)

CHANGE_INTEREST_SUGGESTIONS = tuple(
    {
        "label": suggestion["label"],
        "message": f"Actually change my interest to {suggestion['message'].lower()}",
    }
    for suggestion in INTEREST_SUGGESTIONS[:-1]
)

SELECTION_PATTERNS = (
    (0, re.compile(r"\b(?:first|1st|option\s*1|number\s*1)\b", re.IGNORECASE)),
    (1, re.compile(r"\b(?:second|2nd|option\s*2|number\s*2)\b", re.IGNORECASE)),
    (2, re.compile(r"\b(?:third|3rd|option\s*3|number\s*3)\b", re.IGNORECASE)),
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


def _fee_summary(attraction: Mapping[str, Any]) -> str:
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
    return "Entrance fee has not been verified"


def _duration_summary(attraction: Mapping[str, Any]) -> str:
    hours = attraction.get("recommended_duration_hours")
    if hours is None:
        return "Recommended visit duration has not been verified"
    return f"Suggested visit duration: about {float(hours):g} hour(s)"


def _access_summary(attraction: Mapping[str, Any]) -> str:
    elderly = str(attraction.get("elderly_friendly") or "Unknown").title()
    wheelchair = str(attraction.get("wheelchair_accessible") or "Unknown").title()
    return f"Elderly-friendly: {elderly}; wheelchair access: {wheelchair}"


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
    result["display_description"] = _display_description(attraction)
    result["cost_summary"] = _fee_summary(attraction)
    result["duration_summary"] = _duration_summary(attraction)
    result["accessibility_summary"] = _access_summary(attraction)
    verification = str(attraction.get("verification_status") or "").casefold()
    if attraction.get("information_origin") == "open_data":
        checked = attraction.get("date_verified") or "recently"
        result["verification_note"] = (
            f"Maya found this in public open-data sources and checked it on "
            f"{checked}. Prices, opening hours and accessibility can change."
        )
    else:
        result["verification_note"] = (
            "Some visitor details are AI-assisted and still require confirmation "
            "from an official source."
            if verification not in {"verified", "source verified"}
            else "Visitor details have a recorded source-verification status."
        )
    return result


@dataclass
class ChatSession:
    """Serializable state belonging to one user, not the global application."""

    context: ConversationContext = field(default_factory=ConversationContext)
    shown_attraction_ids: list[str] = field(default_factory=list)
    latest_recommendation_ids: list[str] = field(default_factory=list)
    ranking_preference: str | None = None

    @classmethod
    def from_dict(cls, values: Mapping[str, Any] | None) -> "ChatSession":
        if values is None:
            return cls()
        if not isinstance(values, Mapping):
            raise TypeError("values must be a mapping or None")
        return cls(
            context=ConversationContext.from_dict(values.get("context")),
            shown_attraction_ids=list(values.get("shown_attraction_ids", [])),
            latest_recommendation_ids=list(
                values.get("latest_recommendation_ids", [])
            ),
            ranking_preference=values.get("ranking_preference"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "shown_attraction_ids": list(self.shown_attraction_ids),
            "latest_recommendation_ids": list(self.latest_recommendation_ids),
            "ranking_preference": self.ranking_preference,
        }

    def reset(self) -> None:
        self.context.reset()
        self.shown_attraction_ids.clear()
        self.latest_recommendation_ids.clear()
        self.ranking_preference = None


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "action": self.action,
            "intent": self.intent,
            "confidence": self.confidence,
            "context": dict(self.context),
            "recommendations": [dict(item) for item in self.recommendations],
            "suggestions": [dict(item) for item in self.suggestions],
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
    ):
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if recommendation_limit < 1:
            raise ValueError("recommendation_limit must be at least 1")
        self.classifier = classifier or IntentClassifier()
        self.confidence_threshold = confidence_threshold
        self.recommendation_limit = recommendation_limit
        self.web_discovery = web_discovery or OpenDataDiscovery()

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
        intent = prediction.label
        message_preferences = extract_preferences(text)
        state_changed = (
            message_preferences.state is not None
            and message_preferences.state != session.context.state
        )
        requested_ranking = _ranking_criterion(text)

        if intent == "reset_conversation" and EXPLICIT_RESET_PATTERN.fullmatch(text):
            session.reset()
            return self._response(
                "Your travel preferences have been cleared. Where would you like to go?",
                "reset",
                prediction,
                session,
                suggestions=STATE_SUGGESTIONS,
            )

        if intent == "goodbye" and EXPLICIT_GOODBYE_PATTERN.fullmatch(text):
            return self._response(
                "Goodbye. I hope you enjoy planning your trip in Malaysia.",
                "goodbye",
                prediction,
                session,
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
        changes = session.context.update_from_text(text)
        if changes:
            session.shown_attraction_ids.clear()
            session.latest_recommendation_ids.clear()

        # A short slot answer such as "Penang" may have a weak or unexpected
        # intent prediction. Recognised structured preferences take priority.
        if changes:
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            return self._recommendation_response(
                prediction,
                session,
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
                "Which preference would you like to change: location, interest, "
                "budget or accessibility?",
                "request_refinement",
                prediction,
                session,
            )

        if intent == "request_recommendation":
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            session.shown_attraction_ids.clear()
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
            limit=50,
        )
        web_candidates = self.web_discovery.discover(
            session.context.to_dict(),
            limit=max(self.recommendation_limit * 2, 6),
        )
        candidates = self._merge_candidates(local_candidates, web_candidates)
        candidates = self._sort_candidates(candidates, sort_by)

        if not candidates:
            session.latest_recommendation_ids.clear()
            state = session.context.state or "that location"
            interest = ", ".join(session.context.interests) or "selected"
            return self._response(
                f"I could not find an exact match for {interest} attractions "
                f"in {state} in the saved collection or from live web sources. "
                "Your preferences are still saved. Please choose another "
                "attraction type, or tell me a different state.",
                "no_results",
                prediction,
                session,
                suggestions=CHANGE_INTEREST_SUGGESTIONS,
            )

        unseen = [
            item
            for item in candidates
            if item["attraction_id"] not in session.shown_attraction_ids
        ]
        if alternative and not unseen:
            return self._response(
                "There are no more matching alternatives in the saved or live "
                "results. Try changing one of your preferences.",
                "no_alternatives",
                prediction,
                session,
            )

        selected = (unseen or candidates)[: self.recommendation_limit]
        selected_ids = [item["attraction_id"] for item in selected]
        for attraction_id in selected_ids:
            if attraction_id not in session.shown_attraction_ids:
                session.shown_attraction_ids.append(attraction_id)
        session.latest_recommendation_ids = selected_ids

        presented = [_present_attraction(item) for item in selected]
        names = ", ".join(item["attraction_name"] for item in presented)
        prefix = "Here is another match" if alternative else "I found"
        reply = (
            f"{prefix}: {names}. I have compared their recorded cost, visit "
            "duration and accessibility below. Which option suits you best? "
            "Choose a place by name, or ask for the easiest access, lowest "
            "cost or shortest visit."
        )
        suggestions = self._result_suggestions(presented)
        return self._response(
            reply,
            "alternative" if alternative else "recommend",
            prediction,
            session,
            presented,
            suggestions,
        )

    @staticmethod
    def _merge_candidates(
        local: list[Mapping[str, Any]],
        web: list[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        """Combine both sources without repeating the same named place."""
        merged: list[Mapping[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in [*web, *local]:
            key = (
                _normalise_name(str(item.get("attraction_name") or "")),
                _normalise_name(str(item.get("state_territory") or "")),
            )
            if key in seen:
                continue
            seen.add(key)
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
        access = attraction.get("accessibility_notes") or (
            "Detailed terrain, seating, toilet and step information has not "
            "been confirmed."
        )
        reply = (
            f"{attraction['attraction_name']}: "
            f"{attraction['display_description']} "
            f"{attraction['cost_summary']}. {attraction['duration_summary']}. "
            f"{attraction['accessibility_summary']}. "
            f"Accessibility notes: {access}"
        )
        return self._response(
            reply,
            "information",
            prediction,
            session,
            [attraction],
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
        return get_attraction_by_id(attraction_id) or self.web_discovery.get_by_id(
            attraction_id
        )

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
                f"I cannot choose reliably by {criterion} because that "
                "information has not been verified for these places. Choose "
                "a place by name, or use its visitor-information link to "
                "confirm the details.",
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
