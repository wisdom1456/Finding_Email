.PHONY: help install lint format test security clean

help:
	@echo "Available commands:"
	@echo "  install    Install dependencies"
	@echo "  lint       Run linting checks"
	@echo "  format     Format code"
	@echo "  test       Run tests"
	@echo "  security   Run security scans"
	@echo "  clean      Clean up generated files"

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pre-commit install

lint:
	ruff check . --fix

format:
	ruff format .

test:
	pytest utils/tests/ --cov=utils --cov=core --cov=services

security:
	bandit -r core/ services/ utils/
	safety check
	pip-audit

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .coverage coverage.xml htmlcov/
	rm -rf .cache/ benchmark.json bandit-report.json