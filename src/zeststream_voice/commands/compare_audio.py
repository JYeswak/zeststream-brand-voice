"""`zv compare-audio` — multi-engine voice-gate bakeoff.

Runs `zv score-audio` against N .wav files (one per TTS engine or take)
and emits a side-by-side table so an operator can pick the winner at a
glance. Flags which engine wins on each axis.

Each input wav may have an adjacent .json sidecar with engine name +
latency metadata (e.g. `voicebox-sample-1.wav` + `voicebox-sample-1.json`
containing `{"engine": "voicebox", "latency_s": 3.2}`); if present the
sidecar is surfaced in the table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

import click

from zeststream_voice.commands.score_audio import (
    AudioProbe,
    THRESHOLDS,
    default_written_scorer,
    real_audio_probe,
    real_transcriber,
    score_audio_pipeline,
)


def load_sidecar(wav: Path) -> dict[str, Any]:
    """Load optional .json sidecar next to the .wav. Missing = empty dict."""
    sidecar = wav.with_suffix(".json")
    if not sidecar.exists():
        return {}
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_sidecar_error": f"could not parse {sidecar}"}


def engine_label(wav: Path, sidecar: dict[str, Any]) -> str:
    """Prefer sidecar.engine, else filename stem."""
    return str(sidecar.get("engine") or wav.stem)


def score_many(
    wavs: list[Path],
    *,
    reference_script: Optional[str],
    transcriber: Callable[[Path], str],
    audio_probe: Callable[[Path], AudioProbe],
    written_scorer: Callable[[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run score_audio_pipeline on each wav, attach sidecar metadata."""
    rows: list[dict[str, Any]] = []
    for wav in wavs:
        sidecar = load_sidecar(wav)
        result = score_audio_pipeline(
            wav=wav,
            reference_script=reference_script,
            transcriber=transcriber,
            audio_probe=audio_probe,
            written_scorer=written_scorer,
        )
        result["engine"] = engine_label(wav, sidecar)
        result["sidecar"] = sidecar
        result["latency_s"] = sidecar.get("latency_s")
        rows.append(result)
    return rows


def pick_winners(rows: list[dict[str, Any]]) -> dict[str, str]:
    """For each axis, return the engine that wins. Ties resolved by first seen."""
    if not rows:
        return {}
    winners: dict[str, str] = {}

    def _best(key_fn: Callable[[dict[str, Any]], float], higher_is_better: bool = True):
        sign = 1 if higher_is_better else -1
        best = max(rows, key=lambda r: sign * key_fn(r))
        return best["engine"]

    winners["fidelity"] = _best(lambda r: r.get("fidelity_pct", 0.0))
    winners["composite"] = _best(lambda r: r.get("composite", 0.0))
    winners["pacing"] = _best(lambda r: r["audio_dims"].get("pacing", 0.0))
    winners["silence_glitch"] = _best(
        lambda r: r["audio_dims"].get("silence_glitch", 0.0)
    )
    # Latency: lower is better. Only rank rows that have it.
    latency_rows = [r for r in rows if r.get("latency_s") is not None]
    if latency_rows:
        fastest = min(latency_rows, key=lambda r: r["latency_s"])
        winners["latency"] = fastest["engine"]
    return winners


def render_table(rows: list[dict[str, Any]], winners: dict[str, str]) -> str:
    """Human-readable side-by-side table. Fixed-width for terminal use."""
    if not rows:
        return "(no wavs scored)\n"

    # Column widths. Engine name max 14 chars.
    headers = [
        "engine", "composite", "fidelity%", "pacing(wpm)",
        "silences", "latency(s)", "pass>=92?",
    ]
    widths = [max(14, len(h)) for h in headers[:1]] + [len(h) for h in headers[1:]]

    lines: list[str] = []

    def _fmt_row(cells: list[str]) -> str:
        out = []
        for i, cell in enumerate(cells):
            w = widths[i] if i < len(widths) else 10
            out.append(cell.ljust(w))
        return "  ".join(out)

    lines.append(_fmt_row(headers))
    lines.append(_fmt_row(["-" * w for w in widths]))

    for r in rows:
        engine = r["engine"][:14]
        composite = f"{r['composite']:.2f}"
        fidelity = f"{r['fidelity_pct']:.1f}" if r.get("has_reference") else "—"
        wpm = f"{r['audio_diagnostics']['wpm']:.1f}"
        sil = str(r["audio_diagnostics"]["silence_count"])
        latency = (
            f"{r['latency_s']:.2f}" if r.get("latency_s") is not None else "—"
        )
        pass_flag = (
            "PASS" if r["composite"] >= THRESHOLDS["automated_narration_min"]
            else "FAIL"
        )
        lines.append(_fmt_row([engine, composite, fidelity, wpm, sil, latency, pass_flag]))

    lines.append("")
    lines.append("WINNERS:")
    for axis in ("composite", "fidelity", "pacing", "silence_glitch", "latency"):
        if axis in winners:
            lines.append(f"  {axis:16s} {winners[axis]}")
    return "\n".join(lines) + "\n"


@click.command(
    "compare-audio",
    help="Score multiple .wav files and compare engines side-by-side.",
)
@click.argument(
    "wavs",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--reference-script",
    "reference_script_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Reference script all engines were supposed to read.",
)
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def cli(
    wavs: tuple[Path, ...],
    reference_script_path: Optional[Path],
    brand: str,
    brand_path: Optional[str],
    as_json: bool,
) -> None:
    if len(wavs) < 1:
        raise click.UsageError("provide at least one .wav to compare")

    reference_script = (
        reference_script_path.read_text(encoding="utf-8")
        if reference_script_path
        else None
    )
    written = default_written_scorer(brand=brand, brand_path=brand_path)

    rows = score_many(
        wavs=list(wavs),
        reference_script=reference_script,
        transcriber=real_transcriber,
        audio_probe=real_audio_probe,
        written_scorer=written,
    )
    winners = pick_winners(rows)

    if as_json:
        click.echo(json.dumps({"rows": rows, "winners": winners}, indent=2))
        return

    click.echo(render_table(rows, winners))
