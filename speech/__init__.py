"""Offline speech generation for Maya's read-aloud feature."""

from .synthesizer import SpeechSynthesisError, synthesize_speech

__all__ = ["SpeechSynthesisError", "synthesize_speech"]
