---
id: cache-breakthrough-post-v1
surface: post
audience: operator
phase: na
source_url: "LinkedIn / X"
source_sha: "capabilities-brief.md:61"
composite: 97
scored_at: "2026-04-19T20:15:03Z"
promoted_at: "2026-04-19T20:15:03Z"
dims:
  testable: 10
  secure: 10
  fun: 10
  valuable: 10
  easy: 9
  brand_voice: 10
  canon_present: 8
  person_named: 10
  receipt_shown: 10
  invite_not_pitch: 9
  yuzu_phase_mapped: 10
  plain_language: 9
  specificity: 10
  rhythm: 10
  friction_calibrated: 10
notes: |
  Narrative-hook social post. Tension → insight → receipt → philosophical close.
  Reference for all LinkedIn/X technical storytelling posts.
---

The radix cache was running at 0.007% hit rate.

Every 50K-token prompt was a fresh compute path. We were burning GPU time on cache misses that shouldn't have existed.

I found it in a billing header — `cch=XXXXX` at position 0, changing per request. The cache was keyed on the full prompt, and that one mutating token meant no two prompts ever matched.

A 2-line regex in the prompt trimmer normalized `cch=0` before forwarding.

Hit rate jumped to 6.37%. That's 910× improvement on a 2-line diff.

Sometimes the wiring problem is a regex.

---

I rebuilt CubCloud's 8-GPU inference stack from bare metal. Writing up the receipts at zeststream.ai.
