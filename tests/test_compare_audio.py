"""Tests for `zv compare-audio` — multi-engine bakeoff.

Uses injected fake transcriber + probe; no subprocess. Sidecar JSON
parsing + winner-picking + table rendering all covered without touching
whisper or ffmpeg.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zeststream_voice.commands.compare_audio import (
    engine_label,
    load_sidecar,
    pick_winners,
    render_table,
    score_many,
)
from zeststream_voice.commands.score_audio import AudioProbe


# ---------------------------------------------------------------------------
# Sidecar parsing
# ---------------------------------------------------------------------------


def test_load_sidecar_missing_returns_empty_dict(tmp_path: Path):
    wav = tmp_path / "voicebox.wav"
    wav.write_bytes(b"fake")
    assert load_sidecar(wav) == {}


def test_load_sidecar_present_parses_json(tmp_path: Path):
    wav = tmp_path / "voicebox.wav"
    wav.write_bytes(b"fake")
    sidecar = wav.with_suffix(".json")
    sidecar.write_text(
        json.dumps({"engine": "voicebox", "latency_s": 3.2}),
        encoding="utf-8",
    )
    meta = load_sidecar(wav)
    assert meta == {"engine": "voicebox", "latency_s": 3.2}


def test_load_sidecar_malformed_returns_error(tmp_path: Path):
    wav = tmp_path / "bad.wav"
    wav.write_bytes(b"fake")
    wav.with_suffix(".json").write_text("{ not json", encoding="utf-8")
    meta = load_sidecar(wav)
    assert "_sidecar_error" in meta


def test_engine_label_prefers_sidecar(tmp_path: Path):
    wav = tmp_path / "take-01.wav"
    assert engine_label(wav, {"engine": "voicebox"}) == "voicebox"
    assert engine_label(wav, {}) == "take-01"


# ---------------------------------------------------------------------------
# score_many + pick_winners with fakes
# ---------------------------------------------------------------------------


def _fake_written_scorer(composite: float):
    def _s(transcript: str) -> dict:
        return {"composite": composite, "passed": composite >= 95.0, "layers": {}}
    return _s


def _make_wav(path: Path, sidecar: dict | None = None):
    path.write_bytes(b"fake")
    if sidecar is not None:
        path.with_suffix(".json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )


def test_score_many_attaches_sidecar_metadata(tmp_path: Path):
    wav_a = tmp_path / "voicebox.wav"
    wav_b = tmp_path / "coqui.wav"
    _make_wav(wav_a, {"engine": "voicebox-v1", "latency_s": 3.2})
    _make_wav(wav_b, {"engine": "coqui-xtts", "latency_s": 5.7})

    def transcribe(p: Path) -> str:
        return {wav_a: "hello world one two three",
                wav_b: "hello world four five six"}[p]

    def probe(p: Path) -> AudioProbe:
        return AudioProbe(duration_s=2.3, silences=[], clipping_detected=False)

    rows = score_many(
        wavs=[wav_a, wav_b],
        reference_script="hello world one two three",
        transcriber=transcribe,
        audio_probe=probe,
        written_scorer=_fake_written_scorer(95.0),
    )
    assert len(rows) == 2
    assert rows[0]["engine"] == "voicebox-v1"
    assert rows[0]["latency_s"] == 3.2
    assert rows[1]["engine"] == "coqui-xtts"
    assert rows[1]["latency_s"] == 5.7
    # voicebox matches reference 100%, coqui only 40% (3 of 5 substituted)
    assert rows[0]["fidelity_pct"] > rows[1]["fidelity_pct"]


def test_pick_winners_picks_right_engine_per_axis(tmp_path: Path):
    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    _make_wav(wav_a, {"engine": "alpha", "latency_s": 2.0})
    _make_wav(wav_b, {"engine": "beta", "latency_s": 6.0})

    def transcribe(p: Path) -> str:
        return {wav_a: "hello world one two three",
                wav_b: "hello world one two three"}[p]

    def probe_a_clean(p: Path) -> AudioProbe:
        # Perfect pacing + no silences for alpha; messy for beta.
        if p == wav_a:
            return AudioProbe(duration_s=2.3, silences=[], clipping_detected=False)
        return AudioProbe(
            duration_s=30.0,
            silences=[(10.0, 3.0), (20.0, 2.5)],
            clipping_detected=False,
        )

    rows = score_many(
        wavs=[wav_a, wav_b],
        reference_script="hello world one two three",
        transcriber=transcribe,
        audio_probe=probe_a_clean,
        written_scorer=_fake_written_scorer(95.0),
    )
    winners = pick_winners(rows)
    assert winners["composite"] == "alpha"
    assert winners["pacing"] == "alpha"
    assert winners["silence_glitch"] == "alpha"
    # Both matched 100%, ties go to first seen (alpha).
    assert winners["fidelity"] == "alpha"
    # Latency: alpha 2.0 < beta 6.0
    assert winners["latency"] == "alpha"


def test_pick_winners_latency_missing_on_all_rows(tmp_path: Path):
    wav = tmp_path / "solo.wav"
    _make_wav(wav, {"engine": "solo"})  # No latency_s

    rows = score_many(
        wavs=[wav],
        reference_script=None,
        transcriber=lambda p: "hi there",
        audio_probe=lambda p: AudioProbe(
            duration_s=2.3, silences=[], clipping_detected=False
        ),
        written_scorer=_fake_written_scorer(95.0),
    )
    winners = pick_winners(rows)
    # latency key absent when no row has latency_s
    assert "latency" not in winners
    assert winners["composite"] == "solo"


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------


def test_render_table_empty_rows():
    out = render_table([], {})
    assert "no wavs" in out


def test_render_table_columns_and_winners(tmp_path: Path):
    wav_a = tmp_path / "alpha.wav"
    wav_b = tmp_path / "beta.wav"
    _make_wav(wav_a, {"engine": "alpha", "latency_s": 2.0})
    _make_wav(wav_b, {"engine": "beta", "latency_s": 6.0})

    rows = score_many(
        wavs=[wav_a, wav_b],
        reference_script="hi there",
        transcriber=lambda p: "hi there",
        audio_probe=lambda p: AudioProbe(
            duration_s=1.0, silences=[], clipping_detected=False
        ),
        written_scorer=_fake_written_scorer(95.0),
    )
    winners = pick_winners(rows)
    out = render_table(rows, winners)
    # Header row.
    assert "engine" in out and "composite" in out and "latency(s)" in out
    # Both engines appear.
    assert "alpha" in out and "beta" in out
    # Winners block.
    assert "WINNERS:" in out
    assert "composite" in out
