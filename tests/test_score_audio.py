"""Tests for `zv score-audio` — voice gate TTS extension.

Strategy: unit-test the pure pipeline with injected fake transcriber +
injected fake audio_probe (no subprocess). One end-to-end smoke test runs
the real whisper-cli against take2.wav if the binary + model are present
(otherwise it skips — no flaky CI).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zeststream_voice.commands.score_audio import (
    AudioProbe,
    _parse_ffmpeg_output,
    compose_composite,
    fidelity_percent,
    real_audio_probe,
    real_transcriber,
    score_audio_pipeline,
    score_fidelity,
    score_pacing,
    score_silence,
    tokenize,
    word_levenshtein,
)


TAKE2_WAV = Path.home() / "Developer/zesttube/.planning/shoot-takes/take2.wav"
TAKE2_TXT = Path.home() / "Developer/zesttube/.planning/shoot-takes/take2.txt"
WHISPER_BIN = Path("/opt/homebrew/bin/whisper-cli")
WHISPER_MODEL = Path.home() / "models/whisper/ggml-large-v3.bin"
FFMPEG_BIN = Path("/opt/homebrew/bin/ffmpeg")


# ---------------------------------------------------------------------------
# Unit: tokenization + levenshtein + fidelity
# ---------------------------------------------------------------------------


def test_tokenize_lowercases_and_strips_punctuation():
    assert tokenize("Hello, World! 2024") == ["hello", "world", "2024"]
    assert tokenize("don't worry") == ["don't", "worry"]
    assert tokenize("") == []


def test_word_levenshtein_basic():
    assert word_levenshtein([], []) == 0
    assert word_levenshtein(["a"], []) == 1
    assert word_levenshtein(["a", "b", "c"], ["a", "b", "c"]) == 0
    # One substitution:
    assert word_levenshtein(["a", "b", "c"], ["a", "X", "c"]) == 1
    # Insertion + substitution:
    assert word_levenshtein(["a", "b"], ["a", "c", "d"]) == 2


def test_fidelity_percent_identical():
    assert fidelity_percent("hello world", "Hello, world!") == 100.0


def test_fidelity_percent_total_mismatch():
    assert fidelity_percent("cat dog", "moon river sun") < 50.0


def test_fidelity_percent_partial():
    # 4 of 5 words match -> 1 substitution, dist=1, len=5, 80%
    pct = fidelity_percent(
        "the quick brown fox jumps",
        "the quick brown FROG jumps",
    )
    assert 78.0 <= pct <= 82.0


# ---------------------------------------------------------------------------
# Unit: dimension scores
# ---------------------------------------------------------------------------


def test_score_fidelity_bands():
    assert score_fidelity(100.0, has_reference=True) == 10.0
    assert score_fidelity(97.0, has_reference=True) == 8.0
    assert score_fidelity(92.0, has_reference=True) == 6.0
    assert score_fidelity(85.0, has_reference=True) == 5.0
    assert score_fidelity(50.0, has_reference=True) == 1.0
    # No reference -> 10 (doesn't drag composite).
    assert score_fidelity(0.0, has_reference=False) == 10.0


def test_score_pacing_bands():
    assert score_pacing(130.0) == 10.0  # reference
    assert score_pacing(120.0) == 10.0  # within 10%
    assert score_pacing(110.0) == 8.0   # ~15% off
    assert score_pacing(100.0) == 5.0   # ~23% off -> still within 30% band
    assert score_pacing(80.0) == 3.0    # ~38% off
    assert score_pacing(0.0) == 0.0


def test_score_silence_bands():
    assert score_silence(silence_count=0, clipping_detected=False) == 10.0
    assert score_silence(silence_count=1, clipping_detected=False) == 8.0
    assert score_silence(silence_count=2, clipping_detected=False) == 6.0
    assert score_silence(silence_count=5, clipping_detected=False) == 1.0
    # Clipping caps at 5 regardless of silences.
    assert score_silence(silence_count=0, clipping_detected=True) <= 5.0


# ---------------------------------------------------------------------------
# Unit: ffmpeg output parser (no subprocess)
# ---------------------------------------------------------------------------


FFMPEG_CLEAN = """
Input #0, wav, from 'take2.wav':
  Duration: 00:02:03.45, bitrate: 256 kb/s
  Stream #0:0: Audio: pcm_s16le, 16000 Hz, mono, s16, 256 kb/s
