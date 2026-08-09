"""Download the embedding model once and index curated attractions."""

from contextlib import closing
from pathlib import Path
import sqlite3
import sys


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from recommendation_engine.semantic_search import SemanticRanker


DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"


def main() -> None:
    ranker = SemanticRanker()
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        count = ranker.rebuild_index(connection, allow_download=True)
    print(f"Successfully indexed {count} attractions.")
    print(f"Embedding model: {ranker.model_name}")
    print(f"Database updated at: {DATABASE_PATH}")


if __name__ == "__main__":
    main()
