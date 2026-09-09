"""Import the confirmed JomVoyage catalogue into SQLite.

Existing attractions retain their richer fee, accessibility and coordinate
fields. Newly confirmed candidates are imported with explicit ``Unknown``
values where the master catalogue does not provide a verified fact.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from recommendation_engine.recommendation_engine import rebuild_search_index


MASTER_EXCEL_PATH = (
    PROJECT_DIR / "data" / "General Dataset for Malaysian Tourism.xlsx"
)
LEGACY_EXCEL_PATH = PROJECT_DIR / "data" / "FYP_Malaysia_Tourism_Dataset.xlsx"
ACCESSIBILITY_EXCEL_PATH = (
    PROJECT_DIR / "data"
    / "Elderly-friendly Dataset for Malaysian Tourism.xlsx"
)
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"
IMAGE_CATALOGUE_PATH = PROJECT_DIR / "data" / "attraction_images.json"

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
    "reviewer_notes", "candidate_id", "canonical_id",
    "record_relationship", "related_site_id", "coverage_lens", "source_basis",
    "source_status", "state_tourism_guide_url", "origin_batch",
    "elderly_recommendation_eligibility", "accessibility_evidence_source",
    "accessibility_screening_notes", "documented_accessibility_features",
    "accessibility_screening_date",
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
    "recommendation_status",
}
ACCESSIBILITY_RECOMMENDATION_STATUSES = {
    "documented support - conditional",
    "reported support - confirm",
}
IMAGE_LIBRARY_COLUMNS = {
    "candidate_id", "image_number", "display_url", "commons_file_page",
    "creator", "license",
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


def load_image_library(path: Path) -> pd.DataFrame:
    """Load Wikimedia image candidates and their attribution metadata."""

    dataframe = pd.read_excel(path, sheet_name="Image Library", header=3)
    dataframe = _normalise_columns(dataframe)
    missing = IMAGE_LIBRARY_COLUMNS - set(dataframe.columns)
    if missing:
        raise ValueError(
            f"The image library in {path.name} is missing columns: "
            + ", ".join(sorted(missing))
        )
    return dataframe.dropna(subset=["candidate_id", "display_url"])


def build_attraction_image_catalogue(
    master_candidates: pd.DataFrame,
    image_libraries: list[pd.DataFrame],
    existing_catalogue: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, str]]:
    """Map workbook images to runtime attraction IDs.

    Locally cached images remain preferred. For workbook entries, the first
    valid Wikimedia candidate is used so every recommendation card stays
    compact while gaining the widest available attraction coverage.
    """

    candidate_to_attraction: dict[str, str] = {}
    for _, candidate in master_candidates.iterrows():
        status = (_text(candidate.get("review_status")) or "").casefold()
        candidate_id = _text(candidate.get("candidate_id"))
        if status not in CONFIRMED_STATUSES or not candidate_id:
            continue
        candidate_to_attraction[candidate_id] = (
            _text(candidate.get("existing_record_id")) or candidate_id
        )

    catalogue: dict[str, dict[str, str]] = {}
    for attraction_id, item in (existing_catalogue or {}).items():
        if not isinstance(item, dict):
            continue
        image_url = _text(item.get("image_url"))
        if image_url and image_url.startswith("/static/images/attractions/"):
            catalogue[str(attraction_id).strip()] = {
                key: value.strip()
                for key, value in item.items()
                if key in {
                    "image_url", "image_page_url", "image_attribution",
                    "image_license",
                } and isinstance(value, str) and value.strip()
            }

    for library in image_libraries:
        ordered = library.copy()
        ordered["image_number"] = pd.to_numeric(
            ordered["image_number"], errors="coerce"
        )
        ordered = ordered.sort_values(
            ["candidate_id", "image_number"], na_position="last"
        )
        for _, image in ordered.iterrows():
            candidate_id = _text(image.get("candidate_id"))
            attraction_id = candidate_to_attraction.get(candidate_id or "")
            if not attraction_id or attraction_id in catalogue:
                continue
            image_url = _text(image.get("display_url"))
            if not image_url or not image_url.casefold().startswith("https://"):
                continue
            image_url = image_url.replace(
                "https://thumb.wikimedia.org/",
                "https://upload.wikimedia.org/",
            )
            page_url = _text(image.get("commons_file_page"))
            catalogue[attraction_id] = {
                "image_url": image_url,
                "image_page_url": page_url or "",
                "image_attribution": _text(image.get("creator"))
                or _text(image.get("credit"))
                or "Wikimedia Commons contributor",
                "image_license": _text(image.get("license")) or "",
            }

    return dict(sorted(catalogue.items()))


def write_attraction_image_catalogue(
    master_candidates: pd.DataFrame,
    image_paths: tuple[Path, ...] = (
        MASTER_EXCEL_PATH,
        ACCESSIBILITY_EXCEL_PATH,
    ),
    catalogue_path: Path = IMAGE_CATALOGUE_PATH,
) -> int:
    """Rebuild the app image catalogue from the current workbooks."""

    existing: dict[str, dict[str, Any]] = {}
    if catalogue_path.exists():
        try:
            payload = json.loads(catalogue_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                existing = payload
        except (OSError, json.JSONDecodeError):
            existing = {}

    libraries = [load_image_library(path) for path in image_paths]
    catalogue = build_attraction_image_catalogue(
        master_candidates,
        libraries,
        existing,
    )
    catalogue_path.write_text(
        json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(catalogue)


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
    missing_evidence = dataframe[
        dataframe["evidence_tier"].isna()
        | dataframe["evidence_tier"].astype(str).str.strip().eq("")
    ]
    if not missing_evidence.empty:
        raise ValueError(
            "Every elderly recommendation row must name its evidence tier: "
            f"{missing_evidence['spot_id'].tolist()}"
        )
    statuses = dataframe["recommendation_status"].astype(str).str.strip().str.casefold()
    unsupported = dataframe[~statuses.isin(ACCESSIBILITY_RECOMMENDATION_STATUSES)]
    if not unsupported.empty:
        raise ValueError(
            "Unsupported elderly recommendation status for Spot IDs: "
            + ", ".join(unsupported["spot_id"].astype(str))
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
    suitability_folded = suitability_value.casefold()
    if suitability_folded == "suitable":
        elderly_friendly = "Yes"
    elif suitability_folded == "not recommended":
        elderly_friendly = "No"
    elif suitability_folded == "suitable with assistance" or suitability_folded.startswith(
        "conditional"
    ):
        elderly_friendly = "Partial"
    else:
        elderly_friendly = "Unknown"

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
        "elderly_suitability": (
            "Suitable with assistance"
            if suitability_folded.startswith("conditional")
            else suitability_value or "Unknown"
        ),
    }


def _explicit_accessibility_value(value: Any, field: str) -> str:
    """Normalise the reviewed workbook's structured accessibility fields."""

    text = (_text(value) or "").casefold()
    if not text or text == "unknown":
        return "Unknown"
    if field == "parking_proximity":
        if "near" in text or "under 20 m" in text or "drop-off" in text:
            return "Near"
        if "far" in text:
            return "Far"
        if "distance unknown" in text:
            return "Unknown"
        return "Moderate"
    if text.startswith("no"):
        return "No"
    if "unknown" in text or "unconfirmed" in text:
        return "Unknown"
    if (
        "partial" in text
        or "reported" in text
        or "likely" in text
        or "limited" in text
        or "confirm" in text
    ):
        return "Partial"
    return "Yes"


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
    structured = _structured_accessibility(structured_text, suitability)
    explicit_fields = {
        "step_free_access": "step_free_access",
        "resting_seats_available": "resting_seats",
        "accessible_toilet": "accessible_toilet",
        "parking_proximity": "parking",
        "shelter_available": "shelter",
    }
    for target, source in explicit_fields.items():
        value = _explicit_accessibility_value(accessibility.get(source), target)
        if value != "Unknown":
            structured[target] = value
    for field, value in structured.items():
        if value != "Unknown":
            record[field] = value

    combined_notes = "; ".join(
        value for value in (features, notes) if value
    ) or None
    record.update({
        "elderly_recommendation_eligibility": "Eligible",
        "accessibility_notes": combined_notes,
        "elderly_accessibility_notes": combined_notes,
        "accessibility_evidence_source": _text(
            accessibility.get("evidence_source_s")
        ),
        "accessibility_screening_notes": _text(
            accessibility.get("why_it_qualifies")
        ),
        "documented_accessibility_features": features,
        "accessibility_screening_date": _date(
            accessibility.get("latest_review_date")
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
            "canonical_id": _text(candidate.get("canonical_id")) or candidate_id,
            "record_relationship": _text(candidate.get("record_relationship"))
            or "Distinct candidate",
            "related_site_id": _text(candidate.get("related_site_id")),
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
    write_attraction_image_catalogue(
        master,
        image_paths=(master_path, accessibility_path),
    )
    return len(attractions)


def main() -> None:
    count = import_attractions()
    accessibility_count = len(load_verified_accessibility())
    print(f"Successfully imported {count} confirmed attractions.")
    print(f"Database created at: {DATABASE_PATH}")
    print("All confirmed attractions remain available for general travel searches.")
    print(
        "Elderly and accessibility requests use the "
        f"{accessibility_count}-record reviewed overlay."
    )
    print(
        f"Image catalogue contains "
        f"{len(json.loads(IMAGE_CATALOGUE_PATH.read_text(encoding='utf-8')))} "
        "attractions."
    )
    print("Run scripts/build_semantic_index.py before enabling semantic search.")


if __name__ == "__main__":
    main()
