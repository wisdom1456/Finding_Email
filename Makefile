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