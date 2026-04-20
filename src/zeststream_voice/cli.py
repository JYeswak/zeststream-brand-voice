"""Command-line interface for zeststream-voice.

Subcommands:
  info     — show package version + loaded brand paths + layer status
  score    — score one text (positional or --file) against layer 1 + grounding
  enforce  — walk a directory, score every .md, exit 1 if any composite < threshold
  ground   — run only the grounding pass against a text
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from zeststream_voice import __version__
from zeststream_voice._brands import discover_brand
from zeststream_voice.sdk import BrandVoiceEnforcer


# ------------------------------------------------------------------ layer status
LAYER_STATUS = [
    ("layer1_banned_words", "v0.4", "REAL"),
    ("layer2_rules", "v0.5", "STUB (NotImplementedError)"),
    ("layer3_embedding", "v0.6", "STUB (NotImplementedError)"),
    ("layer4_rubric", "v0.6", "STUB (NotImplementedError)"),
    ("grounding", "v0.4", "REAL"),
]


def _load_text(text: Optional[str], file: Optional[str]) -> str:
    if file:
        return Path(file).read_text(encoding="utf-8")
    if text is None:
        raise click.UsageError("provide either TEXT or --file PATH")
    return text


def _make_enforcer(brand: str, brand_path: Optional[str]) -> BrandVoiceEnforcer:
    try:
        return BrandVoiceEnforcer(brand=brand, brand_path=brand_path)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e


# =============================================================================
# CLI entry
# =============================================================================
@click.group(help="Brand voice scoring + claim grounding for ZestStream copy.")
@click.version_option(__version__, prog_name="zeststream-voice")
def cli() -> None:  # pragma: no cover - group shim
    pass


# -----------------------------------------------------------------------------
@cli.command("info", help="Show package version, brand paths, and layer status.")
@click.option("--brand", default="zeststream", show_default=True)
@click.option(
    "--brand-path",
    default=None,
    help="Explicit brand directory containing voice.yaml (overrides --brand).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def info_cmd(brand: str, brand_path: Optional[str], as_json: bool) -> None:
    try:
        paths = discover_brand(
            slug=brand,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
        paths_info = {
            "slug": paths.slug,
            "brand_dir": str(paths.brand_dir),
            "voice_yaml": str(paths.voice_yaml),
            "ground_truth_yaml": (
                str(paths.ground_truth_yaml) if paths.ground_truth_yaml else None
            ),
        }
    except FileNotFoundError as e:
        paths_info = {"error": str(e)}

    payload = {
        "version": __version__,
        "brand": paths_info,
        "layers": [
            {"name": n, "version": v, "status": s} for n, v, s in LAYER_STATUS
        ],
    }

    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"zeststream-voice {__version__}")
    click.echo("")
    click.echo("Brand:")
    for k, v in paths_info.items():
        click.echo(f"  {k}: {v}")
    click.echo("")
    click.echo("Layers:")
    for name, version, status in LAYER_STATUS:
        click.echo(f"  {name:24s} {version:6s} {status}")


# -----------------------------------------------------------------------------
@cli.command("score", help="Score TEXT (or --file) against layer 1 + grounding.")
@click.argument("text", required=False)
@click.option("--file", "file", type=click.Path(exists=True, dir_okay=False))
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@click.option("--no-grounding", is_flag=True, help="Skip the grounding pass.")
def score_cmd(
    text: Optional[str],
    file: Optional[str],
    brand: str,
    brand_path: Optional[str],
    as_json: bool,
    no_grounding: bool,
) -> None:
    content = _load_text(text, file)
    enforcer = _make_enforcer(brand, brand_path)
    result = enforcer.score(content, include_grounding=not no_grounding)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        click.echo(f"status: {status}")
        click.echo(f"composite: {result.composite:.2f}")
        click.echo("")
        click.echo("layers:")
        for name, layer in result.layers.items():
            veto = " (VETO)" if layer.vetoed else ""
            click.echo(f"  {name}: {layer.score:.2f}{veto} — {layer.reason}")
            hits = layer.details.get("hits", [])
            for h in hits:
                word = h.get("word", "?")
                span = h.get("span", [0, 0])
                ctx = h.get("context", "").replace("\n", " ")
                click.echo(f"    - {word!r} @ {span} …{ctx}…")
        if result.grounded is not None:
            click.echo("")
            click.echo(
                f"grounding: {len(result.grounded.matched)} matched, "
                f"{len(result.grounded.unmatched)} unmatched"
            )
            for val, gt_id in result.grounded.matched:
                click.echo(f"  + {val} -> {gt_id}")
            for c in result.grounded.unmatched:
                click.echo(f"  ? {c.value} (context: …{c.context.strip()[:80]}…)")

    sys.exit(0 if result.passed else 2)


# -----------------------------------------------------------------------------
@cli.command(
    "enforce",
    help="Walk a directory, score every .md, exit 1 if any composite < --fail-under.",
)
@click.option(
    "--path",
    "root",
    type=click.Path(exists=True, file_okay=False),
    required=True,
)
@click.option("--fail-under", type=float, default=95.0, show_default=True)
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option("--json", "as_json", is_flag=True)
def enforce_cmd(
    root: str,
    fail_under: float,
    brand: str,
    brand_path: Optional[str],
    as_json: bool,
) -> None:
    enforcer = _make_enforcer(brand, brand_path)
    base = Path(root)
    files = sorted(base.rglob("*.md"))

    results = []
    any_fail = False
    for f in files:
        text = f.read_text(encoding="utf-8")
        r = enforcer.score(text, include_grounding=False)
        fail = r.composite < fail_under or not r.passed
        any_fail = any_fail or fail
        results.append(
            {
                "path": str(f),
                "composite": r.composite,
                "passed": r.passed,
                "fail_under": fail_under,
                "fail": fail,
                "banned_hits": len(r.banned_hits),
            }
        )

    if as_json:
        click.echo(json.dumps({"results": results, "failed": any_fail}, indent=2))
    else:
        for r in results:
            marker = "FAIL" if r["fail"] else "OK  "
            click.echo(
                f"{marker}  {r['composite']:6.2f}  {r['banned_hits']:3d} hits  {r['path']}"
            )
        click.echo("")
        click.echo(
            f"scanned {len(results)} files; "
            f"failed={sum(1 for r in results if r['fail'])}"
        )
    sys.exit(1 if any_fail else 0)


# -----------------------------------------------------------------------------
@cli.command("ground", help="Extract claims and match them against ground-truth.")
@click.argument("text", required=False)
@click.option("--file", "file", type=click.Path(exists=True, dir_okay=False))
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option("--json", "as_json", is_flag=True)
def ground_cmd(
    text: Optional[str],
    file: Optional[str],
    brand: str,
    brand_path: Optional[str],
    as_json: bool,
) -> None:
    content = _load_text(text, file)
    enforcer = _make_enforcer(brand, brand_path)
    result = enforcer.ground(content)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    click.echo(f"matched: {len(result.matched)}")
    for val, gt_id in result.matched:
        click.echo(f"  + {val} -> {gt_id}")
    click.echo(f"unmatched: {len(result.unmatched)}")
    for c in result.unmatched:
        click.echo(f"  ? {c.value} (context: …{c.context.strip()[:80]}…)")


def main() -> None:
    """Console-script entry point."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
