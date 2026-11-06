from __future__ import annotations

import asyncio
import re
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import edge_tts


@dataclass(slots=True)
class SynthesisResult:
    audio_path: Path
    duration_seconds: float
    provider_name: str


def measure_duration_seconds(path: Path, ffmpeg_path: str) -> float:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())
    command = [ffmpeg_path, "-i", str(path)]
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    output = process.stderr or process.stdout
    match = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", output)
    if not match:
        raise RuntimeError(f"Could not measure media duration for {path}")
    hours, minutes, seconds = match.groups()
    return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)


async def _edge_save(text: str, voice_profile: str, output_path: Path) -> None:
    communicator = edge_tts.Communicate(text, voice=voice_profile, rate="+4%")
    await communicator.save(str(output_path))


def synthesize_with_edge(text: str, voice_profile: str, output_path: Path) -> None:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            asyncio.run(_edge_save(text=text, voice_profile=voice_profile, output_path=output_path))
            if output_path.exists() and output_path.stat().st_size > 256:
                return
        except Exception as exc:
            last_error = exc
            time.sleep(1.5)
    raise RuntimeError(f"edge-tts synthesis failed: {last_error}")


def synthesize_with_windows_sapi(text: str, output_path: Path) -> None:
    text_path = output_path.with_suffix(".input.txt")
    text_path.write_text(text, encoding="utf-8")
    try:
        script = rf"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synth.GetInstalledVoices() | ForEach-Object {{ $_.VoiceInfo }} | Where-Object {{ $_.Culture.Name -eq 'zh-CN' }} | Select-Object -First 1
if ($voice) {{ $synth.SelectVoice($voice.Name) }}
$text = Get-Content -Raw -Encoding UTF8 '{text_path}'
$synth.Rate = 1
$synth.SetOutputToWaveFile('{output_path}')
$synth.Speak($text)
$synth.Dispose()
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        text_path.unlink(missing_ok=True)
    if not output_path.exists() or output_path.stat().st_size <= 64:
        raise RuntimeError("Windows SAPI synthesis produced no usable audio.")


def synthesize_voice(text: str, voice_profile: str, output_dir: Path, ffmpeg_path: str) -> SynthesisResult:
    edge_path = output_dir / "voice.mp3"
    try:
        synthesize_with_edge(text=text, voice_profile=voice_profile, output_path=edge_path)
        return SynthesisResult(
            audio_path=edge_path,
            duration_seconds=measure_duration_seconds(edge_path, ffmpeg_path),
            provider_name="edge-tts",
        )
    except Exception:
        wave_path = output_dir / "voice.wav"
        synthesize_with_windows_sapi(text=text, output_path=wave_path)
        return SynthesisResult(
            audio_path=wave_path,
            duration_seconds=measure_duration_seconds(wave_path, ffmpeg_path),
            provider_name="windows-sapi",
        )

