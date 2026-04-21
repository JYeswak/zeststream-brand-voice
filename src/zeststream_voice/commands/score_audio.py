"""`zv score-audio` — grade AI-synthesized (or human) audio.

Extends the voice gate past written-text rules with three audio-specific
dimensions: fidelity (transcript match to reference script), pacing (wpm vs
~130 wpm reference), and silence/glitch (long silences + clipping via
ffmpeg). Re-transcribes the .wav with whisper-cli, runs the standard
16-dim written scorer over the transcript, and emits a JSON composite.

Zest Feed bar: `--min-composite 92` (stricter on automated narration because
TTS has less forgiveness than live Joshua). Written-text bar stays at 95.

Design note: the whisper/ffmpeg shell-outs are injectable via `transcriber`
and `audio_probe` callables so unit tests can drop mock callables at the
boundary without patching subprocess. That's the only mocked collaborator
allowed — the rest of the pipeline runs against real fs + real scorer.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import click


# ---------------------------------------------------------------------------
# Voice-gate threshold tiers. Stay constants for now; voice.yaml integration
# is deferred until Joshua picks a TTS engine and wants the tiers wired in.
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "written_text_min": 95.0,
    "automated_narration_min": 92.0,
    "casual_voice_min": 88.0,
}

REFERENCE_WPM = 130.0  # Joshua take-2 reference
SILENCE_DB = "-35dB"   # ffmpeg silencedetect noise threshold
# Only silences >=2s count as problematic; natural speech pauses (1-2s) on
# the Joshua take2 baseline produce 13 of them. 2s is the "noticeable dead
# air" threshold for TTS output and live narration.
SILENCE_MIN_S = 2.0

WHISPER_BIN_DEFAULT = "/opt/homebrew/bin/whisper-cli"
WHISPER_MODEL_DEFAULT = str(Path.home() / "models" / "whisper" / "ggml-large-v3.bin")
FFMPEG_BIN_DEFAULT = "/opt/homebrew/bin/ffmpeg"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AudioProbe:
    """Result of ffmpeg-based audio analysis."""

    duration_s: float
    silences: list[tuple[float, float]] = field(default_factory=list)  # (start, duration)
    clipping_detected: bool = False
    max_volume_db: float = 0.0


@dataclass
class AudioDims:
    """The three audio-specific dimensions (0-10, rounded to 0.5)."""

    fidelity: float
    pacing: float
    silence_glitch: float
    # Diagnostics so the JSON can explain the scores.
    fidelity_pct: float = 0.0
    word_count: int = 0
    wpm: float = 0.0
    silence_count: int = 0


# ---------------------------------------------------------------------------
# Tokenization + levenshtein for fidelity
# ---------------------------------------------------------------------------


_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Strips punctuation but keeps apostrophes + digits."""
    return [w.lower() for w in _WORD_RE.findall(text)]


