"""``zv history|tag|revert|diff`` — semantic voice version tags.

Per doc 10 §versioning. A tag is a small YAML file in
``<brand_dir>/.voice-history/<name>.tag`` pointing at a git SHA + a
human-readable summary. Tags are *semantic* — not a replacement for git,
but a lookup layer for "what did voice look like when we shipped X?".

Revert uses `git show <sha>:<relpath>` to restore a prior voice.yaml.
Diff uses `difflib.unified_diff` on either the current voice.yaml (if one
side omits a SHA) or two historical versions.

``zv score --at <tag>`` is implemented via a new option wired into the
existing score command (see ``cli.py`` for the glue).
"""

from __future__ import annotations

import difflib
import json
import subprocess
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import Optional

import click
import yaml

from zeststream_voice._brands import discover_brand


TAG_DIR_NAME = ".voice-history"
TAG_SUFFIX = ".tag"


@dataclass
class VoiceTag:
    """A semantic voice version tag."""

    tag: str
    git_sha: str
    date: str
    summary: str
    path: Path

    @classmethod
    def load(cls, path: Path) -> "VoiceTag":
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            tag=str(data.get("tag") or path.stem),
            git_sha=str(data.get("git_sha") or ""),
            date=str(data.get("date") or ""),
            summary=str(data.get("summary") or "").strip(),
            path=path,
        )

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "git_sha": self.git_sha,
            "date": self.date,
            "summary": self.summary,
            "path": str(self.path),
        }


# ---------------------------------------------------------------------------
# Tag I/O
# ---------------------------------------------------------------------------


def _tag_dir(brand_dir: Path) -> Path:
    return brand_dir / TAG_DIR_NAME


def _list_tags(brand_dir: Path) -> list[VoiceTag]:
    d = _tag_dir(brand_dir)
    if not d.is_dir():
        return []
    tags: list[VoiceTag] = []
    for p in sorted(d.glob(f"*{TAG_SUFFIX}")):
        try:
            tags.append(VoiceTag.load(p))
        except Exception:
            continue
    # Sort by date ascending; unknown dates last.
    tags.sort(key=lambda t: (t.date or "9999"))
    return tags


def _resolve_tag(brand_dir: Path, name: str) -> VoiceTag:
    p = _tag_dir(brand_dir) / f"{name}{TAG_SUFFIX}"
    if not p.exists():
        raise click.ClickException(
            f"tag {name!r} not found at {p}. Run `zv history` to see valid tags."
        )
    return VoiceTag.load(p)


def _write_tag(
    brand_dir: Path,
    name: str,
    git_sha: str,
    summary: str,
    tag_date: Optional[str] = None,
) -> VoiceTag:
    d = _tag_dir(brand_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}{TAG_SUFFIX}"
    if path.exists():
        raise click.ClickException(
            f"tag {name!r} already exists at {path}. Delete it first if you mean to overwrite."
        )
    payload = {
        "tag": name,
        "git_sha": git_sha,
        "date": tag_date or _date.today().isoformat(),
        "summary": summary.strip() + "\n",
    }
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, default_flow_style=False)
    return VoiceTag.load(path)


# ---------------------------------------------------------------------------
# Git helpers (minimal — only read; no mutation)
# ---------------------------------------------------------------------------


