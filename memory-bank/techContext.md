# Technical Context

## 1. Core Technologies

*   **Programming Language**: Python 3.11+
*   **Web Framework**: Streamlit
*   **Primary AI Service**: OpenAI API (GPT-4)
*   **Deployment Environment**: Docker (local), Google Cloud (production target)

## 2. Key Libraries & Frameworks

*   **`legal_portal`**: The unified, in-house Python package containing all backend logic.
*   **`requests`**: For making HTTP requests to external APIs.
*   **`PyYAML`**: For parsing YAML configuration files.
*   **`python-dotenv`**: For managing environment variables.
*   **`ruff`**: For code linting and formatting, enforced via pre-commit hooks.
*   **`pytest`**: For running automated tests.

## 3. Codebase Structure (`src/legal_portal`)

The consolidation has resulted in a single, installable Python package, `legal_portal`, located in the `src` directory. This promotes a clean, modern Python project structure.

*   **Namespace**: All backend code now resides under the `legal_portal` namespace.
    *   Example import: `from legal_portal.core.auth import authenticate_user`
*   **Configuration**:
    *   Service configurations and authentication details are managed in `src/legal_portal/config/`.
    *   The `config_manager.py` provides a centralized interface for accessing configuration values.
*   **Services**:
    *   All business logic is organized into services within `src/legal_portal/services/`.
    *   This includes specialized processors for different file types (`file_processors`), AI integrations (`openai_integration_service`), and core application workflows (`main_processor`).

## 4. Development & CI/CD

*   **Dependency Management**: `pip` with `requirements.txt` and `requirements-dev.txt`.
*   **Code Quality**: `ruff` is configured in `pyproject.toml` and run automatically via `pre-commit`.
*   **Testing**: Unit and integration tests are located in the `tests/` directory and run with `pytest`.
*   **Containerization**: A `Dockerfile` is present for building a production-ready container image.