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
        self.received_texts = []

    def process_message(self, text, chat_session):
        self.received_texts.append(text)
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
        self.assertIn(b'id="saved-conversations"', response.data)
        self.assertIn(b'id="current-conversation-title"', response.data)
        self.assertIn(b'id="easy-access-start-button"', response.data)
        self.assertIn(b"Plan an elderly-friendly trip", response.data)

    def test_home_page_uses_modern_design_without_public_theme_picker(self):
        response = self.client.get("/")
        self.assertNotIn(b'id="design-select"', response.data)
        self.assertNotIn(b'class="hero-art"', response.data)
        self.assertIn(b'class="brand-mark" aria-hidden="true">JV</span>', response.data)
        self.assertIn(b'id="modern-design-styles"', response.data)
        self.assertIn(b'/static/styles.css', response.data)
        self.assertIn(b'/static/modern.css', response.data)
        self.assertIn(b'/static/design.js', response.data)

    def test_design_assets_are_served(self):
        for asset in ("modern.css", "design.js"):
            with self.subTest(asset=asset):
                response = self.client.get(f"/static/{asset}")
                self.addCleanup(response.close)
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 100)

    def test_chat_script_attaches_cards_to_their_maya_reply(self):
        response = self.client.get("/static/chat.js")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"message-recommendations", response.data)
        self.assertIn(
            b"showRecommendations(data.recommendations, replyRow)",
            response.data,
        )
        self.assertIn(b"language: currentLanguage", response.data)
        self.assertIn(b"function historyTopic", response.data)
        self.assertIn(b"refreshHistoryItem(replyRow)", response.data)
        self.assertIn(b'Recommendations', response.data)
        self.assertIn("Cadangan tempat".encode(), response.data)
        self.assertIn("景点推荐".encode(), response.data)
        self.assertIn(b"function saveCurrentConversation", response.data)
        self.assertIn(b"function openSavedConversation", response.data)
        self.assertIn(b'MAX_SAVED_CONVERSATIONS = 8', response.data)
        self.assertIn("Rancang percutian".encode(), response.data)
        self.assertIn("\u4e0e Maya \u4e00\u8d77\u89c4\u5212".encode(), response.data)
        self.assertIn("Sesuai dengan bantuan".encode(), response.data)
        self.assertIn("适合在协助下游览".encode(), response.data)
        self.assertIn(b"function localizedCardDescription", response.data)
        self.assertIn(b"function localizedFact", response.data)
        self.assertIn(b"function appendOriginalEnglishDetails", response.data)

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
        self.assertEqual(data["session_state"]["context"]["state"], "Johor")

    def test_chat_normalizes_malay_before_nlp_processing(self):
        response = self.client.post(
            "/api/chat",
            json={
                "message": "Cadangkan tempat mesra warga emas di Pulau Pinang",
                "language": "ms",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.service.received_texts[-1],
            "recommend place elderly friendly in Pulau Pinang",
        )

    def test_chat_normalizes_chinese_before_nlp_processing(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "推荐槟城适合长者的景点", "language": "zh"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.service.received_texts[-1],
            "recommend Penang suitable for elderly attraction",
        )

    def test_chat_rejects_unsupported_language(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "Bonjour", "language": "fr"},
        )
        self.assertEqual(response.status_code, 400)

    def test_session_state_is_kept_between_requests(self):
        self.client.post("/api/chat", json={"message": "Johor"})
        self.client.post("/api/chat", json={"message": "Nature"})
        self.assertEqual(self.service.received_contexts[1]["context"]["state"], "Johor")

    def test_reset_clears_session_state(self):
        self.client.post("/api/chat", json={"message": "Johor"})
        reset_response = self.client.post("/api/reset", json={})
        self.client.post("/api/chat", json={"message": "Nature"})
        self.assertEqual(reset_response.status_code, 200)
        reset_data = reset_response.get_json()
        self.assertGreater(len(reset_data["suggestions"]), 0)
        self.assertEqual(reset_data["action"], "greeting")
        self.assertIn("Hello, I am Maya", reset_data["reply"])
        self.assertNotIn("cleared", reset_data["reply"].casefold())
        self.assertEqual(self.service.received_contexts[1]["context"], {})

    def test_preference_reset_keeps_endpoint_separate_from_new_chat(self):
        self.client.post("/api/chat", json={"message": "Johor"})
        response = self.client.post("/api/reset-preferences", json={})
        self.client.post("/api/chat", json={"message": "Nature"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "reset_preferences")
        self.assertEqual(response.get_json()["context"], {})
        self.assertIn(
            "Switch to elderly-friendly trip",
            {
                suggestion["label"]
                for suggestion in response.get_json()["suggestions"]
            },
        )
        self.assertEqual(self.service.received_contexts[1]["context"], {})

    def test_saved_conversation_session_can_be_restored(self):
        response = self.client.post(
            "/api/restore-session",
            json={
                "session_state": {
                    "context": {"state": "Johor", "interests": ["nature"]},
                    "shown_attraction_ids": ["A001"],
                    "shown_destination_group_ids": ["johor:a001"],
                    "latest_recommendation_ids": ["A001"],
                    "ranking_preference": None,
                    "retrieval_query": "nature in Johor",
                    "accessibility_clarified": False,
                    "pending_attraction_id": None,
                    "pending_preference_field": "interest",
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["context"]["state"], "Johor")
        self.client.post("/api/chat", json={"message": "Show me more options"})
        self.assertEqual(
            self.service.received_contexts[-1]["context"]["interests"],
            ["nature"],
        )

    def test_restore_rejects_unsupported_session_fields(self):
        response = self.client.post(
            "/api/restore-session",
            json={"session_state": {"context": {}, "admin": True}},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
