import unittest

from chatbot.service import ChatbotService, ChatSession
from dialogue.context_manager import ConversationContext
from nlp.intent_classifier import IntentPrediction


class FixedClassifier:
    def __init__(self, label, confidence=0.95):
        self.label = label
        self.confidence = confidence

    def predict(self, text):
        return IntentPrediction(
            label=self.label,
            confidence=self.confidence,
            scores={self.label: self.confidence},
        )


class ChatbotServiceTests(unittest.TestCase):

    def make_service(self, label, confidence=0.95, limit=3):
        return ChatbotService(
            classifier=FixedClassifier(label, confidence),
            recommendation_limit=limit,
        )

    def test_greeting(self):
        response = self.make_service("greeting").process_message("Hello")
        self.assertEqual(response.action, "greeting")
        self.assertIn("Malaysian state", response.reply)

    def test_help(self):
        response = self.make_service("help").process_message("Help me")
        self.assertEqual(response.action, "help")
        self.assertIn("accessibility", response.reply)

    def test_reset_clears_session(self):
        session = ChatSession(
            context=ConversationContext(
                state="Johor",
                interests=["nature"],
            ),
            shown_attraction_ids=["A001"],
            latest_recommendation_ids=["A001"],
        )
        response = self.make_service("reset_conversation").process_message(
            "Start over",
            session,
        )
        self.assertEqual(response.action, "reset")
        self.assertEqual(session.context.to_dict(), {})
        self.assertEqual(session.shown_attraction_ids, [])

    def test_recognised_interest_is_not_mistaken_for_reset(self):
        session = ChatSession(
            context=ConversationContext(state="Penang")
        )
        response = self.make_service("reset_conversation").process_message(
            "Relaxation",
            session,
        )
        self.assertEqual(response.action, "recommend")
        self.assertEqual(session.context.state, "Penang")
        self.assertEqual(session.context.interests, ["relaxation"])
        self.assertGreater(len(response.recommendations), 0)
        self.assertTrue(all(
            item["state_territory"] == "Penang"
            for item in response.recommendations
        ))

    def test_reset_prediction_without_reset_words_does_not_clear_context(self):
        session = ChatSession(
            context=ConversationContext(
                state="Johor",
                interests=["nature"],
            )
        )
        response = self.make_service("reset_conversation").process_message(
            "Something else",
            session,
        )
        self.assertNotEqual(response.action, "reset")
        self.assertEqual(session.context.state, "Johor")

    def test_first_slot_answer_triggers_clarification(self):
        session = ChatSession()
        response = self.make_service("request_recommendation").process_message(
            "Penang",
            session,
        )
        self.assertEqual(response.action, "clarify_preferences")
        self.assertEqual(session.context.state, "Penang")
        self.assertIn("type of attraction", response.reply)

    def test_second_slot_answer_triggers_recommendation(self):
        session = ChatSession(
            context=ConversationContext(state="W.P. Putrajaya")
        )
        response = self.make_service("request_recommendation").process_message(
            "Nature",
            session,
        )
        self.assertEqual(response.action, "recommend")
        self.assertGreater(len(response.recommendations), 0)

    def test_low_confidence_without_entities_asks_for_rephrasing(self):
        response = self.make_service(
            "request_recommendation",
            confidence=0.20,
        ).process_message("Something suitable")
        self.assertEqual(response.action, "low_confidence")

    def test_structured_slot_is_used_even_with_low_confidence(self):
        session = ChatSession()
        response = self.make_service(
            "help",
            confidence=0.20,
        ).process_message("Johor", session)
        self.assertEqual(response.action, "clarify_preferences")
        self.assertEqual(session.context.state, "Johor")

    def test_alternative_avoids_previous_result(self):
        session = ChatSession(
            context=ConversationContext(
                state="Penang",
                interests=["nature"],
            )
        )
        first = self.make_service(
            "request_recommendation",
            limit=1,
        ).process_message("Recommend a place", session)
        second = self.make_service(
            "request_alternative",
            limit=1,
        ).process_message("Show another", session)

        self.assertEqual(first.action, "recommend")
        self.assertEqual(second.action, "alternative")
        self.assertNotEqual(
            first.recommendations[0]["attraction_id"],
            second.recommendations[0]["attraction_id"],
        )

    def test_information_request_uses_latest_recommendation(self):
        session = ChatSession(
            context=ConversationContext(
                state="W.P. Putrajaya",
                interests=["nature"],
            )
        )
        self.make_service("request_recommendation").process_message(
            "Recommend a place",
            session,
        )
        response = self.make_service("request_information").process_message(
            "Tell me more",
            session,
        )
        self.assertEqual(response.action, "information")
        self.assertGreater(len(response.recommendations), 0)
        self.assertIn("Accessibility information", response.reply)

    def test_information_requires_previous_recommendation(self):
        response = self.make_service("request_information").process_message(
            "Tell me more",
            ChatSession(),
        )
        self.assertEqual(response.action, "information_unavailable")

    def test_no_results_returns_helpful_message(self):
        session = ChatSession(
            context=ConversationContext(
                state="Kuala Lumpur",
                interests=["hot spring"],
            )
        )
        response = self.make_service("request_recommendation").process_message(
            "Recommend a place",
            session,
        )
        self.assertEqual(response.action, "no_results")
        self.assertIn("Kuala Lumpur", response.reply)
        self.assertIn("hot spring", response.reply)
        self.assertIn("still saved", response.reply)
        self.assertGreater(len(response.suggestions), 0)

    def test_session_round_trip(self):
        original = ChatSession(
            context=ConversationContext(
                state="Johor",
                interests=["nature"],
            ),
            shown_attraction_ids=["A001"],
            latest_recommendation_ids=["A001"],
        )
        restored = ChatSession.from_dict(original.to_dict())
        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_empty_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self.make_service("greeting").process_message("  ")


if __name__ == "__main__":
    unittest.main()
