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

    def test_goodbye_requires_actual_goodbye_words(self):
        goodbye = self.make_service("goodbye").process_message("See you")
        self.assertEqual(goodbye.action, "goodbye")

        session = ChatSession(
            context=ConversationContext(state="Kedah")
        )
        not_goodbye = self.make_service("goodbye").process_message(
            "No changes",
            session,
        )
        self.assertEqual(not_goodbye.action, "clarify_preferences")
        self.assertIn("type of attraction", not_goodbye.reply)

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
            ranking_preference="accessibility",
        )
        response = self.make_service("reset_conversation").process_message(
            "Start over",
            session,
        )
        self.assertEqual(response.action, "reset")
        self.assertEqual(session.context.to_dict(), {})
        self.assertEqual(session.shown_attraction_ids, [])
        self.assertIsNone(session.ranking_preference)

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

    def test_state_inside_information_question_takes_priority(self):
        session = ChatSession()
        response = self.make_service("request_information").process_message(
            "Okay, what about places that are in Kedah?",
            session,
        )
        self.assertEqual(response.action, "clarify_preferences")
        self.assertEqual(session.context.state, "Kedah")
        self.assertIn("type of attraction", response.reply)

    def test_new_state_replaces_previous_location_despite_intent_label(self):
        session = ChatSession(
            context=ConversationContext(
                state="Sarawak",
                interests=["nature"],
            )
        )
        self.make_service("request_recommendation").process_message(
            "Recommend somewhere",
            session,
        )
        response = self.make_service("request_information").process_message(
            "What about Kedah?",
            session,
        )
        self.assertEqual(response.action, "recommend")
        self.assertEqual(session.context.state, "Kedah")
        self.assertTrue(all(
            item["state_territory"] == "Kedah"
            for item in response.recommendations
        ))

    def test_repeated_state_still_asks_for_missing_interest(self):
        session = ChatSession(
            context=ConversationContext(state="Kedah")
        )
        response = self.make_service("refine_preferences").process_message(
            "Kedah",
            session,
        )
        self.assertEqual(response.action, "clarify_preferences")
        self.assertIn("type of attraction", response.reply)

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
        recommendation = self.make_service("request_recommendation").process_message(
            "Recommend a place",
            session,
        )
        selected_name = recommendation.recommendations[1]["attraction_name"]
        response = self.make_service("request_information").process_message(
            f"Tell me about {selected_name}",
            session,
        )
        self.assertEqual(response.action, "information")
        self.assertGreater(len(response.recommendations), 0)
        self.assertEqual(
            response.recommendations[0]["attraction_name"],
            selected_name,
        )
        self.assertIn("Accessibility", response.reply)

    def test_generic_information_request_asks_user_to_choose(self):
        session = ChatSession(
            context=ConversationContext(
                state="Perak",
                interests=["nature"],
            )
        )
        self.make_service("request_recommendation").process_message(
            "Recommend places",
            session,
        )
        response = self.make_service("request_information").process_message(
            "Tell me more",
            session,
        )
        self.assertEqual(response.action, "choose_recommendation")
        self.assertEqual(len(response.suggestions), 3)

    def test_results_offer_conversational_refinement(self):
        session = ChatSession(
            context=ConversationContext(
                state="Perak",
                interests=["nature"],
            )
        )
        response = self.make_service("request_recommendation").process_message(
            "Recommend places",
            session,
        )
        labels = {item["label"] for item in response.suggestions}
        self.assertIn("Easiest access", labels)
        self.assertIn("Lowest cost", labels)
        self.assertIn("Shortest visit", labels)
        self.assertTrue(all(
            "AI-generated candidate" not in item["display_description"]
            for item in response.recommendations
        ))

    def test_shortest_visit_comparison_uses_recorded_duration(self):
        session = ChatSession(
            context=ConversationContext(
                state="W.P. Putrajaya",
                interests=["nature"],
            )
        )
        self.make_service("request_recommendation").process_message(
            "Recommend places",
            session,
        )
        response = self.make_service("request_information").process_message(
            "Which option has the shortest visit?",
            session,
        )
        self.assertEqual(response.action, "comparison")
        self.assertEqual(
            response.recommendations[0]["attraction_name"],
            "Saujana Hijau Park",
        )

    def test_natural_back_request_restores_previous_options(self):
        session = ChatSession(
            context=ConversationContext(
                state="Perak",
                interests=["nature"],
            )
        )
        original = self.make_service("request_recommendation").process_message(
            "Recommend places",
            session,
        )
        selected_name = original.recommendations[0]["attraction_name"]
        self.make_service("request_information").process_message(
            f"Tell me about {selected_name}",
            session,
        )

        response = self.make_service("help").process_message(
            "What's the other choice?",
            session,
        )

        self.assertEqual(response.action, "show_previous_options")
        self.assertEqual(
            [item["attraction_id"] for item in response.recommendations],
            session.latest_recommendation_ids,
        )
        self.assertGreater(len(response.suggestions), 3)

    def test_new_state_takes_priority_over_old_result_comparison(self):
        session = ChatSession(
            context=ConversationContext(
                state="Sarawak",
                interests=["nature"],
            )
        )
        self.make_service("request_recommendation").process_message(
            "Recommend places",
            session,
        )

        response = self.make_service("help").process_message(
            "Cheapest location in Kuala Lumpur",
            session,
        )

        self.assertEqual(response.action, "recommend")
        self.assertEqual(session.context.state, "Kuala Lumpur")
        self.assertEqual(session.ranking_preference, "cost")
        self.assertTrue(all(
            item["state_territory"] == "Kuala Lumpur"
            for item in response.recommendations
        ))
        self.assertNotIn(
            "Bako National Park",
            {item["attraction_name"] for item in response.recommendations},
        )

    def test_ranking_request_survives_a_clarification_turn(self):
        session = ChatSession()
        first = self.make_service("help").process_message(
            "Find the cheapest place in Kuala Lumpur",
            session,
        )
        self.assertEqual(first.action, "clarify_preferences")
        self.assertEqual(session.ranking_preference, "cost")

        second = self.make_service("request_recommendation").process_message(
            "Nature",
            session,
        )
        self.assertEqual(second.action, "recommend")
        self.assertEqual(
            second.recommendations[0]["attraction_name"],
            "KL Bird Park",
        )

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
            ranking_preference="duration",
        )
        restored = ChatSession.from_dict(original.to_dict())
        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_empty_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self.make_service("greeting").process_message("  ")


if __name__ == "__main__":
    unittest.main()
