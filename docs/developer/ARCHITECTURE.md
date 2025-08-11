# Project Architecture and Directory Structure

This document outlines the standardized, production-grade directory structure for the Finding Emails project. The new layout is designed to improve organization, scalability, and maintainability by separating concerns and centralizing application components.

## High-Level Overview

The new architecture is organized into the following top-level directories:

- **`/app`**: The core application source code, including business logic, API endpoints, and UI components.
- **`/config`**: Centralized configuration management for all application environments.
- **`/core`**: Cross-cutting concerns and core utilities shared across the application.
- **`/docs`**: All project documentation, including architectural diagrams, development guides, and API specifications.
- **`/scripts`**: Helper scripts for automation, database management, and other operational tasks.
- **`/tests`**: The unified testing suite, with separate directories for unit, integration, and end-to-end tests.

---

## Detailed Directory Structure

### 1. Root Directory

- **`.github/`**: CI/CD workflows for GitHub Actions.
- **`.idea/`, `.vscode/`**: IDE-specific settings (should be in `.gitignore`).
- **`app/`**: Main application source code.
- **`config/`**: Unified application configuration.
- **`core/`**: Core utilities and shared services.
- **`docs/`**: Project documentation.
- **`memory-bank/`**: Canonical, searchable knowledge base.
- **`scripts/`**: Automation and operational scripts.
- **`tests/`**: All application tests.
- **`.env.example`**: Example environment file.
- **`.gitignore`**: Git ignore rules.
- **`Dockerfile`**: Containerization configuration.
- **`Makefile`**: Standardized build and run commands.
- **`pyproject.toml`**: Python project configuration and dependencies.
- **`README.md`**: Project overview.

### 2. Core Application (`/app`)

- **`app/`**: Contains all core application source code.
  - **`__init__.py`**: Initializes the `app` module.
  - **`main.py`**: The main application entry point (e.g., for Streamlit or FastAPI).
  - **`components/`**: Reusable UI components for the Streamlit application.
  - **`services/`**: Business logic and external service integrations (e.g., OpenAI, database connections).
  - **`utils/`**: Shared utility functions and helper classes.

### 3. Configuration (`/config`)

- **`config/`**: Centralized configuration management.
  - **`__init__.py`**: Initializes the `config` module.
  - **`default.py`**: Base configuration settings for all environments.
  - **`development.py`**, **`production.py`**: Environment-specific overrides.

### 4. Testing (`/tests`)

- **`tests/`**: Houses all unit, integration, and end-to-end tests.
  - **`__init__.py`**: Initializes the `tests` module.
  - **`conftest.py`**: Shared fixtures and test configuration.
  - **`unit/`**: Unit tests for individual components and functions.
  - **`integration/`**: Integration tests for interactions between services.
  - **`e2e/`**: End-to-end tests that simulate user workflows.