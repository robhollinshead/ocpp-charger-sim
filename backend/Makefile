.PHONY: install run test

PORT ?= 8001
# Must run from backend/ so "main" and "api" resolve. Prefer: ./run.sh
PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	@test -d .venv || (echo "Run 'make install' from backend/ first (creates .venv)"; exit 1)
	$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port $(PORT)

test:
	@echo "Tests TBD — add pytest in Phase 7"
