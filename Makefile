.PHONY: help install dev lint format test clean type-check security

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

test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage
	uv run pytest --cov=src/vibesop --cov-report=html

security: ## Run security checks (pip-audit)
	uv run pip-audit

clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov/

check: lint type-check test ## Run all checks (lint, type-check, test)

benchmark: ## Run performance benchmarks
	uv run pytest tests/benchmark/ -v -m benchmark --no-cov

bootstrap: dev ## Bootstrap development environment
	@echo "✨ Development environment ready!"
	@echo "Run 'make check' to verify everything is working."
