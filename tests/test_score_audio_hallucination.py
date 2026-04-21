"""Tests for the hallucination dim + composite cap.

Motivated by a real P1: Qwen 1.7B TTS produced audio scoring composite
100 / PASS despite 24 hallucinated words (spurious intro + mid-insert +
end-loop). This dim is pure text math; no whisper/ffmpeg needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zeststream_voice.commands.score_audio import (
    AudioProbe,
    apply_hallucination_cap,
    compute_hallucination_dim,
    score_audio_pipeline,
)


# ---------------------------------------------------------------------------
# Real artifacts
# ---------------------------------------------------------------------------


VOICE_SAMPLES = Path.home() / "Developer/zesttube/voice-samples"
SCRIPT_200W = VOICE_SAMPLES / "test-script-200w.txt"
QWEN_TRANSCRIPT = VOICE_SAMPLES / "qwen-1.7b-200w.txt"


# ---------------------------------------------------------------------------
# Unit: compute_hallucination_dim
# ---------------------------------------------------------------------------


def test_identical_reference_scores_100():
    ref = "The quick brown fox jumps over the lazy dog in the morning sun."
    halluc = compute_hallucination_dim(ref, ref)
    assert halluc["score"] == 100.0
    assert halluc["extra_words"] == 0
    assert halluc["longest_match_coverage"] == 1.0
    assert halluc["repeated_phrases"] == []
    assert halluc["flags"] == []


def test_10_percent_extra_words_is_acceptable():
    """10% extra words, all within the slack budget → no penalty."""
    ref = " ".join(f"word{i}" for i in range(100))
    # Pad with 5 extra words at end — within 5% slack window.
    trans = ref + " padding padding padding padding padding"
    halluc = compute_hallucination_dim(ref, trans)
    # 5 extra words == 5% slack boundary — zero extra beyond slack.
    assert halluc["extra_words"] == 0
    # No drift flags because head matches.
    assert "spurious_prefix" not in halluc["flags"]


def test_20_percent_extra_words_penalized():
    ref = " ".join(f"word{i}" for i in range(100))
    trans = ref + " " + " ".join(f"extra{i}" for i in range(20))
    halluc = compute_hallucination_dim(ref, trans)
    # 20 transcript words beyond slack budget (105). 115 - 105 = 10 extra.
    assert halluc["extra_words"] >= 10
    assert halluc["penalties"]["extra_words"] >= 20.0
    assert halluc["score"] < 85.0


def test_spurious_prefix_drift_flagged():
    """A substantial spurious prefix shifts the first-20-token window enough
    that the SequenceMatcher ratio drops below the drift threshold.
    """
    ref = " ".join(f"reference{i}" for i in range(50))
    # Insert 15 totally unrelated words at the start — enough to dominate
    # the first-20-token window vs reference's first-20.
    prefix = " ".join(f"alien{i}" for i in range(15))
    trans = prefix + " " + ref
    halluc = compute_hallucination_dim(ref, trans)
    assert "spurious_prefix" in halluc["flags"]
    assert halluc["prefix_drift_ratio"] < 0.6


def test_end_loop_flagged_via_repetition():
    """A 5-gram from the middle that repeats twice → repeated_phrase flag."""
    ref = (
        "OpenAI shipped a new model called GPT-7. The model handles images, "
        "audio, and text. It costs less than the previous version. "
        "Developers should try it today."
    )
    # Re-read the middle sentence at the end (end-loop simulation).
    trans = ref + " The model handles images, audio, and text."
    halluc = compute_hallucination_dim(ref, trans)
    assert len(halluc["repeated_phrases"]) >= 1
    assert "repeated_phrase" in halluc["flags"]
    assert halluc["penalties"]["repeated_phrases"] >= 10.0


def test_broken_midscript_low_longest_match():
    """Transcript shares only a short block with script → low longest-match."""
    ref = " ".join(f"script{i}" for i in range(100))
    # Only the first 10 words match, rest is garbage.
    trans = " ".join(f"script{i}" for i in range(10)) + " " + " ".join(
        f"garbage{i}" for i in range(90)
    )
    halluc = compute_hallucination_dim(ref, trans)
    assert halluc["longest_match_coverage"] <= 0.15
    assert "broken_midscript" in halluc["flags"]
    assert halluc["penalties"]["longest_match"] >= 20.0


def test_severe_drift_floors_to_zero():
    """Huge extra-word count pushes score to 0 floor, never negative."""
    ref = "short reference text"
    trans = " ".join(f"noise{i}" for i in range(200))
    halluc = compute_hallucination_dim(ref, trans)
    assert halluc["score"] == 0.0


# ---------------------------------------------------------------------------
# Golden: real Qwen 1.7B sample should fail hard
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (SCRIPT_200W.exists() and QWEN_TRANSCRIPT.exists()),
    reason="voice-samples not available",
)
def test_qwen_1_7b_real_sample_scores_low_halluc():
    """Documented hallucinations: spurious intro, mid-insert, end-loop.

    Must score hallucination < 70 so composite gets capped at ≤75.
    """
    ref = SCRIPT_200W.read_text(encoding="utf-8")
    trans = QWEN_TRANSCRIPT.read_text(encoding="utf-8")
    halluc = compute_hallucination_dim(ref, trans)
    assert halluc["score"] < 70.0, (
        f"qwen-1.7b should trip the cap but scored {halluc['score']}; "
        f"flags={halluc['flags']}, penalties={halluc['penalties']}"
    )
    # End-loop repeats the OpenAI paragraph → must flag repeated_phrase.
    assert "repeated_phrase" in halluc["flags"]


# ---------------------------------------------------------------------------
# apply_hallucination_cap thresholds
# ---------------------------------------------------------------------------


def test_cap_passes_through_when_halluc_ok():
    assert apply_hallucination_cap(98.0, hallucination_score=95.0) == 98.0
    assert apply_hallucination_cap(98.0, hallucination_score=70.0) == 98.0  # boundary


def test_cap_soft_kicks_in_below_70():
    assert apply_hallucination_cap(98.0, hallucination_score=69.9) == 75.0
    assert apply_hallucination_cap(80.0, hallucination_score=60.0) == 75.0
    # If raw composite is below the cap, don't raise it.
    assert apply_hallucination_cap(40.0, hallucination_score=60.0) == 40.0


def test_cap_hard_kicks_in_below_50():
    assert apply_hallucination_cap(98.0, hallucination_score=49.9) == 50.0
    assert apply_hallucination_cap(98.0, hallucination_score=0.0) == 50.0


# ---------------------------------------------------------------------------
# Pipeline integration: cap triggers composite change
# ---------------------------------------------------------------------------


def _fake_written_scorer(composite: float = 100.0):
    def _s(text: str) -> dict:
        return {"composite": composite, "passed": composite >= 95.0, "layers": {}}
    return _s


def _fake_transcriber(text: str):
    def _t(wav: Path) -> str:
        return text
    return _t


def _fake_probe(duration_s: float = 10.0):
    def _p(wav: Path) -> AudioProbe:
        return AudioProbe(
            duration_s=duration_s, silences=[], clipping_detected=False
        )
    return _p


def test_pipeline_clean_synthetic_hits_100(tmp_path: Path):
    """Transcript == reference → composite 100, no cap applied."""
    wav = tmp_path / "clean.wav"
    wav.write_bytes(b"fake")
    ref = " ".join(f"w{i}" for i in range(22))  # ~130 wpm in 10s
    result = score_audio_pipeline(
        wav=wav,
        reference_script=ref,
        transcriber=_fake_transcriber(ref),
        audio_probe=_fake_probe(duration_s=10.0),
        written_scorer=_fake_written_scorer(100.0),
    )
    assert result["hallucination"]["score"] == 100.0
    assert result["hallucination_cap_triggered"] is False
    assert result["composite"] == result["composite_raw"]
    assert result["composite"] == 100.0


def test_pipeline_qwen_style_sample_caps_composite(tmp_path: Path):
    """Synthetic mimic of the Qwen failure: script + 24 extra words + end-loop.

    Composite should be capped at ≤75 from whatever raw score the other
    dims produced (which would have been 100).
    """
    wav = tmp_path / "qwen.wav"
    wav.write_bytes(b"fake")
    ref = (
        "Anthropic shipped a new context window. Grok handles longer tool "
        "chains. OpenAI released a smaller model. Everything ships weekly now."
    )
    # 24 extra words + re-read of the OpenAI sentence at end.
    trans = (
        "That is what makes it exciting. "
        + ref
        + " And that is what makes it exciting. "
        + "OpenAI released a smaller model. Everything ships weekly now."
    )
    result = score_audio_pipeline(
        wav=wav,
        reference_script=ref,
        transcriber=_fake_transcriber(trans),
        audio_probe=_fake_probe(duration_s=30.0),
        written_scorer=_fake_written_scorer(100.0),
    )
    assert result["hallucination"]["score"] < 70.0
    assert result["hallucination_cap_triggered"] is True
    assert result["composite"] <= 75.0
    assert result["composite_raw"] > result["composite"]


def test_pipeline_no_hallucination_cap_disables(tmp_path: Path):
    """`apply_hallucination_cap_flag=False` returns raw composite."""
    wav = tmp_path / "qwen.wav"
    wav.write_bytes(b"fake")
    ref = "short reference"
    trans = " ".join(f"garbage{i}" for i in range(50))  # severe drift
    result = score_audio_pipeline(
        wav=wav,
        reference_script=ref,
        transcriber=_fake_transcriber(trans),
        audio_probe=_fake_probe(duration_s=10.0),
        written_scorer=_fake_written_scorer(100.0),
        apply_hallucination_cap_flag=False,
    )
    assert result["hallucination"]["score"] < 70.0
    # Cap not applied → composite == composite_raw.
    assert result["composite"] == result["composite_raw"]
    assert result["hallucination_cap_triggered"] is False
    assert result["hallucination_cap_applied"] is False


def test_pipeline_no_reference_skips_hallucination(tmp_path: Path):
    """Without reference, hallucination is 100 (not meaningful to compute)."""
    wav = tmp_path / "anon.wav"
    wav.write_bytes(b"fake")
    result = score_audio_pipeline(
        wav=wav,
        reference_script=None,
        transcriber=_fake_transcriber("anything goes here"),
        audio_probe=_fake_probe(duration_s=10.0),
        written_scorer=_fake_written_scorer(95.0),
    )
    assert result["hallucination"]["score"] == 100.0
    assert result["hallucination_cap_triggered"] is False
    assert result["hallucination_cap_applied"] is False
