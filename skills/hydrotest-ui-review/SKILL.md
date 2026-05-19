---
name: hydrotest-ui-review
description: Review or improve the operator workflow of this hydrostatic test Tkinter app with attention to units, sign conventions, validation, and field ergonomics. Use when redesigning steps, reducing operator error, or adding UI guidance.
---

# Hydrotest UI Review

Use this skill for operator-facing workflow improvements.

## First reads

1. Read `../../docs/ui_ergonomics.md`.
2. Read `../../docs/spec/ngtl_5007_hydrostatic_analysis.md` for workflow steps that the UI should reflect.
3. Read `../../tests/test_ui_workflow.py` to understand current expectations.

## Review heuristics

- Prefer guided sequence over free-form data entry.
- Keep units and sign conventions visible near the field.
- Reduce the chance of evaluating with stale coefficients.
- Make the acceptance rule visible at the moment of decision.
- Preserve the calculation engine; prefer UI-only improvements when possible.

## Validation

- Extend `../../tests/test_ui_workflow.py` for any new guided behavior.
- Re-run the full test suite after UI changes.
