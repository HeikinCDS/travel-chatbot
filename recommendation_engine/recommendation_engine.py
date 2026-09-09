from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3

from recommendation_engine.semantic_search import SemanticRanker

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"

SEARCH_STOPWORDS = {
    "a", "about", "an", "and", "at", "be", "for", "i", "in", "is",
    "me", "my", "of", "on", "place", "places", "recommend", "show",
    "something", "that", "the", "to", "travel", "want", "with",
    "yang", "dan", "di", "mahu", "saya", "tempat", "untuk",
    "johor", "kedah", "kelantan", "melaka", "malacca", "sembilan",
    "pahang", "penang", "perak", "perlis", "sabah", "sarawak",
    "selangor", "terengganu", "kuala", "lumpur", "labuan", "putrajaya",
    "malaysia", "malaysian",
}

_SEMANTIC_RANKER = None


def _environment_flag(name, *, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _semantic_ranker():
    global _SEMANTIC_RANKER
    if _SEMANTIC_RANKER is None:
        _SEMANTIC_RANKER = SemanticRanker()
    return _SEMANTIC_RANKER


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


def _search_expression(text, ignored_terms=()):
    """Convert unrestricted user text into a safe FTS5 OR expression."""

    if not isinstance(text, str):
        return None
    ignored_tokens = {
        token
        for term in ignored_terms
        if term
        for token in re.findall(r"[a-z0-9]+", str(term).casefold())
    }
    tokens = []
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        if (
            len(token) < 2
            or token in SEARCH_STOPWORDS
            or token in ignored_tokens
            or token in tokens
        ):
            continue
        tokens.append(token)
    return " OR ".join(f'"{token}"' for token in tokens[:20]) or None


def _rank_by_search(
    connection,
    attractions,
    query_text,
    semantic_ranker=None,
    semantic_mode=None,
    ignored_terms=(),
):
    """Blend exact FTS5 relevance with optional semantic similarity."""

    expression = _search_expression(query_text, ignored_terms)
    if not attractions:
        return attractions
    rank_by_id = {}
    try:
        if expression:
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
            rank_by_id = {
                str(row["attraction_id"]): rank
                for rank, row in enumerate(ranked_rows)
            }
    except sqlite3.OperationalError:
        # Existing databases continue working until the importer builds FTS5.
        rank_by_id = {}

    semantic_scores = {}
    ranker = semantic_ranker
    configured_mode = str(
        semantic_mode
        or os.getenv("SEMANTIC_SEARCH_MODE", "adaptive")
    ).strip().casefold()
    if configured_mode not in {"off", "adaptive", "always"}:
        configured_mode = "adaptive"
    if (
        ranker is None
        and not _environment_flag("ENABLE_SEMANTIC_SEARCH", default=True)
    ):
        configured_mode = "off"
    if ranker is False:
        configured_mode = "off"

    candidate_ids = {
        str(attraction["attraction_id"])
        for attraction in attractions
    }
    has_candidate_fts_match = any(
        attraction_id in candidate_ids
        for attraction_id in rank_by_id
    )
    should_use_semantic = configured_mode == "always" or (
        configured_mode == "adaptive"
        and expression is not None
        and not has_candidate_fts_match
    )
    if should_use_semantic:
        ranker = ranker or _semantic_ranker()
        try:
            semantic_scores = ranker.scores(
                connection,
                attractions,
                query_text,
            )
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            sqlite3.Error,
        ):
            semantic_scores = {}

    if not rank_by_id and not semantic_scores:
        return attractions
    indexed = list(enumerate(attractions))

    def combined_score(attraction):
        attraction_id = str(attraction["attraction_id"])
        fts_rank = rank_by_id.get(attraction_id)
        fts_score = 1.0 / (1.0 + fts_rank) if fts_rank is not None else 0.0
        semantic_score = max(
            0.0,
            min(1.0, semantic_scores.get(attraction_id, 0.0)),
        )
        if semantic_scores and rank_by_id:
            return 0.45 * fts_score + 0.55 * semantic_score
        return semantic_score if semantic_scores else fts_score

    indexed.sort(
        key=lambda pair: (
            -combined_score(pair[1]),
            pair[0],
        )
    )
    return [attraction for _, attraction in indexed]


