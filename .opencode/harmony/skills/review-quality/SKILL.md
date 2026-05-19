---
name: review-quality
description: Analyze code quality, architecture, test coverage, and technical debt. Produces a scored evaluation report with prioritized action items.
---

# Review Quality

Use this skill for comprehensive code quality audits.

## First reads

1. Read `../../CHANGELOG.md` for version history context.
2. Read `../../tasks/todo.md` for known open items.
3. Read `../../README.md` for project scope.

## Review dimensions

### Architecture (weight: 25%)
- Layer separation: domain / data / services / ui
- Module sizes and method counts
- Circular dependency risk
- Import hygiene

### Code quality (weight: 25%)
- Type annotations coverage
- Magic numbers and named constants
- Error handling patterns
- Docstring and inline documentation

### Testing (weight: 25%)
- Test count and organization
- Domain vs UI test balance
- Accept/reject scenario coverage
- Edge case handling

### Maintainability (weight: 15%)
- app_main.py line count (target: under 2000)
- Mixin pattern consistency
- Configuration vs code separation
- Build pipeline health

### Security (weight: 10%)
- Dependency audit
- Update mechanism integrity
- Subprocess usage
- File path handling

## Output format

| Kriter | Puan | Not |
|---|---|---|
| Mimari | X/10 | ... |
| Kod kalitesi | X/10 | ... |
| Test | X/10 | ... |
| Bakim | X/10 | ... |
| Guvenlik | X/10 | ... |
| **Ortalama** | **X/10** | |

Followed by a prioritized action plan table.

## Validation

```bash
python -m pytest tests/
Get-Content hidrostatik_test/ui/app_main.py | Measure-Object -Line
```
