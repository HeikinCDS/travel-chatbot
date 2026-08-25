"""Generate WAV speech with the built-in Windows SAPI voice."""

from __future__ import annotations

import base64
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


MAX_SPEECH_TEXT_LENGTH = 3000
LANGUAGE_PREFIXES = {
    "en": "en",
    "ms": "ms",
    "zh": "zh",
}


class SpeechSynthesisError(RuntimeError):
    """Raised when the local speech engine cannot create an audio file."""


def _validated_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    text = " ".join(text.split())
    if not text:
        raise ValueError("text must not be empty")
    if len(text) > MAX_SPEECH_TEXT_LENGTH:
        raise ValueError(
            f"text must not exceed {MAX_SPEECH_TEXT_LENGTH} characters"
        )
    return text


def _run_windows_sapi(text: str, output_path: Path, language: str) -> None:
    if sys.platform != "win32":
        raise SpeechSynthesisError("Windows speech synthesis is unavailable")
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise SpeechSynthesisError("Windows PowerShell is unavailable")

    text_base64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    path_base64 = base64.b64encode(
        str(output_path).encode("utf-8")
    ).decode("ascii")
    language_prefix = LANGUAGE_PREFIXES[language]
    script = f"""
Add-Type -AssemblyName System.Speech
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{text_base64}'))
$outputPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{path_base64}'))
$synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
    $languagePrefix = '{language_prefix}'
    $languageVoices = $synthesizer.GetInstalledVoices() |
        Where-Object {{
            $_.Enabled -and
            $_.VoiceInfo.Culture.Name.StartsWith($languagePrefix)
        }}
    $selectedVoice = $languageVoices |
        Where-Object {{
            $_.VoiceInfo.Gender -eq [System.Speech.Synthesis.VoiceGender]::Female
        }} | Select-Object -First 1
    if (-not $selectedVoice) {{
        $selectedVoice = $languageVoices | Select-Object -First 1
    }}
    if (-not $selectedVoice) {{
        $selectedVoice = $synthesizer.GetInstalledVoices() |
            Where-Object {{ $_.Enabled }} | Select-Object -First 1
    }}
    if ($selectedVoice) {{
        $synthesizer.SelectVoice($selectedVoice.VoiceInfo.Name)
    }}
    $synthesizer.Rate = -1
    $synthesizer.Volume = 100
    $synthesizer.SetOutputToWaveFile($outputPath)
    $synthesizer.Speak($text)
}} finally {{
    $synthesizer.Dispose()
}}
"""
    encoded_command = base64.b64encode(
        script.encode("utf-16-le")
    ).decode("ascii")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded_command,
            ],
            check=True,
            capture_output=True,
            timeout=20,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SpeechSynthesisError(
            "The Windows speech engine could not create audio"
        ) from error


def synthesize_speech(text: str, language: str = "en") -> bytes:
    """Return a WAV file containing spoken ``text`` without using an API."""

    text = _validated_text(text)
    if language not in LANGUAGE_PREFIXES:
        raise ValueError("language must be 'en', 'ms' or 'zh'")
    with tempfile.TemporaryDirectory(prefix="jomvoyage-speech-") as directory:
        output_path = Path(directory) / "maya-response.wav"
        _run_windows_sapi(text, output_path, language)
        try:
            audio = output_path.read_bytes()
        except OSError as error:
            raise SpeechSynthesisError(
                "The Windows speech engine did not return an audio file"
            ) from error
    if len(audio) < 44 or not audio.startswith(b"RIFF"):
        raise SpeechSynthesisError("The generated WAV audio is invalid")
    return audio
