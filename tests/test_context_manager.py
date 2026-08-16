import unittest

from dialogue.context_manager import ConversationContext
from nlp.entity_extractor import TravelPreferences
from recommendation_engine.recommendation_engine import recommend_attractions


class ConversationContextTests(unittest.TestCase):

    def test_retains_specific_elderly_accessibility_needs(self):
        context = ConversationContext()
        context.update_from_text(
            "My father cannot walk far and needs benches and nearby parking"
        )

        self.assertEqual(
            set(context.accessibility_needs),
            {"low_walking", "seating", "nearby_parking"},
        )
        self.assertIn("minimal walking", context.preference_summary())
        self.assertEqual(
            set(context.recommendation_filters()["accessibility_needs"]),
            set(context.accessibility_needs),
        )

    def test_new_context_is_empty(self):
        context = ConversationContext()
        self.assertEqual(context.to_dict(), {})
        self.assertFalse(context.is_ready_for_recommendation())

    def test_retains_preferences_across_turns(self):
        context = ConversationContext()

        first_changes = context.update_from_text("I want to visit Penang")
        second_changes = context.update_from_text("Somewhere relaxing")
        third_changes = context.update_from_text("Keep it under RM20")

        self.assertEqual(first_changes, {"state": "Penang"})
        self.assertEqual(second_changes, {"interests": ["relaxation"]})
        self.assertEqual(third_changes, {"maximum_fee": 20.0})
        self.assertEqual(context.state, "Penang")
        self.assertEqual(context.interests, ["relaxation"])
        self.assertEqual(context.maximum_fee, 20.0)
        self.assertTrue(context.is_ready_for_recommendation())

    def test_adds_another_interest(self):
        context = ConversationContext(interests=["nature"])
        context.update_from_text("I also like wildlife")
        self.assertEqual(context.interests, ["nature", "wildlife"])

    def test_correction_replaces_interests(self):
        context = ConversationContext(interests=["nature", "hiking"])
        changes = context.update_from_text("Actually, make it a beach instead")
        self.assertEqual(changes, {"interests": ["beach"]})
        self.assertEqual(context.interests, ["beach"])

    def test_new_state_replaces_previous_state(self):
        context = ConversationContext(state="Penang")
        context.update_from_text("Change the destination to Perak")
        self.assertEqual(context.state, "Perak")

    def test_free_entry_is_not_treated_as_missing(self):
        context = ConversationContext()
        context.update_from_text("I only want free entry")
        self.assertEqual(context.maximum_fee, 0.0)

    def test_next_question_asks_for_state_first(self):
        context = ConversationContext()
        self.assertIn("state or federal territory", context.next_clarification_question())

    def test_next_question_asks_for_interest_after_state(self):
        context = ConversationContext(state="Johor")
        self.assertIn("type of attraction", context.next_clarification_question())

    def test_no_question_when_required_preferences_exist(self):
        context = ConversationContext(state="Johor", interests=["nature"])
        self.assertIsNone(context.next_clarification_question())

    def test_context_round_trip_for_flask_session(self):
        original = ConversationContext(
            state="W.P. Putrajaya",
            interests=["nature", "relaxation"],
            maximum_fee=20,
            elderly_friendly=True,
        )
        restored = ConversationContext.from_dict(original.to_dict())
        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_clear_one_preference(self):
        context = ConversationContext(
            state="Johor",
            interests=["nature"],
            maximum_fee=25,
        )
        context.clear_preference("maximum_fee")
        self.assertEqual(context.state, "Johor")
        self.assertEqual(context.interests, ["nature"])
        self.assertIsNone(context.maximum_fee)

    def test_reset_clears_every_preference(self):
        context = ConversationContext(
            state="Johor",
            interests=["nature"],
            family_friendly=True,
        )
        context.reset()
        self.assertEqual(context.to_dict(), {})

    def test_recommendation_filters_use_current_context(self):
        context = ConversationContext(
            state="W.P. Putrajaya",
            interests=["nature", "relaxation"],
            maximum_fee=20,
            elderly_friendly=True,
        )
        self.assertEqual(
            context.recommendation_filters(),
            {
                "state": "W.P. Putrajaya",
                "interest": "nature",
                "maximum_fee": 20,
                "elderly_friendly": True,
            },
        )

    def test_context_can_drive_recommendation_engine(self):
        context = ConversationContext()
        context.update_from_text("I want nature in Putrajaya")
        context.update_from_text("It is for my elderly parents")

        results = recommend_attractions(
            **context.recommendation_filters(),
            limit=5,
        )

        self.assertGreater(len(results), 0)
        for attraction in results:
            self.assertEqual(attraction["state_territory"], "W.P. Putrajaya")
            self.assertIn(
                attraction["elderly_friendly"].lower(),
                ["yes", "partial", "unknown"],
            )

    def test_summary_is_readable(self):
        context = ConversationContext(
            state="Penang",
            interests=["nature"],
            maximum_fee=10,
        )
        summary = context.preference_summary()
        self.assertIn("location: Penang", summary)
        self.assertIn("interests: nature", summary)
        self.assertIn("RM10", summary)

    def test_update_requires_travel_preferences(self):
        context = ConversationContext()
        with self.assertRaises(TypeError):
            context.update({"state": "Johor"})

    def test_from_dict_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            ConversationContext.from_dict({"unknown": "value"})


if __name__ == "__main__":
    unittest.main()
