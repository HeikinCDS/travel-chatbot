"""Load the curated, openly licensed attraction image catalogue."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
IMAGE_CATALOGUE_PATH = PROJECT_DIR / "data" / "attraction_images.json"


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(IMAGE_CATALOGUE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def get_attraction_image(attraction_id: object) -> dict[str, Any]:
    """Return safe display metadata for an attraction, if curated."""

    if not isinstance(attraction_id, str):
        return {}
    item = _catalogue().get(attraction_id.strip())
    if not isinstance(item, dict):
        return {}
    allowed = {
        "image_url", "image_page_url", "image_attribution", "image_license",
    }
    return {
        key: value for key, value in item.items()
        if key in allowed and isinstance(value, str) and value.strip()
    }
