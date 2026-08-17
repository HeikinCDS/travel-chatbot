"""Cache openly licensed Wikimedia Commons images for eligible attractions.

Run from the project root. Existing curated entries are preserved unless
``--refresh`` is supplied.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"
CATALOGUE_PATH = PROJECT_DIR / "data" / "attraction_images.json"
IMAGE_DIR = PROJECT_DIR / "static" / "images" / "attractions"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "JomVoyage-FYP/1.0 (academic prototype)"
COMMONS_FILE_OVERRIDES = {
    "A082": "Penang Hill (8345232894).jpg",
    "A088": "Penang Botanic Gardens.jpg",
    "MC0180": "Pinang Peranakan Mansion (I).jpg",
    "MC0194": "Penang Bird Park entrance building (12340610483).jpg",
}


def _plain_text(value: object) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
        if len(token) >= 4 and token not in {"malaysia", "park"}
    }


def _request_json(params: dict[str, object]) -> dict:
    for attempt in range(3):
        request = Request(
            f"{COMMONS_API}?{urlencode(params)}",
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code != 429 or attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    return {}


def _find_image(
    name: str,
    state: str,
    *,
    commons_filename: str | None = None,
) -> dict[str, str]:
    wanted = _tokens(name)
    searches = (f"{name} {state}", name)
    for search_text in searches:
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": 1000,
        }
        if commons_filename:
            params["titles"] = f"File:{commons_filename}"
        else:
            params.update({
                "generator": "search",
                "gsrsearch": search_text,
                "gsrnamespace": 6,
                "gsrlimit": 12,
            })
        payload = _request_json(params)
        pages = payload.get("query", {}).get("pages", {}).values()
        for page in pages:
            title_tokens = _tokens(str(page.get("title") or ""))
            if not commons_filename and wanted and not wanted.intersection(title_tokens):
                continue
            info = (page.get("imageinfo") or [{}])[0]
            mime = str(info.get("mime") or "")
            if not mime.startswith("image/"):
                continue
            metadata = info.get("extmetadata") or {}
            image_url = info.get("thumburl") or info.get("url")
            page_url = info.get("descriptionurl")
            licence = _plain_text(
                (metadata.get("LicenseShortName") or {}).get("value")
            )
            if not image_url or not page_url or not licence:
                continue
            return {
                "download_url": str(image_url),
                "page_url": str(page_url),
                "attribution": _plain_text(
                    (metadata.get("Artist") or {}).get("value")
                ) or "Wikimedia Commons contributor",
                "license": licence,
                "mime": mime,
            }
        if commons_filename:
            break
    return {}


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--ids", nargs="*", help="Only process these IDs")
    args = parser.parse_args()

    existing = {}
    if CATALOGUE_PATH.exists():
        existing = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as connection:
        rows = connection.execute("""
            SELECT attraction_id, attraction_name, state_territory
            FROM attractions
            WHERE LOWER(COALESCE(elderly_recommendation_eligibility, ''))
                  = 'eligible'
            ORDER BY attraction_id
        """).fetchall()

    added = 0
    for attraction_id, name, state in rows:
        if args.ids and attraction_id not in set(args.ids):
            continue
        if attraction_id in existing and not args.refresh:
            continue
        try:
            found = _find_image(
                name,
                state,
                commons_filename=COMMONS_FILE_OVERRIDES.get(attraction_id),
            )
            if not found:
                print(f"No suitable Commons image: {name}")
                continue
            extension = mimetypes.guess_extension(found.pop("mime")) or ".jpg"
            if extension == ".jpe":
                extension = ".jpg"
            destination = IMAGE_DIR / f"{attraction_id}{extension}"
            _download(found.pop("download_url"), destination)
            existing[attraction_id] = {
                "image_url": f"/static/images/attractions/{destination.name}",
                "image_page_url": found["page_url"],
                "image_attribution": found["attribution"],
                "image_license": found["license"],
            }
            added += 1
            print(f"Added: {name}")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Skipped {name}: {error}")
        time.sleep(1)

    CATALOGUE_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Image catalogue contains {len(existing)} attraction(s); {added} added.")


if __name__ == "__main__":
    main()
