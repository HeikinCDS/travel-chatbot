"""Train and evaluate the travel chatbot's spaCy intent classifier.

Run this script from the project root:

    python scripts/train_intent_classifier.py

By default, it reads ``nlp/intents.json`` and saves the trained model,
evaluation metrics, and the reproducible data split under
``models/intent_classifier``.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import spacy
from spacy.training import Example
from spacy.util import compounding, minibatch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "nlp" / "intents.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "models" / "intent_classifier"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train and evaluate the spaCy intent classifier."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help=f"Path to intents JSON (default: {DEFAULT_DATA_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Directory for the trained model (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=30,
        help="Number of training epochs (default: 30)",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.20,
        help="Fraction of each intent reserved for testing (default: 0.20)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for a reproducible split and training run (default: 42)",
    )
    parser.add_argument(
        "--retrain-on-all",
        action="store_true",
        help=(
            "After measuring the split model, train the deployable model on "
            "all approved examples while retaining the split evaluation reports."
        ),
    )
    return parser.parse_args()


def load_intents(path: Path) -> dict[str, list[str]]:
    """Load and validate the intent dataset."""
    if not path.is_file():
        raise FileNotFoundError(f"Intent dataset not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        raw_data = json.load(file)

    intent_items = raw_data.get("intents")
    if not isinstance(intent_items, list) or not intent_items:
        raise ValueError("The JSON must contain a non-empty 'intents' list.")

    dataset: dict[str, list[str]] = {}
    seen_examples: dict[str, str] = {}

    for item in intent_items:
        if not isinstance(item, dict):
            raise ValueError("Every item in 'intents' must be an object.")

        label = item.get("label")
        examples = item.get("examples")

        if not isinstance(label, str) or not label.strip():
            raise ValueError("Every intent requires a non-empty string 'label'.")
        label = label.strip()

        if label in dataset:
            raise ValueError(f"Duplicate intent label: {label}")
        if not isinstance(examples, list) or len(examples) < 2:
            raise ValueError(f"Intent '{label}' requires at least two examples.")

        cleaned_examples: list[str] = []
        for example in examples:
            if not isinstance(example, str) or not example.strip():
                raise ValueError(f"Intent '{label}' contains an invalid example.")

            cleaned = example.strip()
            normalized = cleaned.casefold()
            if normalized in seen_examples:
                previous_label = seen_examples[normalized]
                raise ValueError(
                    f"Duplicate example '{cleaned}' found in intents "
                    f"'{previous_label}' and '{label}'."
                )

            seen_examples[normalized] = label
            cleaned_examples.append(cleaned)

        dataset[label] = cleaned_examples

    return dataset


def stratified_split(
    dataset: dict[str, list[str]], test_ratio: float, seed: int
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Split every intent separately so all labels occur in both sets."""
    if not 0.0 < test_ratio < 1.0:
        raise ValueError("--test-ratio must be greater than 0 and less than 1.")

    rng = random.Random(seed)
    train_data: list[tuple[str, str]] = []
    test_data: list[tuple[str, str]] = []

    for label, examples in dataset.items():
        shuffled = examples.copy()
        rng.shuffle(shuffled)

        test_count = max(1, round(len(shuffled) * test_ratio))
        test_count = min(test_count, len(shuffled) - 1)

        test_data.extend((text, label) for text in shuffled[:test_count])
        train_data.extend((text, label) for text in shuffled[test_count:])

    rng.shuffle(train_data)
    rng.shuffle(test_data)
    return train_data, test_data


def make_examples(
    nlp: spacy.language.Language,
    records: list[tuple[str, str]],
    labels: list[str],
) -> list[Example]:
    examples: list[Example] = []
    for text, correct_label in records:
        cats = {label: float(label == correct_label) for label in labels}
        examples.append(Example.from_dict(nlp.make_doc(text), {"cats": cats}))
    return examples


def train_model(
    train_data: list[tuple[str, str]],
    labels: list[str],
    epochs: int,
    seed: int,
) -> tuple[spacy.language.Language, list[dict[str, Any]]]:
    if epochs < 1:
        raise ValueError("--epochs must be at least 1.")

    random.seed(seed)
    spacy.util.fix_random_seed(seed)

    nlp = spacy.blank("en")
    textcat = nlp.add_pipe("textcat")
    for label in labels:
        textcat.add_label(label)

    train_examples = make_examples(nlp, train_data, labels)
    optimizer = nlp.initialize(lambda: train_examples)
    history: list[dict[str, Any]] = []

    for epoch in range(1, epochs + 1):
        random.shuffle(train_examples)
        losses: dict[str, float] = {}
        batches = minibatch(train_examples, size=compounding(4.0, 32.0, 1.001))

        for batch in batches:
            nlp.update(batch, sgd=optimizer, drop=0.20, losses=losses)

        epoch_loss = float(losses.get("textcat", 0.0))
        history.append({"epoch": epoch, "textcat_loss": round(epoch_loss, 6)})
        print(f"Epoch {epoch:02d}/{epochs} - textcat loss: {epoch_loss:.4f}")

    return nlp, history


