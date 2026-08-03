from pathlib import Path
import sqlite3

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"


def recommend_attractions(
    state=None,
    interest=None,
    maximum_fee=None,
    family_friendly=False,
    elderly_friendly=False,
    wheelchair_accessible=False,
    limit=5
):
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
            wheelchair_accessible
        FROM attractions
        {where_clause}
        ORDER BY completeness DESC, attraction_name ASC
        LIMIT ?
    """

    parameters.append(limit)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row

        results = connection.execute(
            query,
            parameters
        ).fetchall()

    return [dict(result) for result in results]


def recommend_from_text(text, limit=5):
    """Extract preferences from a message and return matching attractions."""
    from nlp.entity_extractor import extract_preferences, to_recommendation_filters

    preferences = extract_preferences(text)
    filters = to_recommendation_filters(preferences)
    recommendations = recommend_attractions(**filters, limit=limit)
    return {
        "preferences": preferences.to_dict(),
        "recommendations": recommendations,
    }


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
