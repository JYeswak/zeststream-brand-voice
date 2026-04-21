"""`zv peel` — conversational wizard that walks a new brand through the 9-block
peel flow and emits voice.yaml + supporting artifacts.

Authoritative spec:
  /Users/josh/Developer/zesttube/.planning/brand-voice-cli/05-unified-spec.md
  (supersedes 03-peel-wizard-spec.md; doc 03 retained as archaeology)

v0.5 scope:
  - pre-flight checks (7 items per spec)
  - Block 1 IDENTITY — full implementation
  - Block 2 CANON    — full implementation
  - Blocks 3-9       — stubs that print "not yet implemented, skipping"
  - merge_to_voice_yaml writes voice.yaml and yaml.safe_load-validates it
    (silent-failure guard, session-14 trauma class)
  - Destructive writes are backed up first (P0-1 gate); copytree is atomic
    via tmp+rename (P1-3); corrupt --resume state is recoverable (P0-2).

Tokenization: word count uses a word-boundary regex (see ``_WORD_RE``) so
that hyphens and apostrophes bind words together. This matches Vale-default
word-boundary behavior used by downstream surface_sentence_caps scoring.

Deterministic: no LLM calls, no network, no anthropic/openai imports.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,31}$")
# Reject empty labels, leading/trailing dashes, and consecutive dots.
# Each label: starts+ends with alnum, may contain hyphens in the middle.
# TLD: 2+ alpha chars.
DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)
# Vale-default-ish tokenizer: words bind via ' and -; no empty tokens.
_WORD_RE = re.compile(r"\b\w+(?:['-]\w+)*\b")
STATE_FILENAME = ".peel-state.json"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PeelState:
    """Persisted wizard state across runs — lets `--resume` work."""

    version: int = 1
    slug: str = ""
    started_at: str = ""
    last_updated: str = ""
    blocks_completed: list[int] = field(default_factory=list)
    current_block: int = 1
    answers: dict[str, dict] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "PeelState":
        return cls(
            version=d.get("version", 1),
            slug=d.get("slug", ""),
            started_at=d.get("started_at", ""),
            last_updated=d.get("last_updated", ""),
            blocks_completed=list(d.get("blocks_completed", [])),
            current_block=d.get("current_block", 1),
            answers=dict(d.get("answers", {})),
        )


@dataclass
class BrandDirs:
    """Resolved output locations after pre-flight."""

    slug: str
    brand_dir: Path
    voice_yaml: Path
    state_file: Path
    is_fresh: bool


# ---------------------------------------------------------------------------
# State I/O
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_state(brand_dir: Path) -> PeelState | None:
    """Read .peel-state.json if it exists. Returns None if missing.

    Raises click.ClickException on JSONDecodeError so the CLI layer can
    offer the three-way (resume / abort / discard) recovery prompt.
    """
    state_file = brand_dir / STATE_FILENAME
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise click.ClickException(
            f"corrupted peel state at {state_file}: {e}"
        ) from e
    return PeelState.from_dict(data)


def save_state(brand_dir: Path, state: PeelState) -> None:
    """Write .peel-state.json atomically (tmp + rename — session-14 guard)."""
    state.last_updated = _now_iso()
    state_file = brand_dir / STATE_FILENAME
    tmp = state_file.with_suffix(".json.tmp")
    tmp.write_text(state.to_json(), encoding="utf-8")
    os.replace(tmp, state_file)


# ---------------------------------------------------------------------------
# Backup helpers (P0-1 gate: never destroy load-bearing state silently)
# ---------------------------------------------------------------------------


def _backup_file(path: Path, *, suffix: str = "bak") -> Path | None:
    """Copy `path` to `path.<existing-suffix>.<suffix>.<epoch>`. Returns the
    backup path, or None if source did not exist. Uses `shutil.copy2` so
    mtime is preserved. Caller is expected to announce the backup path.
    """
    if not path.exists():
        return None
    epoch = _epoch_suffix()
    backup = path.with_name(f"{path.name}.{suffix}.{epoch}")
    shutil.copy2(path, backup)
    return backup


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def _find_brands_root(search_from: Path | None = None) -> Path:
    """Walk up looking for skills/brand-voice/brands/. Fail clearly if absent."""
    start = (search_from or Path.cwd()).resolve()
    for parent in [start, *start.parents]:
        candidate = parent / "skills" / "brand-voice" / "brands"
        if candidate.exists():
            return candidate
    raise click.ClickException(
        f"could not find skills/brand-voice/brands/ walking up from {start} "
        "(run `zv peel` from inside the zeststream-brand-voice repo)"
    )


def _atomic_copytree(src: Path, dst: Path) -> None:
    """Copy `src` tree to `dst` atomically: stage at `dst.tmp`, rename on
    success, cleanup tmp on failure. Prevents half-bootstrapped brand dirs
    from surviving a crashed preflight (P1-3).
    """
    if dst.exists():
        raise click.ClickException(
            f"atomic copytree refused: {dst} already exists"
        )
    staging = dst.with_name(dst.name + ".tmp")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        shutil.copytree(src, staging)
        os.rename(staging, dst)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def preflight(
    slug: str,
    force: bool = False,
    resume: bool = False,
    *,
    brands_root: Path | None = None,
) -> BrandDirs:
    """Run the 7 pre-flight checks from the spec. Returns resolved dirs.

    Raises click.ClickException (exit 2 via click) on any failure.

    When `force=True` and an existing populated voice.yaml is about to be
    overwritten, the file is first copied to voice.yaml.bak.<epoch> so a
    bad wizard run can be reverted. Same for .peel-state.json before
    unlink. This closes the session-14 silent-failure class.
    """
    # 1. Slug format
    if not SLUG_RE.match(slug):
        raise click.ClickException(
            f"invalid slug {slug!r} — must match ^[a-z][a-z0-9-]{{2,31}}$ "
            "(e.g. 'acme-saas', 'clutterfreespaces')"
        )

    # Find brands root
    root = brands_root or _find_brands_root()
    brand_dir = root / slug
    voice_yaml = brand_dir / "voice.yaml"
    state_file = brand_dir / STATE_FILENAME

    # 2. Brand folder: create from _template if missing; guard against
    #    overwriting populated voice.yaml without --force.
    is_fresh = not brand_dir.exists()
    if is_fresh:
        template_dir = root / "_template"
        if not template_dir.exists():
            # Fallback with warning (matches bootstrap-client.sh behavior).
            fallback = root / "zeststream"
            click.echo(
                f"WARN: template missing at {template_dir}, falling back to "
                f"{fallback} (Yuzu Method contamination risk — strip in Block 3)",
                err=True,
            )
            if not fallback.exists():
                raise click.ClickException(
                    "no template and no fallback — cannot create brand skeleton"
                )
            template_dir = fallback
        _atomic_copytree(template_dir, brand_dir)
    else:
        if voice_yaml.exists() and voice_yaml.read_text(encoding="utf-8").strip():
            if not (force or resume):
                raise click.ClickException(
                    f"brand already exists at {brand_dir} with populated "
                    "voice.yaml — pass --force to overwrite or --resume to "
                    "continue a prior run"
                )
            if force:
                # P0-1: Back up the existing voice.yaml before any overwrite.
                backup = _backup_file(voice_yaml)
                if backup is not None:
                    click.echo(
                        f"backed up existing voice.yaml -> {backup}", err=True
                    )

    # 3. Template present (already handled implicitly via is_fresh branch).

    # 4. State file / resume handshake
    existing_state = state_file.exists()
    if existing_state and not resume and not force:
        raise click.ClickException(
            f"existing peel state at {state_file} — pass --resume to continue "
            "or --force to discard"
        )
    if existing_state and force:
        # P0-1: Back up the state file before discard so a bad force run is
        # not irrecoverable.
        backup = _backup_file(state_file)
        if backup is not None:
            click.echo(
                f"backed up existing peel state -> {backup}", err=True
            )
        state_file.unlink()

    # 5. Writable check
    if not os.access(brand_dir, os.W_OK):
        raise click.ClickException(
            f"brand dir {brand_dir} is not writable"
        )

    # 6. yaml library sanity — catch session-14 "import silently broken" class.
    probe = yaml.safe_load("a: b")
    if probe != {"a": "b"}:
        raise click.ClickException(
            "yaml.safe_load sanity probe failed — PyYAML install is broken"
        )

    # 7. (Operator-name prompt happens in Block 1 Q1.2, not pre-flight.)

    return BrandDirs(
        slug=slug,
        brand_dir=brand_dir,
        voice_yaml=voice_yaml,
        state_file=state_file,
        is_fresh=is_fresh,
    )


# ---------------------------------------------------------------------------
# Input helpers (thin wrappers over click.prompt for testability)
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Strip surrounding whitespace from a caller-supplied prompt result.

    Intentionally narrow: defaults are assumed pre-cleaned (see P2-7). The
    helper exists so we never accidentally strip data that isn't ours.
    """
    return text.strip()


