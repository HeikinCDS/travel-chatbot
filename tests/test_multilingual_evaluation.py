import unittest
from collections import Counter
from pathlib import Path

from scripts.evaluate_multilingual_input import (
    calculate_entity_metrics,
    load_multilingual_cases,
    write_markdown_summary,
)


class MultilingualEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = (
            Path(__file__).resolve().parents[1]
            / "evaluation"
            / "multilingual_queries.json"
        )
        cls.cases = load_multilingual_cases(cls.path)

    def test_fixed_dataset_is_balanced_by_language_and_intent(self):
        self.assertEqual(len(self.cases), 54)
        language_counts = Counter(case["language"] for case in self.cases)
        self.assertEqual(language_counts, {"ms": 27, "zh": 27})

        for language in ("ms", "zh"):
            intent_counts = Counter(
                case["expected_intent"]
                for case in self.cases
                if case["language"] == language
            )
            self.assertEqual(len(intent_counts), 9)
            self.assertEqual(set(intent_counts.values()), {3})

    def test_dataset_contains_entity_expectations_for_both_languages(self):
        languages = {
            case["language"]
            for case in self.cases
            if case.get("expected_preferences")
        }
        self.assertEqual(languages, {"ms", "zh"})

    def test_entity_metrics_score_expected_fields(self):
        cases = [
            {
                "id": "MS-TEST",
                "language": "ms",
                "text": "Cadangkan pantai di Penang",
                "expected_intent": "request_recommendation",
                "expected_preferences": {
                    "state": "Penang",
                    "interests": ["beach"],
                },
            }
        ]
        metrics = calculate_entity_metrics(cases)
        self.assertEqual(metrics["field_accuracy"], 1.0)
        self.assertEqual(metrics["case_accuracy"], 1.0)

    def test_report_summary_includes_limitations(self):
        results = {
            "intent_classification": {
                "total_examples": 2,
                "accuracy": 1.0,
                "macro_f1_score": 1.0,
            },
            "per_language": {
                "ms": {"accuracy": 1.0},
                "zh": {"accuracy": 1.0},
            },
            "entity_extraction": {
                "field_accuracy": 1.0,
                "correct_fields": 2,
                "evaluated_fields": 2,
                "perfect_cases": 1,
                "evaluated_cases": 1,
            },
            "training_overlap_count": 0,
        }
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.md"
            write_markdown_summary(results, path)
            text = path.read_text(encoding="utf-8")
        self.assertIn("do not prove unrestricted fluency", text)
        self.assertIn("Exact overlap", text)


if __name__ == "__main__":
    unittest.main()