def evaluate_model(
    nlp: spacy.language.Language,
    test_data: list[tuple[str, str]],
    labels: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    confusion = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    predictions: list[dict[str, Any]] = []
    correct = 0

    for text, actual in test_data:
        doc = nlp(text)
        predicted = max(doc.cats, key=doc.cats.get)
        confidence = float(doc.cats[predicted])
        confusion[actual][predicted] += 1
        correct += int(predicted == actual)
        predictions.append(
            {
                "text": text,
                "actual": actual,
                "predicted": predicted,
                "confidence": round(confidence, 6),
            }
        )

    per_intent: dict[str, dict[str, Any]] = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(
            confusion[actual][label] for actual in labels if actual != label
        )
        false_negative = sum(
            confusion[label][predicted]
            for predicted in labels
            if predicted != label
        )
        support = sum(confusion[label].values())

        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = true_positive / support if support else 0.0
        f1_score = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )

        per_intent[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "support": support,
        }

    accuracy = correct / len(test_data) if test_data else 0.0
    macro_f1 = sum(item["f1_score"] for item in per_intent.values()) / len(labels)
    metrics = {
        "accuracy": round(accuracy, 4),
        "macro_f1_score": round(macro_f1, 4),
        "correct_predictions": correct,
        "test_examples": len(test_data),
        "per_intent": per_intent,
        "confusion_matrix": confusion,
    }
    return metrics, predictions


def save_results(
    nlp: spacy.language.Language,
    output_path: Path,
    train_data: list[tuple[str, str]],
    test_data: list[tuple[str, str]],
    history: list[dict[str, Any]],
    metrics: dict[str, Any],
    predictions: list[dict[str, Any]],
    seed: int,
    test_ratio: float,
) -> None:
    if output_path.exists() and not output_path.is_dir():
        raise ValueError(f"The output path is not a directory: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(output_path)

    split = {
        "seed": seed,
        "test_ratio": test_ratio,
        "training_examples": [
            {"text": text, "label": label} for text, label in train_data
        ],
        "testing_examples": [
            {"text": text, "label": label} for text, label in test_data
        ],
    }

    result_files = {
        "metrics.json": metrics,
        "training_history.json": history,
        "data_split.json": split,
        "test_predictions.json": predictions,
    }
    for filename, content in result_files.items():
        with (output_path / filename).open("w", encoding="utf-8") as file:
            json.dump(content, file, indent=2, ensure_ascii=False)


def print_dataset_summary(
    train_data: list[tuple[str, str]], test_data: list[tuple[str, str]]
) -> None:
    train_counts = Counter(label for _, label in train_data)
    test_counts = Counter(label for _, label in test_data)

    print("\nData split")
    print("-" * 57)
    print(f"{'Intent':30} {'Training':>10} {'Testing':>10}")
    print("-" * 57)
    for label in sorted(train_counts):
        print(f"{label:30} {train_counts[label]:>10} {test_counts[label]:>10}")
    print("-" * 57)
    print(f"{'Total':30} {len(train_data):>10} {len(test_data):>10}\n")


def main() -> None:
    args = parse_args()
    data_path = args.data.resolve()
    output_path = args.output.resolve()

    dataset = load_intents(data_path)
    labels = list(dataset)
    train_data, test_data = stratified_split(
        dataset, test_ratio=args.test_ratio, seed=args.seed
    )

    print(f"Loaded {sum(map(len, dataset.values()))} examples from {data_path}")
    print_dataset_summary(train_data, test_data)

    nlp, history = train_model(
        train_data=train_data,
        labels=labels,
        epochs=args.epochs,
        seed=args.seed,
    )
    metrics, predictions = evaluate_model(nlp, test_data, labels)
    save_results(
        nlp=nlp,
        output_path=output_path,
        train_data=train_data,
        test_data=test_data,
        history=history,
        metrics=metrics,
        predictions=predictions,
        seed=args.seed,
        test_ratio=args.test_ratio,
    )

    if args.retrain_on_all:
        all_data = [
            (text, label)
            for label, examples in dataset.items()
            for text in examples
        ]
        print("\nRetraining deployable model on all approved examples")
        print("-" * 57)
        deployed_nlp, deployment_history = train_model(
            train_data=all_data,
            labels=labels,
            epochs=args.epochs,
            seed=args.seed,
        )
        deployed_nlp.to_disk(output_path)
        deployment = {
            "retrained_on_all_examples": True,
            "training_examples": len(all_data),
            "epochs": args.epochs,
            "seed": args.seed,
            "evaluation_reports_describe_split_model": True,
            "training_history": deployment_history,
        }
        with (output_path / "deployment_training.json").open(
            "w", encoding="utf-8"
        ) as file:
            json.dump(deployment, file, indent=2, ensure_ascii=False)

    print("\nEvaluation")
    print("-" * 40)
    print(f"Accuracy: {metrics['accuracy']:.2%}")
    print(f"Macro F1 score: {metrics['macro_f1_score']:.2%}")
    print(f"Correct: {metrics['correct_predictions']}/{metrics['test_examples']}")
    if args.retrain_on_all:
        print(
            "Deployed model retrained on all "
            f"{sum(map(len, dataset.values()))} examples."
        )
    print(f"Model and reports saved to: {output_path}")


if __name__ == "__main__":
    main()