def _ask(prompt: str, *, default: str | None = None) -> str:
    """Prompt for a freeform string. Returns the stripped answer.

    If `default` is provided it is shown in the prompt and accepted on
    empty enter. Pass the rejected value as default on re-prompt so the
    user can edit rather than retype (P1-1).
    """
    return _clean(
        click.prompt(
            prompt, default=default, type=str, show_default=default is not None
        )
    )


def _ask_list(prompt: str) -> list[str]:
    """Prompt for a comma-separated list. Empty input returns []."""
    raw = click.prompt(prompt, default="", show_default=False, type=str)
    if not raw.strip():
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _ask_choice(
    prompt: str, choices: list[str], *, default: str | None = None
) -> str:
    """Prompt for one of `choices` (case-insensitive). Returns lowercased."""
    return click.prompt(
        prompt,
        type=click.Choice(choices, case_sensitive=False),
        default=default,
        show_default=default is not None,
    ).lower()


def _ask_yn(prompt: str, *, default: bool = False) -> bool:
    """Yes/no confirm. Returns bool."""
    return click.confirm(prompt, default=default)


# ---------------------------------------------------------------------------
# Block 1 — IDENTITY
# ---------------------------------------------------------------------------


def block_1_identity(state: PeelState) -> dict:
    """Collect IDENTITY block per spec. Returns dict with brand + posture keys."""
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 1 — IDENTITY")
    click.echo("=" * 60)
    click.echo(
        "Locks canonical operator name, pronoun posture, and domain.\n"
        "Prevents the Josh/Joshua drift class (session 15 trauma).\n"
    )

    q11 = _ask("Q1.1 Brand display name (what appears in logos, titles)?")
    while not q11 or len(q11) > 40:
        click.echo("  must be non-empty and <=40 chars")
        q11 = _ask("Q1.1 Brand display name?", default=q11 or None)

    q12 = _ask("Q1.2 Canonical operator name (full, as you want it on public copy)?")
    while not q12:
        q12 = _ask("Q1.2 Operator name?", default=q12 or None)

    q13 = _ask_list(
        f"Q1.3 Name variants that MUST be auto-rejected? Comma-separated "
        f"(e.g. for {q12!r}: 'Josh, J. Nowak')"
    )
    if not q13:
        click.echo("  (no banned variants — workers can use any nickname)")

    q14 = _ask("Q1.4 Primary domain (no protocol, e.g. zeststream.ai)?")
    while not DOMAIN_RE.match(q14):
        click.echo(
            "  must match domain pattern (non-empty labels, no leading/"
            "trailing dashes, TLD 2+ chars — e.g. 'example.com')"
        )
        q14 = _ask("Q1.4 Primary domain?", default=q14 or None)

    q15 = _ask_choice(
        "Q1.5 Is this a solo operator brand or a team brand? [solo/team]",
        ["solo", "team"],
        default="solo",
    )

    q16 = None
    q17_exceptions: list[dict] = []
    if q15 == "team":
        q16 = _ask_choice(
            "Q1.6 Who speaks in copy? [single-voice-founder/collective-we/both]",
            ["single-voice-founder", "collective-we", "both"],
            default="single-voice-founder",
        )
    else:
        if _ask_yn(
            "Q1.7 Any permitted 'we' exceptions (e.g. 'we sold the company' "
            "referring to a prior collective)?",
            default=False,
        ):
            ctx = _ask("  context (e.g. 'named prior-company collective action')")
            example = _ask("  example phrase")
            where = _ask("  where allowed (e.g. 'origin_story_surfaces')")
            rationale = _ask("  rationale")
            q17_exceptions.append(
                {
                    "context": ctx,
                    "example": example,
                    "where_allowed": where,
                    "rationale": rationale,
                }
            )

    q18 = _ask(
        "Q1.8 Source-of-truth file path for capability claims (blank to default)?",
        default="",
    )

    # Derive pronouns + voice posture
    if q15 == "solo":
        voice_label = "first-person singular"
        pronouns_allowed = ["I", "me", "my", "you", "your"]
        pronouns_banned = ["we", "our", "our team", "us"]
    else:
        if q16 == "collective-we":
            voice_label = "first-person plural"
            pronouns_allowed = ["we", "our", "us", "you", "your"]
            pronouns_banned = []
        elif q16 == "both":
            voice_label = "mixed first-person"
            pronouns_allowed = ["I", "we", "our", "us", "you", "your"]
            pronouns_banned = []
        else:
            voice_label = "first-person singular (founder voice)"
            pronouns_allowed = ["I", "me", "my", "you", "your"]
            pronouns_banned = ["our team", "us"]

    source_of_truth = q18 or f"brands/{state.slug}/SOURCE_OF_TRUTH.md"

    payload = {
        "brand": {
            "slug": state.slug,
            "name": q11,
            "operator": q12,
            "operator_variants_banned": q13,
            "domain": q14,
            "source_of_truth": source_of_truth,
            "ground_truth": f"brands/{state.slug}/data/capabilities-ground-truth.yaml",
        },
        "posture": {
            "voice": voice_label,
            "pronouns_allowed": pronouns_allowed,
            "pronouns_banned": pronouns_banned,
            "permitted_exceptions": q17_exceptions,
            "attribution_rule": (
                "<filled in Block 5 BANS — upstream tool attribution rules>"
            ),
        },
    }

    # Checkpoint
    click.echo("")
    click.echo("IDENTITY locked:")
    click.echo(f"  Brand:    {q11} ({state.slug})")
    click.echo(f"  Operator: {q12} — banned variants: {q13 or '(none)'}")
    click.echo(f"  Voice:    {voice_label}")
    click.echo(f"  Allowed:  {pronouns_allowed}")
    click.echo(f"  Banned:   {pronouns_banned}")

    return payload


