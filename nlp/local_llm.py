"""Optional, validated natural-language interpretation through LM Studio."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .entity_extractor import INTEREST_ALIASES, STATE_ALIASES, TravelPreferences


DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "qwen3.5-4b"
VALID_INTENTS = {
    "greeting",
    "goodbye",
    "help",
    "request_recommendation",
    "refine_preferences",
    "request_alternative",
    "request_information",
    "reset_conversation",
    "out_of_scope",
}
VALID_STATES = frozenset(STATE_ALIASES.values())
VALID_INTERESTS = frozenset(INTEREST_ALIASES.values())


@dataclass(frozen=True)
class LLMInterpretation:
    """A local model result after strict application-side validation."""

    intent: str
    confidence: float
    travel_related: bool
    preferences: TravelPreferences


def merge_preferences(
    rules: TravelPreferences,
    model: TravelPreferences,
) -> TravelPreferences:
    """Prefer deterministic extraction and fill only its missing values."""

    interests = list(rules.interests)
    for interest in model.interests:
        if interest not in interests:
            interests.append(interest)
    return TravelPreferences(
        state=rules.state or model.state,
        interests=tuple(interests),
        maximum_fee=(
            rules.maximum_fee
            if rules.maximum_fee is not None
            else model.maximum_fee
        ),
        duration_days=rules.duration_days or model.duration_days,
        duration_hours=rules.duration_hours or model.duration_hours,
        family_friendly=(
            rules.family_friendly
            if rules.family_friendly is not None
            else model.family_friendly
        ),
        elderly_friendly=(
            rules.elderly_friendly
            if rules.elderly_friendly is not None
            else model.elderly_friendly
        ),
        wheelchair_accessible=(
            rules.wheelchair_accessible
            if rules.wheelchair_accessible is not None
            else model.wheelchair_accessible
        ),
        accessibility_needs=tuple(dict.fromkeys(
            (*rules.accessibility_needs, *model.accessibility_needs)
        )),
    )


class LocalLLMInterpreter:
    """Ask an LM Studio model for JSON, then reject unsupported values."""

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        urlopen_function: Any | None = None,
        timeout: float = 120,
    ) -> None:
        self.model = (
            model
            if model is not None
            else os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL)
        ).strip()
        configured_url = base_url or os.getenv("LM_STUDIO_URL", DEFAULT_BASE_URL)
        configured_url = configured_url.rstrip("/")
        self.endpoint = (
            configured_url
            if configured_url.endswith("/chat/completions")
            else f"{configured_url}/chat/completions"
        )
        self._urlopen = urlopen_function or urlopen
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.model)

    def interpret(
        self,
        text: str,
        context: Mapping[str, Any],
    ) -> LLMInterpretation | None:
        if not self.enabled:
            return None

        prompt = {
            "message": text,
            "current_preferences": dict(context),
            "allowed_states": sorted(VALID_STATES),
            "allowed_interests": sorted(VALID_INTERESTS),
        }
        request_body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You interpret messages for JomVoyage, a Malaysia-only "
                        "travel chatbot. Return JSON only. Never answer the user. "
                        "Extract only preferences clearly expressed or implied by "
                        "the message. Never invent a numeric budget or duration."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=False),
                },
            ],
            "temperature": 0.1,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "travel_message_interpretation",
                    "strict": True,
                    "schema": self._schema(),
                },
            },
        }
        content = self._completion_content(request_body)
        if content is None:
            return None
        try:
            return self._validate(json.loads(content))
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def generate_descriptions(
        self,
        attractions: list[Mapping[str, Any]],
    ) -> dict[str, str]:
        """Create concise descriptions without inventing operational facts."""
        if not self.enabled or not attractions:
            return {}
        facts = [{
            "attraction_id": str(item.get("attraction_id") or ""),
            "name": str(item.get("attraction_name") or ""),
            "state": str(item.get("state_territory") or ""),
            "category": str(item.get("primary_category") or ""),
            "source_description": str(item.get("short_description") or ""),
        } for item in attractions]
        request_body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Write two polished, natural sentences of about 35 to 55 "
                        "words for each Malaysian attraction. Describe its setting "
                        "or character, then explain why it may appeal to a visitor. "
                        "Use the supplied name, location, category and source facts. "
                        "Never use phrases such as 'listed by' or 'recorded by'. "
                        "Do not invent named facilities, "
                        "activities, prices, opening hours, accessibility, ratings "
                        "or historical claims. Return JSON only."
                    ),
                },
                {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
            ],
            "temperature": 0.25,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "attraction_descriptions",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "attraction_id": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["attraction_id", "description"],
                                },
                            }
                        },
                        "required": ["items"],
                    },
                },
            },
        }
        content = self._completion_content(request_body)
        if content is None:
            return {}
        try:
            values = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        allowed_ids = {item["attraction_id"] for item in facts}
        generated: dict[str, str] = {}
        for item in values.get("items", []) if isinstance(values, Mapping) else []:
            if not isinstance(item, Mapping):
                continue
            attraction_id = str(item.get("attraction_id") or "")
            description = " ".join(str(item.get("description") or "").split())
            if attraction_id in allowed_ids and 30 <= len(description) <= 500:
                generated[attraction_id] = description
        return generated

    def _completion_content(self, request_body: Mapping[str, Any]) -> str | None:
        request = Request(
            self.endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            return content if isinstance(content, str) else None
        except HTTPError as error:
            error.close()
            return None
        except (
            URLError,
            TimeoutError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
        ):
            return None

    @staticmethod
    def _schema() -> dict[str, Any]:
        nullable_string = {"type": ["string", "null"]}
        nullable_number = {"type": ["number", "null"]}
        nullable_integer = {"type": ["integer", "null"]}
        nullable_boolean = {"type": ["boolean", "null"]}
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent": {"type": "string", "enum": sorted(VALID_INTENTS)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "travel_related": {"type": "boolean"},
                "state": nullable_string,
                "interests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                },
                "maximum_fee": nullable_number,
                "duration_days": nullable_integer,
                "duration_hours": nullable_number,
                "family_friendly": nullable_boolean,
                "elderly_friendly": nullable_boolean,
                "wheelchair_accessible": nullable_boolean,
            },
            "required": [
                "intent",
                "confidence",
                "travel_related",
                "state",
                "interests",
                "maximum_fee",
                "duration_days",
                "duration_hours",
                "family_friendly",
                "elderly_friendly",
                "wheelchair_accessible",
            ],
        }

    @staticmethod
    def _validate(values: Mapping[str, Any]) -> LLMInterpretation | None:
        if not isinstance(values, Mapping):
            return None
        intent = values.get("intent")
        if intent not in VALID_INTENTS:
            return None
        confidence = values.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            return None
        travel_related = values.get("travel_related")
        if not isinstance(travel_related, bool):
            return None

        state = values.get("state")
        state = state if state in VALID_STATES else None
        raw_interests = values.get("interests")
        if not isinstance(raw_interests, list):
            raw_interests = []
        interests = tuple(
            value
            for value in raw_interests
            if value in VALID_INTERESTS
        )

        return LLMInterpretation(
            intent=str(intent),
            confidence=max(0.0, min(1.0, float(confidence))),
            travel_related=travel_related,
            preferences=TravelPreferences(
                state=state,
                interests=interests,
                maximum_fee=_non_negative_number(values.get("maximum_fee")),
                duration_days=_positive_integer(values.get("duration_days")),
                duration_hours=_positive_number(values.get("duration_hours")),
                family_friendly=_true_or_none(values.get("family_friendly")),
                elderly_friendly=_true_or_none(values.get("elderly_friendly")),
                wheelchair_accessible=_true_or_none(
                    values.get("wheelchair_accessible")
                ),
            ),
        )


def _non_negative_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _positive_number(value: Any) -> float | None:
    number = _non_negative_number(value)
    return number if number and number > 0 else None


def _positive_integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _true_or_none(value: Any) -> bool | None:
    return True if value is True else None
