# Contributing to Layered LLM Defense

Thank you for considering a contribution. This is a working research
artifact, not a closed product, and reviewer / replication / extension
work is explicitly welcome.

## Reporting issues

If you find a bug, a false positive / false negative, or a benchmark
result you cannot reproduce, please open an issue with:

- The exact command you ran
- The expected behavior
- The observed behavior
- Your Python version and OS
- If possible, a minimal reproducer

## Suggesting attacks the defense misses

We are particularly interested in reports of attacks that bypass
LLD-Full. Please:

- Describe the attack class (jailbreak, GCG-style suffix, encoding,
  social engineering, etc.)
- Provide the attack input (or a sanitized version)
- Note which defense layer you expected to catch it
- If you have run it against the real-LLM benchmark, attach the
  `groq_run_<date>.json` slice

## Code contributions

Process:

1. Open an issue first to discuss the proposed change. This avoids
   duplicate work and helps shape the design.
2. Fork and create a feature branch.
3. Add tests for any new behavior. Existing tests live in `tests/test_*.py`.
4. Run `python3 -m pytest tests/ -q`. All 453+ tests must pass.
5. If your change touches `IntegratedDefense`, also run the ablation
   harness to verify no regression: `python3 -m lld.ablation --extended`.
6. Submit a pull request with a clear description of the change and
   the test results.

## Honesty rules

Two non-negotiable rules:

1. **Do not fabricate evidence.** Quotes, outputs, annotations, and
   measurements must come from real runs. If a number is missing,
   say so. Reconstructed or "representative" content is not
   acceptable.
2. **Document every limitation.** If your change works in some
   conditions but not others, document the failure mode. The
   limitations report and CHANGELOG are part of every PR.

## Style

- Standard library only for the core. Third-party dependencies
  are allowed only for benchmarking and tooling, never for the
  defense pipeline itself.
- Type hints where they add clarity. No `# type: ignore` without
  a comment explaining why.
- Test-driven preferred. Tests should be deterministic — if a
  test depends on a seed, set it explicitly.
- Comments explain *why*, not *what*. The code should explain
  what it does.

## License

By contributing, you agree that your contribution will be released
under the same license as the project (Apache 2.0 for code,
CC-BY-4.0 for documentation).

## Code of conduct

Be civil. Disagreements are about the work, not the people.
Reports of harassment or hostile behavior should be sent privately
to the maintainer.
