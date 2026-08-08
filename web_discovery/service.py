"""Free, source-backed attraction discovery for JomVoyage.

Attractions come from Wikidata and OpenStreetMap. Photographs come from
Wikimedia Commons with licence metadata.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from nlp.local_llm import LocalLLMInterpreter


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "instance" / "travel_recommender.db"
CACHE_LIFETIME = timedelta(days=7)
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
OVERPASS_API = "https://overpass-api.de/api/interpreter"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
CACHE_SCHEMA_VERSION = 2

STATE_ISO_CODES = {
    "johor": "MY-01",
    "kedah": "MY-02",
    "kelantan": "MY-03",
    "melaka": "MY-04",
    "malacca": "MY-04",
    "negeri sembilan": "MY-05",
    "pahang": "MY-06",
    "penang": "MY-07",
    "pulau pinang": "MY-07",
    "perak": "MY-08",
    "perlis": "MY-09",
    "selangor": "MY-10",
    "terengganu": "MY-11",
    "sabah": "MY-12",
    "sarawak": "MY-13",
    "kuala lumpur": "MY-14",
    "w p kuala lumpur": "MY-14",
    "labuan": "MY-15",
    "w p labuan": "MY-15",
    "putrajaya": "MY-16",
    "w p putrajaya": "MY-16",
}

INTEREST_TERMS = {
    "nature": {
        "nature", "natural", "park", "forest", "garden", "waterfall",
        "mountain", "cave", "lake", "reserve", "island", "trail",
        "mangrove", "wetland", "hot spring",
    },
    "beach": {"beach", "coast", "coastal", "island", "marine", "sea"},
    "history": {
        "history", "historic", "heritage", "museum", "monument", "fort",
        "palace", "archaeological", "temple", "mosque", "church",
    },
    "wildlife": {
        "wildlife", "zoo", "animal", "bird", "marine", "reserve",
        "sanctuary", "aquarium",
    },
    "relaxation": {
        "relaxation", "relax", "garden", "park", "beach", "lake",
        "promenade", "hot spring", "spa", "scenic",
    },
    "adventure": {
        "adventure", "hiking", "trail", "cave", "mountain", "waterfall",
        "climbing", "rafting", "diving", "marine",
    },
}


def _plain_text(value: Any, *, maximum: int = 2000) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()[:maximum]


def _normalised_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _safe_http_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


class OpenDataDiscovery:
    """Discover, validate, rank, photograph and cache Malaysian attractions."""

    def __init__(
        self,
        *,
        database_path: Path | str = DATABASE_PATH,
        urlopen_function: Any | None = None,
        now: Any | None = None,
        language_model: Any | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self._urlopen = urlopen_function or urlopen
        self._now = now or (lambda: datetime.now(UTC))
        self.language_model = language_model or LocalLLMInterpreter()
        contact = os.getenv("JOMVOYAGE_CONTACT", "academic prototype")
        self.user_agent = f"JomVoyage-FYP/1.0 ({contact})"
        self._failed_until: dict[str, datetime] = {}
        self._description_retry_after = datetime.min.replace(tzinfo=UTC)

    def discover(
        self,
        preferences: Mapping[str, Any],
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return cached or freshly discovered open-data recommendations."""
        if limit < 1:
            return []
        state = _plain_text(preferences.get("state"), maximum=80)
        iso_code = STATE_ISO_CODES.get(_normalised_key(state))
        if not state or not iso_code:
            return []

        query_key = self._query_key(preferences)
        cached = self._read_cache(query_key, limit)
        if cached:
            if self._apply_generated_descriptions(cached):
                self._write_cache(query_key, cached)
            return cached
        failed_until = self._failed_until.get(
            query_key, datetime.min.replace(tzinfo=UTC)
        )
        if failed_until > self._now():
            return []

        raw_items: list[Mapping[str, Any]] = []
        try:
            raw_items.extend(self._search_wikidata(state, iso_code))
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
            pass
        try:
            # Kept sequential to respect public Overpass service capacity.
            raw_items.extend(self._search_openstreetmap(state, iso_code))
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
            pass

        candidates: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for raw in raw_items:
            item = self._validate_candidate(raw, preferences)
            if item is None:
                continue
            name_key = _normalised_key(item["attraction_name"])
            if name_key in seen_names:
                continue
            seen_names.add(name_key)
            candidates.append(item)

        candidates.sort(
            key=lambda item: (
                self._interest_score(item, preferences),
                bool(item.get("official_url")),
                bool(item.get("short_description")),
            ),
            reverse=True,
        )
        selected = candidates[:limit]
        for item in selected:
            item.update(self._find_commons_image(item))
            for key in [name for name in item if name.startswith("_")]:
                item.pop(key, None)
        self._apply_generated_descriptions(selected)
        if selected:
            self._write_cache(query_key, selected)
            self._failed_until.pop(query_key, None)
        else:
            # Avoid repeatedly hitting community services after a timeout,
            # rate limit or a query with no open-data matches.
            self._failed_until[query_key] = self._now() + timedelta(minutes=10)
        return selected

    def _apply_generated_descriptions(
        self,
        items: list[dict[str, Any]],
    ) -> bool:
        pending = [
            item for item in items
            if item.get("description_origin") != "local_ai_from_source_facts"
        ]
        if not pending or self._description_retry_after > self._now():
            return False
        generated = self.language_model.generate_descriptions(pending)
        if not generated:
            self._description_retry_after = self._now() + timedelta(minutes=10)
            return False
        self._description_retry_after = datetime.min.replace(tzinfo=UTC)
        changed = False
        for item in pending:
            description = generated.get(str(item["attraction_id"]))
            if description:
                item["short_description"] = description
                item["description_origin"] = "local_ai_from_source_facts"
                changed = True
        return changed

    def get_by_id(self, attraction_id: str) -> dict[str, Any] | None:
        self._ensure_cache_table()
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT payload_json FROM web_attraction_cache WHERE attraction_id = ?",
                (attraction_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _search_wikidata(self, state: str, iso_code: str) -> list[dict[str, Any]]:
        query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX schema: <http://schema.org/>
SELECT DISTINCT ?item ?itemLabel ?itemDescription ?typeLabel ?image
                ?coordinate ?officialWebsite ?article WHERE {{
  ?admin wdt:P300 "{iso_code}".
  VALUES ?root {{
    wd:Q570116 wd:Q33506 wd:Q46169 wd:Q179049 wd:Q22698
    wd:Q40080 wd:Q43501 wd:Q167346 wd:Q194195 wd:Q23413 wd:Q839954
  }}
  ?item wdt:P131* ?admin;
        wdt:P31 ?type.
  ?type wdt:P279* ?root.
  OPTIONAL {{ ?item wdt:P18 ?image. }}
  OPTIONAL {{ ?item wdt:P625 ?coordinate. }}
  OPTIONAL {{ ?item wdt:P856 ?officialWebsite. }}
  OPTIONAL {{
    ?article schema:about ?item;
             schema:isPartOf <https://en.wikipedia.org/>.
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ms". }}
}}
LIMIT 60
""".strip()
        payload = self._request_json(
            WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            timeout=25,
        )
        items: list[dict[str, Any]] = []
        for binding in payload.get("results", {}).get("bindings", []):
            name = self._binding(binding, "itemLabel")
            item_url = _safe_http_url(self._binding(binding, "item"))
            if not name or not item_url or name.startswith("Q"):
                continue
            category = self._binding(binding, "typeLabel") or "Tourist attraction"
            description = self._binding(binding, "itemDescription")
            article = _safe_http_url(self._binding(binding, "article"))
            official = _safe_http_url(self._binding(binding, "officialWebsite"))
            source_links = [{"title": "Wikidata", "url": item_url}]
            if article:
                source_links.append({"title": "Wikipedia", "url": article})
            item = self._base_item(
                name=name,
                state=state,
                category=category,
                description=description or (
                    f"{name} is listed by Wikidata as a {category.casefold()} in {state}."
                ),
                source_url=item_url,
                official_url=official,
                source_links=source_links,
            )
            image = self._binding(binding, "image")
            if image:
                item["_commons_filename"] = unquote(urlparse(image).path.rsplit("/", 1)[-1])
            coordinate = self._binding(binding, "coordinate")
            match = re.fullmatch(r"Point\(([-.0-9]+) ([-.0-9]+)\)", coordinate)
            if match:
                item["longitude"] = float(match.group(1))
                item["latitude"] = float(match.group(2))
            items.append(item)
        return items

    def _search_openstreetmap(self, state: str, iso_code: str) -> list[dict[str, Any]]:
        query = f"""
[out:json][timeout:25];
area["ISO3166-2"="{iso_code}"][boundary=administrative]->.state;
(
  nwr["tourism"](area.state);
  nwr["leisure"~"park|nature_reserve|garden|water_park|theme_park"](area.state);
  nwr["natural"~"beach|cave_entrance|waterfall|peak|hot_spring"](area.state);
  nwr["historic"](area.state);
);
out center tags 80;
""".strip()
        payload = self._request_json(
            OVERPASS_API,
            data=urlencode({"data": query}).encode("utf-8"),
            timeout=30,
        )
        items: list[dict[str, Any]] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = tags.get("name:en") or tags.get("name") or tags.get("name:ms")
            if not name:
                continue
            category = (
                tags.get("tourism") or tags.get("leisure")
                or tags.get("natural") or tags.get("historic")
                or "tourist attraction"
            ).replace("_", " ")
            element_type = element.get("type")
            element_id = element.get("id")
            source_url = f"https://www.openstreetmap.org/{element_type}/{element_id}"
            description = tags.get("description:en") or tags.get("description") or (
                f"{name} is recorded by OpenStreetMap as a {category} place in {state}."
            )
            official = _safe_http_url(
                tags.get("website") or tags.get("contact:website") or tags.get("url")
            )
            item = self._base_item(
                name=str(name),
                state=state,
                category=category,
                description=str(description),
                source_url=source_url,
                official_url=official,
                source_links=[{"title": "OpenStreetMap", "url": source_url}],
            )
            wheelchair = str(tags.get("wheelchair") or "").casefold()
            item["wheelchair_accessible"] = {
                "yes": "Yes", "limited": "Partial", "no": "No",
            }.get(wheelchair, "Unknown")
            access_notes: list[str] = []
            if wheelchair:
                access_notes.append(f"OpenStreetMap wheelchair tag: {wheelchair}.")
            if tags.get("bench") == "yes":
                access_notes.append("Seating is recorded.")
            item["accessibility_notes"] = " ".join(access_notes) or (
                "Accessibility information is not available in the open-data record."
            )
            if tags.get("fee") == "no":
                item.update(
                    entrance_fee_status="Free",
                    min_fee_myr=0.0,
                    max_fee_myr=0.0,
                )
            commons = str(tags.get("wikimedia_commons") or "")
            if commons.casefold().startswith("file:"):
                item["_commons_filename"] = commons[5:].strip()
            position = element.get("center") or element
            item["latitude"] = position.get("lat")
            item["longitude"] = position.get("lon")
            items.append(item)
        return items

    def _base_item(
        self,
        *,
        name: str,
        state: str,
        category: str,
        description: str,
        source_url: str,
        official_url: str | None,
        source_links: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "attraction_name": _plain_text(name, maximum=160),
            "state_territory": state,
            "city_district": "",
            "primary_category": _plain_text(category, maximum=80).title(),
            "interests_tags": _plain_text(category, maximum=300).casefold(),
            "short_description": _plain_text(description),
            "entrance_fee_status": "Unknown",
            "min_fee_myr": None,
            "max_fee_myr": None,
            "recommended_duration_hours": None,
            "family_friendly": "Unknown",
            "elderly_friendly": "Unknown",
            "wheelchair_accessible": "Unknown",
            "accessibility_notes": (
                "Accessibility information is not available in the open-data record."
            ),
            "official_url": official_url,
            "source_url": source_url,
            "source_links": source_links,
        }

    def _validate_candidate(
        self,
        raw: Mapping[str, Any],
        preferences: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        name = _plain_text(raw.get("attraction_name"), maximum=160)
        state = _plain_text(raw.get("state_territory"), maximum=80)
        expected_state = _plain_text(preferences.get("state"), maximum=80)
        source_url = _safe_http_url(raw.get("source_url"))
        if not name or not source_url:
            return None
        if _normalised_key(state) != _normalised_key(expected_state):
            return None
        if self._interest_score(raw, preferences) <= 0:
            return None
        item = dict(raw)
        item["attraction_id"] = "OPEN-" + hashlib.sha256(
            f"{name}|{state}".casefold().encode("utf-8")
        ).hexdigest()[:16].upper()
        item["date_verified"] = self._now().date().isoformat()
        item["verification_status"] = "open_data_discovered"
        item["information_origin"] = "open_data"
        return item

    @staticmethod
    def _interest_score(
        item: Mapping[str, Any],
        preferences: Mapping[str, Any],
    ) -> int:
        interests = preferences.get("interests") or []
        if not interests:
            return 1
        searchable = _normalised_key(" ".join(str(item.get(key) or "") for key in (
            "attraction_name", "primary_category", "interests_tags", "short_description"
        )))
        score = 0
        for interest in interests:
            normalised = _normalised_key(str(interest))
            terms = INTEREST_TERMS.get(normalised, {normalised})
            score += sum(1 for term in terms if _normalised_key(term) in searchable)
        return score

    def _find_commons_image(self, item: Mapping[str, Any]) -> dict[str, Any]:
        filename = _plain_text(item.get("_commons_filename"), maximum=300)
        params = {
            "action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime", "iiurlwidth": 900,
        }
        if filename:
            params["titles"] = f"File:{filename.removeprefix('File:')}"
        else:
            params.update(
                generator="search",
                gsrsearch=f"{item['attraction_name']} {item['state_territory']} Malaysia",
                gsrnamespace=6,
                gsrlimit=5,
            )
        try:
            payload = self._request_json(COMMONS_API, params=params, timeout=10)
            pages = payload.get("query", {}).get("pages", {}).values()
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
            return self._find_openverse_image(item)
        name_tokens = {
            token for token in _normalised_key(str(item["attraction_name"])).split()
            if len(token) >= 4
        }
        for page in pages:
            if not filename:
                title = _normalised_key(str(page.get("title") or ""))
                if name_tokens and not any(token in title for token in name_tokens):
                    continue
            info = (page.get("imageinfo") or [{}])[0]
            if not str(info.get("mime", "")).startswith("image/"):
                continue
            metadata = info.get("extmetadata") or {}
            image_url = _safe_http_url(info.get("thumburl") or info.get("url"))
            page_url = _safe_http_url(info.get("descriptionurl"))
            licence = _plain_text(
                (metadata.get("LicenseShortName") or {}).get("value"), maximum=80
            )
            artist = _plain_text(
                (metadata.get("Artist") or {}).get("value"), maximum=240
            )
            if image_url and page_url and licence:
                return {
                    "image_url": image_url,
                    "image_page_url": page_url,
                    "image_attribution": artist or "Wikimedia Commons contributor",
                    "image_license": licence,
                }
        return self._find_openverse_image(item)

    def _find_openverse_image(self, item: Mapping[str, Any]) -> dict[str, Any]:
        """Use openly licensed search as a fallback when Commons has no match."""
        name = str(item.get("attraction_name") or "")
        state = str(item.get("state_territory") or "")
        try:
            payload = self._request_json(
                OPENVERSE_API,
                params={
                    "q": f'"{name}" {state} Malaysia',
                    "page_size": 10,
                    "mature": "false",
                },
                timeout=10,
            )
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
            return {}

        name_tokens = {
            token for token in _normalised_key(name).split() if len(token) >= 4
        }
        required_matches = max(1, (len(name_tokens) + 1) // 2)
        for result in payload.get("results", []):
            if result.get("mature") is True:
                continue
            tags = " ".join(
                str(tag.get("name") or "")
                for tag in result.get("tags", [])
                if isinstance(tag, Mapping)
            )
            searchable = _normalised_key(
                f"{result.get('title', '')} {tags}"
            )
            matches = sum(token in searchable for token in name_tokens)
            if name_tokens and matches < required_matches:
                continue
            image_url = _safe_http_url(
                result.get("thumbnail") or result.get("url")
            )
            page_url = _safe_http_url(result.get("foreign_landing_url"))
            licence = _plain_text(result.get("license"), maximum=40).upper()
            version = _plain_text(result.get("license_version"), maximum=20)
            creator = _plain_text(
                result.get("creator") or result.get("attribution"), maximum=240
            )
            if image_url and page_url and licence:
                return {
                    "image_url": image_url,
                    "image_page_url": page_url,
                    "image_attribution": creator or "Openverse contributor",
                    "image_license": f"{licence} {version}".strip(),
                }
        return {}

    def _request_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: bytes | None = None,
        timeout: int = 20,
        content_type: str = "application/x-www-form-urlencoded",
    ) -> Mapping[str, Any]:
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(
            url,
            data=data,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Content-Type": content_type,
            },
        )
        try:
            with self._urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            error.close()
            raise

    @staticmethod
    def _binding(binding: Mapping[str, Any], name: str) -> str:
        return str((binding.get(name) or {}).get("value") or "")

    @staticmethod
    def _query_key(preferences: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            {"version": CACHE_SCHEMA_VERSION, "preferences": dict(preferences)},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _ensure_cache_table(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS web_attraction_cache (
                    attraction_id TEXT PRIMARY KEY,
                    query_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_web_cache_query "
                "ON web_attraction_cache(query_key, expires_at)"
            )
            connection.commit()

    def _read_cache(self, query_key: str, limit: int) -> list[dict[str, Any]]:
        self._ensure_cache_table()
        with closing(sqlite3.connect(self.database_path)) as connection:
            rows = connection.execute(
                "SELECT payload_json FROM web_attraction_cache "
                "WHERE query_key = ? AND expires_at > ? "
                "ORDER BY checked_at DESC LIMIT ?",
                (query_key, self._now().isoformat(), limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _write_cache(
        self,
        query_key: str,
        items: list[Mapping[str, Any]],
    ) -> None:
        self._ensure_cache_table()
        checked = self._now()
        expires = checked + CACHE_LIFETIME
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO web_attraction_cache (
                    attraction_id, query_key, payload_json, checked_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(attraction_id) DO UPDATE SET
                    query_key = excluded.query_key,
                    payload_json = excluded.payload_json,
                    checked_at = excluded.checked_at,
                    expires_at = excluded.expires_at
                """,
                [(
                    item["attraction_id"], query_key,
                    json.dumps({
                        key: value for key, value in dict(item).items()
                        if not key.startswith("_")
                    }, ensure_ascii=False),
                    checked.isoformat(), expires.isoformat(),
                ) for item in items],
            )
            connection.commit()


# Compatibility for code written against the earlier paid-search prototype.
LiveWebDiscovery = OpenDataDiscovery
