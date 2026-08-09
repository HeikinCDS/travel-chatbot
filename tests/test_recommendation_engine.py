from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from recommendation_engine import recommendation_engine as engine
from recommendation_engine.recommendation_engine import (
    recommend_attractions,
    recommend_from_text,
)


class RecommendationEngineTests(unittest.TestCase):

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
