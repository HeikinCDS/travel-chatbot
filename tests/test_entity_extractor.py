import unittest

from nlp.entity_extractor import extract_preferences, to_recommendation_filters


class EntityExtractorTests(unittest.TestCase):

    def test_extracts_specific_elderly_accessibility_needs(self):
        result = extract_preferences(
            "My elderly mother cannot walk far or climb stairs. We need "
            "benches, an accessible toilet, nearby parking and shade."
        )

        self.assertTrue(result.elderly_friendly)
        self.assertEqual(
            set(result.accessibility_needs),
            {
                "low_walking", "step_free", "seating",
                "accessible_toilet", "nearby_parking", "shelter",
            },
        )
        self.assertEqual(
            set(to_recommendation_filters(result)["accessibility_needs"]),
            set(result.accessibility_needs),
        )

    def test_extracts_full_state_name(self):
        result = extract_preferences("I want to visit Negeri Sembilan")
        self.assertEqual(result.state, "Negeri Sembilan")

    def test_normalises_state_alias(self):
        result = extract_preferences("Show me something interesting in KL")
        self.assertEqual(result.state, "Kuala Lumpur")

    def test_normalises_malacca_name(self):
        result = extract_preferences("Find attractions in Malacca")
        self.assertEqual(result.state, "Melaka")

    def test_extracts_numeric_budget(self):
        result = extract_preferences("My budget is RM 1,500")
        self.assertEqual(result.maximum_fee, 1500.0)

    def test_extracts_budget_after_change_command(self):
        result = extract_preferences("Change my budget to RM30")
        self.assertEqual(result.maximum_fee, 30.0)

    def test_extracts_free_entry(self):
        result = extract_preferences("I only want somewhere with free entry")
        self.assertEqual(result.maximum_fee, 0.0)

    def test_extracts_duration_in_days(self):
        result = extract_preferences("Plan a 4-day trip to Sabah")
        self.assertEqual(result.duration_days, 4)
        self.assertEqual(result.state, "Sabah")

    def test_extracts_duration_in_hours(self):
        result = extract_preferences("I have around 3 hours for a visit")
        self.assertEqual(result.duration_hours, 3.0)

    def test_normalises_interest_synonyms(self):
        result = extract_preferences("I like seaside scenery and trekking")
        self.assertEqual(result.interests, ("beach", "nature", "hiking"))

    def test_extracts_family_and_accessibility_needs(self):
        result = extract_preferences(
            "Find a wheelchair-friendly place for my family and elderly parents"
        )
        self.assertTrue(result.family_friendly)
        self.assertTrue(result.elderly_friendly)
        self.assertTrue(result.wheelchair_accessible)

    def test_combined_message_maps_to_recommender(self):
        result = extract_preferences(
            "Recommend a relaxing place in Putrajaya for my senior parents "
            "under RM20"
        )
        filters = to_recommendation_filters(result)

        self.assertEqual(filters["state"], "W.P. Putrajaya")
        self.assertEqual(filters["interest"], "relaxation")
        self.assertEqual(filters["maximum_fee"], 20.0)
        self.assertTrue(filters["elderly_friendly"])

    def test_unrelated_message_returns_no_preferences(self):
        result = extract_preferences("Hello, how are you?")
        self.assertEqual(result.to_dict(), {})

    def test_rejects_non_string_input(self):
        with self.assertRaises(TypeError):
            extract_preferences(None)


if __name__ == "__main__":
    unittest.main()
