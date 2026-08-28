"""Evaluate JomVoyage's Malay and Chinese input-understanding layer.

This fixed holdout evaluates the complete deterministic normalization plus
spaCy intent-classification path. It never trains or modifies the model.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nlp.entity_extractor import extract_preferences
from nlp.intent_classifier import IntentClassifier
from nlp.multilingual_normalizer import (
    SUPPORTED_INPUT_LANGUAGES,
    normalize_user_input,
)
from scripts.evaluate_intent_classifier import calculate_metrics, find_training_overlaps


DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "intent_classifier"
DEFAULT_CASES_PATH = PROJECT_ROOT / "evaluation" / "multilingual_queries.json"
DEFAULT_TRAINING_PATH = PROJECT_ROOT / "nlp" / "intents.json"
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "evaluation" / "multilingual_evaluation_results.json"
)
DEFAULT_SUMMARY_PATH = (
    PROJECT_ROOT / "evaluation" / "multilingual_evaluation_summary.md"
)

# ChatbotService gives direct information phrases priority over the statistical
# label because a place name such as "Penang Hill" also contains a state name.
# The evaluation mirrors that production routing rule.
DIRECT_INFORMATION_PATTERN = re.compile(
    r"\b(?:tell\s+me\s+about|information\s+(?:about|on)|"
    r"what\s+(?:is|are)|describe|details?\s+(?:about|on))\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Malay and Chinese input understanding."
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--training-data", type=Path, default=DEFAULT_TRAINING_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    return parser.parse_args()


def load_multilingual_cases(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Multilingual evaluation dataset not found: {path}")
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("The multilingual evaluation JSON must be a non-empty list.")

    required = {"id", "language", "text", "expected_intent"}
    seen_ids: set[str] = set()
    seen_texts: set[tuple[str, str]] = set()
    for case in cases:
        if not isinstance(case, dict) or not required <= case.keys():
            raise ValueError(f"Every case requires: {', '.join(sorted(required))}.")
        if not all(isinstance(case[key], str) and case[key].strip() for key in required):
            raise ValueError("Required multilingual case values must be non-empty strings.")
        if case["language"] not in SUPPORTED_INPUT_LANGUAGES - {"en"}:
            raise ValueError(f"Unsupported evaluation language: {case['language']}")
        if case["id"] in seen_ids:
            raise ValueError(f"Duplicate evaluation case ID: {case['id']}")
        text_key = (case["language"], case["text"].strip().casefold())
        if text_key in seen_texts:
            raise ValueError(f"Duplicate evaluation text: {case['text']}")
        if "expected_preferences" in case and not isinstance(
            case["expected_preferences"], dict
        ):
            raise ValueError("expected_preferences must be an object when provided.")
        seen_ids.add(case["id"])
        seen_texts.add(text_key)
    return cases


def _score_cases(cases: list[dict], classifier: IntentClassifier) -> dict:
    normalized_cases = []
    normalized_by_id = {}
    original_by_id = {}
    language_by_id = {}
    for case in cases:
        normalized = normalize_user_input(case["text"], case["language"])
        normalized_by_id[case["id"]] = normalized
        original_by_id[case["id"]] = case["text"]
        language_by_id[case["id"]] = case["language"]
        normalized_cases.append(
            {
                "id": case["id"],
                "text": normalized,
                "expected_intent": case["expected_intent"],
            }
        )

    def predict(text: str) -> tuple[str, float]:
        if DIRECT_INFORMATION_PATTERN.search(text):
            return "request_information", 1.0
        prediction = classifier.predict(text)
        return prediction.label, prediction.confidence

    metrics = calculate_metrics(normalized_cases, predict)
    for prediction in metrics["predictions"]:
        case_id = prediction["id"]
        prediction["original_text"] = original_by_id[case_id]
        prediction["language"] = language_by_id[case_id]
        prediction["normalized_text"] = normalized_by_id[case_id]
        prediction.pop("text", None)
    return metrics


def calculate_entity_metrics(cases: list[dict]) -> dict:
    predictions = []
    total_fields = 0
    correct_fields = 0
    perfect_cases = 0
    evaluated_cases = 0

    for case in cases:
        expected = case.get("expected_preferences")
        if not expected:
            continue
        evaluated_cases += 1
        normalized = normalize_user_input(case["text"], case["language"])
        actual = extract_preferences(normalized).to_dict()
        field_results = {}
        for key, expected_value in expected.items():
            total_fields += 1
            correct = actual.get(key) == expected_value
            correct_fields += int(correct)
            field_results[key] = {
                "expected": expected_value,
                "actual": actual.get(key),
                "correct": correct,
            }
        perfect = all(item["correct"] for item in field_results.values())
        perfect_cases += int(perfect)
        predictions.append(
            {
                "id": case["id"],
                "language": case["language"],
                "original_text": case["text"],
                "normalized_text": normalized,
                "perfect": perfect,
                "fields": field_results,
            }
        )

    return {
        "evaluated_cases": evaluated_cases,
        "perfect_cases": perfect_cases,
        "case_accuracy": round(perfect_cases / evaluated_cases, 4),
        "evaluated_fields": total_fields,
        "correct_fields": correct_fields,
        "field_accuracy": round(correct_fields / total_fields, 4),
        "predictions": predictions,
    }


def evaluate(cases: list[dict], classifier: IntentClassifier) -> dict:
    overall = _score_cases(cases, classifier)
    languages = sorted({case["language"] for case in cases})
    per_language = {
        language: _score_cases(
            [case for case in cases if case["language"] == language],
            classifier,
        )
        for language in languages
    }
    return {
        "dataset_summary": {
            "total_examples": len(cases),
            "language_counts": dict(Counter(case["language"] for case in cases)),
            "intent_counts": dict(Counter(case["expected_intent"] for case in cases)),
        },
        "intent_classification": overall,
        "per_language": per_language,
        "entity_extraction": calculate_entity_metrics(cases),
    }


def print_report(results: dict) -> None:
    overall = results["intent_classification"]
    entities = results["entity_extraction"]
    print("Multilingual input-understanding evaluation")
    print("-" * 72)
    print(
        f"Examples: {overall['total_examples']} | "
        f"Correct routed intents: {overall['correct_predictions']} | "
        f"Routing accuracy: {overall['accuracy']:.2%} | "
        f"Macro F1: {overall['macro_f1_score']:.2%}"
    )
    for language, metrics in results["per_language"].items():
        print(
            f"{language.upper():<3} routing accuracy: {metrics['accuracy']:.2%} | "
            f"Macro F1: {metrics['macro_f1_score']:.2%}"
        )
    print(
        f"Entity fields: {entities['correct_fields']}/{entities['evaluated_fields']} "
        f"correct ({entities['field_accuracy']:.2%}) | "
        f"Perfect cases: {entities['perfect_cases']}/{entities['evaluated_cases']}"
    )

    mistakes = [
        item for item in overall["predictions"] if not item["correct"]
    ]
    print(f"\nMisclassified examples: {len(mistakes)}")
    for item in mistakes:
        print(
            f"{item['id']} | expected {item['expected_intent']} | "
            f"predicted {item['predicted_intent']} ({item['confidence']:.3f}) | "
            f"{item['normalized_text']}"
        )

    entity_mistakes = [
        item for item in entities["predictions"] if not item["perfect"]
    ]
    print(f"Entity-extraction mistakes: {len(entity_mistakes)}")
    for item in entity_mistakes:
        wrong = [key for key, value in item["fields"].items() if not value["correct"]]
        print(f"{item['id']} | incorrect fields: {', '.join(wrong)}")


def write_markdown_summary(results: dict, path: Path) -> None:
    overall = results["intent_classification"]
    entities = results["entity_extraction"]
    malay = results["per_language"]["ms"]
    chinese = results["per_language"]["zh"]
    content = f"""# Multilingual Input Evaluation

