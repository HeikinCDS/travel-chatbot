"""Report exact and likely duplicate attractions in the active workbooks."""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
import re

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
GENERAL_PATH = PROJECT_DIR / "data" / "General Dataset for Malaysian Tourism.xlsx"
ELDERLY_PATH = (
    PROJECT_DIR / "data" / "Elderly-friendly Dataset for Malaysian Tourism.xlsx"
)
CONFIRMED = {"approved", "complete", "completed", "confirmed"}


def normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def main() -> None:
    general = pd.read_excel(GENERAL_PATH, sheet_name="Catalogue", header=2).fillna("")
    general = general[
        general["Review Status"].astype(str).str.casefold().isin(CONFIRMED)
    ].reset_index(drop=True)
    elderly = pd.read_excel(
        ELDERLY_PATH,
        sheet_name="Elderly-Friendly Spots",
    ).fillna("")

    exact_groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for _, row in general.iterrows():
        key = (normalise(row["Attraction Name"]), normalise(row["State / Territory"]))
        exact_groups.setdefault(key, []).append(
            (str(row["Candidate ID"]), str(row["Attraction Name"]))
        )
    exact = [records for records in exact_groups.values() if len(records) > 1]

    likely_unmarked: list[tuple[float, str, str, str, str]] = []
    for first_index in range(len(general)):
        first = general.iloc[first_index]
        for second_index in range(first_index + 1, len(general)):
            second = general.iloc[second_index]
            if normalise(first["State / Territory"]) != normalise(
                second["State / Territory"]
            ):
                continue
            first_name = normalise(first["Attraction Name"])
            second_name = normalise(second["Attraction Name"])
            similarity = SequenceMatcher(None, first_name, second_name).ratio()
            first_tokens = set(first_name.split())
            second_tokens = set(second_name.split())
            token_overlap = len(first_tokens & second_tokens) / max(
                1, len(first_tokens | second_tokens)
            )
            score = max(similarity, token_overlap)
            if score < 0.84:
                continue
            first_id = str(first["Candidate ID"]).strip()
            second_id = str(second["Candidate ID"]).strip()
            same_canonical = bool(
                str(first["Canonical ID"]).strip()
                and str(first["Canonical ID"]).strip()
                == str(second["Canonical ID"]).strip()
            )
            linked = (
                str(first["Related Site ID"]).strip() == second_id
                or str(second["Related Site ID"]).strip() == first_id
            )
            if not same_canonical and not linked:
                likely_unmarked.append(
                    (
                        score,
                        first_id,
                        str(first["Attraction Name"]),
                        second_id,
                        str(second["Attraction Name"]),
                    )
                )

    general_ids = set(general["Candidate ID"].astype(str).str.strip())
    elderly_ids = elderly["Spot ID"].astype(str).str.strip()
    print(f"Confirmed general rows: {len(general)}")
    print(f"Exact same-name groups: {len(exact)}")
    for group in exact:
        print("  " + " | ".join(f"{item_id}: {name}" for item_id, name in group))
    print(
        "Explicit duplicate aliases: "
        f"{int(general['Record Relationship'].eq('Duplicate alias').sum())}"
    )
    print(
        "Related sites/components: "
        f"{int(general['Record Relationship'].eq('Related site or component').sum())}"
    )
    print(f"Unmarked high-similarity pairs: {len(likely_unmarked)}")
    for score, first_id, first_name, second_id, second_name in sorted(
        likely_unmarked,
        reverse=True,
    ):
        print(
            f"  {score:.3f} | {first_id}: {first_name} | "
            f"{second_id}: {second_name}"
        )
    print(f"Elderly rows: {len(elderly)}")
    print(f"Duplicate elderly IDs: {int(elderly_ids.duplicated().sum())}")
    print(
        "Duplicate elderly names: "
        f"{int(elderly['Attraction Name'].map(normalise).duplicated().sum())}"
    )
    print(f"Elderly IDs missing from general: {len(set(elderly_ids) - general_ids)}")


if __name__ == "__main__":
    main()
