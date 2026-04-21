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
# Block 4 — RECEIPTS (writes data/capabilities-ground-truth.yaml)
# ---------------------------------------------------------------------------


RECEIPT_CATEGORIES = ["capability", "number", "client", "tool", "duration", "benchmark"]
RECEIPT_VISIBILITY = ["public", "internal-only", "private-ceiling"]
RECEIPT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_EVIDENCE_FUZZY_RE = re.compile(r"~|\broughly\b|\bapproximately\b", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _receipt_category_hint(receipts: dict) -> str:
    """Nudge operator toward empty categories so distribution stays broad."""
    seen = {r.get("category") for r in receipts.values()}
    missing = [c for c in RECEIPT_CATEGORIES if c not in seen]
    if not missing or not receipts:
        return ""
    return f"  (so far covered: {sorted(seen)}; missing: {missing})"


def block_4_receipts(state: PeelState, brand_dir: Path) -> dict:
    """Collect RECEIPTS block per spec. Writes ground-truth sidecar file.

    Returns a payload dict `{"ground_truth_file": "<relative path>"}` so
    merge_to_voice_yaml can reference the sidecar without inlining claims.
    """
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 4 — RECEIPTS")
    click.echo("=" * 60)
    click.echo(
        "Ground-truth claims every copy worker cites against.\n"
        "Minimum 5 receipts. 'I remember' is NOT evidence.\n"
    )

    receipts: dict[str, dict] = {}
    min_receipts = 5

    while True:
        idx = len(receipts) + 1
        click.echo("")
        click.echo(f"--- Receipt #{idx} ---")
        hint = _receipt_category_hint(receipts)
        if hint:
            click.echo(hint)

        q41 = _ask_choice(
            "Q4.1 Category? [capability/number/client/tool/duration/benchmark]",
            RECEIPT_CATEGORIES,
        )

        # Q4.2 key — unique, regex-valid, <=32 chars
        while True:
            q42 = _ask("Q4.2 Short label (used as key, [a-z][a-z0-9_]*, <=32 chars)?")
            if not RECEIPT_KEY_RE.match(q42) or len(q42) > 32:
                click.echo(
                    "  invalid key — must match ^[a-z][a-z0-9_]*$ and be <=32 chars"
                )
                continue
            if q42 in receipts:
                click.echo(f"  key {q42!r} already used — pick another")
                continue
            break

        q43 = _ask("Q4.3 The claim, verbatim as you'd say it in copy?")
        while not q43:
            q43 = _ask("  must be non-empty. Q4.3 Claim?", default=q43 or None)

        while True:
            q44 = _ask(
                "Q4.4 Evidence — link, SHA, file path, benchmark log, "
                "client name w/ permission (required)?"
            )
            if not q44:
                click.echo("  evidence is required. 'I remember' is not evidence.")
                continue
            if _EVIDENCE_FUZZY_RE.search(q44):
                click.echo(
                    "  WARN: evidence contains fuzzy qualifier "
                    "(~, roughly, approximately) — tighten if possible."
                )
            break

        q45 = _ask_choice(
            "Q4.5 Permission level? [public/internal-only/private-ceiling]",
            RECEIPT_VISIBILITY,
            default="public",
        )

        while True:
            q46 = _ask(
                "Q4.6 Expires? [never / YYYY-MM-DD]", default="never"
            )
            if q46 == "never" or ISO_DATE_RE.match(q46):
                break
            click.echo("  must be 'never' or ISO date YYYY-MM-DD")

        receipts[q42] = {
            "category": q41,
            "claim": q43,
            "evidence": q44,
            "visibility": q45,
            "expires": q46,
        }

        if len(receipts) < min_receipts:
            click.echo(
                f"  captured {len(receipts)}/{min_receipts} minimum — continuing."
            )
            continue

        if not _ask_yn("Q4.7 Add another receipt?", default=False):
            break

    # Write sidecar atomically.
    data_dir = brand_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    gt_path = data_dir / "capabilities-ground-truth.yaml"

    ground_truth = {
        "version": 1,
        "last_updated": _now_iso(),
        "receipts": receipts,
        "private_pricing": {
            "in_pocket_floor": None,
            "retainer_ceiling": None,
        },
    }

    header = (
        f"# {state.slug} capabilities ground-truth — cited by voice-gate\n"
        f"# generated by zv peel block 4 at {_now_iso()}\n"
        "# private_pricing populated by Block 7 (OFFER + PRICING).\n"
        "\n"
    )
    body = yaml.safe_dump(ground_truth, sort_keys=False, allow_unicode=True, width=100)
    tmp = gt_path.with_suffix(".yaml.tmp")
    tmp.write_text(header + body, encoding="utf-8")

    try:
        reparsed = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        tmp.unlink(missing_ok=True)
        raise click.ClickException(
            f"capabilities-ground-truth.yaml did not round-trip: {e}"
        ) from e
    if not isinstance(reparsed, dict) or "receipts" not in reparsed:
        tmp.unlink(missing_ok=True)
        raise click.ClickException(
            "capabilities-ground-truth.yaml parsed but missing 'receipts' key"
        )

    os.replace(tmp, gt_path)

    # Checkpoint summary
    click.echo("")
    click.echo(f"RECEIPTS locked: {len(receipts)} claims")
    for key, receipt in receipts.items():
        click.echo(f"  [{receipt['category']}] {key}: {receipt['claim'][:60]}")
    click.echo(f"  sidecar: {gt_path}")
    click.echo(
        "If a worker cites these and someone asks 'show me', "
        "you can hand them evidence in <5 min."
    )

    return {
        "ground_truth_file": str(gt_path.relative_to(brand_dir.parent.parent)),
        "receipt_count": len(receipts),
    }


# ---------------------------------------------------------------------------
# Block 6 — WE_ARE / WE_ARE_NOT (writes WE_ARE.md + WE_ARE_NOT.md)
# ---------------------------------------------------------------------------


WE_ARE_BANNED_VERBS = frozenset(
    {"help", "enable", "empower", "leverage", "streamline", "transform"}
)


def _has_banned_verb(text: str) -> str | None:
    """Return the first banned verb found (case-insensitive word boundary), or None."""
    lowered = text.lower()
    for verb in WE_ARE_BANNED_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", lowered):
            return verb
    return None


WE_ARE_TEMPLATE = """# We Are — {brand_name}

{q61}

## What we do
{q62}

## How we prove it
- {q65_1}
- {q65_2}
- {q65_3}

## Origin
{q66}
"""


WE_ARE_NOT_TEMPLATE = """# We Are Not — {brand_name}

{q63}

## What we refuse to do
- {q64_1}
- {q64_2}
- {q64_3}
"""


def _ask_exact_n(prompt: str, n: int) -> list[str]:
    """Prompt repeatedly until the operator supplies exactly n comma-separated items."""
    while True:
        items = _ask_list(prompt)
        if len(items) == n:
            return items
        click.echo(f"  need exactly {n} items (got {len(items)}). Re-enter.")


def block_6_we_are(state: PeelState, brand_dir: Path) -> dict:
    """Collect WE_ARE / WE_ARE_NOT block per spec. Writes two markdown files.

    Returns payload with the written file paths so the operator can audit.
    """
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 6 — WE_ARE / WE_ARE_NOT")
    click.echo("=" * 60)
    click.echo(
        "Narrative anchor docs. Every worker reads these before writing copy.\n"
        "Q6.2 auto-rejects banned verbs (help/enable/empower/leverage/"
        "streamline/transform).\n"
    )

    # Q6.1
    q61 = _ask("Q6.1 In 2-3 sentences: who is this brand? (First person if solo.)")
    while not q61:
        q61 = _ask("  must be non-empty. Q6.1 Who is this brand?", default=q61 or None)

    # Q6.2 — banned-verb gate
    while True:
        q62 = _ask(
            "Q6.2 What does this brand DO, concretely? "
            "(No 'help', no 'enable', no 'empower'.)"
        )
        if not q62:
            click.echo("  must be non-empty.")
            continue
        banned = _has_banned_verb(q62)
        if banned:
            click.echo(
                f"  auto-reject: contains banned verb {banned!r}. "
                "Rewrite with concrete action verbs."
            )
            continue
        break

    # Q6.3
    q63 = _ask(
        "Q6.3 What does this brand REFUSE to do? (Anti-scope — 'not for everyone'.)"
    )
    while not q63:
        q63 = _ask("  must be non-empty. Q6.3 Refuse to do?", default=q63 or None)

    # Q6.4 — exactly 3
    q64 = _ask_exact_n(
        "Q6.4 Exactly 3 things competitors do that you explicitly do NOT do? "
        "(comma-separated)",
        3,
    )

    # Q6.5 — exactly 3
    q65 = _ask_exact_n(
        "Q6.5 Exactly 3 receipt moves you make that competitors do not? "
        "(comma-separated)",
        3,
    )

    # Q6.6 — 3-8 sentences
    while True:
        q66 = _ask(
            "Q6.6 One paragraph of origin: how did you get here, "
            "why does this brand exist? (3-8 sentences)"
        )
        if not q66:
            click.echo("  must be non-empty.")
            continue
        # sentence count by terminal punctuation.
        sentence_count = len(re.findall(r"[.!?]+(?:\s|$)", q66))
        if sentence_count < 3:
            click.echo(f"  need >=3 sentences (got {sentence_count}). Expand.")
            continue
        if sentence_count > 8:
            click.echo(f"  need <=8 sentences (got {sentence_count}). Tighten.")
            continue
        break

    brand_name = state.answers.get("1", {}).get("brand", {}).get("name") or state.slug

    we_are_text = WE_ARE_TEMPLATE.format(
        brand_name=brand_name,
        q61=q61,
        q62=q62,
        q65_1=q65[0],
        q65_2=q65[1],
        q65_3=q65[2],
        q66=q66,
    )
    we_are_not_text = WE_ARE_NOT_TEMPLATE.format(
        brand_name=brand_name,
        q63=q63,
        q64_1=q64[0],
        q64_2=q64[1],
        q64_3=q64[2],
    )

    we_are_path = brand_dir / "WE_ARE.md"
    we_are_not_path = brand_dir / "WE_ARE_NOT.md"

    # Back up existing files (P0-1 class) before overwrite.
    for path in (we_are_path, we_are_not_path):
        if path.exists() and path.read_text(encoding="utf-8").strip():
            backup = _backup_file(path)
            if backup is not None:
                click.echo(f"backed up existing {path.name} -> {backup}", err=True)

    tmp_a = we_are_path.with_suffix(".md.tmp")
    tmp_a.write_text(we_are_text, encoding="utf-8")
    os.replace(tmp_a, we_are_path)

    tmp_b = we_are_not_path.with_suffix(".md.tmp")
    tmp_b.write_text(we_are_not_text, encoding="utf-8")
    os.replace(tmp_b, we_are_not_path)

    click.echo("")
    click.echo(f"WE_ARE.md     written: {we_are_path}")
    click.echo(f"WE_ARE_NOT.md written: {we_are_not_path}")
    click.echo(
        "Read both. If a stranger reads them and then your homepage, "
        "do they feel whiplash?"
    )

    return {
        "we_are_file": str(we_are_path.relative_to(brand_dir.parent.parent)),
        "we_are_not_file": str(we_are_not_path.relative_to(brand_dir.parent.parent)),
    }


# ---------------------------------------------------------------------------
# Blocks 3, 5, 7-9 — stubs
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
# Block 3 — METHOD (optional)
# ---------------------------------------------------------------------------


# Yuzu Method is ZestStream IP — always auto-rejected in non-zeststream brands.
_YUZU_IP_TOKENS = ("yuzu", "peel. press. pour", "blackpond")


def _slugify_phase(name: str) -> str:
    """Turn a phase name into a YAML-safe key (lowercase alnum + underscore)."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "phase"


def block_3_method(state: PeelState) -> dict:
    """Collect METHOD block. OPTIONAL — returns {} if operator has no method.

    Q3.0 = n → {} (caller must OMIT the `method:` key entirely, not null).
    Q3.0 = y → full Q3.1..Q3.8; Q3.4..Q3.7 iterate per phase.
    Q3.8 auto-rejects responses containing Yuzu / Peel. Press. Pour / BlackPond.
    """
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 3 — METHOD (optional)")
    click.echo("=" * 60)
    click.echo(
        "A named phase model clients move through (e.g. Discover → Design → Deliver).\n"
        "Optional — many brands don't have one. Skip if unsure.\n"
        "NOTE: Yuzu Method is ZestStream IP — must not appear in your output.\n"
    )

    q30 = _ask_yn(
        "Q3.0 Do you have a named methodology / phase model?", default=False
    )
    if not q30:
        click.echo("No methodology declared. `method:` will be omitted from voice.yaml.")
        return {}

    q31 = _ask("Q3.1 Methodology full name (with ™/® marks if registered)?")
    while not q31:
        q31 = _ask("Q3.1 Methodology full name?", default=q31 or None)

    q32 = _ask('Q3.2 Short motto (e.g. "Peel. Press. Pour.™")?')
    while not q32:
        q32 = _ask("Q3.2 Short motto?", default=q32 or None)

    # Q3.3 — phase count [2..5]
    while True:
        raw = _ask("Q3.3 How many phases? [2-5]", default="3")
        try:
            n_phases = int(raw)
        except ValueError:
            click.echo("  must be an integer 2-5")
            continue
        if 2 <= n_phases <= 5:
            break
        click.echo("  must be between 2 and 5")

    phases: dict[str, dict] = {}
    for i in range(1, n_phases + 1):
        click.echo("")
        click.echo(f"— Phase {i} of {n_phases} —")

        p_name = _ask(f"Q3.4 Phase {i} name?")
        while not p_name:
            p_name = _ask(f"Q3.4 Phase {i} name?", default=p_name or None)

        p_duration = _ask(f'Q3.5 Phase {i} duration? (e.g. "Week 1", "Weeks 2-8")')
        while not p_duration:
            p_duration = _ask(
                f"Q3.5 Phase {i} duration?", default=p_duration or None
            )

        p_role = _ask(f"Q3.6 Phase {i} role? (Discovery/Build/Launch/other)")
        while not p_role:
            p_role = _ask(f"Q3.6 Phase {i} role?", default=p_role or None)

        p_quote = _ask(
            f"Q3.7 Phase {i} milestone quote — something a client would actually say?"
        )
        while not p_quote:
            p_quote = _ask(
                f"Q3.7 Phase {i} milestone quote?", default=p_quote or None
            )
        if p_quote.lower().lstrip().startswith(("we'll ", "we will ")):
            click.echo(
                "  WARN: quote starts with marketing-tense 'We'll'. "
                "Consider rewording to past/present client voice."
            )

        slug = _slugify_phase(p_name)
        base_slug = slug
        collide = 2
        while slug in phases:
            slug = f"{base_slug}_{collide}"
            collide += 1
        phases[slug] = {
            "duration": p_duration,
            "role": p_role,
            "milestone_quote": p_quote,
        }

    # Q3.8 — Yuzu IP guard loop. Blank answer is allowed.
    while True:
        q38 = _ask(
            "Q3.8 Does your methodology conflict with or extend another named "
            "framework? (Leave blank if no. Yuzu Method is ZestStream IP and "
            "must NOT appear here.)",
            default="",
        )
        lower = q38.lower()
        if any(tok in lower for tok in _YUZU_IP_TOKENS):
            click.echo(
                "  REJECTED: contains reference to Yuzu Method / "
                "Peel. Press. Pour / BlackPond — ZestStream IP. Re-phrase."
            )
            continue
        break

    method: dict = {
        "name_full": q32,
        "name_registered": q31,
        "phases": phases,
        "phase_not_gate": True,
    }
    if q38:
        method["conflicts_or_extends"] = q38

    click.echo("")
    click.echo(f"METHOD locked: {q31} — {q32}")
    for slug, p in phases.items():
        click.echo(f"  {slug}: {p['duration']}, {p['role']}")
        click.echo(f'    Milestone: "{p["milestone_quote"]}"')

    return {"method": method}


# ---------------------------------------------------------------------------
# Block 5 — BANS
# ---------------------------------------------------------------------------


# Starter default-slop list — operators extract their own bans by
# intersecting this with the nauseating-copy paste they provide in Q5.1.
# Do NOT re-derive per brand.
DEFAULT_SLOP = [
    "platform", "enterprise", "seamless", "transformation", "robust",
    "leverage", "streamline", "synergy", "innovative", "cutting-edge",
    "paradigm", "disrupt", "solution", "empower", "unlock",
    "revolutionize", "best-in-class", "world-class",
]


def _extract_slop_candidates(paste: str) -> dict[str, int]:
    """Return {slop_word: count} for DEFAULT_SLOP terms appearing in paste.

    Case-insensitive. Hyphenated slop ("cutting-edge") uses substring
    search; single-word slop uses the Vale tokenizer so "leveraging"
    does not match "leverage".
    """
    lowered = paste.lower()
    tokens = [t.lower() for t in _WORD_RE.findall(paste)]
    counts: dict[str, int] = {}
    for term in DEFAULT_SLOP:
        if "-" in term:
            c = lowered.count(term)
            if c:
                counts[term] = c
        else:
            c = sum(1 for t in tokens if t == term)
            if c:
                counts[term] = c
    return counts


def _read_multiline(prompt: str, *, min_lines: int = 3) -> str:
    """Read multi-line input until a blank line. Re-prompt if <min_lines."""
    while True:
        click.echo(prompt)
        click.echo(
            f"  (end with a blank line; need at least {min_lines} "
            "non-empty lines)"
        )
        lines: list[str] = []
        while True:
            raw = click.get_text_stream("stdin").readline()
            if raw == "":
                break
            stripped = raw.rstrip("\n")
            if stripped.strip() == "":
                break
            lines.append(stripped)
        if len(lines) >= min_lines:
            return "\n".join(lines)
        click.echo(f"  need at least {min_lines} non-empty lines, got {len(lines)}")


def block_5_bans(state: PeelState) -> dict:
    """Collect BANS block. Returns dict with banned_words, banned_phrases,
    and (optionally) attribution_rules. Block 8 reads these from state so
    its inline scanner can count hits while the operator types exemplars.
    """
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 5 — BANS")
    click.echo("=" * 60)
    click.echo(
        "Lexical grep guard — the cheapest, highest-leverage voice enforcement.\n"
        "Every banned word caught pre-emit never reaches the weighted rubric.\n"
    )

    paste = _read_multiline(
        "Q5.1 Paste 3-5 sentences from competitors or marketing you find "
        "nauseating. (We'll extract ban patterns.)",
        min_lines=3,
    )

    candidates = _extract_slop_candidates(paste)
    accepted_from_slop: list[str] = []
    if candidates:
        click.echo("")
        click.echo("Auto-extracted ban candidates (default-slop ∩ your paste):")
        for term, count in sorted(candidates.items(), key=lambda x: (-x[1], x[0])):
            click.echo(f"  {term}  (×{count})")
        choice = _ask_choice(
            "Q5.2 Accept these bans? [all/none/select]",
            ["all", "none", "select"],
            default="all",
        )
        if choice == "all":
            accepted_from_slop = sorted(candidates.keys())
        elif choice == "select":
            for term in sorted(candidates.keys()):
                if _ask_yn(f"  ban {term!r}?", default=True):
                    accepted_from_slop.append(term)
    else:
        click.echo("  (no default-slop terms found in your paste)")

    custom_words = _ask_list(
        "Q5.3 Any custom single-word bans specific to your domain? "
        "(comma-separated)"
    )

    banned_phrases = _ask_list(
        'Q5.4 Banned PHRASES (multi-word patterns)? '
        '(comma-separated; e.g. "Not just X but Y","In today\'s world")'
    )

    click.echo("")
    click.echo("Q5.5 Attribution rules — tools built by others that MUST be credited.")
    click.echo(
        "  Format each as '<tool> — <upstream_author>'  "
        "(comma-separated). Leave blank for none."
    )
    raw_attrs = _ask_list("  attribution list?")
    attribution_rules: list[dict] = []
    for raw in raw_attrs:
        parts = re.split(r"\s+[—–-]\s+|\s*\|\s*", raw, maxsplit=1)
        if len(parts) != 2:
            click.echo(
                f"  could not parse {raw!r} — expected 'tool — author'; skipping"
            )
            continue
        tool = parts[0].strip()
        author = parts[1].strip()
        if not tool or not author:
            continue
        default_regex = rf"\b{re.escape(tool)}\b(?!.*{re.escape(author)})"
        q56 = _ask(
            f"Q5.6 Auto-reject regex for misattributing {tool!r}? "
            "(blank = generated default)",
            default="",
        )
        regex = q56 or default_regex
        try:
            re.compile(regex)
        except re.error as e:
            click.echo(f"  invalid regex ({e}); falling back to generated default")
            regex = default_regex
        rule_id = re.sub(r"[^a-z0-9]+", "_", tool.lower()).strip("_") or "attribution"
        attribution_rules.append({
            "id": rule_id,
            "upstream_author": author,
            "tools": [tool],
            "rule": f"Cite {author} whenever {tool} is mentioned.",
            "trigger_regex": regex,
            "action": "auto_reject",
            "explanation": (
                f"Prevents silently reattributing {tool} away from {author}."
            ),
        })

    never_appear = _ask_list(
        "Q5.7 Any subject/phrase that must NEVER appear in copy "
        "(trademarked competitor, deprecated product, NDA-covered client)?"
    )

    banned_words = list(dict.fromkeys(accepted_from_slop + custom_words))
    banned_phrases_combined = list(dict.fromkeys(banned_phrases + never_appear))

    payload: dict = {
        "banned_words": banned_words,
        "banned_phrases": banned_phrases_combined,
    }
    if attribution_rules:
        payload["attribution_rules"] = attribution_rules

    click.echo("")
    click.echo(
        f"BANS locked: {len(banned_words)} words, "
        f"{len(banned_phrases_combined)} phrases, "
        f"{len(attribution_rules)} attribution rules."
    )

    return payload


# ---------------------------------------------------------------------------
# Block 7 — OFFER + PRICING
# ---------------------------------------------------------------------------


def _write_private_pricing(
    brand_dir: Path,
    slug: str,
    in_pocket_floor: str | None,
    retainer_ceiling: str | None,
) -> Path:
    """Append private_pricing to capabilities-ground-truth.yaml.

    Creates the file with a minimal structure if Block 4 was skipped.
    Uses safe_load + merge + safe_dump — never string-append. Round-trip
    guard catches silent-failure class (session-14).
    """
    gt_path = brand_dir / "data" / "capabilities-ground-truth.yaml"
    gt_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if gt_path.exists():
        try:
            loaded = yaml.safe_load(gt_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except yaml.YAMLError as e:
            raise click.ClickException(
                f"existing {gt_path} is not valid YAML: {e}"
            ) from e
    else:
        data = {
            "version": 1,
            "last_updated": _now_iso(),
            "brand": slug,
            "receipts": {},
        }

    data.setdefault("version", 1)
    data["last_updated"] = _now_iso()
    data["private_pricing"] = {
        "in_pocket_floor": in_pocket_floor,
        "retainer_ceiling": retainer_ceiling,
        "rule": (
            "Never speak in-pocket floor in public copy. "
            "Never quote retainer ceiling unscoped."
        ),
    }

    tmp = gt_path.with_suffix(".yaml.tmp")
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    tmp.write_text(body, encoding="utf-8")
    try:
        yaml.safe_load(tmp.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        tmp.unlink(missing_ok=True)
        raise click.ClickException(
            f"ground-truth.yaml did not round-trip: {e}"
        ) from e
    os.replace(tmp, gt_path)
    return gt_path


def block_7_offer_pricing(state: PeelState, brand_dir: Path) -> dict:
    """Collect OFFER + PRICING. Public fragment → voice.yaml.offer; private
    pricing → capabilities-ground-truth.yaml.private_pricing (sidecar).

    Q7.1 = peel-only is the default & recommended doctrine.
    Q7.5/Q7.6 are PRIVATE and never written to voice.yaml.
    Q7.7 CTA is validated against surfaces.cta.sentence_max_words (default 5).
    """
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 7 — OFFER + PRICING")
    click.echo("=" * 60)
    click.echo(
        "Public commercial invitation. Peel-only pricing is the default — "
        "publishing tiered prices pre-commits you to numbers before scope.\n"
    )

    q71 = _ask_choice(
        "Q7.1 Pricing doctrine: [peel-only / public-tiers / hybrid]",
        ["peel-only", "public-tiers", "hybrid"],
        default="peel-only",
    )
    if q71 != "peel-only":
        click.echo(
            "  WARN: non-peel-only doctrine means published prices are "
            "held to. Make sure scope is bounded."
        )

    q72 = _ask('Q7.2 Free on-ramp offer (e.g. "Free 20-min Peel session")?')
    while not q72:
        q72 = _ask("Q7.2 Free on-ramp offer?", default=q72 or None)

    q73 = _ask(
        'Q7.3 Low-commitment paid offer (e.g. "$500 Peel Report, 1 week, fixed scope")?'
    )
    while not q73:
        q73 = _ask("Q7.3 Low-commitment paid offer?", default=q73 or None)

    tiers: list[dict] = []
    if q71 != "peel-only":
        click.echo(
            "Q7.4 List paid tiers. For each: name, price, duration, scope. "
            "Leave tier name blank to finish."
        )
        while True:
            t_name = _ask("  tier name? (blank to finish)", default="")
            if not t_name:
                break
            t_price = _ask("    price?")
            t_duration = _ask("    duration?")
            t_scope = _ask("    scope?")
            tiers.append({
                "name": t_name, "price": t_price,
                "duration": t_duration, "scope": t_scope,
            })

    click.echo("")
    click.echo("PRIVATE pricing — NEVER written to voice.yaml, stored in ground-truth.")
    q75 = _ask(
        "Q7.5 In-pocket floor (lowest you'd take — never spoken)?",
        default="",
    ) or None
    q76 = _ask(
        "Q7.6 Retainer ceiling (highest engagement size)?",
        default="",
    ) or None
    if not q75 or not q76:
        click.echo(
            "  WARN: private ceilings unset — workers have no rail against "
            "accidental underquoting in public copy."
        )

    # Q7.7 CTA — validate against surfaces.cta.sentence_max_words if set.
    cta_max = 5
    surfaces_state = state.answers.get("surfaces")
    if isinstance(surfaces_state, dict):
        cta_cap = surfaces_state.get("cta", {}).get("sentence_max_words")
        if isinstance(cta_cap, int) and cta_cap > 0:
            cta_max = cta_cap

    while True:
        q77 = _ask("Q7.7 Primary CTA text on conversion surfaces?")
        if not q77:
            continue
        wc = _word_count(q77)
        if wc > cta_max:
            click.echo(f"  CTA is {wc} words — max {cta_max}. Tighten it.")
            continue
        break

    q78 = _ask(
        'Q7.8 What do you REFUSE to price publicly? '
        '(e.g. "We never quote retainer publicly.")'
    )
    while not q78:
        q78 = _ask("Q7.8 Never-public pricing rule?", default=q78 or None)

    gt_path = _write_private_pricing(brand_dir, state.slug, q75, q76)
    click.echo(f"  private pricing written to {gt_path}")

    payload = {
        "offer": {
            "doctrine": q71,
            "free_onramp": {"label": q72, "cta": q77},
            "paid_entry": {"label": q73, "price_public": q73},
            "tiers": tiers,
            "never_quote_publicly": q78,
        }
    }

    click.echo("")
    click.echo("OFFER locked:")
    click.echo(f"  doctrine:     {q71}")
    click.echo(f"  free on-ramp: {q72}")
    click.echo(f"  paid entry:   {q73}")
    click.echo(f"  CTA:          {q77}")
    if tiers:
        click.echo(f"  tiers:        {len(tiers)}")

    return payload


# ---------------------------------------------------------------------------
# Block 8 / 9 shared helpers (banned-word scanning via scorer layer 1)
# ---------------------------------------------------------------------------


def _banned_words_from_state(state: PeelState) -> tuple[list[str], list[str]]:
    """Pull banned_words + banned_phrases from block 5 answers if present.

    Block 5 (BANS) is owned by another worker and may not have run yet.
    When absent, the inline scanner reports 0 hits and peel still produces
    a valid scaffold.
    """
    b5 = state.answers.get("5", {}) or {}
    words = list(b5.get("banned_words", []) or [])
    phrases = list(b5.get("banned_phrases", []) or [])
    return words, phrases


def _scan_bans(text: str, words: list[str], phrases: list[str]) -> int:
    """Run the real scorer.score_layer1_banned; return raw hit count."""
    from zeststream_voice.scorer import score_layer1_banned

    voice = {"banned_words": words, "banned_phrases": phrases}
    result = score_layer1_banned(text, voice)
    return len(result.details.get("hits", []))


def _slug_from_label(label: str) -> str:
    """Derive an id-safe slug from a free-text situation label."""
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return s or "playbook"


# ---------------------------------------------------------------------------
# Block 8 — SITUATION PLAYBOOKS
# ---------------------------------------------------------------------------


def block_8_playbooks(state: PeelState) -> dict:
    """Collect >=5 SITUATION PLAYBOOKS per 03-peel-wizard-spec.md lines 407-451.

    Each playbook pairs an ON-BRAND response with an OFF-BRAND response
    plus a one-line rule. Operator sees inline banned-word scans on both
    sides before closing.
    """
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 8 — SITUATION PLAYBOOKS")
    click.echo("=" * 60)
    click.echo(
        "Pre-scripted responses to recurring situations.\n"
        "Minimum 5 playbooks. Chat/voice agents drift without these.\n"
        "Starter ideas: prospect asks for discount; prospect asks about\n"
        "methodology without context; inbound request outside scope;\n"
        "bad-fit client sends intake; prospect wants fixed-fee on open scope.\n"
    )

    words, phrases = _banned_words_from_state(state)
    if not words and not phrases:
        click.echo(
            "  note: block 5 (BANS) not yet populated — inline ban counts "
            "will report 0 until banned lists are seeded.\n"
        )

    playbooks: list[dict] = []
    while True:
        idx = len(playbooks) + 1
        click.echo(f"--- Playbook {idx} ---")

        q81 = _ask(f"Q8.1 Situation label (playbook {idx})?")
        while not q81:
            q81 = _ask("  must be non-empty", default=q81 or None)

        while True:
            q82 = _ask_list("Q8.2 Trigger phrases / regex (comma-separated, >=1)?")
            if q82:
                break
            click.echo("  need at least one trigger")

        q83 = _ask("Q8.3 ON-BRAND response (verbatim, in your voice)?")
        while not q83:
            q83 = _ask("  must be non-empty", default=q83 or None)

        q84 = _ask("Q8.4 OFF-BRAND response (what a lazy copywriter would say)?")
        while not q84:
            q84 = _ask("  must be non-empty", default=q84 or None)

        q85 = _ask("Q8.5 One-line rule — why ON beats OFF?")
        while not q85:
            q85 = _ask("  must be non-empty", default=q85 or None)

        on_bans = _scan_bans(q83, words, phrases)
        off_bans = _scan_bans(q84, words, phrases)
        mark = "ok" if on_bans == 0 else "WARN"
        click.echo(
            f"  ON-brand: {on_bans} bans ({mark}). "
            f"OFF-brand: {off_bans} bans fired."
        )

        playbooks.append(
            {
                "id": _slug_from_label(q81),
                "triggers": q82,
                "on_brand": q83,
                "off_brand": q84,
                "rule": q85,
                "inline_score": {
                    "on_brand_bans": on_bans,
                    "off_brand_bans": off_bans,
                },
            }
        )

        if len(playbooks) < 5:
            click.echo(
                f"  {len(playbooks)}/5 playbooks — minimum not yet reached."
            )
            _ask_yn("Q8.7 Another situation? (required — min 5)", default=True)
            continue
        if not _ask_yn("Q8.7 Another situation?", default=False):
            break

    click.echo("")
    click.echo(f"BLOCK 8 — {len(playbooks)} playbooks locked.")
    for p in playbooks:
        click.echo(
            f"  - {p['id']}: on={p['inline_score']['on_brand_bans']} bans, "
            f"off={p['inline_score']['off_brand_bans']} bans"
        )

    return {
        "situation_playbooks": {
            "playbooks": playbooks,
            "mandatory_on_chat_surfaces": True,
        }
    }


# ---------------------------------------------------------------------------
# Block 9 — EXEMPLARS SEED
# ---------------------------------------------------------------------------


_EXEMPLAR_SURFACES = ["hero", "body", "cta", "email", "post", "meta"]


def _score_band_to_int(band: str) -> int:
    """Representative integer score for frontmatter (band -> int)."""
    if band == "95+":
        return 96
    if band == "90-94":
        return 92
    return 88


def _write_exemplar_file(
    brand_dir: Path,
    *,
    surface: str,
    score_num: int,
    text: str,
    weakness: str | None,
    idx: int,
    aspiring: bool,
) -> Path:
    """Write one exemplar md file (YAML frontmatter + body). Atomic."""
    base = brand_dir / "voice_examples_by_context"
    if aspiring:
        sub = base / "aspiring"
        fname = f"{surface}-near-miss-{idx:02d}.md"
    else:
        sub = base / surface
        fname = f"exemplar-{idx:02d}.md"
    sub.mkdir(parents=True, exist_ok=True)
    out = sub / fname

    fm = {
        "surface": surface,
        "score": score_num,
        "source": "peel-block-9",
        "weakness": weakness,
    }
    body = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
        + "\n---\n"
        + text.rstrip("\n")
        + "\n"
    )
    tmp = out.with_suffix(".md.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, out)
    return out


def block_9_exemplars(state: PeelState, brand_dir: Path) -> dict:
    """Collect 3+ exemplars and 0+ trauma entries per spec lines 454-510.

    Sidecar files written under brand_dir (never inlined into voice.yaml):
      - voice_examples_by_context/<surface>/exemplar-NN.md (>=95)
      - voice_examples_by_context/aspiring/<surface>-near-miss-NN.md (<95)
      - trauma.jsonl — one JSON per line; empty file when no entries so
        downstream readers never FileNotFound (session-14 trauma guard).

    CHECKPOINT (spec line 509): any 95+ exemplar that fires >=1 ban from
    the operator's own banned list aborts the block with ClickException.
    """
    click.echo("")
    click.echo("=" * 60)
    click.echo("BLOCK 9 — EXEMPLARS SEED")
    click.echo("=" * 60)
    click.echo(
        "3 on-brand exemplars (min) anchor the voice-scorer.\n"
        "Optional trauma entries capture past voice fails for "
        "pattern-recurrence detection.\n"
    )

    words, phrases = _banned_words_from_state(state)

    exemplars: list[dict] = []
    surface_counters: dict[str, int] = {s: 0 for s in _EXEMPLAR_SURFACES}
    aspiring_counters: dict[str, int] = {s: 0 for s in _EXEMPLAR_SURFACES}
    written_files: list[str] = []

    for i in range(1, 4):
        click.echo(f"--- Exemplar {i}/3 ---")

        while True:
            q91 = _ask(f"Q9.1 Paste on-brand copy sample {i} (>=40 chars)?")
            if len(q91) >= 40:
                break
            click.echo(f"  too short ({len(q91)} chars, need >=40)")

        q92 = _ask_choice(
            "Q9.2 Surface? [hero/body/cta/email/post/meta]",
            _EXEMPLAR_SURFACES,
            default="body",
        )

        q93 = _ask_choice(
            "Q9.3 Honest self-score? [95+/90-94/<90]",
            ["95+", "90-94", "<90"],
            default="95+",
        )

        score_num = _score_band_to_int(q93)
        is_aspiring = q93 != "95+"

        weakness: str | None = None
        if is_aspiring:
            while True:
                weakness = _ask("Q9.4 What's weak about it? (1 line)")
                if weakness:
                    break

        if not is_aspiring:
            hits = _scan_bans(q91, words, phrases)
            if hits > 0:
                raise click.ClickException(
                    f"Exemplar {i} marked 95+ fires {hits} ban(s) from your "
                    "own banned list. Fix exemplar or loosen bans. Cannot "
                    "proceed."
                )

        if is_aspiring:
            aspiring_counters[q92] += 1
            idx = aspiring_counters[q92]
        else:
            surface_counters[q92] += 1
            idx = surface_counters[q92]

        path = _write_exemplar_file(
            brand_dir,
            surface=q92,
            score_num=score_num,
            text=q91,
            weakness=weakness,
            idx=idx,
            aspiring=is_aspiring,
        )
        rel = str(path.relative_to(brand_dir))
        written_files.append(rel)
        exemplars.append(
            {
                "surface": q92,
                "score_band": q93,
                "score_num": score_num,
                "aspiring": is_aspiring,
                "path": rel,
            }
        )
        click.echo(
            f"  wrote {rel} ({'aspiring' if is_aspiring else '95+'})"
        )

    click.echo("")
    click.echo("--- Trauma log (optional) ---")
    traumas: list[dict] = []
    if _ask_yn(
        "Q9.5 Do you have voice-fail / trauma incidents to record?",
        default=False,
    ):
        for j in range(1, 3):
            incident = _ask(
                f"Q9.5 Trauma {j} — paste the line that went wrong "
                "(blank to stop)",
                default="",
            )
            if not incident:
                break
            while True:
                root_cause = _ask("Q9.6 Root cause (1 line)?")
                if root_cause:
                    break
            while True:
                rule_added = _ask(
                    "Q9.7 Rule to prevent recurrence "
                    "(banned_words / attribution_rules / situation_playbooks)?"
                )
                if rule_added:
                    break
            traumas.append(
                {
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "incident": incident,
                    "root_cause": root_cause,
                    "rule_added": rule_added,
                    "source_block": 9,
                }
            )

    # ALWAYS write trauma.jsonl — empty if no entries (session-14 guard).
    trauma_file = brand_dir / "trauma.jsonl"
    lines = "".join(json.dumps(t) + "\n" for t in traumas)
    tmp = trauma_file.with_suffix(".jsonl.tmp")
    tmp.write_text(lines, encoding="utf-8")
    os.replace(tmp, trauma_file)

    click.echo("")
    click.echo(
        f"BLOCK 9 — {len(exemplars)} exemplars + {len(traumas)} trauma entries."
    )
    for f in written_files:
        click.echo(f"  {f}")
    click.echo(
        f"  trauma.jsonl: {len(traumas)} entries "
        f"({trauma_file.relative_to(brand_dir)})"
    )

    return {
        "_block_9": {
            "exemplars": exemplars,
            "traumas": len(traumas),
            "written": written_files,
        }
    }


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

    # Block 3 METHOD is optional. When skipped (Q3.0 = n) the payload is {}
    # and `method:` is OMITTED from voice.yaml entirely — absence is meaningful
    # and must not degrade to `method: null`.
    b3 = state.answers.get("3", {})
    if b3 and b3.get("method"):
        voice["method"] = b3["method"]

    # Block 7 OFFER — inlined into voice.yaml.offer. Private pricing lives
    # in the ground-truth sidecar (never in voice.yaml).
    b7 = state.answers.get("7", {})
    if b7 and b7.get("offer"):
        voice["offer"] = b7["offer"]

    # Block 5 BANS — top-level lists inlined into voice.yaml so the Layer 1
    # scorer picks them up directly. attribution_rules only emitted if
    # Q5.5 produced at least one rule (absence is meaningful).
    b5 = state.answers.get("5", {})
    if b5:
        if b5.get("banned_words"):
            voice["banned_words"] = b5["banned_words"]
        if b5.get("banned_phrases"):
            voice["banned_phrases"] = b5["banned_phrases"]
        if b5.get("attribution_rules"):
            voice["attribution_rules"] = b5["attribution_rules"]

    # Block 4 RECEIPTS is a sidecar file; voice.yaml just references its path
    # so downstream workers know where to cite claims from. The actual
    # receipts live in brands/<slug>/data/capabilities-ground-truth.yaml.
    b4 = state.answers.get("4", {})
    if b4 and b4.get("ground_truth_file"):
        voice.setdefault("ground_truth", {})
        voice["ground_truth"]["file"] = b4["ground_truth_file"]
        voice["ground_truth"]["receipt_count"] = b4.get("receipt_count", 0)

    # Block 6 WE_ARE/WE_ARE_NOT are sidecar markdown docs — not inlined.

    # Block 8 SITUATION PLAYBOOKS is inline in voice.yaml per spec lines 432-441.
    b8 = state.answers.get("8", {})
    if b8 and b8.get("situation_playbooks"):
        voice["situation_playbooks"] = b8["situation_playbooks"]

    # Block 9 EXEMPLARS SEED is pure sidecar (voice_examples_by_context/ +
    # trauma.jsonl) — nothing to inline here.

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

    # Block 3 — METHOD (optional)
    if 3 in state.blocks_completed:
        click.echo("Block 3 already complete — skipping.")
    elif skip_block == 3:
        click.echo("Skipping Block 3 (--skip-block). METHOD will be omitted.")
    else:
        state.answers["3"] = block_3_method(state)
        state.blocks_completed.append(3)
        state.current_block = 4
        save_state(dirs.brand_dir, state)

    # Block 4 — RECEIPTS
    if 4 in state.blocks_completed:
        click.echo("Block 4 already complete — skipping.")
    elif skip_block == 4:
        click.echo("Skipping Block 4 (--skip-block).")
    else:
        state.answers["4"] = block_4_receipts(state, dirs.brand_dir)
        state.blocks_completed.append(4)
        state.current_block = 5
        save_state(dirs.brand_dir, state)

    # Block 5 — BANS
    if 5 in state.blocks_completed:
        click.echo("Block 5 already complete — skipping.")
    elif skip_block == 5:
        click.echo("Skipping Block 5 (--skip-block).")
    else:
        state.answers["5"] = block_5_bans(state)
        state.blocks_completed.append(5)
        state.current_block = 6
        save_state(dirs.brand_dir, state)

    # Block 6 — WE_ARE / WE_ARE_NOT
    if 6 in state.blocks_completed:
        click.echo("Block 6 already complete — skipping.")
    elif skip_block == 6:
        click.echo("Skipping Block 6 (--skip-block).")
    else:
        state.answers["6"] = block_6_we_are(state, dirs.brand_dir)
        state.blocks_completed.append(6)
        state.current_block = 7
        save_state(dirs.brand_dir, state)

    # Block 7 — OFFER + PRICING
    if 7 in state.blocks_completed:
        click.echo("Block 7 already complete — skipping.")
    elif skip_block == 7:
        click.echo("Skipping Block 7 (--skip-block).")
    else:
        state.answers["7"] = block_7_offer_pricing(state, dirs.brand_dir)
        state.blocks_completed.append(7)
        state.current_block = 8
        save_state(dirs.brand_dir, state)

    # Block 8 — SITUATION PLAYBOOKS
    if 8 in state.blocks_completed:
        click.echo("Block 8 already complete — skipping.")
    elif skip_block == 8:
        click.echo("Skipping Block 8 (--skip-block).")
    else:
        state.answers["8"] = block_8_playbooks(state)
        state.blocks_completed.append(8)
        state.current_block = 9
        save_state(dirs.brand_dir, state)

    # Block 9 — EXEMPLARS SEED
    if 9 in state.blocks_completed:
        click.echo("Block 9 already complete — skipping.")
    elif skip_block == 9:
        click.echo("Skipping Block 9 (--skip-block).")
    else:
        state.answers["9"] = block_9_exemplars(state, dirs.brand_dir)
        state.blocks_completed.append(9)
        state.current_block = 10
        save_state(dirs.brand_dir, state)

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
