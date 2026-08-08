import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError

from web_discovery import OpenDataDiscovery


WIKIDATA_PAYLOAD = {
    "results": {
        "bindings": [{
            "item": {"value": "https://www.wikidata.org/entity/Q123"},
            "itemLabel": {"value": "Example Nature Park"},
            "itemDescription": {"value": "A protected forest park in Penang."},
            "typeLabel": {"value": "nature reserve"},
            "image": {
                "value": (
                    "http://commons.wikimedia.org/wiki/Special:FilePath/"
                    "Example Nature Park.jpg"
                )
            },
            "coordinate": {"value": "Point(100.4 5.3)"},
            "officialWebsite": {"value": "https://example.gov.my/park"},
            "article": {"value": "https://en.wikipedia.org/wiki/Example_Nature_Park"},
        }]
    }
}

OVERPASS_PAYLOAD = {
    "elements": [{
        "type": "node",
        "id": 456,
        "lat": 5.4,
        "lon": 100.3,
        "tags": {
            "name": "Example Riverside Garden",
            "leisure": "garden",
            "description": "A public riverside garden.",
            "wheelchair": "yes",
            "bench": "yes",
            "fee": "no",
        },
    }]
}

COMMONS_PAYLOAD = {
    "query": {
        "pages": {
            "1": {
                "title": "File:Example Nature Park.jpg",
                "imageinfo": [{
                    "mime": "image/jpeg",
                    "thumburl": "https://upload.wikimedia.org/example.jpg",
                    "descriptionurl": (
                        "https://commons.wikimedia.org/wiki/File:Example_Nature_Park.jpg"
                    ),
                    "extmetadata": {
                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "Artist": {"value": "Example photographer"},
                    },
                }],
            }
        }
    }
}

OPENVERSE_PAYLOAD = {
    "results": [{
        "title": "Pantai Irama Kelantan",
        "thumbnail": "https://api.openverse.org/example-thumb.jpg",
        "url": "https://images.example.org/pantai-irama.jpg",
        "foreign_landing_url": "https://example.org/pantai-irama-photo",
        "creator": "Example photographer",
        "license": "by-sa",
        "license_version": "4.0",
        "mature": False,
        "tags": [{"name": "Pantai Irama"}, {"name": "Kelantan"}],
    }]
}


class OfflineLanguageModel:
    def generate_descriptions(self, attractions):
        return {}


class RecordingLanguageModel:
    def __init__(self):
        self.calls = 0

    def generate_descriptions(self, attractions):
        self.calls += 1
        return {
            str(item["attraction_id"]): (
                f"{item['attraction_name']} offers a welcoming natural setting "
                "for visitors interested in a relaxed Malaysian outing."
            )
            for item in attractions
        }


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeUrlOpen:
    def __init__(self, *, fail=False, commons_payload=None):
        self.fail = fail
        self.commons_payload = (
            COMMONS_PAYLOAD if commons_payload is None else commons_payload
        )
        self.calls = []

    def __call__(self, request, **kwargs):
        url = request.full_url
        self.calls.append(url)
        if self.fail:
            raise URLError("offline")
        if "query.wikidata.org" in url:
            return FakeHttpResponse(WIKIDATA_PAYLOAD)
        if "overpass-api.de" in url:
            return FakeHttpResponse(OVERPASS_PAYLOAD)
        if "commons.wikimedia.org" in url:
            return FakeHttpResponse(self.commons_payload)
        if "api.openverse.org" in url:
            return FakeHttpResponse(OPENVERSE_PAYLOAD)
        raise AssertionError(f"Unexpected URL: {url}")


class OpenDataDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "cache.db"

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_open_data_is_merged_photographed_and_cached(self):
        fake_urlopen = FakeUrlOpen()
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=fake_urlopen,
            language_model=OfflineLanguageModel(),
        )
        preferences = {"state": "Penang", "interests": ["nature"]}

        first = discovery.discover(preferences, limit=3)
        calls_after_first = len(fake_urlopen.calls)
        second = discovery.discover(preferences, limit=3)

        self.assertEqual(first, second)
        self.assertEqual(len(fake_urlopen.calls), calls_after_first)
        self.assertEqual(len(first), 2)
        self.assertTrue(first[0]["attraction_id"].startswith("OPEN-"))
        self.assertEqual(first[0]["information_origin"], "open_data")
        self.assertEqual(first[0]["image_license"], "CC BY-SA 4.0")
        self.assertEqual(first[0]["source_links"][0]["title"], "Wikidata")
        cached = discovery.get_by_id(first[0]["attraction_id"])
        self.assertEqual(cached["attraction_name"], first[0]["attraction_name"])

    def test_openstreetmap_accessibility_and_free_entry_are_conservative(self):
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=FakeUrlOpen(),
            language_model=OfflineLanguageModel(),
        )
        items = discovery._search_openstreetmap("Penang", "MY-07")
        item = items[0]
        self.assertEqual(item["wheelchair_accessible"], "Yes")
        self.assertEqual(item["elderly_friendly"], "Unknown")
        self.assertEqual(item["entrance_fee_status"], "Free")
        self.assertIn("Seating is recorded", item["accessibility_notes"])

    def test_network_failure_returns_empty_result_for_sqlite_fallback(self):
        fake_urlopen = FakeUrlOpen(fail=True)
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=fake_urlopen,
            language_model=OfflineLanguageModel(),
        )
        preferences = {"state": "Penang", "interests": ["nature"]}
        self.assertEqual(discovery.discover(preferences, limit=3), [])
        calls_after_failure = len(fake_urlopen.calls)
        self.assertEqual(discovery.discover(preferences, limit=3), [])
        self.assertEqual(len(fake_urlopen.calls), calls_after_failure)

    def test_unknown_state_is_not_sent_to_public_services(self):
        fake_urlopen = FakeUrlOpen()
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=fake_urlopen,
            language_model=OfflineLanguageModel(),
        )
        self.assertEqual(
            discovery.discover(
                {"state": "Unknown State", "interests": ["nature"]},
                limit=3,
            ),
            [],
        )
        self.assertEqual(fake_urlopen.calls, [])

    def test_openverse_is_used_when_commons_has_no_matching_image(self):
        fake_urlopen = FakeUrlOpen(commons_payload={"query": {"pages": {}}})
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=fake_urlopen,
            language_model=OfflineLanguageModel(),
        )
        image = discovery._find_commons_image({
            "attraction_name": "Pantai Irama",
            "state_territory": "Kelantan",
        })
        self.assertEqual(image["image_license"], "BY-SA 4.0")
        self.assertIn("openverse", image["image_url"])

    def test_cached_source_text_is_enriched_when_local_model_becomes_available(self):
        preferences = {"state": "Penang", "interests": ["nature"]}
        language_model = RecordingLanguageModel()
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=FakeUrlOpen(),
            language_model=language_model,
        )
        query_key = discovery._query_key(preferences)
        discovery._write_cache(query_key, [{
            "attraction_id": "OPEN-CACHED",
            "attraction_name": "Example Nature Park",
            "state_territory": "Penang",
            "primary_category": "Nature",
            "short_description": "Listed as a park in Penang.",
        }])

        result = discovery.discover(preferences, limit=1)
        self.assertEqual(language_model.calls, 1)
        self.assertEqual(
            result[0]["description_origin"],
            "local_ai_from_source_facts",
        )
        self.assertIn("welcoming natural setting", result[0]["short_description"])


if __name__ == "__main__":
    unittest.main()
