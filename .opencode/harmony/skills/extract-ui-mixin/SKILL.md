---
name: extract-ui-mixin
description: Extract a group of related methods from app_main.py into a new mixin file under ui/ using the established mixin inheritance pattern. Preserves all imports, tests, and the app.py re-export chain.
---

# Extract UI Mixin

Use this skill to split `hidrostatik_test/ui/app_main.py` into smaller mixin modules.

## Pre-checks

1. Identify the method group (e.g., all `_build_*_tab`, all `_on_*_mode_changed`).
2. Verify the methods only reference `self.*` attributes (no module-level globals except tkinter).
3. Run `python -m pytest tests/` to confirm baseline is green.

## Extraction steps

1. **Read** the target methods from `app_main.py` — note exact line ranges.
2. **Create** `ui/tab_<name>.py` (or `ui/<name>.py`) with:
   ```python
   from __future__ import annotations
   import tkinter as tk
   from tkinter import ttk
   from typing import TYPE_CHECKING
   # Import domain/data modules used by the methods
   if TYPE_CHECKING:
       from .app_main import HydrostaticTestApp

   class <Name>Mixin:
       # pasted methods here
   ```
3. **Add import** in `app_main.py`: `from .tab_<name> import <Name>Mixin`
4. **Add to class**: `class HydrostaticTestApp(..., <Name>Mixin):`
5. **Remove methods** from `app_main.py` using line-based deletion.
6. **Fix imports** in the new mixin — add any missing domain/data imports.
7. **Handle bare constant references**: if methods reference `AUTO_A_MODE` etc., add as class attributes on `HydrostaticTestApp` and use `self.AUTO_A_MODE` in the mixin.

## Circular import prevention

- Mixin files import tkinter/domain modules at module level.
- Mixin files import `HydrostaticTestApp` only under `TYPE_CHECKING`.
- `app_main.py` imports mixin classes at module level (after all domain/data imports).

## Validation

```bash
python -m pytest tests/ -v
```
All tests must pass before the extraction is considered complete.
