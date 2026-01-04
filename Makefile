# Makefile for the Finding Emails project

# Set the Python interpreter
PYTHON = python3

# Set the source directory
SRC = app

# Set the test directory
TESTS = tests

# Default command
all: help

# Help command
help:
	@echo "Makefile for the Finding Emails project"
	@echo ""
	@echo "Usage:"
	@echo "  make help        - Show this help message"
	@echo "  make run         - Run the main application"
	@echo "  make test        - Run the test suite"
	@echo "  make clean       - Remove all temporary files"
	@echo ""
	@echo "Local Debug Testing:"
	@echo "  make debug       - Start backend in Vercel simulation mode"
	@echo "  make frontend    - Start frontend dev server"
	@echo "  make pull-case   - Pull case data from Supabase (NAME=client name)"
	@echo "  make run-analysis- Run full analysis on snapshot"
	@echo "  make step-test   - Step-by-step analysis to isolate failures"
	@echo "  make test-api    - Test OpenAI API directly"
	@echo "  make clean-test  - Clean test snapshots and debug output"
	@echo ""

# Run the main application
run:
	@echo "Running the main application..."
	@$(PYTHON) -m $(SRC).main

# Run the test suite
test:
	@echo "Running the test suite..."
	@PYTHONPATH=. $(PYTHON) -m unittest discover -s $(TESTS)

# Remove all temporary files
clean:
	@echo "Removing all temporary files..."
	@find . -type f -name "*.py[co]" -delete
	@find . -type d -name "__pycache__" -delete

# === LOCAL DEBUG TESTING ===

# Start backend in debug/Vercel mode (simulates production SSE behavior)
debug:
	@echo "Starting backend in Vercel simulation mode..."
	@VERCEL=1 LOG_LEVEL=DEBUG DIAGNOSTIC_MODE=true \
	 bash -c 'source venv/bin/activate && uvicorn api.index:app --host 0.0.0.0 --port 8000 --reload'

# Start backend without Vercel simulation (uses BackgroundTasks)
backend:
	@echo "Starting backend in local mode..."
	@source venv/bin/activate && uvicorn api.index:app --host 0.0.0.0 --port 8000 --reload

# Start frontend dev server
frontend:
	@cd frontend && npm run dev

# Pull case data from Supabase (default: Mary Ann Rivera)
# Usage: make pull-case NAME="Client Name"
pull-case:
	@source venv/bin/activate && python scripts/testing/pull_case.py "$(or $(NAME),Mary Ann Rivera)"

# List available cases in Supabase
list-cases:
	@source venv/bin/activate && python scripts/testing/pull_case.py --list

# Run full analysis on snapshot
# Usage: make run-analysis SNAPSHOT=path/to/case.json
run-analysis:
	@source venv/bin/activate && python scripts/testing/run_analysis.py \
	 "$(or $(SNAPSHOT),scripts/snapshots/mary_ann_rivera/case.json)"

# Step-by-step analysis (isolate failure point)
# Usage: make step-test SNAPSHOT=path/to/case.json
step-test:
	@source venv/bin/activate && python scripts/testing/step_test.py \
	 "$(or $(SNAPSHOT),scripts/snapshots/mary_ann_rivera/case.json)"

# Direct OpenAI API test with fact extraction parameters
test-api:
	@source venv/bin/activate && python scripts/testing/test_api.py

# Clean snapshots and debug output
clean-test:
	@rm -rf scripts/snapshots/*/
	@rm -rf debug_output/sessions/*
	@rm -f .cursor/debug.log
	@echo "Test data and debug output cleaned"

# Pre-deployment verification (run BEFORE git push)
verify:
	@source venv/bin/activate && python scripts/testing/verify_deployment.py

# Full pre-push check: verify + test API
pre-push: verify test-api
	@echo "\n✓ All checks passed - safe to push"