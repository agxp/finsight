.PHONY: help install migrate seed run-api test lint typecheck docker-up docker-down

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -e ".[dev]"

migrate: ## Apply database migrations
	@for f in finsight/database/migrations/*.sql; do \
		echo "Applying $$f..."; \
		psql "$$DATABASE_URL" -f "$$f"; \
	done

seed: ## Seed dev tenant and print API key
	python scripts/seed_tenant.py

run-api: ## Run the FastAPI server
	uvicorn finsight.api.main:app --reload --port 8000

test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v

test-integration: ## Run integration tests only
	pytest tests/integration/ -v -m integration

lint: ## Run ruff linter
	ruff check finsight/ tests/

format: ## Auto-fix linting issues
	ruff check --fix finsight/ tests/
	ruff format finsight/ tests/

typecheck: ## Run mypy
	mypy finsight/

docker-up: ## Start all Docker services
	docker-compose up -d

docker-down: ## Stop all Docker services
	docker-compose down

verify: ## Run end-to-end smoke test
	python scripts/verify_pipeline.py