[Parsed_volumedetect] mean_volume: -25.3 dB
[Parsed_volumedetect] max_volume: -3.1 dB
"""

FFMPEG_WITH_SILENCE = """
Input #0, wav, from 'take.wav':
  Duration: 00:01:00.00, bitrate: 256 kb/s
[silencedetect @ 0x1] silence_start: 12.34
[silencedetect @ 0x1] silence_end: 14.00 | silence_duration: 1.66
[silencedetect @ 0x1] silence_start: 30.00
[silencedetect @ 0x1] silence_end: 32.50 | silence_duration: 2.50
[Parsed_volumedetect] max_volume: 0.5 dB
"""


def test_parse_ffmpeg_clean_recording():
    probe = _parse_ffmpeg_output(FFMPEG_CLEAN)
    assert probe.duration_s == pytest.approx(123.45, abs=0.05)
    assert probe.silences == []
    assert probe.clipping_detected is False
    assert probe.max_volume_db == pytest.approx(-3.1)


def test_parse_ffmpeg_with_silences_and_clipping():
    # Parser returns ALL detected silences; the pipeline filters by
    # SILENCE_MIN_S (currently 2.0s) before scoring.
    probe = _parse_ffmpeg_output(FFMPEG_WITH_SILENCE)
    assert probe.duration_s == 60.0
    assert len(probe.silences) == 2
    assert probe.silences[0] == (12.34, 1.66)
    assert probe.silences[1] == (30.0, 2.5)
    assert probe.clipping_detected is True
    assert probe.max_volume_db == 0.5


# ---------------------------------------------------------------------------
# Unit: score_audio_pipeline with injected fakes
# ---------------------------------------------------------------------------


def _fake_written_scorer_factory(composite: float = 95.0):
    def _scorer(text: str) -> dict:
        return {
            "composite": composite,
            "passed": composite >= 95.0,
            "layers": {},
            "text_len": len(text),
        }
    return _scorer


def _fake_transcriber(text: str):
    def _t(wav: Path) -> str:
        return text
    return _t


def _fake_probe(duration_s: float, silences=None, clipping=False):
    def _p(wav: Path) -> AudioProbe:
        return AudioProbe(
            duration_s=duration_s,
            silences=silences or [],
            clipping_detected=clipping,
            max_volume_db=-3.0 if not clipping else 0.5,
        )
    return _p


def test_pipeline_fidelity_100_on_identical_transcript_and_ref(tmp_path: Path):
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    result = score_audio_pipeline(
        wav=wav,
        reference_script="the quick brown fox jumps",
        transcriber=_fake_transcriber("The quick brown fox jumps."),
        audio_probe=_fake_probe(duration_s=2.3),  # 5 words / 2.3s = ~130 wpm
        written_scorer=_fake_written_scorer_factory(95.0),
    )
    assert result["has_reference"] is True
    assert result["fidelity_pct"] == 100.0
    assert result["audio_dims"]["fidelity"] == 10.0
    # 5 words / 2.3s = ~130 wpm -> pacing 10
    assert result["audio_dims"]["pacing"] == 10.0
    assert result["audio_dims"]["silence_glitch"] == 10.0
    # Composite = 0.7*95 + 0.3*100 = 96.5
    assert result["composite"] == pytest.approx(96.5, abs=0.1)


def test_pipeline_fidelity_drops_on_wrong_reference(tmp_path: Path):
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    result = score_audio_pipeline(
        wav=wav,
        reference_script="totally different words about something else",
        transcriber=_fake_transcriber("the quick brown fox jumps"),
        audio_probe=_fake_probe(duration_s=2.3),
        written_scorer=_fake_written_scorer_factory(95.0),
    )
    assert result["fidelity_pct"] < 50.0
    assert result["audio_dims"]["fidelity"] < 5.0


def test_pipeline_no_reference_still_works(tmp_path: Path):
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    result = score_audio_pipeline(
        wav=wav,
        reference_script=None,
        transcriber=_fake_transcriber("anything goes here five words"),
        audio_probe=_fake_probe(duration_s=2.3),
        written_scorer=_fake_written_scorer_factory(95.0),
    )
    assert result["has_reference"] is False
    # Fidelity slot is still 10 so it doesn't drag the composite; but the
    # composer drops it from the audio mean when no reference.
    assert result["audio_dims"]["fidelity"] == 10.0


def test_pipeline_bad_pacing_drags_composite(tmp_path: Path):
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    # 5 words in 10s = 30 wpm — way off reference.
    result = score_audio_pipeline(
        wav=wav,
        reference_script="hello hello hello hello hello",
        transcriber=_fake_transcriber("hello hello hello hello hello"),
        audio_probe=_fake_probe(duration_s=10.0),
        written_scorer=_fake_written_scorer_factory(100.0),
    )
    assert result["audio_dims"]["pacing"] <= 3.0
    assert result["audio_diagnostics"]["wpm"] == 30.0


def test_pipeline_silences_drag_composite(tmp_path: Path):
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    # Long duration so silences can be interior (not edge). 3 interior
    # silences each ≥SILENCE_MIN_S (2.0s) should count.
    result = score_audio_pipeline(
        wav=wav,
        reference_script=None,
        transcriber=_fake_transcriber("one two three four five"),
        audio_probe=_fake_probe(
            duration_s=60.0,
            silences=[(10.0, 2.5), (25.0, 2.1), (40.0, 3.2)],
        ),
        written_scorer=_fake_written_scorer_factory(100.0),
    )
    assert result["audio_diagnostics"]["silence_count"] == 3
    assert result["audio_dims"]["silence_glitch"] <= 5.0


# ---------------------------------------------------------------------------
# Compose composite bounds
# ---------------------------------------------------------------------------


def test_compose_composite_all_max():
    from zeststream_voice.commands.score_audio import AudioDims

    audio = AudioDims(
        fidelity=10.0, pacing=10.0, silence_glitch=10.0,
        fidelity_pct=100.0, word_count=100, wpm=130.0, silence_count=0,
    )
    assert compose_composite(100.0, audio, has_reference=True) == 100.0


def test_compose_composite_audio_drags_on_good_text():
    from zeststream_voice.commands.score_audio import AudioDims

    audio = AudioDims(
        fidelity=2.0, pacing=2.0, silence_glitch=2.0,
        fidelity_pct=20.0, word_count=100, wpm=50.0, silence_count=4,
    )
    # Written 95, audio mean 2 -> 20%. 0.7*95 + 0.3*20 = 72.5.
    assert compose_composite(95.0, audio, has_reference=True) == pytest.approx(72.5)


# ---------------------------------------------------------------------------
# Smoke: real whisper + ffmpeg against take2.wav (skips when env missing)
# ---------------------------------------------------------------------------


_CAN_SMOKE = (
    TAKE2_WAV.exists()
    and TAKE2_TXT.exists()
    and WHISPER_BIN.exists()
    and WHISPER_MODEL.exists()
    and FFMPEG_BIN.exists()
    and os.getenv("ZV_SKIP_AUDIO_SMOKE") != "1"
)


@pytest.mark.skipif(not _CAN_SMOKE, reason="whisper/ffmpeg/take2.wav not available")
def test_smoke_take2_real_pipeline():
    """End-to-end: real whisper + real ffmpeg on Joshua take2.wav baseline."""
    reference = TAKE2_TXT.read_text(encoding="utf-8")
    result = score_audio_pipeline(
        wav=TAKE2_WAV,
        reference_script=reference,
        transcriber=real_transcriber,
        audio_probe=real_audio_probe,
        written_scorer=_fake_written_scorer_factory(90.0),
    )
    # Fidelity against its own whisper-derived reference should be high.
    assert result["fidelity_pct"] >= 70.0, (
        f"unexpectedly low fidelity on take2 vs itself: {result['fidelity_pct']}"
    )
    # Joshua's natural pace should land in the pacing-10 or pacing-8 band.
    assert result["audio_dims"]["pacing"] >= 8.0, (
        f"pacing too off for take2: {result['audio_diagnostics']['wpm']} wpm"
    )
    # Clean recording -> silence should be ≥8.
    assert result["audio_dims"]["silence_glitch"] >= 8.0, (
        f"silence_glitch dropped: {result['audio_diagnostics']}"
    )
