"""Runtime wrapper for the trained spaCy intent-classification model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "intent_classifier"


@dataclass(frozen=True)
class IntentPrediction:
    """The best intent label and all scores produced by the model."""

    label: str
    confidence: float
    scores: Mapping[str, float]

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "scores": dict(self.scores),
        }


class IntentClassifier:
    """Load the trained model once and classify multiple messages."""

    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH):
        try:
            import spacy
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "spaCy is required to load the intent classifier. "
                "Activate the project virtual environment and install the "
                "packages from requirements.txt."
            ) from error

        self.model_path = Path(model_path).resolve()
        if not self.model_path.is_dir():
            raise FileNotFoundError(
                f"Intent-classifier model not found: {self.model_path}"
            )
        self.nlp = spacy.load(self.model_path)

    def predict(self, text: str) -> IntentPrediction:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text.strip():
            raise ValueError("text must not be empty")

        document = self.nlp(text.strip())
        if not document.cats:
            raise RuntimeError("The loaded model did not produce intent scores")

        label = max(document.cats, key=document.cats.get)
        scores = {
            name: round(float(score), 6)
            for name, score in document.cats.items()
        }
        return IntentPrediction(
            label=label,
            confidence=scores[label],
            scores=scores,
        )
