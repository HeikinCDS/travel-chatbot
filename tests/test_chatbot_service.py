import unittest
from unittest.mock import patch

from chatbot.service import (
    ChatbotService,
    ChatSession,
    _accessibility_detail,
    _accessibility_features,
    _present_attraction,
)
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

    def test_eligible_attraction_shows_one_accessibility_source_without_badge(self):
        presented = _present_attraction({
            "attraction_name": "Accessible Garden",
            "short_description": "A quiet public garden.",
            "elderly_recommendation_eligibility": "Eligible",
            "accessibility_evidence_source": (
                "https://example.org/access\n"
                "https://example.org/secondary-access"
            ),
        })

        self.assertIsNone(presented["accessibility_evidence_badge"])
        self.assertEqual(presented["accessibility_evidence_links"], [{
            "title": "Accessibility information",
            "url": "https://example.org/access",
        }])

    def test_eligible_attraction_exposes_why_it_suits_elderly_visitors(self):
        presented = _present_attraction({
            "attraction_name": "Accessible Garden",
            "short_description": "A quiet public garden.",
            "elderly_recommendation_eligibility": "Eligible",
            "accessibility_screening_notes": (
                "A level boardwalk and resting areas reduce walking barriers."
            ),
        })

        self.assertEqual(
            presented["accessibility_reason"],
            "A level boardwalk and resting areas reduce walking barriers.",
        )

    def test_tanjung_piai_information_explains_elderly_accessibility(self):
        session = ChatSession(latest_recommendation_ids=["A036"])
        response = self.make_service("request_information").process_message(
            "Tell me about Tanjung Piai National Park",
            session,
        )

        self.assertEqual(response.action, "information")
        self.assertIn("Why it may suit elderly visitors", response.reply)
        self.assertIn("Mangrove boardwalk", response.reply)
        self.assertIn("confirm boardwalk condition", response.reply)
        self.assertEqual(
            response.recommendations[0]["accessibility_reason"],
            "Recorded because the source explicitly documents these facilities or restrictions.",
        )

    def test_specific_accessibility_need_overrides_wrong_intent_prediction(self):
        session = ChatSession()
        response = self.make_service("goodbye").process_message(
            "I need nearby parking and benches because I cannot walk far",
            session,
        )

        self.assertEqual(response.action, "clarify_preferences")
        self.assertEqual(
            set(response.context["accessibility_needs"]),
            {"nearby_parking", "seating", "low_walking"},
        )
        self.assertNotIn("Goodbye", response.reply)

    def test_missing_accessibility_fields_are_named_without_verification_warning(self):
        detail = _accessibility_detail({
            "elderly_friendly": "Unknown",
            "wheelchair_accessible": "Unknown",
            "accessibility_notes": (
                "Accessibility information has not been verified. Confirm "
                "terrain, steps, seating and toilets with an official source."
            ),
        })

        self.assertEqual(
            detail,
            "Accessibility details not recorded: elderly suitability and "
            "wheelchair access",
        )
        self.assertNotIn("official source", detail)

    def test_specific_accessibility_note_is_preserved(self):
        detail = _accessibility_detail({
            "elderly_friendly": "Partial",
            "wheelchair_accessible": "Yes",
            "accessibility_notes": "A lift serves the main visitor level.",
        })

        self.assertEqual(
            detail,
            "Accessibility notes: A lift serves the main visitor level.",
        )

    def test_specific_note_is_preserved_when_a_structured_field_is_missing(self):
        detail = _accessibility_detail({
            "elderly_friendly": "Partial",
            "wheelchair_accessible": "Unknown",
            "accessibility_notes": "Benches are available along the main path.",
        })

        self.assertEqual(
            detail,
            "Accessibility notes: Benches are available along the main path.",
        )

    @patch("chatbot.service.find_attraction_by_name_in_text")
    def test_named_attraction_question_overrides_broad_state_search(
        self,
        find_named_attraction,
    ):
        penang_hill = {
            "attraction_id": "TEST-PENANG-HILL",
            "attraction_name": "Penang Hill",
            "state_territory": "Penang",
            "city_district": "George Town",
            "primary_category": "Nature",
            "short_description": "A hill resort reached by funicular railway.",
            "elderly_friendly": "Unknown",
            "wheelchair_accessible": "Unknown",
        }
        find_named_attraction.return_value = penang_hill
        service = self.make_service("request_information")
        session = ChatSession(latest_recommendation_ids=["ESCAPE-PENANG"])

        with patch.object(service, "_get_attraction", return_value=penang_hill):
            response = service.process_message("Tell me about Penang Hill", session)

        self.assertEqual(response.action, "information")
        self.assertEqual(
            response.recommendations[0]["attraction_name"],
            "Penang Hill",
        )
        self.assertIn("Penang Hill:", response.reply)
        self.assertNotIn("ESCAPE Penang", response.reply)
        self.assertEqual(session.latest_recommendation_ids, ["TEST-PENANG-HILL"])
        self.assertEqual(session.context.state, "Penang")

    def test_misheard_place_name_asks_for_confirmation(self):
        session = ChatSession(
            context=ConversationContext(state="Johor", interests=["beach"]),
            latest_recommendation_ids=["MC0025", "MC0029", "MC0024"],
        )
        service = self.make_service("request_information")

        confirmation = service.process_message(
            "OK let's go with a Poppin Beach",
            session,
        )

        self.assertEqual(confirmation.action, "confirm_attraction")
        self.assertIn("Do you mean Air Papan Beach?", confirmation.reply)
        self.assertEqual(session.pending_attraction_id, "MC0025")
        self.assertEqual(
            confirmation.suggestions[0]["label"],
            "Yes, Air Papan Beach",
        )

        details = service.process_message("Yes", session)

        self.assertEqual(details.action, "information")
        self.assertIn("Air Papan Beach:", details.reply)
        self.assertIsNone(session.pending_attraction_id)

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
            enable_live_discovery=web_discovery is not None,
            enable_local_llm=language_interpreter is not None,
        )

    def test_environment_flags_disable_external_services(self):
        class ForbiddenDiscovery:
            def discover(self, preferences, *, limit):
                raise AssertionError("Live discovery must remain disabled")

            def get_by_id(self, attraction_id):
                raise AssertionError("Live discovery must remain disabled")

        class ForbiddenInterpreter:
            def interpret(self, text, context):
                raise AssertionError("The local LLM must remain disabled")

        disabled = {
            "ENABLE_LOCAL_LLM": "false",
            "ENABLE_LIVE_DISCOVERY": "false",
        }
        with patch.dict("os.environ", disabled):
            uncertain_service = ChatbotService(
                classifier=FixedClassifier("out_of_scope", 0.20),
                web_discovery=ForbiddenDiscovery(),
                language_interpreter=ForbiddenInterpreter(),
            )
            uncertain = uncertain_service.process_message(
                "Something calm for my mother"
            )

            recommendation_service = ChatbotService(
                classifier=FixedClassifier("request_recommendation"),
                web_discovery=ForbiddenDiscovery(),
                language_interpreter=ForbiddenInterpreter(),
            )
            session = ChatSession(
                context=ConversationContext(
                    state="Penang",
                    interests=["nature"],
                )
            )
            recommendation = recommendation_service.process_message(
                "Recommend a place",
                session,
            )

        self.assertEqual(uncertain.action, "out_of_scope")
        self.assertIn(
            recommendation.action,
            {"recommend", "no_results"},
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
        service = self.make_service(
            "out_of_scope",
            web_discovery=CandidateDiscovery(),
            language_interpreter=FixedLanguageInterpreter(interpretation),
        )
        session = ChatSession()
        response = service.process_message(
            "My older mother would enjoy somewhere calm nearby",
            session,
        )
        self.assertEqual(response.action, "clarify_accessibility")
        self.assertEqual(response.intent, "request_recommendation")
        self.assertEqual(response.context["state"], "Penang")
        self.assertIn("nature", response.context["interests"])
        self.assertTrue(response.context["elderly_friendly"])

        recommendation = service.process_message(
            "No special accessibility requirements",
            session,
        )
        self.assertEqual(recommendation.action, "recommend")

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
            "short_description": "A referenced test attraction.",
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
            retrieval_query="quiet nature in Johor",
        )
        response = self.make_service("reset_conversation").process_message(
            "Start over",
            session,
        )
        self.assertEqual(response.action, "reset")
        self.assertEqual(session.context.to_dict(), {})
        self.assertEqual(session.shown_attraction_ids, [])
        self.assertIsNone(session.ranking_preference)
        self.assertIsNone(session.retrieval_query)

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
        self.assertEqual(session.retrieval_query, "Relaxation")
        self.assertGreater(len(response.recommendations), 0)
        self.assertTrue(all(
            item["state_territory"] == "Penang"
            for item in response.recommendations
        ))

    def test_state_and_interest_message_replaces_old_interests(self):
        session = ChatSession(
            context=ConversationContext(
                state="Penang",
                interests=["nature", "wildlife"],
            )
        )
        response = self.make_service("request_recommendation").process_message(
            "I want somewhere peaceful in Penang",
            session,
        )

        self.assertEqual(response.action, "recommend")
        self.assertEqual(session.context.interests, ["relaxation"])

    def test_general_elderly_request_asks_for_a_specific_access_need(self):
        session = ChatSession()
        response = self.make_service("request_recommendation").process_message(
            "I want somewhere peaceful for my elderly mother in Penang",
            session,
        )

        self.assertEqual(response.action, "clarify_accessibility")
        self.assertIn("most important accessibility need", response.reply)
        self.assertEqual(
            [suggestion["label"] for suggestion in response.suggestions],
            [
                "Minimal walking",
                "Wheelchair access",
                "Nearby seats",
                "Accessible toilet",
                "No special requirements",
            ],
        )

        recommendation = self.make_service("request_recommendation").process_message(
            "No special accessibility requirements",
            session,
        )
        self.assertEqual(recommendation.action, "recommend")
        self.assertGreater(len(recommendation.recommendations), 0)

    def test_accessibility_features_name_known_and_missing_fields(self):
        features = _accessibility_features({
            "walking_difficulty": "Low",
            "step_free_access": "Yes",
            "resting_seats_available": "Unknown",
            "accessible_toilet": "Yes",
            "parking_proximity": "Near",
            "shelter_available": "Partial",
            "elderly_suitability": "Suitable",
        })

        self.assertEqual(len(features), 7)
        self.assertEqual(features[0], {
            "label": "Walking difficulty",
            "value": "Low",
            "status": "positive",
        })
        self.assertEqual(features[2]["value"], "Not recorded")
        self.assertEqual(features[5]["status"], "caution")

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

    def test_explicit_new_trip_asks_for_fresh_preferences(self):
        session = ChatSession(
            context=ConversationContext(
                state="Penang",
                interests=["nature"],
                maximum_fee=30,
                elderly_friendly=True,
                accessibility_needs=["low_walking"],
            ),
            accessibility_clarified=True,
        )
        service = self.make_service("request_recommendation")

        interest_question = service.process_message(
            "Hello I would like to visit Sarawak with my elderly parents",
            session,
        )

        self.assertEqual(interest_question.action, "clarify_preferences")
        self.assertEqual(session.context.state, "Sarawak")
        self.assertEqual(session.context.interests, [])
        self.assertIsNone(session.context.maximum_fee)
        self.assertTrue(session.context.elderly_friendly)
        self.assertEqual(session.context.accessibility_needs, [])
        self.assertIn("type of attraction", interest_question.reply)

        access_question = service.process_message("Nature", session)

        self.assertEqual(access_question.action, "clarify_accessibility")
        self.assertIn("accessibility need", access_question.reply)

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

    def test_show_more_phrase_returns_next_unseen_batch_despite_wrong_intent(self):
        session = ChatSession(
            context=ConversationContext(
                state="Penang",
                interests=["nature"],
            )
        )
        first = self.make_service(
            "request_recommendation",
            limit=3,
        ).process_message("Recommend some nature places", session)
        second = self.make_service(
            "help",
            limit=3,
        ).process_message("Show me more options", session)

        first_ids = {
            item["attraction_id"] for item in first.recommendations
        }
        second_ids = {
            item["attraction_id"] for item in second.recommendations
        }
        self.assertEqual(second.action, "alternative")
        self.assertTrue(second_ids)
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_repeated_show_more_requests_do_not_repeat_earlier_places(self):
        session = ChatSession(
            context=ConversationContext(
                state="Penang",
                interests=["nature"],
            )
        )
        first = self.make_service(
            "request_recommendation",
            limit=1,
        ).process_message("Recommend a nature place", session)
        second = self.make_service(
            "out_of_scope",
            limit=1,
        ).process_message("Show me more options", session)
        third = self.make_service(
            "greeting",
            limit=1,
        ).process_message("Give me additional choices", session)

        result_ids = [
            response.recommendations[0]["attraction_id"]
            for response in (first, second, third)
        ]
        self.assertEqual(len(result_ids), len(set(result_ids)))

    def test_recommendation_suggestions_include_show_more_button(self):
        session = ChatSession(
            context=ConversationContext(
                state="Johor",
                interests=["nature"],
            )
        )
        response = self.make_service(
            "request_recommendation",
        ).process_message("Recommend nature places", session)

        self.assertIn(
            {
                "label": "Show me more options",
                "message": "Show me more options",
            },
            response.suggestions,
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

    @patch("chatbot.service.recommend_attractions", return_value=[])
    def test_repeated_beach_update_preserves_accessibility_and_explains_no_match(self, search):
        session = ChatSession(context=ConversationContext(
            state="Penang", interests=["beach"], elderly_friendly=True,
            wheelchair_accessible=True, maximum_fee=30,
        ), accessibility_clarified=True)
        before = session.context.to_dict()
        response = self.make_service("refine_preferences").process_message(
            "Actually change my interest to beach", session,
        )
        self.assertEqual(response.action, "no_results")
        self.assertIn("Your interest is already set to beach", response.reply)
        self.assertIn("Penang", response.reply)
        self.assertIn("recorded wheelchair access", response.reply)
        self.assertIn("recorded elderly suitability", response.reply)
        self.assertIn("RM30", response.reply)
        self.assertNotIn("Which preference", response.reply)
        self.assertEqual(session.context.to_dict(), before)
        self.assertEqual(response.to_dict()["unchanged_preferences"], {"interests": ["beach"]})
        self.assertEqual(search.call_count, 1)
        self.assertTrue(search.call_args.kwargs["wheelchair_accessible"])
        self.assertEqual(search.call_args.kwargs["maximum_fee"], 30)

    @patch("chatbot.service.recommend_attractions", return_value=[])
    def test_explicit_repeated_update_overrides_wrong_intent(self, search):
        session = ChatSession(context=ConversationContext(state="Penang", interests=["beach"]))
        response = self.make_service("out_of_scope", confidence=0.2).process_message(
            "Actually change my interest to beach", session,
        )
        self.assertEqual(response.action, "no_results")
        search.assert_called_once()

    @patch("chatbot.service.recommend_attractions", return_value=[])
    def test_changed_interest_replaces_old_interest_and_retains_mobility(self, search):
        session = ChatSession(context=ConversationContext(
            state="Penang", interests=["nature"], wheelchair_accessible=True,
        ), accessibility_clarified=True)
        response = self.make_service("refine_preferences").process_message(
            "Actually change my interest to beach", session,
        )
        self.assertEqual(response.action, "no_results")
        self.assertEqual(session.context.interests, ["beach"])
        self.assertTrue(session.context.wheelchair_accessible)
        self.assertEqual(response.unchanged_preferences, {})

    def test_vague_refinement_still_asks_which_preference(self):
        session = ChatSession(context=ConversationContext(state="Penang", interests=["beach"]))
        response = self.make_service("refine_preferences").process_message(
            "I want to change my preferences", session,
        )
        self.assertEqual(response.action, "request_refinement")

    def test_repeated_interest_asks_only_for_missing_state(self):
        session = ChatSession(context=ConversationContext(interests=["beach"]))
        response = self.make_service("refine_preferences").process_message(
            "Actually change my interest to beach", session,
        )
        self.assertEqual(response.action, "clarify_preferences")
        self.assertIn("state", response.reply)

    def test_repeated_interest_does_not_skip_accessibility_clarification(self):
        session = ChatSession(context=ConversationContext(
            state="Penang", interests=["beach"], elderly_friendly=True,
        ))
        response = self.make_service("refine_preferences").process_message(
            "Actually change my interest to beach", session,
        )
        self.assertEqual(response.action, "clarify_accessibility")

    @patch("chatbot.service.recommend_attractions", return_value=[])
    def test_repeated_budget_and_wheelchair_requests_are_not_vague(self, search):
        for message in ("Change my budget to RM30", "The traveller needs wheelchair access"):
            with self.subTest(message=message):
                session = ChatSession(context=ConversationContext(
                    state="Penang", interests=["beach"], maximum_fee=30,
                    wheelchair_accessible=True,
                ), accessibility_clarified=True)
                response = self.make_service("refine_preferences").process_message(message, session)
                self.assertEqual(response.action, "no_results")
                self.assertTrue(response.unchanged_preferences)

    @patch("chatbot.service.recommend_attractions", return_value=[{
        "attraction_id": "TEST", "attraction_name": "Test beach",
        "state_territory": "Penang", "short_description": "A test fixture.",
    }])
    def test_repeated_interest_can_still_return_available_matches(self, search):
        session = ChatSession(context=ConversationContext(state="Penang", interests=["beach"]))
        response = self.make_service("refine_preferences").process_message(
            "Actually change my interest to beach", session,
        )
        self.assertEqual(response.action, "recommend")
        self.assertEqual(response.recommendations[0]["attraction_id"], "TEST")
        self.assertIn("already set to beach", response.reply)

    def test_elderly_request_uses_reviewed_accessibility_collection(self):
        session = ChatSession(
            context=ConversationContext(
                state="Penang",
                interests=["nature"],
                elderly_friendly=True,
                accessibility_needs=["low_walking"],
            ),
            accessibility_clarified=True,
        )
        response = self.make_service("request_recommendation").process_message(
            "Recommend a place",
            session,
        )

        self.assertEqual(response.action, "recommend")
        self.assertTrue(response.recommendations)
        self.assertTrue(all(
            item["state_territory"] == "Penang"
            for item in response.recommendations
        ))
        self.assertTrue(all(
            item["elderly_recommendation_eligibility"] == "Eligible"
            for item in response.recommendations
        ))

    def test_session_round_trip(self):
        original = ChatSession(
            context=ConversationContext(
                state="Johor",
                interests=["nature"],
            ),
            shown_attraction_ids=["A001"],
            latest_recommendation_ids=["A001"],
            ranking_preference="duration",
            retrieval_query="quiet nature in Johor",
            accessibility_clarified=True,
        )
        restored = ChatSession.from_dict(original.to_dict())
        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_empty_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self.make_service("greeting").process_message("  ")


if __name__ == "__main__":
    unittest.main()
