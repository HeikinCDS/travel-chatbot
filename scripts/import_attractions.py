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
ACCESSIBILITY_EXCEL_PATH = (
    PROJECT_DIR / "data"
    / "Elderly_Friendly_Malaysia_Travel_Spots_Verified.xlsx"
)
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
    "elderly_recommendation_eligibility", "accessibility_evidence_source",
    "accessibility_screening_notes", "accessibility_screening_date",
]

CONFIRMED_STATUSES = {"approved", "complete", "completed", "confirmed"}
APPLICATION_STATE_NAMES = {
    "W.P. Kuala Lumpur": "Kuala Lumpur",
}
VERIFIED_ACCESSIBILITY_COLUMNS = {
    "spot_id",
    "attraction_name",
    "evidence_tier",
    "elderly_suitability",
    "documented_likely_accessibility_features",
    "elderly_accessibility_notes",
    "why_it_qualifies",
    "evidence_source_s",
    "more_info_link_s",
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


def load_verified_accessibility(
    path: Path = ACCESSIBILITY_EXCEL_PATH,
) -> pd.DataFrame:
    """Load and validate the curated elderly-accessibility overlay."""

    dataframe = pd.read_excel(path, sheet_name="Elderly-Friendly Spots")
    dataframe = dataframe.dropna(subset=["Spot ID", "Attraction Name"])
    dataframe = _normalise_columns(dataframe)
    missing = VERIFIED_ACCESSIBILITY_COLUMNS - set(dataframe.columns)
    if missing:
        raise ValueError(
            "The accessibility workbook is missing columns: "
            + ", ".join(sorted(missing))
        )
    duplicate_ids = dataframe[
        dataframe["spot_id"].astype(str).str.strip().duplicated()
    ]["spot_id"].tolist()
    if duplicate_ids:
        raise ValueError(f"Duplicate accessibility Spot IDs: {duplicate_ids}")
    unverified = dataframe[
        dataframe["evidence_tier"].astype(str).str.strip().str.casefold()
        != "verified"
    ]
    if not unverified.empty:
        raise ValueError(
            "Every accessibility overlay row must have Evidence Tier "
            f"'Verified': {unverified['spot_id'].tolist()}"
        )
    return dataframe


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _structured_accessibility(
    feature_text: str | None,
    suitability: str | None,
) -> dict[str, str]:
    """Conservatively derive filter fields from the curated feature summary."""

    features = (feature_text or "").strip()
    folded = features.casefold()
    suitability_value = (suitability or "").strip()
    elderly_friendly = {
        "suitable": "Yes",
        "suitable with assistance": "Partial",
        "not recommended": "No",
    }.get(suitability_value.casefold(), "Unknown")

    walking_match = re.search(
        r"walking difficulty:\s*(low|moderate|high)",
        features,
        flags=re.IGNORECASE,
    )
    walking = walking_match.group(1).title() if walking_match else "Unknown"

    wheelchair = "Unknown"
    if "wheelchair" in folded:
        if _contains_any(folded, (
            r"wheelchair[^;.]*(?:not documented|not confirmed)",
            r"not wheelchair[- ]accessible",
            r"no wheelchair access",
        )):
            wheelchair = "Unknown"
        elif _contains_any(folded, (
            r"partial",
            r"ground floor only",
            r"selected areas",
            r"upper floor[^;.]*(?:not|no )",
            r"broader .* not",
        )):
            wheelchair = "Partial"
        elif _contains_any(folded, (
            r"wheelchair[- ]accessible",
            r"wheelchair access",
            r"wheelchair friendly",
            r"wheelchair provision",
            r"wheelchair rental",
        )):
            wheelchair = "Yes"

    if re.search(r"step-free access\s*\(partial\)", folded):
        step_free = "Partial"
    elif _contains_any(folded, (
        r"no step-free route",
        r"step-free[^;.]*(?:not documented|not confirmed)",
    )):
        step_free = "No" if "no step-free route" in folded else "Unknown"
    elif _contains_any(folded, (
        r"step-free access",
        r"step-free (?:flat )?(?:wooden )?(?:walkway|boardwalk|route)",
        r"fully step-free",
        r"flat,? step-free",
    )):
        step_free = "Yes"
    else:
        step_free = "Unknown"

    if re.search(r"shelter available\s*\(partial\)", folded):
        shelter = "Partial"
    elif _contains_any(folded, (
        r"shelter available",
        r"rest huts?",
        r"covered rest",
    )):
        shelter = "Yes"
    else:
        shelter = "Unknown"

    seating = "Yes" if _contains_any(folded, (
        r"resting seats?",
        r"seating(?:/rest)? areas?",
        r"rest areas?",
        r"benches",
        r"rest huts?",
    )) else "Unknown"

    toilet_negative = _contains_any(folded, (
        r"accessible[- ]toilet[^;.]*(?:not documented|not confirmed)",
        r"accessible[- ]restroom[^;.]*(?:not documented|not confirmed)",
        r"no accessible (?:toilet|restroom)",
    ))
    toilet = "Unknown"
    if not toilet_negative and _contains_any(folded, (
        r"accessible toilet",
        r"accessible restroom",
        r"pwd washroom",
        r"oku toilet",
    )):
        toilet = "Yes"

    if _contains_any(folded, (
        r"parking proximity:\s*near",
        r"designated accessible parking",
        r"accessible parking",
        r"oku parking",
        r"nearby drop-off",
    )):
        parking = "Near"
    elif "parking" in folded:
        parking = "Moderate"
    else:
        parking = "Unknown"

    return {
        "elderly_friendly": elderly_friendly,
        "wheelchair_accessible": wheelchair,
        "walking_difficulty": walking,
        "step_free_access": step_free,
        "resting_seats_available": seating,
        "accessible_toilet": toilet,
        "parking_proximity": parking,
        "shelter_available": shelter,
        "elderly_suitability": suitability_value or "Unknown",
    }


def _apply_accessibility_overlay(
    record: dict[str, Any],
    accessibility: dict[str, Any],
) -> None:
    features = _text(
        accessibility.get("documented_likely_accessibility_features")
    )
    notes = _text(accessibility.get("elderly_accessibility_notes"))
    suitability = _text(accessibility.get("elderly_suitability"))
    structured_text = "; ".join(
        value for value in (features, notes) if value
    )
    record.update(_structured_accessibility(structured_text, suitability))
    record.update({
        "elderly_recommendation_eligibility": "Eligible",
        "accessibility_notes": notes,
        "elderly_accessibility_notes": notes,
        "accessibility_evidence_source": _text(
            accessibility.get("evidence_source_s")
        ),
        "accessibility_screening_notes": _text(
            accessibility.get("why_it_qualifies")
        ),
    })
    info_url = _first_direct_url(accessibility.get("more_info_link_s"))
    if info_url:
        record["official_url"] = info_url
        record["source_url"] = info_url


def build_attractions(
    master_candidates: pd.DataFrame,
    legacy_attractions: pd.DataFrame,
    accessibility_records: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge confirmed master candidates with detailed legacy records."""

    legacy_by_id = {
        str(row["attraction_id"]).strip(): row.to_dict()
        for _, row in legacy_attractions.iterrows()
        if _text(row.get("attraction_id"))
    }
    accessibility_by_id = {}
    if accessibility_records is not None:
        accessibility_by_id = {
            str(row["spot_id"]).strip(): row.to_dict()
            for _, row in accessibility_records.iterrows()
            if _text(row.get("spot_id"))
        }

    records = []
    for _, candidate in master_candidates.iterrows():
        status = (_text(candidate.get("review_status")) or "").casefold()
        if status not in CONFIRMED_STATUSES:
            continue

        eligibility = (
            "General only" if accessibility_records is not None else _text(
                candidate.get("elderly_recommendation_eligibility")
            )
        )
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
            "elderly_recommendation_eligibility": eligibility or "Not screened",
            "accessibility_evidence_source": _text(
                candidate.get("accessibility_evidence_source")
            ),
            "accessibility_screening_notes": _text(
                candidate.get("accessibility_screening_notes")
            ),
            "accessibility_screening_date": _date(
                candidate.get("accessibility_screening_date")
            ),
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

        accessibility = accessibility_by_id.get(candidate_id or "")
        if accessibility:
            _apply_accessibility_overlay(record, accessibility)

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
    accessibility_path: Path = ACCESSIBILITY_EXCEL_PATH,
    database_path: Path = DATABASE_PATH,
) -> int:
    master = load_master_candidates(master_path)
    legacy = load_legacy_attractions(legacy_path)
    accessibility = load_verified_accessibility(accessibility_path)
    attractions = build_attractions(master, legacy, accessibility)

    missing_ids = sorted(
        set(accessibility["spot_id"].astype(str).str.strip())
        - set(attractions["candidate_id"].dropna().astype(str).str.strip())
    )
    if missing_ids:
        raise ValueError(
            "Accessibility Spot IDs are absent from the confirmed catalogue: "
            + ", ".join(missing_ids)
        )

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
    print("All confirmed attractions remain available for general travel searches.")
    print("Elderly and accessibility requests use the 66-record verified overlay.")
    print("Run scripts/build_semantic_index.py before enabling semantic search.")


if __name__ == "__main__":
    main()
