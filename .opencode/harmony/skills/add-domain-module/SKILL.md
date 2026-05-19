---
name: add-domain-module
description: Add a new domain calculation module (e.g., a new spec section evaluation). Creates dataclass inputs/outputs, a pure evaluation function, __init__.py exports, and mandatory accept/reject tests.
---

# Add Domain Module

Use this skill to add a new evaluation function to `hidrostatik_test/domain/`.

## Workflow

1. Read the relevant spec section from `../../docs/spec/ngtl_5007_hydrostatic_analysis.md` or `../../docs/spec/ngtl_5007_raw_extract.txt`.
2. Identify inputs, outputs, constants, and acceptance criteria.
3. Create `hidrostatik_test/domain/<module>.py` with:
   - `Final` constants at the top
   - A frozen `@dataclass` for inputs (with `__post_init__` validation raising `ValidationError`)
   - A frozen `@dataclass` for results
   - A pure `evaluate_*` function
4. Update `hidrostatik_test/domain/__init__.py` to export all public symbols.
5. Create `tests/test_<module>.py` with at least:
   - One accept/pass scenario
   - One reject/fail scenario
   - Edge case validation tests

## Conventions

- Use `FLOAT_TOLERANCE` from `hydrotest_core` for comparisons.
- Raise `ValidationError` (not generic `ValueError`) for invalid inputs.
- Turkish error messages in `ValidationError`.
- Named constants for all magic numbers.
- Import `from __future__ import annotations`.

## Validation

```bash
python -m pytest tests/test_<module>.py -v
python -m pytest tests/  # full regression
```
