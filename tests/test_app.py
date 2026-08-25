import unittest

try:
    from app import create_app
    from chatbot.service import ChatbotResponse
except ModuleNotFoundError as error:
    if error.name == "flask":
        create_app = None
        ChatbotResponse = None
    else:
        raise


class RecordingService:
    def __init__(self):
        self.received_contexts = []

    def process_message(self, text, chat_session):
        self.received_contexts.append(chat_session.to_dict())
        chat_session.context.state = "Johor"
        return ChatbotResponse(
            reply=f"Received: {text}",
            action="clarify_preferences",
            intent="request_recommendation",
            confidence=0.91,
            context=chat_session.context.to_dict(),
        )


@unittest.skipIf(create_app is None, "Flask is not installed")
class FlaskApplicationTests(unittest.TestCase):
    def setUp(self):
        self.service = RecordingService()
        self.app = create_app(
            service=self.service,
            speech_synthesizer=lambda text, language="en": b"RIFF" + (b"\x00" * 40) + b"WAVE",
            config={"TESTING": True, "SECRET_KEY": "test-key"},
        )
        self.client = self.app.test_client()

    def test_home_page_contains_accessible_chat_controls(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"JomVoyage", response.data)
        self.assertIn(b"Maya", response.data)
        self.assertIn(
            b"Plan holiday trip in Malaysia with Maya",
            response.data,
        )
        self.assertIn(b'id="message-input"', response.data)
        self.assertIn(b'id="voice-input-button"', response.data)
        self.assertIn(b'id="language-select"', response.data)
        self.assertIn(b'option value="ms"', response.data)
        self.assertIn(b'option value="zh"', response.data)
        self.assertIn(b'Speak your travel request', response.data)
        self.assertIn(b'id="text-size-button"', response.data)
        self.assertIn(b'id="contrast-button"', response.data)
        self.assertIn(b'class="composer-area"', response.data)
        self.assertIn(b'class="trip-sidebar"', response.data)
        self.assertIn(b'id="preference-list"', response.data)
        self.assertIn(b'id="preference-reset-button"', response.data)
        self.assertIn(b'id="sidebar-toggle-button"', response.data)
        self.assertIn(b'id="trip-sidebar"', response.data)
        self.assertIn(b'id="chat-history"', response.data)
        self.assertIn(b'id="easy-access-start-button"', response.data)
        self.assertIn(b"Plan an elderly-friendly trip", response.data)

    def test_chat_script_attaches_cards_to_their_maya_reply(self):
        response = self.client.get("/static/chat.js")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"message-recommendations", response.data)
        self.assertIn(
            b"showRecommendations(data.recommendations, replyRow)",
            response.data,
        )
        self.assertIn("Rancang percutian".encode(), response.data)
        self.assertIn("\u4e0e Maya \u4e00\u8d77\u89c4\u5212".encode(), response.data)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_warmup_endpoint_prepares_chatbot_service(self):
        response = self.client.get("/api/warmup")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ready"})

    def test_speech_endpoint_returns_wav_audio(self):
        response = self.client.post(
            "/api/speech",
            json={"text": "Hello from Maya"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "audio/wav")
        self.assertTrue(response.data.startswith(b"RIFF"))

    def test_speech_endpoint_rejects_empty_text(self):
        response = self.client.post("/api/speech", json={"text": " "})
        self.assertEqual(response.status_code, 400)

    def test_speech_endpoint_accepts_supported_language(self):
        response = self.client.post(
            "/api/speech",
            json={"text": "Selamat datang", "language": "ms"},
        )
        self.assertEqual(response.status_code, 200)

    def test_speech_endpoint_rejects_unsupported_language(self):
        response = self.client.post(
            "/api/speech",
            json={"text": "Hello", "language": "fr"},
        )
        self.assertEqual(response.status_code, 400)

    def test_chat_rejects_empty_message(self):
        response = self.client.post("/api/chat", json={"message": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_chat_rejects_message_over_limit(self):
        response = self.client.post("/api/chat", json={"message": "a" * 501})
        self.assertEqual(response.status_code, 400)

    def test_chat_returns_service_response(self):
        response = self.client.post("/api/chat", json={"message": "Johor"})
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["reply"], "Received: Johor")
        self.assertEqual(data["context"]["state"], "Johor")
        self.assertEqual(data["suggestions"], [])

    def test_session_state_is_kept_between_requests(self):
        self.client.post("/api/chat", json={"message": "Johor"})
        self.client.post("/api/chat", json={"message": "Nature"})
        self.assertEqual(self.service.received_contexts[1]["context"]["state"], "Johor")

    def test_reset_clears_session_state(self):
        self.client.post("/api/chat", json={"message": "Johor"})
        reset_response = self.client.post("/api/reset", json={})
        self.client.post("/api/chat", json={"message": "Nature"})
        self.assertEqual(reset_response.status_code, 200)
        self.assertGreater(len(reset_response.get_json()["suggestions"]), 0)
        self.assertEqual(self.service.received_contexts[1]["context"], {})

    def test_preference_reset_keeps_endpoint_separate_from_new_chat(self):
        self.client.post("/api/chat", json={"message": "Johor"})
        response = self.client.post("/api/reset-preferences", json={})
        self.client.post("/api/chat", json={"message": "Nature"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "reset_preferences")
        self.assertEqual(response.get_json()["context"], {})
        self.assertEqual(self.service.received_contexts[1]["context"], {})


if __name__ == "__main__":
    unittest.main()
