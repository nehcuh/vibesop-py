.PHONY: help install dev lint format test test-fast test-cov clean clean-cov type-check security

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

dev: install ## Install development dependencies
	uv sync --extra dev

lint: ## Run linting
	uv run ruff check .

format: ## Format code
	uv run ruff format .

type-check: ## Run type checking
	uv run basedpyright

test: clean-cov ## Run tests (skip slow/benchmark for reasonable speed)
	uv run pytest -m "not benchmark and not slow"

test-fast: clean-cov ## Run tests fast (skip slow/benchmark)
	uv run pytest -q -m "not benchmark and not slow"

test-cov: clean-cov ## Run tests with coverage
	uv run pytest --cov=src/vibesop --cov-report=html

test-parallel: ## Run tests with pytest-xdist (may fail on stateful tests)
	uv run pytest -n auto -m "not benchmark and not slow"

test-full: ## Run full test suite including benchmark and slow tests
	uv run pytest

security: ## Run security checks (pip-audit)
	uv run pip-audit

clean: clean-cov ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache htmlcov/

clean-cov: ## Clean coverage artifacts (fixes local DataError from stale .coverage.* xdist files)
	@rm -f .coverage .coverage.*

docs: ## Generate API documentation
	uv run pdoc src/vibesop -o docs/api --docformat google

docs-serve: ## Serve API documentation locally
	uv run pdoc src/vibesop --docformat google

check: lint type-check test-fast ## Run all checks (lint, type-check, test-fast)

benchmark: ## Run performance benchmarks
	uv run pytest tests/benchmark/ tests/benchmarks/ -v -m benchmark --no-cov

bootstrap: dev ## Bootstrap development environment
	@echo "✨ Development environment ready!"
	@echo "Run 'make check' to verify everything is working."
