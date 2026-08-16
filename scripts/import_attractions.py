"""Import the confirmed JomVoyage catalogue into SQLite.

Existing attractions retain their richer fee, accessibility and coordinate
fields. Newly confirmed candidates are imported with explicit ``Unknown``
values where the master catalogue does not provide a verified fact.
"""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any

import pandas as pd

from recommendation_engine.recommendation_engine import rebuild_search_index


PROJECT_DIR = Path(__file__).resolve().parent.parent
MASTER_EXCEL_PATH = PROJECT_DIR / "data" / "Malaysia_Tourism_Master_Candidates.xlsx"
LEGACY_EXCEL_PATH = PROJECT_DIR / "data" / "FYP_Malaysia_Tourism_Dataset.xlsx"
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"

DATABASE_COLUMNS = [
    "attraction_id", "attraction_name", "state_territory", "city_district",
    "primary_category", "interests_tags", "indoor_outdoor",
    "short_description", "entrance_fee_status", "min_fee_myr",
    "max_fee_myr", "recommended_duration_hours", "suitable_travel_groups",
    "family_friendly", "elderly_friendly", "wheelchair_accessible",
    "accessibility_notes", "walking_difficulty", "step_free_access",
    "resting_seats_available", "accessible_toilet", "parking_proximity",
    "shelter_available", "elderly_suitability",
    "elderly_accessibility_notes", "latitude", "longitude", "official_url",
    "source_url", "date_verified", "verification_status", "completeness",
    "reviewer_notes", "candidate_id", "coverage_lens", "source_basis",
    "source_status", "state_tourism_guide_url", "origin_batch",
]

CONFIRMED_STATUSES = {"approved", "complete", "completed", "confirmed"}
APPLICATION_STATE_NAMES = {
    "W.P. Kuala Lumpur": "Kuala Lumpur",
}


def _normalise_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.copy()
    dataframe.columns = (
        dataframe.columns.astype(str).str.strip().str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")
    )
    return dataframe


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    result = str(value).strip()
    return result or None


def _date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _urls(value: Any) -> list[str]:
    return re.findall(r"https?://[^\s;]+", _text(value) or "")


def _first_direct_url(value: Any) -> str | None:
    return next(
        (url for url in _urls(value) if "google.com/maps" not in url.casefold()),
        None,
    )


def _known(value: Any) -> bool:
    text = (_text(value) or "").casefold()
    return bool(text and text not in {"unknown", "not verified", "n/a"})


def _completion_score(record: dict[str, Any]) -> float:
    fields = (
        "attraction_name", "state_territory", "city_district",
        "primary_category", "interests_tags", "short_description",
        "entrance_fee_status", "recommended_duration_hours",
        "elderly_friendly", "wheelchair_accessible", "latitude",
        "official_url",
    )
    known = sum(_known(record.get(field)) for field in fields)
    return round(100 * known / len(fields), 1)


def load_legacy_attractions(path: Path = LEGACY_EXCEL_PATH) -> pd.DataFrame:
    dataframe = pd.read_excel(path, sheet_name="Attractions Entry", header=2)
    dataframe = dataframe.dropna(subset=["Attraction ID", "Attraction Name"])
    dataframe = _normalise_columns(dataframe)
    if "date_verified" in dataframe.columns:
        dataframe["date_verified"] = dataframe["date_verified"].map(_date)
    return dataframe


def load_master_candidates(path: Path = MASTER_EXCEL_PATH) -> pd.DataFrame:
    dataframe = pd.read_excel(path, sheet_name="Catalogue", header=2)
    dataframe = dataframe.dropna(subset=["Candidate ID", "Attraction Name"])
    return _normalise_columns(dataframe)


