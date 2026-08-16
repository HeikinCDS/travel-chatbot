from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from recommendation_engine import recommendation_engine as engine
from recommendation_engine.recommendation_engine import (
    _accessibility_score,
    recommend_attractions,
    recommend_from_text,
)


class RecommendationEngineTests(unittest.TestCase):

    def test_penang_elderly_pilot_ranks_source_supported_places(self):
        minimal_walking = recommend_attractions(
            state="Penang",
            interest="relaxation",
            elderly_friendly=True,
            accessibility_needs=("low_walking",),
            limit=3,
        )
        accessible_toilet = recommend_attractions(
            state="Penang",
            interest="wildlife",
            elderly_friendly=True,
            accessibility_needs=("accessible_toilet",),
            limit=3,
        )
        nearby_seats = recommend_attractions(
            state="Penang",
            interest="wildlife",
            elderly_friendly=True,
            accessibility_needs=("seating",),
            limit=3,
        )

        self.assertEqual(minimal_walking[0]["attraction_name"], "Penang Hill")
        self.assertEqual(
            accessible_toilet[0]["attraction_name"],
            "Entopia by Penang Butterfly Farm",
        )
        self.assertEqual(nearby_seats[0]["attraction_name"], "Penang Bird Park")

    def test_elderly_requests_exclude_places_without_accessibility_evidence(self):
        general_results = recommend_attractions(
            state="Penang",
            interest="nature",
            limit=50,
        )
        elderly_results = recommend_attractions(
            state="Penang",
            interest="nature",
            elderly_friendly=True,
            limit=50,
        )

        general_names = {
            attraction["attraction_name"] for attraction in general_results
        }
        elderly_names = {
            attraction["attraction_name"] for attraction in elderly_results
        }
        self.assertIn("Penang National Park", general_names)
        self.assertNotIn("Penang National Park", elderly_names)
        self.assertIn("Bukit Panchor State Park", elderly_names)

    def test_specific_elderly_needs_improve_accessibility_ranking(self):
        easier = {
            "walking_difficulty": "Low",
            "step_free_access": "Yes",
            "resting_seats_available": "Yes",
            "accessible_toilet": "Yes",
            "parking_proximity": "Near",
            "shelter_available": "Partial",
            "elderly_suitability": "Suitable",
        }
        difficult = {
            "walking_difficulty": "High",
            "step_free_access": "No",
            "resting_seats_available": "No",
            "accessible_toilet": "Unknown",
            "parking_proximity": "Far",
            "shelter_available": "No",
            "elderly_suitability": "Not recommended",
        }
        needs = (
            "low_walking", "step_free", "seating", "accessible_toilet",
            "nearby_parking", "shelter",
        )

        self.assertGreater(
            _accessibility_score(easier, accessibility_needs=needs),
            _accessibility_score(difficult, accessibility_needs=needs),
        )

    def test_fts_ranks_matching_description_after_hard_filters(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "search.db"
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("""
                    CREATE TABLE attractions (
                        attraction_id TEXT,
                        attraction_name TEXT,
                        state_territory TEXT,
                        city_district TEXT,
                        primary_category TEXT,
                        interests_tags TEXT,
                        short_description TEXT,
                        entrance_fee_status TEXT,
                        min_fee_myr REAL,
                        max_fee_myr REAL,
                        recommended_duration_hours REAL,
                        family_friendly TEXT,
                        elderly_friendly TEXT,
                        wheelchair_accessible TEXT,
                        accessibility_notes TEXT,
                        walking_difficulty TEXT,
                        step_free_access TEXT,
                        resting_seats_available TEXT,
                        accessible_toilet TEXT,
                        parking_proximity TEXT,
                        shelter_available TEXT,
                        elderly_suitability TEXT,
                        elderly_accessibility_notes TEXT,
                        official_url TEXT,
                        source_url TEXT,
                        date_verified TEXT,
                        verification_status TEXT,
                        completeness REAL
                    )
                """)
                rows = [
                    (
                        "PEN-ACTIVE", "Active Forest", "Penang", "Balik Pulau",
                        "Nature", "nature, hiking", "A challenging uphill trail.",
                    ),
                    (
                        "PEN-CALM", "Calm Garden", "Penang", "George Town",
                        "Nature", "nature, relaxation", "A quiet peaceful garden.",
                    ),
                    (
                        "JOH-CALM", "Johor Quiet Park", "Johor", "Johor Bahru",
                        "Nature", "nature, relaxation", "A quiet peaceful park.",
                    ),
                ]
                for row in rows:
                    connection.execute("""
                        INSERT INTO attractions (
                            attraction_id, attraction_name, state_territory,
                            city_district, primary_category, interests_tags,
                            short_description, entrance_fee_status,
                            family_friendly, elderly_friendly,
                            wheelchair_accessible, completeness
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Unknown', 'Yes',
                                  'Partial', 'Unknown', 90)
                    """, row)
                connection.commit()

            with patch.object(engine, "DATABASE_PATH", database_path):
                results = engine.recommend_attractions(
                    state="Penang",
                    interest="nature",
                    query_text="somewhere quiet and peaceful!",
                    limit=2,
                )

                class FakeSemanticRanker:
                    def scores(self, connection, attractions, query_text):
                        return {
                            "PEN-CALM": 0.95,
                            "PEN-ACTIVE": 0.10,
                            "JOH-CALM": 0.99,
                        }

                semantic_results = engine.recommend_attractions(
                    state="Penang",
                    interest="nature",
                    query_text="somewhere soothing",
                    semantic_ranker=FakeSemanticRanker(),
                    limit=2,
                )

                class ForbiddenSemanticRanker:
                    def scores(self, connection, attractions, query_text):
                        raise AssertionError(
                            "Semantic search should be skipped for FTS matches"
                        )

                adaptive_results = engine.recommend_attractions(
                    state="Penang",
                    interest="nature",
                    query_text="somewhere quiet and peaceful!",
                    semantic_ranker=ForbiddenSemanticRanker(),
                    semantic_mode="adaptive",
                    limit=2,
                )

            with closing(sqlite3.connect(database_path)) as connection:
                indexed = connection.execute(
                    "SELECT COUNT(*) FROM attractions_fts"
                ).fetchone()[0]
                triggers = connection.execute("""
                    SELECT COUNT(*) FROM sqlite_master
                    WHERE type = 'trigger' AND name LIKE 'attractions_fts_%'
                """).fetchone()[0]

            self.assertEqual(
                [item["attraction_id"] for item in results],
                ["PEN-CALM", "PEN-ACTIVE"],
            )
            self.assertEqual(
                [item["attraction_id"] for item in semantic_results],
                ["PEN-CALM", "PEN-ACTIVE"],
            )
            self.assertEqual(
                [item["attraction_id"] for item in adaptive_results],
                ["PEN-CALM", "PEN-ACTIVE"],
            )
            self.assertEqual(indexed, 3)
            self.assertEqual(triggers, 3)

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
            self.assertNotEqual(
                attraction["wheelchair_accessible"].lower(),
                "no",
            )

    def test_elderly_friendly_filter(self):
        results = recommend_attractions(
            elderly_friendly=True,
            limit=50
        )

        self.assertGreater(len(results), 0)

        for attraction in results:
            self.assertNotEqual(
                attraction["elderly_friendly"].lower(),
                "no",
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
                ["yes", "partial", "unknown"]
            )


if __name__ == "__main__":
    unittest.main()
