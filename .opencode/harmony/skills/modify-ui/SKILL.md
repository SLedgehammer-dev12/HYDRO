---
name: modify-ui
description: Add or modify UI elements — new tabs, input panels, action buttons, decision cards, or report sections. Follows the mixin pattern and three-pane layout conventions.
---

# Modify UI

Use this skill when changing the Tkinter operator interface.

## First reads

1. Read `../../docs/ui_ergonomics.md` for operator workflow.
2. Read `_build_ui` in `../../hidrostatik_test/ui/app_main.py` for layout.
3. Read the relevant tab mixin file (`tab_air.py`, `tab_pressure.py`, `tab_field.py`).

## Adding an input field

1. Register `StringVar` in `__init__` of `app_main.py`.
2. Build the field via `self._add_entry(frame, row, label, variable, field_key=...)` in the tab build method.
3. Add live validation in `_semantic_field_feedback`.
4. Add to clear logic in the `_clear_*_form` method.

## Adding a new tab

1. Create `ui/tab_<name>.py` with `<Name>TabMixin`.
2. Add `_build_<name>_input_panel` and `_build_<name>_tab` methods.
3. Register the mixin in `app_main.py`: import + add to class inheritance.
4. Add tab to notebook in `_build_ui`.
5. Update `_on_tab_changed`, `_clear_active_form`, `_active_tab_key`.
6. Add workflow hint in `_update_workflow_hint`.

## Decision card and report

- Use `_update_decision_card(title, status, summary)` for results.
- Use `_build_report_text()` for report generation; add new sections there.

## Validation

```bash
python -m pytest tests/ -v
```
