from pathlib import Path
import unittest
from unittest.mock import patch

from speech.synthesizer import synthesize_speech


class SpeechSynthesizerTests(unittest.TestCase):
    def test_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            synthesize_speech("   ")

    def test_rejects_excessively_long_text(self):
        with self.assertRaises(ValueError):
            synthesize_speech("a" * 3001)

    @patch("speech.synthesizer._run_windows_sapi")
    def test_returns_generated_wav_bytes(self, run_windows_sapi):
        expected = b"RIFF" + (b"\x00" * 40) + b"WAVE"

        def create_audio(text: str, output_path: Path, language: str) -> None:
            self.assertEqual(text, "Hello from Maya")
            self.assertEqual(language, "en")
            output_path.write_bytes(expected)

        run_windows_sapi.side_effect = create_audio

        self.assertEqual(synthesize_speech(" Hello   from Maya "), expected)

    def test_rejects_unsupported_language(self):
        with self.assertRaises(ValueError):
            synthesize_speech("Bonjour", language="fr")


if __name__ == "__main__":
    unittest.main()
