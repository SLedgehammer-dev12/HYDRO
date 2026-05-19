---
name: harmony
description: Orchestrate work on the Hidrostatik Test project. Routes tasks to the appropriate sub-agent (domain, ui, test, refactor) and enforces spec-first development with mandatory regression testing. Use for ANY code change in this repository.
---

# Harmony — Project Orchestrator

Master skill for the Hidrostatik Test Değerlendirme project. Load this skill for any task; it will route to the correct sub-skill.

## Project map

| Area | Path | Sub-skill |
|---|---|---|
| Formulas, dataclasses, validation | `hidrostatik_test/domain/` | `add-domain-module` |
| Tkinter UI, tabs, widgets, workflow | `hidrostatik_test/ui/` | `modify-ui` |
| File splitting, import cleanup | `hidrostatik_test/ui/app_main.py` | `extract-ui-mixin` |
| Tests (unit + UI workflow) | `tests/` | `write-test` |
| Code quality audit | All | `review-quality` |

## Available agents

| Agent | Purpose |
|---|---|
| `domain-expert` | Domain layer calculations and validation |
| `ui-developer` | Tkinter UI changes |
| `test-writer` | Test creation and maintenance |
| `refactoring-architect` | Code restructuring |

## Mandatory rules

1. **Spec first**: Read `docs/spec/ngtl_5007_hydrostatic_analysis.md` before formula changes.
2. **Test with every change**: Run `python -m pytest tests/` after any code change.
3. **Preserve the re-export chain**: `app.py` → `app_main.py` imports must not break.
4. **Mixin pattern**: New tab methods go in `tab_*.py` mixins, not directly in `app_main.py`.
5. **Turkish UI**: Operator-facing strings are in Turkish; domain error messages are in Turkish.
6. **No new deps without discussion**: Current deps are `CoolProp==7.0.0` only.

## Quick validation

```bash
python -m pytest tests/ -v --tb=short
python -c "from hidrostatik_test.ui.app import HydrostaticTestApp; print('import-ok')"
```