def build_attractions(
    master_candidates: pd.DataFrame,
    legacy_attractions: pd.DataFrame,
) -> pd.DataFrame:
    """Merge confirmed master candidates with detailed legacy records."""

    legacy_by_id = {
        str(row["attraction_id"]).strip(): row.to_dict()
        for _, row in legacy_attractions.iterrows()
        if _text(row.get("attraction_id"))
    }
    records = []

    for _, candidate in master_candidates.iterrows():
        status = (_text(candidate.get("review_status")) or "").casefold()
        if status not in CONFIRMED_STATUSES:
            continue

        candidate_id = _text(candidate.get("candidate_id"))
        existing_id = _text(candidate.get("existing_record_id"))
        attraction_id = existing_id or candidate_id
        if not attraction_id:
            continue

        record = {column: None for column in DATABASE_COLUMNS}
        if existing_id and existing_id in legacy_by_id:
            record.update(legacy_by_id[existing_id])

        source_text = candidate.get("discovery_source_link_s")
        all_urls = _urls(source_text)
        direct_url = _first_direct_url(source_text)
        tags = _text(candidate.get("interests_tags"))
        workbook_state = _text(candidate.get("state_territory"))
        record.update({
            "attraction_id": attraction_id,
            "attraction_name": _text(candidate.get("attraction_name")),
            "state_territory": APPLICATION_STATE_NAMES.get(
                workbook_state,
                workbook_state,
            ),
            "city_district": _text(candidate.get("city_district")),
            "primary_category": _text(candidate.get("primary_category")),
            "interests_tags": tags,
            "indoor_outdoor": _text(candidate.get("setting")) or "Unknown",
            "short_description": _text(candidate.get("candidate_description")),
            "official_url": direct_url or _text(record.get("official_url")),
            "source_url": direct_url or (all_urls[0] if all_urls else None)
            or _text(candidate.get("state_tourism_guide_url")),
            "date_verified": _date(candidate.get("date_added")),
            "verification_status": "Confirmed",
            "reviewer_notes": _text(candidate.get("reviewer_notes")),
            "candidate_id": candidate_id,
            "coverage_lens": _text(candidate.get("coverage_lens")),
            "source_basis": _text(candidate.get("source_basis")),
            "source_status": _text(candidate.get("source_status")),
            "state_tourism_guide_url": _text(candidate.get("state_tourism_guide_url")),
            "origin_batch": _text(candidate.get("origin_batch")),
        })

        defaults = {
            "entrance_fee_status": "Unknown",
            "suitable_travel_groups": "Unknown",
            "family_friendly": "Yes" if tags and "family" in tags.casefold() else "Unknown",
            "elderly_friendly": "Unknown",
            "wheelchair_accessible": "Unknown",
            "accessibility_notes": "Accessibility information has not been confirmed.",
            "walking_difficulty": "Unknown",
            "step_free_access": "Unknown",
            "resting_seats_available": "Unknown",
            "accessible_toilet": "Unknown",
            "parking_proximity": "Unknown",
            "shelter_available": "Unknown",
            "elderly_suitability": "Unknown",
            "elderly_accessibility_notes": None,
        }
        for field, default in defaults.items():
            candidate_value = candidate.get(field)
            if _known(candidate_value):
                record[field] = _text(candidate_value)
            elif not _known(record.get(field)):
                record[field] = default

        if not _known(record.get("completeness")):
            record["completeness"] = _completion_score(record)
        records.append(record)

    result = pd.DataFrame(records, columns=DATABASE_COLUMNS)
    if result.empty:
        raise ValueError("The master workbook contains no confirmed candidates.")
    duplicate_ids = result[result["attraction_id"].duplicated()]["attraction_id"].tolist()
    if duplicate_ids:
        raise ValueError(f"Duplicate attraction IDs: {duplicate_ids}")
    return result


def import_attractions(
    master_path: Path = MASTER_EXCEL_PATH,
    legacy_path: Path = LEGACY_EXCEL_PATH,
    database_path: Path = DATABASE_PATH,
) -> int:
    master = load_master_candidates(master_path)
    legacy = load_legacy_attractions(legacy_path)
    attractions = build_attractions(master, legacy)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        attractions.to_sql("attractions", connection, if_exists="replace", index=False)
        connection.execute("CREATE UNIQUE INDEX idx_attraction_id ON attractions(attraction_id)")
        connection.execute("CREATE INDEX idx_attraction_state ON attractions(state_territory)")
        connection.execute("CREATE INDEX idx_attraction_category ON attractions(primary_category)")
        connection.execute("DROP TABLE IF EXISTS attraction_embeddings")
        rebuild_search_index(connection)
        connection.commit()
    return len(attractions)


def main() -> None:
    count = import_attractions()
    print(f"Successfully imported {count} confirmed attractions.")
    print(f"Database created at: {DATABASE_PATH}")
    print("Rejected and incomplete candidates were not imported.")
    print("Run scripts/build_semantic_index.py before enabling semantic search.")


if __name__ == "__main__":
    main()
