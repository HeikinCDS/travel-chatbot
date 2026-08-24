import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_intent_classifier import (
    calculate_metrics,
    find_training_overlaps,
    load_cases,
)


class IntentEvaluationTests(unittest.TestCase):
    def test_metrics_include_accuracy_and_per_intent_scores(self):
        cases = [
            {"id": "A", "text": "hello", "expected_intent": "greeting"},
            {"id": "B", "text": "bye", "expected_intent": "goodbye"},
        ]
        predictions = {
            "hello": ("greeting", 0.9),
            "bye": ("greeting", 0.6),
        }
        metrics = calculate_metrics(cases, predictions.__getitem__)

        self.assertEqual(metrics["total_examples"], 2)
        self.assertEqual(metrics["correct_predictions"], 1)
        self.assertEqual(metrics["accuracy"], 0.5)
        self.assertEqual(metrics["per_intent"]["greeting"]["recall"], 1.0)
        self.assertEqual(metrics["per_intent"]["goodbye"]["recall"], 0.0)

    def test_training_overlap_is_detected_case_insensitively(self):
        training = {
            "intents": [{"label": "greeting", "examples": ["Hello Maya"]}]
        }
        cases = [
            {"id": "G1", "text": "hello maya", "expected_intent": "greeting"}
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "training.json"
            path.write_text(json.dumps(training), encoding="utf-8")
            self.assertEqual(find_training_overlaps(cases, path), ["G1"])

    def test_fixed_evaluation_dataset_is_valid_and_balanced(self):
        path = Path(__file__).resolve().parents[1] / "evaluation" / "intent_queries.json"
        cases = load_cases(path)
        counts = {}
        for case in cases:
            counts[case["expected_intent"]] = counts.get(case["expected_intent"], 0) + 1

        self.assertEqual(len(cases), 72)
        self.assertEqual(set(counts.values()), {8})


if __name__ == "__main__":
    unittest.main()
