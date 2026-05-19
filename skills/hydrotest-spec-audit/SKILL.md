---
name: hydrotest-spec-audit
description: Audit formulas, acceptance criteria, and operational gaps in this repo against NGTL 5007 hydrostatic test requirements. Use when validating A/B coefficients, pressure/air-content formulas, sign conventions, or missing spec workflow coverage.
---

# Hydrotest Spec Audit

Use this skill when the task is about whether the code matches the hydrostatic-test specification.

## First reads

1. Read `../../docs/spec/ngtl_5007_hydrostatic_analysis.md`.
2. Read `../../docs/spec/ngtl_5007_validation.md`.
3. If exact extracted wording matters, read `../../docs/spec/ngtl_5007_raw_extract.txt`.

## Audit workflow

1. Identify the exact spec section and variable definitions.
2. Compare code behavior in `../../hidrostatik_test/domain/` and `../../hidrostatik_test/ui/`.
3. Call out whether the repo is `implemented`, `partial`, or `missing`.
4. If the spec text is ambiguous, say so explicitly instead of guessing.

## Output expectations

- Cite the section number or PDF page when possible.
- Separate formula correctness from workflow completeness.
- Note any unit ambiguity, especially around `A`, `B`, `Pa`, and `dT`.
