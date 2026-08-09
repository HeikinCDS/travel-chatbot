from contextlib import closing
from pathlib import Path
import re
import sqlite3

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"

SEARCH_STOPWORDS = {
    "a", "about", "an", "and", "at", "be", "for", "i", "in", "is",
    "me", "my", "of", "on", "place", "places", "recommend", "show",
    "something", "that", "the", "to", "travel", "want", "with",
    "yang", "dan", "di", "mahu", "saya", "tempat", "untuk",
}


def rebuild_search_index(connection):
    """Rebuild the local FTS5 index after importing attraction records."""

    connection.execute("DROP TRIGGER IF EXISTS attractions_fts_insert")
    connection.execute("DROP TRIGGER IF EXISTS attractions_fts_delete")
    connection.execute("DROP TRIGGER IF EXISTS attractions_fts_update")
    connection.execute("DROP TABLE IF EXISTS attractions_fts")
    connection.execute("""
        CREATE VIRTUAL TABLE attractions_fts USING fts5(
            attraction_id UNINDEXED,
            attraction_name,
            short_description,
            primary_category,
            interests_tags,
            city_district,
            state_territory,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    connection.execute("""
        INSERT INTO attractions_fts (
            attraction_id,
            attraction_name,
            short_description,
            primary_category,
            interests_tags,
            city_district,
            state_territory
        )
        SELECT
            attraction_id,
            attraction_name,
            short_description,
            primary_category,
            interests_tags,
            city_district,
            state_territory
        FROM attractions
    """)
    connection.execute("""
        CREATE TRIGGER attractions_fts_insert AFTER INSERT ON attractions BEGIN
            INSERT INTO attractions_fts (
                attraction_id, attraction_name, short_description,
                primary_category, interests_tags, city_district, state_territory
            ) VALUES (
                new.attraction_id, new.attraction_name, new.short_description,
                new.primary_category, new.interests_tags, new.city_district,
                new.state_territory
            );
        END
    """)
    connection.execute("""
        CREATE TRIGGER attractions_fts_delete AFTER DELETE ON attractions BEGIN
            DELETE FROM attractions_fts
            WHERE attraction_id = old.attraction_id;
        END
    """)
    connection.execute("""
        CREATE TRIGGER attractions_fts_update AFTER UPDATE ON attractions BEGIN
            DELETE FROM attractions_fts
            WHERE attraction_id = old.attraction_id;
            INSERT INTO attractions_fts (
                attraction_id, attraction_name, short_description,
                primary_category, interests_tags, city_district, state_territory
            ) VALUES (
                new.attraction_id, new.attraction_name, new.short_description,
                new.primary_category, new.interests_tags, new.city_district,
                new.state_territory
            );
        END
    """)


def _ensure_search_index(connection):
    """Build FTS5 once and rebuild it after the attractions table is replaced."""

    table_exists = connection.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = 'attractions_fts'
    """).fetchone()
    trigger_count = connection.execute("""
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'trigger' AND name IN (
            'attractions_fts_insert',
            'attractions_fts_delete',
            'attractions_fts_update'
        )
    """).fetchone()[0]
    if table_exists and trigger_count == 3:
        return
    rebuild_search_index(connection)
    connection.commit()


def _search_expression(text):
    """Convert unrestricted user text into a safe FTS5 OR expression."""

    if not isinstance(text, str):
        return None
    tokens = []
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        if len(token) < 2 or token in SEARCH_STOPWORDS or token in tokens:
            continue
        tokens.append(token)
    return " OR ".join(f'"{token}"' for token in tokens[:20]) or None


