import json
import unittest
from urllib.error import URLError

from nlp.entity_extractor import TravelPreferences
from nlp.local_llm import LocalLLMInterpreter, merge_preferences


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def interpretation_payload(**overrides):
    values = {
        "intent": "request_recommendation",
        "confidence": 0.92,
        "travel_related": True,
        "state": "Penang",
        "interests": ["relaxation"],
        "maximum_fee": 50,
        "duration_days": None,
        "duration_hours": 2,
        "family_friendly": None,
        "elderly_friendly": True,
        "wheelchair_accessible": None,
    }
    values.update(overrides)
    return {
        "choices": [{
            "message": {"content": json.dumps(values)}
        }]
    }


class LocalLLMInterpreterTests(unittest.TestCase):
    def test_disabled_without_a_model(self):
        interpreter = LocalLLMInterpreter(model="")
        self.assertIsNone(interpreter.interpret("Travel to Penang", {}))

    def test_validated_lm_studio_response(self):
        calls = []

        def fake_urlopen(request, **kwargs):
            calls.append(request)
            return FakeResponse(interpretation_payload())

        interpreter = LocalLLMInterpreter(
            model="qwen3.5-4b",
            urlopen_function=fake_urlopen,
        )
        result = interpreter.interpret("Somewhere calm in Penang", {})

        self.assertEqual(result.intent, "request_recommendation")
        self.assertEqual(result.preferences.state, "Penang")
        self.assertEqual(result.preferences.interests, ("relaxation",))
        self.assertTrue(result.preferences.elderly_friendly)
        self.assertEqual(len(calls), 1)
        request_body = json.loads(calls[0].data.decode("utf-8"))
        self.assertEqual(request_body["model"], "qwen3.5-4b")
        self.assertEqual(
            request_body["response_format"]["type"],
            "json_schema",
        )

    def test_unknown_values_and_invalid_numbers_are_discarded(self):
        def fake_urlopen(request, **kwargs):
            return FakeResponse(interpretation_payload(
                state="Singapore",
                interests=["nightlife", "nature"],
                maximum_fee=-10,
                duration_hours=0,
            ))

        result = LocalLLMInterpreter(
            model="qwen3.5-4b",
            urlopen_function=fake_urlopen,
        ).interpret("Take me anywhere", {})

        self.assertIsNone(result.preferences.state)
        self.assertEqual(result.preferences.interests, ("nature",))
        self.assertIsNone(result.preferences.maximum_fee)
        self.assertIsNone(result.preferences.duration_hours)

    def test_connection_failure_uses_existing_nlp_fallback(self):
        def offline(request, **kwargs):
            raise URLError("offline")

        interpreter = LocalLLMInterpreter(
            model="qwen3.5-4b",
            urlopen_function=offline,
        )
        self.assertIsNone(interpreter.interpret("Travel to Penang", {}))

    def test_rule_values_take_priority_when_merging(self):
        merged = merge_preferences(
            TravelPreferences(
                state="Johor",
                interests=("nature",),
                maximum_fee=20,
            ),
            TravelPreferences(
                state="Penang",
                interests=("relaxation",),
                maximum_fee=50,
                elderly_friendly=True,
            ),
        )
        self.assertEqual(merged.state, "Johor")
        self.assertEqual(merged.maximum_fee, 20)
        self.assertEqual(merged.interests, ("nature", "relaxation"))
        self.assertTrue(merged.elderly_friendly)

    def test_generates_descriptions_in_one_validated_batch(self):
        response = {
            "choices": [{"message": {"content": json.dumps({
                "items": [{
                    "attraction_id": "OPEN-1",
                    "description": (
                        "Pantai Irama offers a relaxed seaside setting in Kelantan "
                        "for visitors who enjoy coastal scenery."
                    ),
                }]
            })}}]
        }

        def fake_urlopen(request, **kwargs):
            return FakeResponse(response)

        descriptions = LocalLLMInterpreter(
            model="qwen3.5-4b",
            urlopen_function=fake_urlopen,
        ).generate_descriptions([{
            "attraction_id": "OPEN-1",
            "attraction_name": "Pantai Irama",
            "state_territory": "Kelantan",
            "primary_category": "Beach",
            "short_description": "A beach in Kelantan.",
        }])
        self.assertIn("seaside", descriptions["OPEN-1"])


if __name__ == "__main__":
    unittest.main()
