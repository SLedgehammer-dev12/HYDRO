---
name: graphify
description: >-
  Deterministic AST codebase knowledge graph, call-graph analyzer, and impact
  mapping tool for HYDRO. Indexes files, classes, methods, imports, SQLite
  tables, and maps affected downstream consumers and linked test suites with
  zero token overhead.
---

# Graphify (HYDRO Knowledge Graph & Impact Analyzer)

Graphify turns the HYDRO codebase and test suite into a queryable knowledge graph
using deterministic AST analysis. It prevents breaking changes by computing exact
impact radiuses and test associations before code modification.

## Commands

```bash
# Rebuild knowledge graph snapshot (.graphify/graph.json)
python3 skills/graphify/scripts/graphify.py build

# Impact analysis for a file or symbol
python3 skills/graphify/scripts/graphify.py impact hidrostatik_test/domain/hydrotest_core.py
python3 skills/graphify/scripts/graphify.py impact evaluate_pressure_variation_test

# Find callers of a function or class
python3 skills/graphify/scripts/graphify.py callers _refresh_live_coefficients

# Tests linked to a module
python3 skills/graphify/scripts/graphify.py test-map hydrotest_core

# Graph metrics and DB table usage
python3 skills/graphify/scripts/graphify.py stats
```

## Workflow

1. `impact <target>` before modifying a file or signature.
2. Identify downstream consumers and linked test suites.
3. Apply the change.
4. Run the linked tests, then the full suite:
   `python3 -m unittest discover -s tests -p "test_*.py"`
