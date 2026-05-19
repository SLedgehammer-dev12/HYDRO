---
name: write-test
description: Write or extend tests following this project's unittest conventions. Covers domain unit tests with accept/reject scenarios and UI workflow tests with real Tk objects.
---

# Write Test

Use this skill when adding or modifying tests in `tests/`.

## Test file conventions

- File: `tests/test_<module>.py`
- Class: `<Module>Tests(unittest.TestCase)`
- Domain tests: pure functions, no Tk, no mocks needed
- UI tests: create real `tk.Tk()` in `setUp`, destroy in `tearDown`

## Domain test template

```python
from hidrostatik_test.domain import evaluate_<name>, <Name>Inputs

class <Name>Tests(unittest.TestCase):
    def test_accept_scenario(self) -> None:
        inputs = <Name>Inputs(...)
        result = evaluate_<name>(inputs)
        self.assertTrue(result.passed)

    def test_reject_scenario(self) -> None:
        inputs = <Name>Inputs(...)
        result = evaluate_<name>(inputs)
        self.assertFalse(result.passed)

    def test_invalid_input_raises(self) -> None:
        with self.assertRaises(ValidationError):
            <Name>Inputs(...)  # invalid field
```

## UI test conventions

- Import from `hidrostatik_test.ui.app` (the re-export module).
- Use `try: tk.Tk() except tk.TclError: self.skipTest(...)` for headless CI.
- Mock `messagebox` and `filedialog` via `@patch("hidrostatik_test.ui.app.messagebox.*")`.
- Use `root.update_idletasks()` after state changes that trigger Tk events.
- Prefer `self.app.notebook.select(N)` + `self.app._on_tab_changed()` for tab switching.

## Validation

```bash
python -m pytest tests/test_<module>.py -v
python -m pytest tests/  # full suite
```
