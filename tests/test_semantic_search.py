from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np

from recommendation_engine.semantic_search import SemanticRanker


class FakeEmbeddingModel:
    def encode(self, texts, **kwargs):
        vectors = []
        for text in texts:
            normalised = str(text).casefold()
            if any(word in normalised for word in ("calm", "quiet", "peaceful")):
                vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            elif any(word in normalised for word in ("active", "challenging")):
                vector = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            else:
                vector = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            vectors.append(vector)
        return np.asarray(vectors, dtype=np.float32)


class SemanticSearchTests(unittest.TestCase):
    def create_database(self, database_path):
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute("""
                CREATE TABLE attractions (
                    attraction_id TEXT PRIMARY KEY,
                    attraction_name TEXT,
                    primary_category TEXT,
                    interests_tags TEXT,
                    short_description TEXT,
                    city_district TEXT,
                    state_territory TEXT,
                    accessibility_notes TEXT
                )
            """)
            connection.executemany("""
                INSERT INTO attractions VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    "CALM", "Calm Garden", "Nature", "garden, relaxation",
                    "A quiet and peaceful garden.", "George Town", "Penang",
                    "Level paths are recorded.",
                ),
                (
                    "ACTIVE", "Active Forest", "Nature", "hiking, adventure",
                    "A challenging uphill trail.", "Balik Pulau", "Penang",
                    "Steep sections are recorded.",
                ),
            ])
            connection.commit()

    def test_builds_cached_vectors_and_scores_semantic_similarity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "semantic.db"
            self.create_database(database_path)
            ranker = SemanticRanker(
                model_name="test-model",
                model_loader=lambda name, local_only: FakeEmbeddingModel(),
            )

            with closing(sqlite3.connect(database_path)) as connection:
                count = ranker.rebuild_index(
                    connection,
                    allow_download=False,
                )
                connection.row_factory = sqlite3.Row
                attractions = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM attractions ORDER BY attraction_id"
                    )
                ]
                scores = ranker.scores(
                    connection,
                    attractions,
                    "somewhere calm for resting",
                )

            self.assertEqual(count, 2)
            self.assertGreater(scores["CALM"], scores["ACTIVE"])

    def test_ignores_embedding_when_source_content_has_changed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "semantic.db"
            self.create_database(database_path)
            ranker = SemanticRanker(
                model_name="test-model",
                model_loader=lambda name, local_only: FakeEmbeddingModel(),
            )

            with closing(sqlite3.connect(database_path)) as connection:
                ranker.rebuild_index(connection, allow_download=False)
                connection.execute("""
                    UPDATE attractions
                    SET short_description = 'The description was updated.'
                    WHERE attraction_id = 'CALM'
                """)
                connection.commit()
                connection.row_factory = sqlite3.Row
                attractions = [
                    dict(row)
                    for row in connection.execute("SELECT * FROM attractions")
                ]
                scores = ranker.scores(connection, attractions, "calm")

            self.assertNotIn("CALM", scores)
            self.assertIn("ACTIVE", scores)


if __name__ == "__main__":
    unittest.main()
