---
id: cubcloud-rebuild-v1
surface: body
audience: operator
phase: pour
source_url: "zeststream.ai/work/cubcloud (planned)"
source_sha: "capabilities-brief.md:47-75"
composite: 98
scored_at: "2026-04-19T20:15:03Z"
promoted_at: "2026-04-19T20:15:03Z"
dims:
  testable: 10
  secure: 10
  fun: 10
  valuable: 10
  easy: 9
  brand_voice: 10
  canon_present: 10
  person_named: 10
  receipt_shown: 10
  invite_not_pitch: 10
  yuzu_phase_mapped: 10
  plain_language: 9
  specificity: 10
  rhythm: 10
  friction_calibrated: 10
notes: |
  Body-copy exemplar with heavy receipts. Every number is grounded in capabilities-ground-truth.yaml.
  Reference for /work/cubcloud, /methods/gpu-rebuild, CubCloud case-study copy.
---

An offline server. 4× RTX 6000 Ada and 4× H200 NVL NVLs sitting in a rack doing nothing. No provisioning, no inference stack, no monitoring, no rotation strategy. Expensive silicon, zero revenue.

I rebuilt it from bare metal.

**Bare-metal bring-up.** Every GPU re-flashed, driver stack standardized, CUDA versions pinned, NVLink topology mapped for TP=4 distribution. Documented in Ansible so the next rebuild is one command away.

**Container discipline.** 100+ containers across the stack — inference workers, routers, health probes, agent harnesses. Every image version-pinned, every secret pulled from Infisical at boot.

**SGLang tuning.** MiniMax M2.5 in FP8 at TP=4. Benchmarked 2026-03-24: **105 tok/s** generation, **670ms** prefill on 50K-token prompts, full proxy chain adds <200ms. Measured numbers, not vendor claims.

**The cache-hit breakthrough.** Claude Code's billing header `cch=XXXXX` at position 0 of the system prompt was destroying the radix cache — **0.007% hit rate**. A 2-line regex in a custom prompt-trimmer normalizes `cch=0` before forwarding. Hit rate moved to **6.37%** — a **910× improvement** on a single optimization.

CubCloud runs the business. I remain their architecture partner on a project basis.

I help SMB owners buy their time back.