def _rank_by_search(connection, attractions, query_text):
    """Put FTS5 matches first while preserving the existing fallback order."""

    expression = _search_expression(query_text)
    if not expression or not attractions:
        return attractions
    try:
        _ensure_search_index(connection)
        ranked_rows = connection.execute("""
            SELECT attraction_id
            FROM attractions_fts
            WHERE attractions_fts MATCH ?
            ORDER BY bm25(
                attractions_fts,
                0.0, 5.0, 2.0, 3.0, 4.0, 1.0, 1.0
            )
        """, (expression,)).fetchall()
    except sqlite3.OperationalError:
        # Existing databases continue working until the importer builds FTS5.
        return attractions

    rank_by_id = {
        str(row["attraction_id"]): rank
        for rank, row in enumerate(ranked_rows)
    }
    indexed = list(enumerate(attractions))
    indexed.sort(
        key=lambda pair: (
            0,
            rank_by_id[str(pair[1]["attraction_id"])],
        )
        if str(pair[1]["attraction_id"]) in rank_by_id
        else (1, pair[0])
    )
    return [attraction for _, attraction in indexed]


def recommend_attractions(
    state=None,
    interest=None,
    maximum_fee=None,
    family_friendly=False,
    elderly_friendly=False,
    wheelchair_accessible=False,
    query_text=None,
    limit=5
):
    if limit < 1:
        return []
    conditions = []
    parameters = []

    if state:
        conditions.append("LOWER(state_territory) = LOWER(?)")
        parameters.append(state)

    if interest:
        conditions.append("""
            (
                LOWER(primary_category) LIKE LOWER(?)
                OR LOWER(interests_tags) LIKE LOWER(?)
            )
        """)
        search_term = f"%{interest}%"
        parameters.extend([search_term, search_term])

    if maximum_fee is not None:
        conditions.append(
            "COALESCE(min_fee_myr, 0) <= ?"
        )
        parameters.append(maximum_fee)

    if family_friendly:
        conditions.append(
            "LOWER(family_friendly) = 'yes'"
        )

    if elderly_friendly:
        conditions.append("""
            LOWER(elderly_friendly)
            IN ('yes', 'partial')
        """)

    if wheelchair_accessible:
        conditions.append("""
            LOWER(wheelchair_accessible)
            IN ('yes', 'partial')
        """)

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT
            attraction_id,
            attraction_name,
            state_territory,
            city_district,
            primary_category,
            interests_tags,
            short_description,
            entrance_fee_status,
            min_fee_myr,
            max_fee_myr,
            recommended_duration_hours,
            family_friendly,
            elderly_friendly,
            wheelchair_accessible,
            accessibility_notes,
            official_url,
            source_url,
            date_verified,
            verification_status
        FROM attractions
        {where_clause}
        ORDER BY completeness DESC, attraction_name ASC
        LIMIT ?
    """

    parameters.append(max(limit * 10, 200))

    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            query,
            parameters
        ).fetchall()
        results = [dict(result) for result in rows]
        results = _rank_by_search(connection, results, query_text)

    return results[:limit]


def recommend_from_text(text, limit=5):
    """Extract preferences from a message and return matching attractions."""
    from nlp.entity_extractor import extract_preferences, to_recommendation_filters

    preferences = extract_preferences(text)
    filters = to_recommendation_filters(preferences)
    recommendations = recommend_attractions(
        **filters,
        query_text=text,
        limit=limit,
    )
    return {
        "preferences": preferences.to_dict(),
        "recommendations": recommendations,
    }


def get_attraction_by_id(attraction_id):
    """Return one attraction for information requests, or ``None``."""
    if not isinstance(attraction_id, str) or not attraction_id.strip():
        raise ValueError("attraction_id must be a non-empty string")

    query = """
        SELECT
            attraction_id,
            attraction_name,
            state_territory,
            city_district,
            primary_category,
            interests_tags,
            short_description,
            entrance_fee_status,
            min_fee_myr,
            max_fee_myr,
            recommended_duration_hours,
            family_friendly,
            elderly_friendly,
            wheelchair_accessible,
            accessibility_notes,
            official_url,
            source_url
        FROM attractions
        WHERE attraction_id = ?
    """

    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        result = connection.execute(query, (attraction_id,)).fetchone()

    return dict(result) if result else None


if __name__ == "__main__":
    recommendations = recommend_attractions(
        state="W.P. Putrajaya",
        interest="nature",
        maximum_fee=20,
        family_friendly=True
    )

    for attraction in recommendations:
        print()
        print(attraction["attraction_name"])
        print(attraction["state_territory"])
        print(attraction["short_description"])
