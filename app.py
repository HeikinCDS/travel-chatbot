"""Flask web application for the Malaysia travel recommendation chatbot."""

from __future__ import annotations

import os
from io import BytesIO
from collections.abc import Callable
from typing import Any

from flask import (
    Flask,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    session,
)

from chatbot.service import ChatSession, ChatbotService, STATE_SUGGESTIONS
from speech import SpeechSynthesisError, synthesize_speech


MAX_MESSAGE_LENGTH = 500


def create_app(
    service: ChatbotService | None = None,
    speech_synthesizer: Callable[[str], bytes] | None = None,
    config: dict[str, Any] | None = None,
) -> Flask:
    """Create the web application, optionally with a test chatbot service."""

    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get(
            "FLASK_SECRET_KEY",
            "local-development-key-change-before-deployment",
        ),
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)
    if service is not None:
        app.extensions["chatbot_service"] = service
    if speech_synthesizer is not None:
        app.extensions["speech_synthesizer"] = speech_synthesizer

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/warmup")
    def warmup():
        """Load Maya's NLP model while the user reads the welcome screen."""
        _get_service()
        return jsonify({"status": "ready"})

    @app.post("/api/speech")
    def speech():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("Send the speech text as JSON.", 400)
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return _error("Please provide text for Maya to read.", 400)
        try:
            audio = _get_speech_synthesizer()(text)
        except ValueError as error:
            return _error(str(error), 400)
        except SpeechSynthesisError:
            return _error("Maya's audio is temporarily unavailable.", 503)
        return send_file(
            BytesIO(audio),
            mimetype="audio/wav",
            download_name="maya-response.wav",
        )

    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("Send the message as JSON.", 400)

        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            return _error("Please enter a message.", 400)
        message = message.strip()
        if len(message) > MAX_MESSAGE_LENGTH:
            return _error(
                f"Please keep the message below {MAX_MESSAGE_LENGTH} characters.",
                400,
            )

        try:
            chat_session = ChatSession.from_dict(session.get("chatbot_session"))
            response = _get_service().process_message(message, chat_session)
        except (TypeError, ValueError) as error:
            return _error(str(error), 400)

        session["chatbot_session"] = chat_session.to_dict()
        return jsonify(response.to_dict())

    @app.post("/api/reset")
    def reset():
        session.pop("chatbot_session", None)
        return jsonify(
            {
                "reply": "Your travel preferences have been cleared. Where would you like to go?",
                "action": "reset",
                "context": {},
                "recommendations": [],
                "suggestions": [
                    {"label": "Johor", "message": "Johor"},
                    {"label": "Penang", "message": "Penang"},
                    {"label": "Perak", "message": "Perak"},
                    {"label": "Pahang", "message": "Pahang"},
                    {"label": "Sabah", "message": "Sabah"},
                    {"label": "Sarawak", "message": "Sarawak"},
                ],
            }
        )

    @app.post("/api/reset-preferences")
    def reset_preferences():
        chat_session = ChatSession.from_dict(session.get("chatbot_session"))
        chat_session.reset()
        session["chatbot_session"] = chat_session.to_dict()
        return jsonify(
            {
                "reply": (
                    "Your saved trip preferences have been cleared. "
                    "Which Malaysian state would you like to explore next?"
                ),
                "action": "reset_preferences",
                "context": {},
                "recommendations": [],
                "suggestions": list(STATE_SUGGESTIONS),
            }
        )

    return app


def _get_service() -> ChatbotService:
    """Load the trained model once, on the first chat request."""

    if "chatbot_service" not in current_app.extensions:
        current_app.extensions["chatbot_service"] = ChatbotService()
    return current_app.extensions["chatbot_service"]


def _get_speech_synthesizer() -> Callable[[str], bytes]:
    return current_app.extensions.get("speech_synthesizer", synthesize_speech)


def _error(message: str, status: int):
    return jsonify({"error": message}), status


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
