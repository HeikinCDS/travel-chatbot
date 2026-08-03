"""Coordinate intent, preference, context and recommendation modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from dialogue.context_manager import ConversationContext
from nlp.intent_classifier import IntentClassifier, IntentPrediction
from recommendation_engine.recommendation_engine import (
    get_attraction_by_id,
    recommend_attractions,
)


class IntentPredictor(Protocol):
    def predict(self, text: str) -> IntentPrediction:
        """Return an intent prediction for one message."""


@dataclass
class ChatSession:
    """Serializable state belonging to one user, not the global application."""

    context: ConversationContext = field(default_factory=ConversationContext)
    shown_attraction_ids: list[str] = field(default_factory=list)
    latest_recommendation_ids: list[str] = field(default_factory=list)

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
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "shown_attraction_ids": list(self.shown_attraction_ids),
            "latest_recommendation_ids": list(self.latest_recommendation_ids),
        }

    def reset(self) -> None:
        self.context.reset()
        self.shown_attraction_ids.clear()
        self.latest_recommendation_ids.clear()


@dataclass(frozen=True)
class ChatbotResponse:
    """Controller result that a web or mobile interface can render."""

    reply: str
    action: str
    intent: str
    confidence: float
    context: Mapping[str, Any]
    recommendations: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "action": self.action,
            "intent": self.intent,
            "confidence": self.confidence,
            "context": dict(self.context),
            "recommendations": [dict(item) for item in self.recommendations],
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
    ):
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if recommendation_limit < 1:
            raise ValueError("recommendation_limit must be at least 1")
        self.classifier = classifier or IntentClassifier()
        self.confidence_threshold = confidence_threshold
        self.recommendation_limit = recommendation_limit

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

        if intent == "reset_conversation":
            session.reset()
            return self._response(
                "Your travel preferences have been cleared. Where would you like to go?",
                "reset",
                prediction,
                session,
            )

        if intent == "goodbye":
            return self._response(
                "Goodbye. I hope you enjoy planning your trip in Malaysia.",
                "goodbye",
                prediction,
                session,
            )

        changes = session.context.update_from_text(text)
        if changes:
            session.shown_attraction_ids.clear()
            session.latest_recommendation_ids.clear()

        if intent == "request_information":
            return self._information_response(prediction, session)

        # A short slot answer such as "Penang" may have a weak or unexpected
        # intent prediction. Recognised structured preferences take priority.
        if changes:
            if not session.context.is_ready_for_recommendation():
                return self._clarification_response(prediction, session)
            return self._recommendation_response(prediction, session)

        if prediction.confidence < self.confidence_threshold:
            return self._response(
                "I am not certain what you mean. Please tell me the Malaysian "
                "state and the type of attraction you prefer.",
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
            )

        if intent == "refine_preferences":
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
            return self._recommendation_response(prediction, session)

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
        return self._response(
            question or "Please provide another travel preference.",
            "clarify_preferences",
            prediction,
            session,
        )

    def _recommendation_response(
        self,
        prediction: IntentPrediction,
        session: ChatSession,
        *,
        alternative: bool = False,
    ) -> ChatbotResponse:
        candidates = recommend_attractions(
            **session.context.recommendation_filters(),
            limit=50,
        )

        if not candidates:
            session.latest_recommendation_ids.clear()
            return self._response(
                "I could not find an exact match. Try changing the state, "
                "interest, budget or accessibility requirement.",
                "no_results",
                prediction,
                session,
            )

        unseen = [
            item
            for item in candidates
            if item["attraction_id"] not in session.shown_attraction_ids
        ]
        if alternative and not unseen:
            return self._response(
                "There are no more matching alternatives in the current "
                "dataset. Try changing one of your preferences.",
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

        names = ", ".join(item["attraction_name"] for item in selected)
        prefix = "Here is another match" if alternative else "I found"
        reply = (
            f"{prefix}: {names}. "
            f"Your preferences are {session.context.preference_summary()}."
        )
        return self._response(
            reply,
            "alternative" if alternative else "recommend",
            prediction,
            session,
            selected,
        )

    def _information_response(
        self,
        prediction: IntentPrediction,
        session: ChatSession,
    ) -> ChatbotResponse:
        if not session.latest_recommendation_ids:
            return self._response(
                "Please ask for a recommendation first, then I can explain "
                "one of the suggested attractions.",
                "information_unavailable",
                prediction,
                session,
            )

        attraction = get_attraction_by_id(session.latest_recommendation_ids[0])
        if attraction is None:
            return self._response(
                "I could not retrieve that attraction's details.",
                "information_unavailable",
                prediction,
                session,
            )

        access = attraction.get("accessibility_notes") or "Not confirmed"
        reply = (
            f"{attraction['attraction_name']}: "
            f"{attraction['short_description']} "
            f"Accessibility information: {access}."
        )
        return self._response(
            reply,
            "information",
            prediction,
            session,
            [attraction],
        )

    @staticmethod
    def _response(
        reply: str,
        action: str,
        prediction: IntentPrediction,
        session: ChatSession,
        recommendations: list[Mapping[str, Any]] | None = None,
    ) -> ChatbotResponse:
        return ChatbotResponse(
            reply=reply,
            action=action,
            intent=prediction.label,
            confidence=prediction.confidence,
            context=session.context.to_dict(),
            recommendations=tuple(recommendations or []),
        )
