---
id: "lld_executive_summary_2026-04-08"
title: "Layered LLM Defense — Executive Summary"
type: "executive_summary"
category: "documentation"
language: "en"
tags: ["executive_summary", "one_pager"]
---

# Layered LLM Defense — Executive Summary

## One-page summary

**The problem.** Large language models in production face Attack Success
Rates (ASR) of 70-85% against undefended models. The best published
defenses (LlamaGuard, RAIN) leave a residual ASR of approximately
10-15%. Existing defenses share three weaknesses: single-mechanism
reliance, ad-hoc composition, and static rule sets.

**The contribution.** Layered LLM Defense (LLD) is a four-layer
defense-in-depth framework — Formal Verification, Antifragile Shell,
Information-theoretic Interface, Moving Target Defense — composed by
**prerequisite negation** (each layer eliminates a precondition for
the next attacker step). LLD adds six biologically-inspired
architectural primitives: Hormesis-calibrated rule strengthening,
Immune Memory fast-paths, Microbiome whitelist baselines, a
Self-Adversarial Loop with thymus-style dual selection, Fever mode,
and Herd Immunity vaccine export. To our knowledge these are not
present in any prior LLM-defense framework.

**The headline result.** An ablation study on a 510-vector benchmark
(HarmBench-style markers + GCG / AutoDAN / PAIR adversarial-suffix
patterns) measures the contribution of each architectural step:

| Configuration | ASR (simulated) | Mean latency |
|---|---:|---:|
| Vanilla (formal verification + sanitization) | 89.8% | 0.85 ms |
| Bio-Off (+ correlation, fragmenter, OODA, response strategy) | 71.2% | 1.75 ms |
| Full (+ biological primitives) | partly artifact* | 2.22 ms |

\* The simulated full-config result is partly a simulation artifact:
the Microbiome whitelist easily flags abstract `[BLOCKED_PAYLOAD_*]`
markers in the test dataset because they do not appear in any clean
baseline. The Vanilla → Bio-Off gain of **18.6 percentage points** is
the most transferable claim. Real production traffic will produce
higher numbers.

Latency is ~2 ms — approximately 100x faster than the LLM inference
itself.

**Real-LLM validation.** On a 100-vector run against `llama-3.3-70b-versatile`
via Groq, raw ASR is 7.0% with FPR 0.0% measured on a 40-input clean
baseline. After deterministic refusal pre-filtering of the 7 reported
bypasses, 5 are confirmed as model refusals (judge false positives).
Two cases (one cybercrime SQL educational explanation, one obfuscated
crime category enumeration) require human verdict. The honest live-LLM
ASR range is **0–2%**, on a small sample of 100 vectors. The 0.0% FPR
is likely optimistic given the small clean baseline.

**What this is not.** No "perfect defense" claim. Not peer-reviewed.
Not deployed in production. Not a head-to-head LlamaGuard comparison
(adapter ready). No human red team. Single author.

**Open source.** Apache 2.0 license, standard-library Python, 453
unit tests passing in ~7 seconds, no third-party dependencies for
the core, working examples in `examples/`. Reproducibility:

```bash
git clone <repo-url>
pip install -e .
python3 -m pytest tests/ -q                            # 453 tests
python3 -m lld.ablation --extended
```

**Author.** Independent researcher. Solo-built.

**Looking for.** Reviewers to challenge the methodology, contributors
to extend the attack suite, comparisons against your own defense
stack, issue reports of attacks that bypass LLD-Full.

---

## Versions

- 2026-04-08 — initial executive summary, matched to technical report
  v0.1.0-draft
