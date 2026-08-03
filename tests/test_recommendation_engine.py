import unittest

from recommendation_engine.recommendation_engine import (
    recommend_attractions,
    recommend_from_text,
)


class RecommendationEngineTests(unittest.TestCase):

    def test_state_filter(self):
        results = recommend_attractions(
            state="W.P. Putrajaya",
            limit=50
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            self.assertEqual(
                attraction["state_territory"],
                "W.P. Putrajaya"
            )

    def test_interest_filter(self):
        results = recommend_attractions(
            interest="beach",
            limit=50
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            searchable_text = (
                attraction["primary_category"] + " "
                + attraction["interests_tags"]
            ).lower()

            self.assertIn("beach", searchable_text)

    def test_maximum_fee_filter(self):
        results = recommend_attractions(
            maximum_fee=10,
            limit=50
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            minimum_fee = attraction["min_fee_myr"] or 0
            self.assertLessEqual(minimum_fee, 10)

    def test_family_friendly_filter(self):
        results = recommend_attractions(
            family_friendly=True,
            limit=50
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            self.assertEqual(
                attraction["family_friendly"].lower(),
                "yes"
            )

    def test_wheelchair_filter(self):
        results = recommend_attractions(
            wheelchair_accessible=True,
            limit=50
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            self.assertIn(
                attraction["wheelchair_accessible"].lower(),
                ["yes", "partial"]
            )

    def test_elderly_friendly_filter(self):
        results = recommend_attractions(
            elderly_friendly=True,
            limit=50
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            self.assertIn(
                attraction["elderly_friendly"].lower(),
                ["yes", "partial"]
            )

    def test_result_limit(self):
        results = recommend_attractions(limit=3)

        self.assertLessEqual(len(results), 3)

    def test_unknown_state(self):
        results = recommend_attractions(
            state="Unknown State"
        )

        self.assertEqual(results, [])

    def test_combined_preferences(self):
        results = recommend_attractions(
            state="W.P. Putrajaya",
            interest="nature",
            maximum_fee=20,
            family_friendly=True,
            limit=5
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            self.assertEqual(
                attraction["state_territory"],
                "W.P. Putrajaya"
            )

            self.assertEqual(
                attraction["family_friendly"].lower(),
                "yes"
            )

    def test_recommend_from_natural_language(self):
        result = recommend_from_text(
            "Find a nature place in Putrajaya for my elderly parents"
        )

        self.assertEqual(
            result["preferences"]["state"],
            "W.P. Putrajaya"
        )
        self.assertTrue(
            result["preferences"]["elderly_friendly"]
        )
        self.assertGreater(len(result["recommendations"]), 0)

        for attraction in result["recommendations"]:
            self.assertEqual(
                attraction["state_territory"],
                "W.P. Putrajaya"
            )
            self.assertIn(
                attraction["elderly_friendly"].lower(),
                ["yes", "partial"]
            )


if __name__ == "__main__":
    unittest.main()