def _accessibility_score(
    attraction,
    *,
    elderly_friendly=False,
    wheelchair_accessible=False,
    accessibility_needs=(),
):
    values = {"yes": 2, "partial": 1}
    score = 0
    if elderly_friendly or wheelchair_accessible or accessibility_needs:
        eligibility = str(
            attraction.get("elderly_recommendation_eligibility") or ""
        ).strip().casefold()
        if eligibility == "eligible":
            # Prefer reviewed records, while still allowing the complete
            # catalogue to provide options in under-researched states.
            score += 6
    if elderly_friendly:
        score += values.get(
            str(attraction.get("elderly_friendly") or "").casefold(),
            0,
        )
    if wheelchair_accessible:
        score += values.get(
            str(attraction.get("wheelchair_accessible") or "").casefold(),
            0,
        )
    needs = set(accessibility_needs or ())
    if "low_walking" in needs:
        score += {
            "low": 4, "moderate": 1, "high": -4,
        }.get(str(attraction.get("walking_difficulty") or "").casefold(), 0)
    if "step_free" in needs:
        score += {
            "yes": 4, "partial": 1, "no": -4,
        }.get(str(attraction.get("step_free_access") or "").casefold(), 0)
    if "seating" in needs:
        score += {
            "yes": 3, "partial": 1, "no": -3,
        }.get(str(attraction.get("resting_seats_available") or "").casefold(), 0)
    if "accessible_toilet" in needs:
        score += {
            "yes": 3, "partial": 1, "no": -3,
        }.get(str(attraction.get("accessible_toilet") or "").casefold(), 0)
    if "nearby_parking" in needs:
        score += {
            "near": 3, "moderate": 1, "far": -3,
        }.get(str(attraction.get("parking_proximity") or "").casefold(), 0)
    if "shelter" in needs:
        score += {
            "yes": 2, "partial": 1, "no": -2,
        }.get(str(attraction.get("shelter_available") or "").casefold(), 0)
    if needs:
        score += {
            "suitable": 3,
            "suitable with assistance": 1,
            "not recommended": -4,
        }.get(str(attraction.get("elderly_suitability") or "").casefold(), 0)
    return score


def _accessibility_need_match_count(attraction, accessibility_needs=()):
    """Count requested needs supported by a positive or partial record."""

    needs = set(accessibility_needs or ())
    checks = {
        "wheelchair": str(
            attraction.get("wheelchair_accessible") or ""
        ).casefold() in {"yes", "partial"},
        "low_walking": str(
            attraction.get("walking_difficulty") or ""
        ).casefold() == "low",
        "step_free": str(
            attraction.get("step_free_access") or ""
        ).casefold() in {"yes", "partial"},
        "seating": str(
            attraction.get("resting_seats_available") or ""
        ).casefold() in {"yes", "partial"},
        "accessible_toilet": str(
            attraction.get("accessible_toilet") or ""
        ).casefold() in {"yes", "partial"},
        "nearby_parking": str(
            attraction.get("parking_proximity") or ""
        ).casefold() in {"near", "moderate"},
        "shelter": str(
            attraction.get("shelter_available") or ""
        ).casefold() in {"yes", "partial"},
    }
    return sum(bool(checks.get(need)) for need in needs)


