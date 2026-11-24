PYTHON ?= python3

.PHONY: lint format test test-web test-frontend openapi release-check release-check-quick

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy hidrostatik_test/domain/
	$(PYTHON) -m mypy --ignore-missing-imports webapp/backend/app
	npm --prefix webapp/frontend run lint
	npm --prefix webapp/frontend run typecheck

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"

test-web:
	$(PYTHON) -m pytest webapp/backend/tests -q

test-frontend:
	npm --prefix webapp/frontend test

openapi:
	PYTHONPATH=webapp/backend:. $(PYTHON) -m app.tools.dump_openapi
	npm --prefix webapp/frontend run check:api

release-check-quick:
	$(PYTHON) scripts/release_gate.py --quick

release-check:
	$(PYTHON) scripts/release_gate.py --with-smoke