def word_levenshtein(a: list[str], b: list[str]) -> int:
    """Classic Levenshtein distance on token lists. O(len(a) * len(b))."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ta in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, tb in enumerate(b, 1):
            cost = 0 if ta == tb else 1
            cur[j] = min(
                cur[j - 1] + 1,           # insertion
                prev[j] + 1,              # deletion
                prev[j - 1] + cost,       # substitution
            )
        prev = cur
    return prev[-1]


def fidelity_percent(transcript: str, reference: str) -> float:
    """Word-level 1 - distance / max(len) as a percent in [0, 100]."""
    a = tokenize(transcript)
    b = tokenize(reference)
    if not a and not b:
        return 100.0
    denom = max(len(a), len(b))
    if denom == 0:
        return 100.0
    dist = word_levenshtein(a, b)
    return max(0.0, (1.0 - dist / denom) * 100.0)


# ---------------------------------------------------------------------------
# Dimension scoring (0-10, round to 0.5)
# ---------------------------------------------------------------------------


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def score_fidelity(pct: float, has_reference: bool) -> float:
    """10 word-for-word, 8 if 1-2 minor subs, 5 at ≥5% drift, <5 substantial.

    If no reference script was supplied the fidelity dim doesn't apply;
    return 10 so it doesn't drag the composite down (the caller can drop
    it from the average instead — see compose_composite).
    """
    if not has_reference:
        return 10.0
    if pct >= 99.0:
        return 10.0
    if pct >= 95.0:
        return 8.0
    if pct >= 90.0:
        return 6.0
    if pct >= 80.0:
        return 5.0
    if pct >= 60.0:
        return 3.0
    return 1.0


def score_pacing(wpm: float) -> float:
    """Reference 130 wpm. 10 within ±10%, 8 ±20%, 5 ±30%, <5 off."""
    if wpm <= 0:
        return 0.0
    deviation = abs(wpm - REFERENCE_WPM) / REFERENCE_WPM
    if deviation <= 0.10:
        return 10.0
    if deviation <= 0.20:
        return 8.0
    if deviation <= 0.30:
        return 5.0
    if deviation <= 0.50:
        return 3.0
    return 1.0


def score_silence(silence_count: int, clipping_detected: bool) -> float:
    """10 clean, 8 one 1-2s silence, 5 ≥2 glitches OR any clipping."""
    if clipping_detected:
        return _round_half(min(5.0, 10 - 2 * silence_count))
    if silence_count == 0:
        return 10.0
    if silence_count == 1:
        return 8.0
    if silence_count == 2:
        return 6.0
    return max(1.0, 10.0 - 2.0 * silence_count)


# ---------------------------------------------------------------------------
# Real whisper + ffmpeg drivers (injectable for tests)
# ---------------------------------------------------------------------------


Transcriber = Callable[[Path], str]
AudioProber = Callable[[Path], AudioProbe]


def real_transcriber(
    wav: Path,
    *,
    whisper_bin: str = WHISPER_BIN_DEFAULT,
    model: str = WHISPER_MODEL_DEFAULT,
    language: str = "en",
) -> str:
    """Shell out to whisper-cli, return plain transcript text.

    Writes to a temp prefix so concurrent runs don't collide. Raises
    click.ClickException with the tail of stderr on whisper failure.
    """
    if not Path(whisper_bin).exists():
        raise click.ClickException(
            f"whisper-cli not found at {whisper_bin} — pass --whisper-bin"
        )
    if not Path(model).exists():
        raise click.ClickException(
            f"whisper model not found at {model} — pass --whisper-model"
        )
    with tempfile.TemporaryDirectory() as td:
        out_prefix = Path(td) / "out"
        cmd = [
            whisper_bin,
            "-m", model,
            "-f", str(wav),
            "-l", language,
            "-otxt",
            "-nt",
            "-of", str(out_prefix),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout)[-500:]
            raise click.ClickException(
                f"whisper-cli exit {proc.returncode}: …{tail}"
            )
        txt_path = out_prefix.with_suffix(".txt")
        if not txt_path.exists():
            raise click.ClickException(
                f"whisper-cli produced no transcript at {txt_path}"
            )
        return txt_path.read_text(encoding="utf-8").strip()


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
_SILENCE_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
_SILENCE_DURATION_RE = re.compile(r"silence_duration:\s*([\d.]+)")
_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(-?[\d.]+)\s*dB")


def real_audio_probe(
    wav: Path,
    *,
    ffmpeg_bin: str = FFMPEG_BIN_DEFAULT,
    silence_db: str = SILENCE_DB,
    silence_min_s: float = SILENCE_MIN_S,
) -> AudioProbe:
    """Run ffmpeg silencedetect + volumedetect, parse stderr."""
    if not shutil.which(ffmpeg_bin) and not Path(ffmpeg_bin).exists():
        raise click.ClickException(
            f"ffmpeg not found at {ffmpeg_bin} — pass --ffmpeg-bin"
        )
    cmd = [
        ffmpeg_bin, "-nostats", "-hide_banner",
        "-i", str(wav),
        "-af",
        f"silencedetect=noise={silence_db}:d={silence_min_s},volumedetect",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    combined = (proc.stderr or "") + (proc.stdout or "")
    return _parse_ffmpeg_output(combined)


def _parse_ffmpeg_output(text: str) -> AudioProbe:
    # Duration
    duration_s = 0.0
    m = _DURATION_RE.search(text)
    if m:
        h, mm, ss = m.groups()
        duration_s = int(h) * 3600 + int(mm) * 60 + float(ss)

    # Silences: pair each silence_start with the next silence_duration.
    starts = _SILENCE_START_RE.findall(text)
    durs = _SILENCE_DURATION_RE.findall(text)
    silences: list[tuple[float, float]] = []
    for s, d in zip(starts, durs):
        silences.append((float(s), float(d)))

    # Max volume (clipping = >= 0 dB).
    max_db = 0.0
    mv = _MAX_VOLUME_RE.search(text)
    if mv:
        try:
            max_db = float(mv.group(1))
        except ValueError:
            max_db = 0.0
    clipping = max_db >= 0.0

    return AudioProbe(
        duration_s=duration_s,
        silences=silences,
        clipping_detected=clipping,
        max_volume_db=max_db,
    )


# ---------------------------------------------------------------------------
# Hallucination dim — pure-text, gates the composite
# ---------------------------------------------------------------------------
#
# Motivated by a real ship-blocker: Qwen 1.7B TTS produced audio that scored
# composite 100 / PASS through the base gate despite 24 hallucinated words
# (spurious intro, mid-script insert, end-loop). Each dim was fine in
# isolation, but the composite didn't surface the semantic drift.
#
# This dim is HARD — it caps the composite when drift is bad enough that
# the audio is saying something the script didn't. A 100 on fidelity /
# pacing / silence over fabricated content is NOT a 100 composite.

EXTRA_WORD_SLACK = 0.05          # 5% headroom for contractions/numerals.
EXTRA_WORD_PENALTY_PER = 2.0     # points deducted per extra word over slack.
LONGEST_MATCH_LOW = 0.80         # <0.80 → -20; <0.60 → -40 (tiered).
LONGEST_MATCH_VERY_LOW = 0.60
REPEATED_PHRASE_PENALTY = 10.0
DRIFT_RATIO_THRESHOLD = 0.6
DRIFT_PENALTY = 10.0
DRIFT_WINDOW_TOKENS = 20
REPETITION_NGRAM = 5
HALLUCINATION_SOFT_CAP_THRESHOLD = 70.0
HALLUCINATION_SOFT_CAP = 75.0
HALLUCINATION_HARD_CAP_THRESHOLD = 50.0
HALLUCINATION_HARD_CAP = 50.0


def _longest_match_coverage(script_tokens: list[str], transcript_tokens: list[str]) -> float:
    """Longest contiguous matching block / len(script). 1.0 = full-script match."""
    from difflib import SequenceMatcher

    if not script_tokens:
        return 1.0
    matcher = SequenceMatcher(a=script_tokens, b=transcript_tokens, autojunk=False)
    longest = matcher.find_longest_match(0, len(script_tokens), 0, len(transcript_tokens))
    return longest.size / len(script_tokens)


def _detect_repeated_phrases(
    script_tokens: list[str], transcript_tokens: list[str], n: int = REPETITION_NGRAM
) -> list[str]:
    """n-grams that (a) appear >=2x in transcript AND (b) appear exactly 1x in script.

    These are the "loop" signatures — the model stuttered or re-read a chunk
    that was a one-shot in the original script. Returns the n-gram strings.
    """
    if len(transcript_tokens) < n:
        return []

    def ngrams(tokens: list[str]) -> list[tuple[str, ...]]:
        return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]

    trans_ngrams = ngrams(transcript_tokens)
    script_ngrams = ngrams(script_tokens)

    # Count occurrences.
    from collections import Counter
    trans_counts = Counter(trans_ngrams)
    script_counts = Counter(script_ngrams)

    flagged: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for ng, count in trans_counts.items():
        if count < 2:
            continue
        if script_counts.get(ng, 0) != 1:
            continue
        if ng in seen:
            continue
        seen.add(ng)
        flagged.append(" ".join(ng))
    return flagged


def _edge_drift_ratio(
    script_tokens: list[str], transcript_tokens: list[str], *, head: bool
) -> float:
    """SequenceMatcher ratio between the first/last DRIFT_WINDOW_TOKENS tokens."""
    from difflib import SequenceMatcher

    w = DRIFT_WINDOW_TOKENS
    if not script_tokens or not transcript_tokens:
        return 1.0
    if head:
        a = script_tokens[:w]
        b = transcript_tokens[:w]
    else:
        a = script_tokens[-w:]
        b = transcript_tokens[-w:]
    return SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def compute_hallucination_dim(reference_script: str, transcript: str) -> dict[str, Any]:
    """Score hallucination 0-100 (higher = cleaner) + diagnostics + flags.

    Purely text math. No audio deps. Runs on any (script, transcript) pair.
    """
    script_tokens = tokenize(reference_script)
    trans_tokens = tokenize(transcript)
    script_len = len(script_tokens)
    trans_len = len(trans_tokens)

    # 1. Extra-word ratio (over 5% slack).
    slack_budget = script_len * (1 + EXTRA_WORD_SLACK)
    extra_words = max(0, trans_len - int(slack_budget))
    extra_penalty = extra_words * EXTRA_WORD_PENALTY_PER

    # 2. Longest-matching-block coverage.
    longest_cov = _longest_match_coverage(script_tokens, trans_tokens)
    if longest_cov < LONGEST_MATCH_VERY_LOW:
        longest_penalty = 40.0
    elif longest_cov < LONGEST_MATCH_LOW:
        longest_penalty = 20.0
    else:
        longest_penalty = 0.0

    # 3. Repetition detection.
    repeated = _detect_repeated_phrases(script_tokens, trans_tokens)
    repeat_penalty = len(repeated) * REPEATED_PHRASE_PENALTY

    # 4. Prefix/suffix drift.
    head_ratio = _edge_drift_ratio(script_tokens, trans_tokens, head=True)
    tail_ratio = _edge_drift_ratio(script_tokens, trans_tokens, head=False)
    drift_penalty = 0.0
    flags: list[str] = []
    if head_ratio < DRIFT_RATIO_THRESHOLD:
        drift_penalty += DRIFT_PENALTY
        flags.append("spurious_prefix")
    if tail_ratio < DRIFT_RATIO_THRESHOLD:
        drift_penalty += DRIFT_PENALTY
        flags.append("end_loop")

    # Additional derived flags for explainability.
    if extra_words >= max(10, int(script_len * 0.1)):
        flags.append("excess_words")
    if repeated:
        flags.append("repeated_phrase")
    if longest_cov < LONGEST_MATCH_LOW:
        flags.append("broken_midscript")

    total_penalty = extra_penalty + longest_penalty + repeat_penalty + drift_penalty
    score = max(0.0, 100.0 - total_penalty)

    return {
        "score": round(score, 2),
        "score_0_10": _round_half(score / 10.0),
        "extra_words": int(extra_words),
        "transcript_word_count": int(trans_len),
        "script_word_count": int(script_len),
        "longest_match_coverage": round(longest_cov, 4),
        "repeated_phrases": repeated,
        "prefix_drift_ratio": round(head_ratio, 4),
        "suffix_drift_ratio": round(tail_ratio, 4),
        "flags": flags,
        "penalties": {
            "extra_words": round(extra_penalty, 2),
            "longest_match": round(longest_penalty, 2),
            "repeated_phrases": round(repeat_penalty, 2),
            "edge_drift": round(drift_penalty, 2),
        },
    }


def apply_hallucination_cap(raw_composite: float, hallucination_score: float) -> float:
    """Cap composite when the audio drifted from script.

    < 50 hallucination → composite capped at 50 (P0 fail).
    < 70 hallucination → composite capped at 75 (P1 ship-blocker).
    Otherwise return raw composite unchanged.
    """
    if hallucination_score < HALLUCINATION_HARD_CAP_THRESHOLD:
        return min(raw_composite, HALLUCINATION_HARD_CAP)
    if hallucination_score < HALLUCINATION_SOFT_CAP_THRESHOLD:
        return min(raw_composite, HALLUCINATION_SOFT_CAP)
    return raw_composite


# ---------------------------------------------------------------------------
# Core scoring pipeline
# ---------------------------------------------------------------------------


def compose_composite(written_score: float, audio: AudioDims, has_reference: bool) -> float:
    """Blend the standard written composite (0-100) with the 3 audio dims.

    We give audio dims 30% weight so a great-sounding take with clean text
    beats a textually-perfect robot voice. When no reference script is
    supplied we drop fidelity from the audio average (it'd be a free 10).
    """
    audio_dims = [audio.pacing, audio.silence_glitch]
    if has_reference:
        audio_dims.insert(0, audio.fidelity)
    audio_mean_0_10 = sum(audio_dims) / max(1, len(audio_dims))
    audio_pct = audio_mean_0_10 * 10.0  # 0-100 scale

    blended = 0.7 * written_score + 0.3 * audio_pct
    return round(blended, 2)


def score_audio_pipeline(
    wav: Path,
    *,
    reference_script: Optional[str],
    transcriber: Transcriber,
    audio_probe: AudioProber,
    written_scorer: Callable[[str], dict[str, Any]],
    apply_hallucination_cap_flag: bool = True,
) -> dict[str, Any]:
    """Pure-ish pipeline: transcribe, probe, score, compose.

    `written_scorer(transcript)` must return a dict with at least:
      {"composite": float, "layers": {...}, "passed": bool}

    When `apply_hallucination_cap_flag=True` (default), a low hallucination
    score caps the composite (75 @ <70, 50 @ <50) so fabricated content
    cannot ship at a PASS composite. Disable for raw-dim inspection during
    engine bakeoffs.
    """
    transcript = transcriber(wav)
    probe = audio_probe(wav)

    # Fidelity
    has_reference = reference_script is not None and reference_script.strip() != ""
    fid_pct = (
        fidelity_percent(transcript, reference_script or "")
        if has_reference
        else 100.0
    )

    # Pacing — wpm over probed duration.
    word_count = len(tokenize(transcript))
    duration_min = probe.duration_s / 60.0 if probe.duration_s > 0 else 0.0
    wpm = word_count / duration_min if duration_min > 0 else 0.0

    # Silence count: only count INTERIOR silences >= silence_min_s.
    # Leading/trailing silences (pre-roll / post-roll) are expected for any
    # real-world recording and are not glitches.
    EDGE_WINDOW = 1.0
    interior_silences = [
        (s, d)
        for s, d in probe.silences
        if d >= SILENCE_MIN_S
        and s > EDGE_WINDOW
        and (s + d) < (probe.duration_s - EDGE_WINDOW)
    ]
    silence_count = len(interior_silences)

    dims = AudioDims(
        fidelity=_round_half(score_fidelity(fid_pct, has_reference)),
        pacing=_round_half(score_pacing(wpm)),
        silence_glitch=_round_half(
            score_silence(silence_count, probe.clipping_detected)
        ),
        fidelity_pct=round(fid_pct, 2),
        word_count=word_count,
        wpm=round(wpm, 1),
        silence_count=silence_count,
    )

    written = written_scorer(transcript)

    raw_composite = compose_composite(
        written_score=float(written.get("composite", 0.0)),
        audio=dims,
        has_reference=has_reference,
    )

    # Hallucination dim — only meaningful when we have a reference script.
    if has_reference:
        halluc = compute_hallucination_dim(reference_script or "", transcript)
    else:
        halluc = {
            "score": 100.0,
            "score_0_10": 10.0,
            "extra_words": 0,
            "transcript_word_count": word_count,
            "script_word_count": 0,
            "longest_match_coverage": 1.0,
            "repeated_phrases": [],
            "prefix_drift_ratio": 1.0,
            "suffix_drift_ratio": 1.0,
            "flags": [],
            "penalties": {
                "extra_words": 0.0,
                "longest_match": 0.0,
                "repeated_phrases": 0.0,
                "edge_drift": 0.0,
            },
        }

    capped_composite = (
        apply_hallucination_cap(raw_composite, halluc["score"])
        if apply_hallucination_cap_flag and has_reference
        else raw_composite
    )
    cap_triggered = capped_composite < raw_composite

    return {
        "wav": str(wav),
        "transcript": transcript,
        "reference_script": reference_script,
        "has_reference": has_reference,
        "fidelity_pct": dims.fidelity_pct,
        "audio_dims": {
            "fidelity": dims.fidelity,
            "pacing": dims.pacing,
            "silence_glitch": dims.silence_glitch,
            "hallucination": halluc["score_0_10"],
        },
        "audio_diagnostics": {
            "word_count": dims.word_count,
            "duration_s": round(probe.duration_s, 2),
            "wpm": dims.wpm,
            "silence_count": dims.silence_count,
            "silences": [
                {"start": round(s, 2), "duration": round(d, 2)}
                for s, d in probe.silences
            ],
            "clipping_detected": probe.clipping_detected,
            "max_volume_db": probe.max_volume_db,
        },
        "hallucination": halluc,
        "written": written,
        "composite": round(capped_composite, 2),
        "composite_raw": raw_composite,
        "hallucination_cap_triggered": cap_triggered,
        "hallucination_cap_applied": bool(apply_hallucination_cap_flag and has_reference),
    }


# ---------------------------------------------------------------------------
# Default written scorer (wraps existing BrandVoiceEnforcer)
# ---------------------------------------------------------------------------


def default_written_scorer(
    brand: str = "zeststream",
    brand_path: Optional[str] = None,
) -> Callable[[str], dict[str, Any]]:
    """Return a callable that delegates to BrandVoiceEnforcer.score."""
    from zeststream_voice.sdk import BrandVoiceEnforcer

    try:
        enforcer = BrandVoiceEnforcer(brand=brand, brand_path=brand_path)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    def _score(transcript: str) -> dict[str, Any]:
        result = enforcer.score(transcript, include_grounding=False)
        return result.to_dict()

    return _score


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("score-audio", help="Grade an audio file (TTS or human) against the voice gate.")
@click.argument("wav", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--reference-script",
    "reference_script_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to the script the audio was supposed to read. Enables fidelity scoring.",
)
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option(
    "--min-composite",
    type=float,
    default=THRESHOLDS["automated_narration_min"],
    show_default=True,
    help="Composite floor. Exit 2 if below. Zest Feed bar = 92.",
)
@click.option(
    "--tier",
    type=click.Choice(["written_text", "automated_narration", "casual_voice"]),
    default=None,
    help="Preset threshold tier (overrides --min-composite when set).",
)
@click.option("--whisper-bin", default=WHISPER_BIN_DEFAULT, show_default=True)
@click.option("--whisper-model", default=WHISPER_MODEL_DEFAULT, show_default=True)
@click.option("--ffmpeg-bin", default=FFMPEG_BIN_DEFAULT, show_default=True)
@click.option(
    "--no-hallucination-cap",
    "no_hallucination_cap",
    is_flag=True,
    default=False,
    help=(
        "Disable the hallucination composite cap. By default, composite is "
        "capped at 75 when hallucination_score<70 and at 50 when <50. Use "
        "this flag for raw-dim inspection during engine comparison."
    ),
)
@click.option("--json", "as_json", is_flag=True, default=True, show_default=True)
def cli(
    wav: Path,
    reference_script_path: Optional[Path],
    brand: str,
    brand_path: Optional[str],
    min_composite: float,
    tier: Optional[str],
    whisper_bin: str,
    whisper_model: str,
    ffmpeg_bin: str,
    no_hallucination_cap: bool,
    as_json: bool,
) -> None:
    if tier:
        min_composite = THRESHOLDS[f"{tier}_min"]

    reference_script = (
        reference_script_path.read_text(encoding="utf-8")
        if reference_script_path
        else None
    )

    def _transcribe(p: Path) -> str:
        return real_transcriber(p, whisper_bin=whisper_bin, model=whisper_model)

    def _probe(p: Path) -> AudioProbe:
        return real_audio_probe(p, ffmpeg_bin=ffmpeg_bin)

    written = default_written_scorer(brand=brand, brand_path=brand_path)

    result = score_audio_pipeline(
        wav=wav,
        reference_script=reference_script,
        transcriber=_transcribe,
        audio_probe=_probe,
        written_scorer=written,
        apply_hallucination_cap_flag=not no_hallucination_cap,
    )
    result["min_composite"] = min_composite
    result["pass"] = result["composite"] >= min_composite

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        status = "PASS" if result["pass"] else "FAIL"
        click.echo(f"status: {status}")
        comp_line = f"composite: {result['composite']:.2f} (floor {min_composite})"
        if result.get("hallucination_cap_triggered"):
            comp_line += f"  [CAPPED from {result['composite_raw']:.2f}]"
        click.echo(comp_line)
        click.echo(f"fidelity: {result['fidelity_pct']:.1f}%")
        click.echo(f"pacing:   {result['audio_diagnostics']['wpm']:.1f} wpm")
        click.echo(f"silences: {result['audio_diagnostics']['silence_count']}")
        halluc = result.get("hallucination", {})
        if halluc:
            flags = halluc.get("flags", [])
            click.echo(
                f"halluc:   {halluc.get('score', 100):.1f}/100 "
                f"({halluc.get('extra_words', 0)} extra words, "
                f"longest-match {halluc.get('longest_match_coverage', 1.0):.2f})"
            )
            if flags:
                click.echo(f"  flags:  {', '.join(flags)}")

    sys.exit(0 if result["pass"] else 2)