# ---------------------------------------------------------------------------
# Block 2 — CANON
# ---------------------------------------------------------------------------


def _word_count(s: str) -> int:
    """Count words using a Vale-compatible tokenizer (P1-4).

    Hyphens and apostrophes bind words together so "state-of-the-art" is 1
    word and "don't" is 1 word. Matches the tokenization used downstream
    by rules/surface_sentence_caps.yaml.
    """
    return len(_WORD_RE.findall(s))


def block_2_canon(state: PeelState) -> dict:
    """Collect CANON block per spec. Returns dict with canon key."""
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 2 — CANON")
    click.echo("=" * 60)
    click.echo(
        "The ONE verbatim line that appears on every top-level route.\n"
        "<=18 words. Never paraphrased. Gives STEP-0 grep an exact target.\n"
    )

    max_words = 18
    q21 = _ask("Q2.1 Your ONE verbatim canon line?")
    while True:
        wc = _word_count(q21)
        if not q21 or wc == 0:
            q21 = _ask("  must be non-empty", default=q21 or None)
            continue
        if wc > max_words:
            click.echo(f"  too long ({wc} words, max {max_words}). Tighten it.")
            q21 = _ask("Q2.1 Canon line?", default=q21)
            continue
        if wc > 14:
            click.echo(f"  WARN: {wc} words — hero surface caps at 14 for punch.")
        break

    q22 = _ask_list(
        "Q2.2 2-3 approved variants (opener variations allowed on /about etc)?"
    )

    q23 = _ask_choice(
        "Q2.3 Where must the primary canon appear verbatim? "
        "[top-level-routes/hero-only/every-page]",
        ["top-level-routes", "hero-only", "every-page"],
        default="top-level-routes",
    )

    q24 = _ask_yn(
        "Q2.4 Can the canon be split across hero + sub-headline?",
        default=False,
    )

    payload = {
        "canon": {
            "primary": q21,
            "variants_approved": q22,
            "rule": (
                f"Primary canon appears verbatim at least once per {q23}. "
                "Variants allowed on /about opener."
            ),
            "allow_split": q24,
        }
    }

    click.echo("")
    click.echo(f'CANON: "{q21}"')
    click.echo(f"  appears verbatim per: {q23}")
    click.echo(f"  variants: {len(q22)}")

    return payload


