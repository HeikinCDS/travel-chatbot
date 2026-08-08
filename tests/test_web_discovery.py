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
    def __init__(self, *, fail=False, ollama_response=None):
        self.fail = fail
        self.ollama_response = ollama_response
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
            return FakeHttpResponse(COMMONS_PAYLOAD)
        if "127.0.0.1:11434" in url:
            return FakeHttpResponse({"response": self.ollama_response or ""})
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
            ollama_model="",
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
            ollama_model="",
        )
        items = discovery._search_openstreetmap("Penang", "MY-07")
        item = items[0]
        self.assertEqual(item["wheelchair_accessible"], "Yes")
        self.assertEqual(item["elderly_friendly"], "Unknown")
        self.assertEqual(item["entrance_fee_status"], "Free")
        self.assertIn("Seating is recorded", item["accessibility_notes"])

    def test_optional_ollama_only_polishes_existing_description(self):
        fake_urlopen = FakeUrlOpen(
            ollama_response="A calm protected forest park suitable for a gentle visit."
        )
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=fake_urlopen,
            ollama_model="test-model",
        )
        item = {
            "attraction_name": "Example Nature Park",
            "short_description": "A protected forest park in Penang.",
        }
        polished = discovery._polish_with_ollama(item)
        self.assertIn("protected forest", polished)
        self.assertTrue(any("127.0.0.1:11434" in url for url in fake_urlopen.calls))

    def test_network_failure_returns_empty_result_for_sqlite_fallback(self):
        fake_urlopen = FakeUrlOpen(fail=True)
        discovery = OpenDataDiscovery(
            database_path=self.database_path,
            urlopen_function=fake_urlopen,
            ollama_model="",
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
        )
        self.assertEqual(
            discovery.discover(
                {"state": "Unknown State", "interests": ["nature"]},
                limit=3,
            ),
            [],
        )
        self.assertEqual(fake_urlopen.calls, [])


if __name__ == "__main__":
    unittest.main()
