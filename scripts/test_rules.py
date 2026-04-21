#!/usr/bin/env python3
"""
test_rules.py — validate acceptance tests for brand-voice rules.

For each rules/*.yaml:
  - should_fail_on  MUST produce ≥1 violation under the rule's patterns
  - should_pass_on  MUST produce 0 violations

Exit code: 0 when all rules pass, 1 when any rule fails its acceptance test.

This script is intentionally permissive about rule shape — it handles
existence, substitution, occurrence, conditional, and metric rules.
Unsupported shapes are reported as skipped, not failed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    sys.stderr.write("pyyaml required: pip install pyyaml\n")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = REPO_ROOT / "skills" / "brand-voice" / "brands" / "zeststream" / "rules"


def _compile_flags(rule: dict) -> int:
    flags = re.MULTILINE
    if rule.get("ignorecase"):
        flags |= re.IGNORECASE
    return flags


def _count_existence(rule: dict, text: str) -> int:
    """existence / substitution: any match on any token counts as a violation."""
    flags = _compile_flags(rule)
    count = 0
    tokens = rule.get("tokens") or []
    if not tokens and isinstance(rule.get("swap"), dict):
        tokens = list(rule["swap"].keys())
    for pat in tokens:
        try:
            count += len(re.findall(pat, text, flags=flags))
        except re.error as e:
            sys.stderr.write(f"  [regex error] {pat!r}: {e}\n")
    return count


def _count_conditional(rule: dict, text: str) -> int:
    """conditional: fires when match is present AND (require_near is None
    OR require_near is absent within window_chars — rule is "require NEAR
    means caveat must be present to pass")."""
    flags = _compile_flags(rule)
    count = 0
    for cond in rule.get("conditions", []):
        window = int(cond.get("window_chars") or 80)
        match_patterns = []
        if cond.get("match"):
            match_patterns.append(cond["match"])
        if cond.get("match_any"):
            match_patterns.extend(cond["match_any"])
        # require_near: if the named pattern is found within window_chars
        # of the match, the rule DOES NOT fire (caveat present). If absent,
        # it fires.
        near_patterns = []
        if cond.get("require_near"):
            near_patterns.append(cond["require_near"])
        if cond.get("require_near_any"):
            near_patterns.extend(cond["require_near_any"])

        for mp in match_patterns:
            try:
                for m in re.finditer(mp, text, flags=flags):
                    start = max(0, m.start() - window)
                    end = min(len(text), m.end() + window)
                    window_text = text[start:end]
                    if near_patterns:
                        caveat_found = any(
                            re.search(np, window_text, flags=flags)
                            for np in near_patterns
                        )
                        if not caveat_found:
                            count += 1
                    else:
                        # Standalone pattern (no sibling check) — presence = violation
                        count += 1
            except re.error as e:
                sys.stderr.write(f"  [regex error] {mp!r}: {e}\n")

        # Handle require_all_match (effort_honesty style)
        if cond.get("require_all_match"):
            rall = cond["require_all_match"]
            # Any of "scope_words" paired with any of "minimizers"
            scope_words = rall.get("scope_words", [])
            minimizers = rall.get("minimizers", [])
            for sw in scope_words:
                try:
                    sw_matches = list(re.finditer(sw, text, flags=flags))
                except re.error:
                    continue
                for m in sw_matches:
                    start = max(0, m.start() - window)
                    end = min(len(text), m.end() + window)
                    window_text = text[start:end]
                    for mw in minimizers:
                        try:
                            if re.search(mw, window_text, flags=flags):
                                count += 1
                        except re.error:
                            continue
    return count


def _count_occurrence(rule: dict, text: str) -> int:
    """occurrence: fires when any required_occurrence does NOT meet its min."""
    flags = _compile_flags(rule)
    violations = 0
    for occ in rule.get("required_occurrences", []):
        min_count = int(occ.get("min") or 1)
        patterns = []
        if occ.get("pattern"):
            patterns.append(occ["pattern"])
        if occ.get("pattern_any"):
            patterns.extend(occ["pattern_any"])
        # any-of: a hit on any pattern counts
        hits = 0
        for p in patterns:
            try:
                hits += len(re.findall(p, text, flags=flags))
            except re.error:
                continue
        if hits < min_count:
            violations += 1
    return violations


def _count_metric(rule: dict, text: str, surface: str = "default") -> int:
    """metric: sentence_max_words — violation if any sentence exceeds cap."""
    if rule.get("metric") != "sentence_max_words":
        return 0
    limits = rule.get("per_surface_limits", {}) or {}
    cap = int(limits.get(surface, limits.get("default", 25)))
    # Naive sentence split on ., !, ? followed by whitespace or EOF
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    violations = 0
    for s in sentences:
        words = re.findall(r"\b\w+\b", s)
        if len(words) > cap:
            violations += 1
    return violations


def count_violations(rule: dict, text: str) -> int:
    ext = (rule.get("extends") or "").strip()
    if ext in ("existence", "substitution"):
        return _count_existence(rule, text)
    if ext == "conditional":
        return _count_conditional(rule, text)
    if ext == "occurrence":
        return _count_occurrence(rule, text)
    if ext == "metric":
        # Use hero as the default surface for the failing test case.
        return _count_metric(rule, text, surface="hero")
    return 0


def test_rule(path: Path) -> tuple[bool, str]:
    with path.open("r") as fh:
        rule = yaml.safe_load(fh)
    if not rule or not isinstance(rule, dict):
        return False, f"{path.name}: not a YAML mapping"

    test = rule.get("acceptance_test")
    if not test:
        return False, f"{path.name}: missing acceptance_test"

    fail_text = test.get("should_fail_on")
    pass_text = test.get("should_pass_on")
    if fail_text is None or pass_text is None:
        return False, f"{path.name}: acceptance_test missing should_fail_on/should_pass_on"

    fail_count = count_violations(rule, fail_text)
    pass_count = count_violations(rule, pass_text)

    if fail_count < 1:
        return False, (
            f"{path.name}: should_fail_on produced 0 violations "
            f"(text={fail_text!r})"
        )
    if pass_count > 0:
        return False, (
            f"{path.name}: should_pass_on produced {pass_count} violation(s) "
            f"(text={pass_text!r})"
        )
    return True, f"{path.name}: PASS (fail={fail_count}, pass=0)"


def main() -> int:
    if not RULES_DIR.exists():
        sys.stderr.write(f"rules dir not found: {RULES_DIR}\n")
        return 2
    paths = sorted(RULES_DIR.glob("*.yaml"))
    if not paths:
        sys.stderr.write("no rule files found\n")
        return 2

    failures = 0
    for p in paths:
        ok, msg = test_rule(p)
        status = "✓" if ok else "✗"
        print(f"{status} {msg}")
        if not ok:
            failures += 1

    total = len(paths)
    passed = total - failures
    print(f"\n{passed}/{total} rules passed acceptance tests")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
