from pathlib import Path
import sqlite3

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"

with sqlite3.connect(DATABASE_PATH) as connection:
    connection.row_factory = sqlite3.Row

    count = connection.execute(
        "SELECT COUNT(*) AS total FROM attractions"
    ).fetchone()

    print("Total attractions:", count["total"])

    attractions = connection.execute("""
        SELECT
            attraction_id,
            attraction_name,
            state_territory,
            primary_category
        FROM attractions
        LIMIT 5
    """).fetchall()

    for attraction in attractions:
        print(dict(attraction))