## Evaluation design

JomVoyage was evaluated using a fixed holdout of {overall['total_examples']} messages that are not present in the spaCy intent-classifier training dataset. The holdout contains 27 Bahasa Melayu and 27 Simplified Chinese messages. Each language contains three examples for all nine supported intents. Twelve cases additionally test extraction of state, interest, budget and elderly-accessibility preferences.

The evaluated pipeline is the same hybrid path used by the application: deterministic offline language normalization, production rule-based intent routing and the deployed spaCy classifier. No paid translation API or online language model is used.

## Results

| Measurement | Result |
|---|---:|
| Overall routed-intent accuracy | {overall['accuracy']:.2%} |
| Overall macro F1 | {overall['macro_f1_score']:.2%} |
| Bahasa Melayu routed-intent accuracy | {malay['accuracy']:.2%} |
| Simplified Chinese routed-intent accuracy | {chinese['accuracy']:.2%} |
| Entity-field accuracy | {entities['field_accuracy']:.2%} ({entities['correct_fields']}/{entities['evaluated_fields']}) |
| Fully correct entity cases | {entities['perfect_cases']}/{entities['evaluated_cases']} |
| Exact overlap with intent training examples | {results['training_overlap_count']} |

## Interpretation and limitations

These results demonstrate reliable handling of the controlled vocabulary and phrase patterns currently supported by the prototype. They do not prove unrestricted fluency in Malay or Chinese. Real users may use dialects, spelling variations, mixed languages or phrases outside the current normalization vocabulary. The holdout should therefore be expanded using messages collected from elderly-user usability testing. Attraction names and stored descriptions may also remain in English even when the interface language changes.

## Reproduction

Run `python scripts/evaluate_multilingual_input.py` from the project root. Complete per-message predictions are saved in `evaluation/multilingual_evaluation_results.json`.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    cases = load_multilingual_cases(args.cases.resolve())
    overlaps = find_training_overlaps(cases, args.training_data.resolve())
    if overlaps:
        raise ValueError(
            "Multilingual holdout messages must not occur in the training data. "
            f"Overlapping case IDs: {', '.join(overlaps)}"
        )
    classifier = IntentClassifier(args.model.resolve())
    results = evaluate(cases, classifier)
    results["model_path"] = str(args.model.resolve())
    results["cases_path"] = str(args.cases.resolve())
    results["training_data_path"] = str(args.training_data.resolve())
    results["training_overlap_count"] = 0
    print_report(results)

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nFull results saved to: {output}")

    summary = args.summary.resolve()
    write_markdown_summary(results, summary)
    print(f"Report summary saved to: {summary}")


if __name__ == "__main__":
    main()