# ---------------------------------------------------------------------------
# Blocks 3-9 — stubs
# ---------------------------------------------------------------------------


BLOCK_NAMES = {
    3: "METHOD",
    4: "RECEIPTS",
    5: "BANS",
    6: "WE_ARE / WE_ARE_NOT",
    7: "OFFER + PRICING",
    8: "SITUATION PLAYBOOKS",
    9: "EXEMPLARS SEED",
}


def block_stub(block_num: int) -> dict:
    """Print a 'not yet implemented' notice. Returns empty payload."""
    label = BLOCK_NAMES.get(block_num, f"BLOCK {block_num}")
    click.echo("")
    click.echo(
        f"[BLOCK {block_num} — {label}] — not yet implemented in v0.5, skipping"
    )
    return {}


# ---------------------------------------------------------------------------
# Merge + write
# ---------------------------------------------------------------------------


def merge_to_voice_yaml(brand_dir: Path, state: PeelState) -> Path:
    """Compose collected block answers into voice.yaml, safe_dump, safe_load-validate.

    Writes to brand_dir/voice.yaml. Returns the written path.
    Raises click.ClickException if the result does not round-trip through
    yaml.safe_load (session-14 silent-failure guard).
    """
    voice: dict = {}

    b1 = state.answers.get("1", {})
    if b1:
        voice["brand"] = b1.get("brand", {})

    b2 = state.answers.get("2", {})
    if b2:
        voice["canon"] = b2.get("canon", {})

    # posture comes from block 1 (lives under posture:)
    if b1 and b1.get("posture"):
        voice["posture"] = b1["posture"]

    # Future blocks merge in as they land in state.answers.

    voice_yaml = brand_dir / "voice.yaml"
    tmp = voice_yaml.with_suffix(".yaml.tmp")

    header = (
        f"# {voice.get('brand', {}).get('name', state.slug)} brand voice — "
        "machine-checkable constants\n"
        f"# generated by zv peel at {_now_iso()}\n"
        "# v0.5 scaffold — only blocks 1-2 wired. Re-run after blocks 3-9 land.\n"
        "\n"
    )
    body = yaml.safe_dump(voice, sort_keys=False, allow_unicode=True, width=100)

    tmp.write_text(header + body, encoding="utf-8")

    # Silent-failure guard: re-parse what we just wrote.
    try:
        reparsed = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        tmp.unlink(missing_ok=True)
        raise click.ClickException(
            f"written voice.yaml did not round-trip yaml.safe_load: {e}"
        ) from e

    if not isinstance(reparsed, dict) or "brand" not in reparsed:
        tmp.unlink(missing_ok=True)
        raise click.ClickException(
            "written voice.yaml parsed but missing 'brand' key — aborting"
        )

    os.replace(tmp, voice_yaml)
    return voice_yaml


