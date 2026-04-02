---
name: hydrotest-development
description: Maintain or extend this hydrostatic test desktop app with spec-first calculation discipline, awareness of the repo package structure, and mandatory regression validation. Use when changing formulas, Tkinter workflow, packaging, reports, or project structure in this repository.
---

# Hydrotest Development

Use this skill for general development work in this repo.

## First reads

1. Read `../../tasks/todo.md`.
2. Read `../../tasks/lessons.md`.
3. Read `../../docs/spec/ngtl_5007_hydrostatic_analysis.md` before changing formulas or acceptance logic.
4. Read `../../docs/ui_ergonomics.md` before changing the operator workflow.

## Working rules

- Keep runtime code under `../../hidrostatik_test/`.
- Keep tests under `../../tests/`.
- Keep spec and workflow notes under `../../docs/`.
- Do not put new source files inside `../../dist/`.
- Treat formula or constant changes as safety-relevant.
- If a formula changes, update tests in the same change.

## Validation

- Run `python -m unittest discover -s tests -p "test_*.py"`.
- Run the import smoke check described in `../../docs/testing.md`.
- If UI behavior changed, inspect `../../tests/test_ui_workflow.py` and extend it when needed.
