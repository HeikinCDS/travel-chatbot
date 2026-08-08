import unittest

from chatbot.service import ChatbotService, ChatSession
from dialogue.context_manager import ConversationContext
from nlp.entity_extractor import TravelPreferences
from nlp.intent_classifier import IntentPrediction
from nlp.local_llm import LLMInterpretation


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


class OfflineDiscovery:
    """Keep unit tests deterministic; live services have dedicated tests."""

    def discover(self, preferences, *, limit):
        return []

    def get_by_id(self, attraction_id):
        return None


class OfflineLanguageInterpreter:
    def interpret(self, text, context):
        return None


class FixedLanguageInterpreter:
    def __init__(self, interpretation):
        self.interpretation = interpretation
        self.calls = 0

    def interpret(self, text, context):
        self.calls += 1
        return self.interpretation


class ChatbotServiceTests(unittest.TestCase):

    def make_service(
        self,
        label,
        confidence=0.95,
        limit=3,
        web_discovery=None,
        language_interpreter=None,
    ):
        return ChatbotService(
            classifier=FixedClassifier(label, confidence),
            recommendation_limit=limit,
            web_discovery=(
                web_discovery if web_discovery is not None else OfflineDiscovery()
            ),
            language_interpreter=(
                language_interpreter
                if language_interpreter is not None
                else OfflineLanguageInterpreter()
            ),
        )

    def test_local_model_recovers_a_flexible_travel_request(self):
        class CandidateDiscovery:
            def discover(self, preferences, *, limit):
                return [{
                    "attraction_id": "LM-TEST",
                    "attraction_name": "Calm Garden",
                    "state_territory": "Penang",
                    "city_district": "George Town",
                    "primary_category": "Nature",
                    "short_description": "A calm public garden.",
                    "elderly_friendly": "Yes",
                }]

            def get_by_id(self, attraction_id):
                return None

        interpretation = LLMInterpretation(
            intent="request_recommendation",
            confidence=0.91,
            travel_related=True,
            preferences=TravelPreferences(
                state="Penang",
                interests=("nature",),
                elderly_friendly=True,
            ),
        )
        response = self.make_service(
            "out_of_scope",
            web_discovery=CandidateDiscovery(),
            language_interpreter=FixedLanguageInterpreter(interpretation),
        ).process_message(
            "My older mother would enjoy somewhere calm nearby"
        )
        self.assertEqual(response.action, "recommend")
        self.assertEqual(response.intent, "request_recommendation")
        self.assertEqual(response.context["state"], "Penang")
        self.assertIn("nature", response.context["interests"])
        self.assertTrue(response.context["elderly_friendly"])

    def test_recognised_state_does_not_wait_for_local_model(self):
        interpreter = FixedLanguageInterpreter(LLMInterpretation(
            intent="refine_preferences",
            confidence=0.99,
            travel_related=True,
            preferences=TravelPreferences(),
        ))
        session = ChatSession(
            context=ConversationContext(interests=["relaxation"])
        )
        response = self.make_service(
            "refine_preferences",
            language_interpreter=interpreter,
        ).process_message("Perak", session)

        self.assertEqual(interpreter.calls, 0)
        self.assertEqual(response.context["state"], "Perak")
        self.assertEqual(response.action, "recommend")

    def test_open_data_candidate_is_combined_with_local_results(self):
        web_item = {
            "attraction_id": "WEB-TEST",
            "attraction_name": "Test Botanical Walk",
            "state_territory": "Penang",
            "city_district": "George Town",
            "primary_category": "Nature",
            "interests_tags": "nature, garden",
            "short_description": "A source-backed test attraction.",
            "entrance_fee_status": "Unknown",
            "min_fee_myr": None,
            "max_fee_myr": None,
            "recommended_duration_hours": 1.5,
            "family_friendly": "Yes",
            "elderly_friendly": "Partial",
            "wheelchair_accessible": "Unknown",
            "accessibility_notes": "Confirm the current route before visiting.",
            "official_url": "https://example.org/attraction",
            "source_url": "https://example.org/attraction",
            "source_links": [
                {"title": "Official source", "url": "https://example.org/attraction"}
            ],
            "date_verified": "2026-08-08",
            "verification_status": "web_discovered",
            "information_origin": "open_data",
        }

        class FakeDiscovery:
            def discover(self, preferences, *, limit):
                return [web_item]

            def get_by_id(self, attraction_id):
                return web_item if attraction_id == "WEB-TEST" else None

        session = ChatSession(
            context=ConversationContext(state="Penang", interests=["nature"])
        )
        service = self.make_service(
            "request_recommendation",
            limit=1,
            web_discovery=FakeDiscovery(),
        )
        response = service.process_message("Recommend a nature place", session)
        self.assertEqual(response.action, "recommend")
        self.assertEqual(response.recommendations[0]["attraction_id"], "WEB-TEST")
        self.assertIsNone(response.recommendations[0]["verification_note"])
        self.assertIsNone(response.recommendations[0]["cost_summary"])
        self.assertEqual(
            response.recommendations[0]["accessibility_summary"],
            "Elderly-friendly: Partial",
        )

        details = service.process_message("Tell me about the first option", session)
        self.assertEqual(details.action, "information")
        self.assertEqual(
            details.recommendations[0]["attraction_name"],
            "Test Botanical Walk",
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
        self.assertIn("travel", response.reply)

    def test_unrelated_message_is_redirected_to_travel(self):
        session = ChatSession(
            context=ConversationContext(
                state="Johor",
                interests=["nature"],
            )
        )
        before = session.to_dict()
        response = self.make_service("out_of_scope").process_message(
            "Can you help me write Python code?",
            session,
        )
        self.assertEqual(response.action, "out_of_scope")
        self.assertIn("travel", response.reply)
        self.assertIn("Malaysia", response.reply)
        self.assertEqual(session.to_dict(), before)
        self.assertGreater(len(response.suggestions), 0)

    def test_travel_entity_overrides_out_of_scope_prediction(self):
        session = ChatSession()
        response = self.make_service("out_of_scope").process_message(
            "What about nature places in Kedah?",
            session,
        )
        self.assertEqual(response.action, "recommend")
        self.assertEqual(session.context.state, "Kedah")
        self.assertEqual(session.context.interests, ["nature"])

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
