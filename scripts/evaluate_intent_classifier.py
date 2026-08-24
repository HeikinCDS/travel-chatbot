"""Evaluate the deployed intent classifier on a fixed holdout dataset.

Run from the project root:

    python scripts/evaluate_intent_classifier.py

Use ``--output`` to save the complete metrics and predictions as JSON.
This script evaluates an existing model; it never trains or modifies one.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nlp.intent_classifier import IntentClassifier


DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "intent_classifier"
DEFAULT_CASES_PATH = PROJECT_ROOT / "evaluation" / "intent_queries.json"
DEFAULT_TRAINING_PATH = PROJECT_ROOT / "nlp" / "intents.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the trained intent classifier on fixed queries."
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--training-data", type=Path, default=DEFAULT_TRAINING_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON file for the complete evaluation results.",
    )
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Intent evaluation dataset not found: {path}")
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("The evaluation JSON must contain a non-empty list.")

    required = {"id", "text", "expected_intent"}
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not required <= case.keys():
            raise ValueError(f"Every case requires: {', '.join(sorted(required))}.")
        if not all(isinstance(case[key], str) and case[key].strip() for key in required):
            raise ValueError("Case IDs, texts and expected intents must be non-empty strings.")

        case_id = case["id"].strip()
        normalized_text = case["text"].strip().casefold()
        if case_id in seen_ids:
            raise ValueError(f"Duplicate evaluation case ID: {case_id}")
        if normalized_text in seen_texts:
            raise ValueError(f"Duplicate evaluation text: {case['text']}")
        seen_ids.add(case_id)
        seen_texts.add(normalized_text)
    return cases


def find_training_overlaps(cases: list[dict[str, str]], path: Path) -> list[str]:
    """Return evaluation IDs whose text appears exactly in the training data."""
    training = json.loads(path.read_text(encoding="utf-8"))
    training_texts = {
        text.strip().casefold()
        for intent in training["intents"]
        for text in intent["examples"]
    }
    return [
        case["id"]
        for case in cases
        if case["text"].strip().casefold() in training_texts
    ]


def calculate_metrics(
    cases: list[dict[str, str]],
    predict: Callable[[str], tuple[str, float]],
) -> dict:
    labels = sorted({case["expected_intent"] for case in cases})
    confusion = {
        actual: {predicted: 0 for predicted in labels}
        for actual in labels
    }
    predictions = []

    for case in cases:
        predicted, confidence = predict(case["text"])
        if predicted not in labels:
            raise ValueError(f"Model returned an unexpected intent: {predicted}")
        actual = case["expected_intent"]
        confusion[actual][predicted] += 1
        predictions.append(
            {
                "id": case["id"],
                "text": case["text"],
                "expected_intent": actual,
                "predicted_intent": predicted,
                "confidence": round(float(confidence), 6),
                "correct": predicted == actual,
            }
        )

    per_intent = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[actual][label] for actual in labels if actual != label)
        false_negative = sum(confusion[label][other] for other in labels if other != label)
        support = sum(confusion[label].values())
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1_score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_intent[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "support": support,
        }

    correct = sum(item["correct"] for item in predictions)
    return {
        "total_examples": len(cases),
        "correct_predictions": correct,
        "accuracy": round(correct / len(cases), 4),
        "macro_precision": round(sum(item["precision"] for item in per_intent.values()) / len(labels), 4),
        "macro_recall": round(sum(item["recall"] for item in per_intent.values()) / len(labels), 4),
        "macro_f1_score": round(sum(item["f1_score"] for item in per_intent.values()) / len(labels), 4),
        "per_intent": per_intent,
        "confusion_matrix": confusion,
        "predictions": predictions,
    }


def print_report(metrics: dict) -> None:
    print("Intent classification evaluation")
    print("-" * 78)
    print(
        f"Examples: {metrics['total_examples']} | "
        f"Correct: {metrics['correct_predictions']} | "
        f"Accuracy: {metrics['accuracy']:.2%} | "
        f"Macro F1: {metrics['macro_f1_score']:.2%}"
    )
    print()
    print(f"{'Intent':<28}{'Precision':>12}{'Recall':>12}{'F1':>12}{'Support':>10}")
    print("-" * 74)
    for label, values in metrics["per_intent"].items():
        print(
            f"{label:<28}{values['precision']:>12.2%}"
            f"{values['recall']:>12.2%}{values['f1_score']:>12.2%}"
            f"{values['support']:>10}"
        )

    mistakes = [item for item in metrics["predictions"] if not item["correct"]]
    print(f"\nMisclassified examples: {len(mistakes)}")
    for item in mistakes:
        print(
            f"{item['id']} | expected {item['expected_intent']} | "
            f"predicted {item['predicted_intent']} "
            f"({item['confidence']:.3f}) | {item['text']}"
        )


def main() -> None:
    args = parse_args()
    cases = load_cases(args.cases.resolve())
    overlaps = find_training_overlaps(cases, args.training_data.resolve())
    if overlaps:
        raise ValueError(
            "Evaluation examples must not occur in the training data. "
            f"Overlapping case IDs: {', '.join(overlaps)}"
        )

    classifier = IntentClassifier(args.model.resolve())

    def predict(text: str) -> tuple[str, float]:
        result = classifier.predict(text)
        return result.label, result.confidence

    metrics = calculate_metrics(cases, predict)
    metrics["model_path"] = str(args.model.resolve())
    metrics["cases_path"] = str(args.cases.resolve())
    metrics["training_overlap_count"] = 0
    print_report(metrics)

    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"\nFull results saved to: {output}")


if __name__ == "__main__":
    main()