def _git_show(repo_root: Path, sha: str, relpath: str) -> str:
    """Return the contents of a file at a given git SHA. Raises ClickException on failure."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "show", f"{sha}:{relpath}"],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"git show {sha}:{relpath} failed: {exc.stderr.decode('utf-8', errors='replace').strip()}"
        ) from exc
    return out.decode("utf-8", errors="replace")


def _git_head_sha(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"git rev-parse HEAD failed: {exc.stderr.decode('utf-8', errors='replace').strip()}"
        ) from exc
    return out.decode("utf-8").strip()


def _repo_root(path: Path) -> Path:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"not a git repo at {path}: {exc.stderr.decode('utf-8', errors='replace').strip()}"
        ) from exc
    return Path(out.decode("utf-8").strip())


def _voice_yaml_for_tag(brand_dir: Path, tag: VoiceTag) -> str:
    """Read voice.yaml contents as of a tag."""
    voice_path = brand_dir / "voice.yaml"
    if not tag.git_sha:
        # No SHA — treat as "current".
        return voice_path.read_text(encoding="utf-8")
    repo = _repo_root(brand_dir)
    rel = voice_path.resolve().relative_to(repo.resolve())
    return _git_show(repo, tag.git_sha, str(rel))


# ---------------------------------------------------------------------------
# CLI: zv history
# ---------------------------------------------------------------------------


@click.command(
    "history",
    help="List semantic voice-version tags for a brand.",
)
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None,
              help="Explicit brand directory (overrides --brand).")
@click.option("--json", "as_json", is_flag=True)
def history_cli(brand: str, brand_path: Optional[str], as_json: bool) -> None:
    try:
        paths = discover_brand(
            slug=brand,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    tags = _list_tags(paths.brand_dir)

    if as_json:
        click.echo(json.dumps({"tags": [t.to_dict() for t in tags]}, indent=2))
        return

    if not tags:
        click.echo(
            f"no voice-history tags at {_tag_dir(paths.brand_dir)}. "
            "Create one with `zv tag <name>`."
        )
        return

    click.echo(f"voice-history for {brand}:")
    for t in tags:
        sha = t.git_sha or "(no-sha)"
        click.echo(f"  {t.date}  {t.tag:32s}  {sha}")
        for line in t.summary.splitlines():
            if line.strip():
                click.echo(f"      {line}")


# ---------------------------------------------------------------------------
# CLI: zv tag
# ---------------------------------------------------------------------------


@click.command(
    "tag",
    help="Create a new semantic snapshot tag pointing at the current git SHA.",
)
@click.argument("name")
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option(
    "--summary",
    required=True,
    help="Short human-readable summary of what this voice version represents.",
)
@click.option(
    "--sha",
    default=None,
    help="Git SHA to tag (default: current HEAD).",
)
@click.option("--date", "tag_date", default=None, help="Override date (YYYY-MM-DD).")
@click.option("--json", "as_json", is_flag=True)
def tag_cli(
    name: str,
    brand: str,
    brand_path: Optional[str],
    summary: str,
    sha: Optional[str],
    tag_date: Optional[str],
    as_json: bool,
) -> None:
    try:
        paths = discover_brand(
            slug=brand,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    head_sha = sha or _git_head_sha(paths.brand_dir)
    tag = _write_tag(paths.brand_dir, name, head_sha, summary, tag_date=tag_date)

    if as_json:
        click.echo(json.dumps(tag.to_dict(), indent=2))
    else:
        click.echo(f"wrote {tag.path}")
        click.echo(f"  tag:     {tag.tag}")
        click.echo(f"  git_sha: {tag.git_sha}")
        click.echo(f"  date:    {tag.date}")
        click.echo(f"  summary: {tag.summary.strip()}")


# ---------------------------------------------------------------------------
# CLI: zv revert
# ---------------------------------------------------------------------------


@click.command(
    "revert",
    help="Restore voice.yaml from a prior tag (creates a new tag; does not rewrite git).",
)
@click.argument("name")
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option(
    "--new-tag",
    default=None,
    help="Name of the snapshot tag to write after reverting "
         "(default: <name>-revert-<date>).",
)
@click.option(
    "--confirm",
    is_flag=True,
    help="Required to actually rewrite voice.yaml. Without it, this is a dry run.",
)
def revert_cli(
    name: str,
    brand: str,
    brand_path: Optional[str],
    new_tag: Optional[str],
    confirm: bool,
) -> None:
    try:
        paths = discover_brand(
            slug=brand,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    target = _resolve_tag(paths.brand_dir, name)
    old_text = paths.voice_yaml.read_text(encoding="utf-8")
    new_text = _voice_yaml_for_tag(paths.brand_dir, target)

    if old_text == new_text:
        click.echo(f"voice.yaml already matches tag {name} — nothing to revert.")
        return

    if not confirm:
        click.echo("DRY RUN — pass --confirm to apply. Preview diff:")
        diff = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile="voice.yaml (current)",
            tofile=f"voice.yaml@{target.tag}",
            n=3,
        )
        click.echo("".join(diff).rstrip() or "(no textual diff)")
        return

    paths.voice_yaml.write_text(new_text, encoding="utf-8")
    snapshot_name = new_tag or f"{name}-revert-{_date.today().isoformat()}"
    snapshot = _write_tag(
        paths.brand_dir,
        snapshot_name,
        _git_head_sha(paths.brand_dir),
        f"Reverted voice.yaml to tag {target.tag} (git_sha={target.git_sha}).",
    )
    click.echo(f"reverted voice.yaml to {target.tag}")
    click.echo(f"snapshot tag written: {snapshot.path}")


# ---------------------------------------------------------------------------
# CLI: zv diff
# ---------------------------------------------------------------------------


@click.command(
    "diff",
    help="Show a unified diff between two voice-history tags (or one tag vs current).",
)
@click.argument("tag_a")
@click.argument("tag_b", required=False)
@click.option("--brand", default="zeststream", show_default=True)
@click.option("--brand-path", default=None)
@click.option("--context", "n_context", type=int, default=3, show_default=True)
def diff_cli(
    tag_a: str,
    tag_b: Optional[str],
    brand: str,
    brand_path: Optional[str],
    n_context: int,
) -> None:
    try:
        paths = discover_brand(
            slug=brand,
            explicit_brand_path=Path(brand_path) if brand_path else None,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    a = _resolve_tag(paths.brand_dir, tag_a)
    a_text = _voice_yaml_for_tag(paths.brand_dir, a)
    a_label = f"voice.yaml@{a.tag}"

    if tag_b is None:
        b_text = paths.voice_yaml.read_text(encoding="utf-8")
        b_label = "voice.yaml (current)"
    else:
        b = _resolve_tag(paths.brand_dir, tag_b)
        b_text = _voice_yaml_for_tag(paths.brand_dir, b)
        b_label = f"voice.yaml@{b.tag}"

    diff = difflib.unified_diff(
        a_text.splitlines(keepends=True),
        b_text.splitlines(keepends=True),
        fromfile=a_label,
        tofile=b_label,
        n=n_context,
    )
    rendered = "".join(diff)
    if not rendered.strip():
        click.echo(f"{a_label} and {b_label} are identical.")
        return
    click.echo(rendered.rstrip())
