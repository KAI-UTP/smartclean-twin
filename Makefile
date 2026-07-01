# SmartClean Twin — common development targets

.PHONY: up down build test unit regression system logs clean scale persist

up:
	docker compose up --build -d
	@echo "Stack starting... use 'make logs' to follow"

down:
	docker compose down

build:
	docker compose build

test: unit regression
	@echo "All offline tests passed."

unit:
	pytest tests/unit/ -v --tb=short

regression:
	pytest tests/regression/ -v --tb=short

system:
	INTEGRATION_TEST=1 pytest tests/system/ -v --tb=short

coverage:
	pytest tests/unit/ tests/regression/ \
	  --cov=shared --cov=services \
	  --cov-report=html --cov-report=term-missing

logs:
	docker compose logs -f

scale:
	docker compose up --scale telemetry-ingestion=2 -d

persist:
	python scripts/persistence_test.py

smoke:
	python scripts/smoke_test.py

clean:
	docker compose down -v
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	find . -name ".coverage" -delete 2>/dev/null; true