# ---------------------------------------------------------------------------
# Corrupt-state recovery (P0-2)
# ---------------------------------------------------------------------------


def _recover_corrupt_state(brand_dir: Path, exc: click.ClickException) -> PeelState | None:
    """Prompt the user on corrupt .peel-state.json — resume/abort/discard.

    Returns None (start fresh) if user picks 'discard'; re-raises on 'abort'.
    'resume' is a no-op fallthrough that re-raises so the caller sees it as
    unresumable — the state file is genuinely unreadable.
    """
    state_file = brand_dir / STATE_FILENAME
    click.echo(str(exc), err=True)
    choice = _ask_choice(
        f"Existing peel state at {state_file} is corrupt. "
        "Resume (retry read), abort (exit), or discard (start fresh)?",
        ["resume", "abort", "discard"],
        default="abort",
    )
    if choice == "discard":
        # Back up the corrupt file before deleting so forensics is possible.
        backup = _backup_file(state_file, suffix="corrupt")
        if backup is not None:
            click.echo(
                f"backed up corrupt state -> {backup}", err=True
            )
        state_file.unlink(missing_ok=True)
        return None
    # resume and abort both surface the original exception — a corrupt file
    # cannot be parsed, there's nothing to retry.
    raise exc


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


@click.command("peel", help="Run the conversational peel wizard for a brand.")
@click.argument("slug")
@click.option("--force", is_flag=True, help="Overwrite existing brand voice.yaml.")
@click.option("--resume", is_flag=True, help="Resume a prior peel run from state.")
@click.option(
    "--skip-block",
    "skip_block",
    type=int,
    default=None,
    help="Skip a single block for this run (preconditions still apply).",
)
@click.option(
    "--brands-root",
    "brands_root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Override brands root (for tests).",
)
def cli(
    slug: str,
    force: bool,
    resume: bool,
    skip_block: int | None,
    brands_root: Path | None,
) -> None:
    dirs = preflight(slug, force=force, resume=resume, brands_root=brands_root)

    click.echo(f"zv peel — brand {slug} at {dirs.brand_dir}")
    click.echo("9-block agenda: IDENTITY, CANON, METHOD, RECEIPTS, BANS,")
    click.echo("                WE_ARE/WE_ARE_NOT, OFFER+PRICING,")
    click.echo("                SITUATION PLAYBOOKS, EXEMPLARS SEED")
    click.echo("")

    # Load or init state. On corrupt state, offer the three-way recovery
    # prompt instead of crashing (P0-2).
    state: PeelState | None = None
    if resume:
        try:
            state = load_state(dirs.brand_dir)
        except click.ClickException as exc:
            state = _recover_corrupt_state(dirs.brand_dir, exc)
    if state is None:
        state = PeelState(
            slug=slug,
            started_at=_now_iso(),
            current_block=1,
            blocks_completed=[],
            answers={},
        )

    # Block 1 — IDENTITY
    if 1 in state.blocks_completed:
        click.echo("Block 1 already complete — skipping (use --force to redo).")
    elif skip_block == 1:
        click.echo("Skipping Block 1 (--skip-block). WARN: structural block.")
    else:
        state.answers["1"] = block_1_identity(state)
        state.blocks_completed.append(1)
        state.current_block = 2
        save_state(dirs.brand_dir, state)

    # Block 2 — CANON
    if 2 in state.blocks_completed:
        click.echo("Block 2 already complete — skipping.")
    elif skip_block == 2:
        click.echo("Skipping Block 2 (--skip-block).")
    else:
        state.answers["2"] = block_2_canon(state)
        state.blocks_completed.append(2)
        state.current_block = 3
        save_state(dirs.brand_dir, state)

    # Blocks 3-9 stubs
    for n in range(3, 10):
        block_stub(n)

    # Compose voice.yaml + silent-failure guard
    written = merge_to_voice_yaml(dirs.brand_dir, state)
    save_state(dirs.brand_dir, state)

    click.echo("")
    click.echo(f"voice.yaml written: {written}")
    click.echo(f"state: {dirs.state_file}")
    click.echo("")
    click.echo("Next steps:")
    click.echo(f"  zeststream-voice score 'test sentence' --brand {slug}")
    click.echo("  (blocks 3-9 land in v0.5 follow-up)")