def recommend_attractions(
    state=None,
    interest=None,
    maximum_fee=None,
    family_friendly=False,
    elderly_friendly=False,
    wheelchair_accessible=False,
    accessibility_needs=(),
    query_text=None,
    semantic_ranker=None,
    semantic_mode=None,
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

    accessibility_requested = bool(
        elderly_friendly or wheelchair_accessible or accessibility_needs
    )
    requested_accessibility_needs = tuple(dict.fromkeys(
        tuple(accessibility_needs or ())
        + (("wheelchair",) if wheelchair_accessible else ())
    ))

    if accessibility_requested:
        conditions.append("""
            LOWER(COALESCE(elderly_recommendation_eligibility, ''))
            = 'eligible'
        """)

    if elderly_friendly:
        conditions.append("""
            LOWER(COALESCE(NULLIF(TRIM(elderly_friendly), ''), 'unknown'))
            IN ('yes', 'partial')
        """)

    if wheelchair_accessible and len(requested_accessibility_needs) == 1:
        conditions.append("""
            LOWER(COALESCE(NULLIF(TRIM(wheelchair_accessible), ''), 'unknown'))
            IN ('yes', 'partial')
        """)

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT
            attraction_id,
            attraction_name,
            canonical_id,
            record_relationship,
            related_site_id,
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
            walking_difficulty,
            step_free_access,
            resting_seats_available,
            accessible_toilet,
            parking_proximity,
            shelter_available,
            elderly_suitability,
            elderly_accessibility_notes,
            elderly_recommendation_eligibility,
            accessibility_evidence_source,
            accessibility_screening_notes,
            documented_accessibility_features,
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
        if len(requested_accessibility_needs) > 1:
            # Multiple needs are alternatives, not an all-or-nothing filter.
            # Keep places with at least one recorded match, then let the score
            # rank places satisfying more of the requested needs first.
            results = [
                attraction
                for attraction in results
                if _accessibility_need_match_count(
                    attraction,
                    requested_accessibility_needs,
                )
                > 0
            ]
        results = _rank_by_search(
            connection,
            results,
            query_text,
            semantic_ranker=semantic_ranker,
            semantic_mode=semantic_mode,
            ignored_terms=(state, interest),
        )

    if elderly_friendly or wheelchair_accessible or accessibility_needs:
        results.sort(
            key=lambda attraction: (
                _accessibility_need_match_count(
                    attraction,
                    requested_accessibility_needs,
                ),
                _accessibility_score(
                    attraction,
                    elderly_friendly=elderly_friendly,
                    wheelchair_accessible=wheelchair_accessible,
                    accessibility_needs=accessibility_needs,
                ),
            ),
            reverse=True,
        )

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
            canonical_id,
            record_relationship,
            related_site_id,
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
            walking_difficulty,
            step_free_access,
            resting_seats_available,
            accessible_toilet,
            parking_proximity,
            shelter_available,
            elderly_suitability,
            elderly_accessibility_notes,
            elderly_recommendation_eligibility,
            accessibility_evidence_source,
            accessibility_screening_notes,
            documented_accessibility_features,
            official_url,
            source_url
        FROM attractions
        WHERE attraction_id = ?
    """

    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        result = connection.execute(query, (attraction_id,)).fetchone()

    return dict(result) if result else None


def find_attraction_by_name_in_text(text):
    """Return the longest saved attraction name explicitly mentioned in text."""

    if not isinstance(text, str) or not text.strip():
        return None

    normalised_text = " " + re.sub(
        r"[^a-z0-9]+", " ", text.casefold()
    ).strip() + " "
    query = """
        SELECT
            attraction_id,
            attraction_name,
            canonical_id,
            record_relationship,
            related_site_id,
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
            walking_difficulty,
            step_free_access,
            resting_seats_available,
            accessible_toilet,
            parking_proximity,
            shelter_available,
            elderly_suitability,
            elderly_accessibility_notes,
            elderly_recommendation_eligibility,
            accessibility_evidence_source,
            accessibility_screening_notes,
            documented_accessibility_features,
            official_url,
            source_url
        FROM attractions
    """

    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query).fetchall()

    matches = []
    for row in rows:
        attraction = dict(row)
        normalised_name = re.sub(
            r"[^a-z0-9]+",
            " ",
            str(attraction["attraction_name"]).casefold(),
        ).strip()
        if normalised_name and f" {normalised_name} " in normalised_text:
            matches.append((len(normalised_name), attraction))

    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]


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
