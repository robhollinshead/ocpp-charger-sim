.PHONY: install run test test-unit test-integration test-api test-quick test-coverage test-report

PORT ?= 8001
# Must run from backend/ so "main" and "api" resolve. Prefer: ./run.sh
PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	@test -d .venv || (echo "Run 'make install' from backend/ first (creates .venv)"; exit 1)
	$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port $(PORT)

test:
	$(PYTHON) -m pytest tests/ -v

test-unit:
	$(PYTHON) -m pytest tests/unit/ -v

test-integration:
	$(PYTHON) -m pytest tests/integration/ -v

test-api:
	$(PYTHON) -m pytest tests/api/ -v

test-quick:
	$(PYTHON) -m pytest tests/api/ -v -m api

test-coverage:
	$(PYTHON) -m pytest tests/ --cov=api --cov=simulator_core --cov=repositories --cov=db --cov=utils --cov=schemas --cov=models --cov-report=term-missing --cov-report=html:htmlcov --cov-fail-under=80

test-report:
	$(PYTHON) scripts/test_report.py
