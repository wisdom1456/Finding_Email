# Technical Context

## 1. Core Technologies

*   **Programming Language**: Python 3.11+
*   **Frontend Framework**: SvelteKit 2 (Svelte 5 with Runes)
*   **Backend API**: FastAPI with Uvicorn
*   **Internal Tools**: Streamlit (for development/admin tools)
*   **Primary AI Service**: OpenAI API (GPT-5.2 and GPT-5-mini)
*   **Database & Auth**: Supabase (PostgreSQL, Authentication, Storage, Realtime)
*   **Deployment Environment**: Vercel (frontend), Docker (backend), Google Cloud (production target)

## 2. Key Libraries & Frameworks

### Frontend (SvelteKit)
*   **`@sveltejs/kit`**: SvelteKit 2 framework with SSR and routing
*   **`svelte`**: Svelte 5 with Runes reactivity system
*   **`@supabase/ssr`**: Supabase authentication for server-side rendering
*   **`tailwindcss`**: Utility-first CSS framework
*   **`lucide-svelte`**: Icon library

### Backend (FastAPI)
*   **`fastapi`**: Modern async web framework for building APIs
*   **`uvicorn`**: ASGI server for FastAPI
*   **`supabase-py`**: Python client for Supabase services
*   **`sse-starlette`**: Server-Sent Events support for real-time updates
*   **`pydantic`**: Data validation and settings management

### OpenAI / GPT-5.2 Integration
*   **SDK Version**: `openai>=1.70.0` (required for GPT-5.2 support)
*   **Primary Model**: `gpt-5.2` - Complex reasoning, legal analysis, letter generation
*   **Cost-Optimized Model**: `gpt-5-mini` - Document summaries, chat, simpler tasks
*   **API**: Chat Completions API with `extra_body` for GPT-5 specific parameters

#### GPT-5.2 Parameters (via extra_body)
*   **`reasoning_effort`**: Controls reasoning depth
    *   `none` - Fastest, minimal reasoning (default for GPT-5.2)
    *   `low` - Light reasoning
    *   `medium` - Balanced reasoning
    *   `high` - Thorough reasoning
    *   `xhigh` - Maximum reasoning effort
*   **`verbosity`**: Controls output length
    *   `low` - Concise responses
    *   `medium` - Balanced (default)
    *   `high` - Detailed, thorough explanations
*   **`max_output_tokens`**: Replaces `max_tokens` for GPT-5 models

#### Implementation Pattern
```python
# Using OpenAIClient.create_response() with GPT-5.2
response = client.create_response(
    model="gpt-5.2",
    input="Your prompt here",
    instructions="System instructions",
    reasoning_effort="medium",
    verbosity="high",
    max_output_tokens=4000,
)

# Parameters are passed via extra_body for SDK compatibility
request_params = {
    "model": model,
    "messages": messages,
    "extra_body": {
        "reasoning_effort": "medium",
        "verbosity": "high",
        "max_output_tokens": 4000,
    }
}
```

#### Model Selection Guidelines
| Use Case | Model | Reasoning | Verbosity |
|----------|-------|-----------|-----------|
| Multi-stage legal analysis | gpt-5.2 | medium | medium |
| Demand letter generation | gpt-5.2 | low | high |
| Document summaries | gpt-5-mini | none | medium |
| Case chat | gpt-5-mini | none | low |
| Complex calculations | gpt-5.2 | high | medium |

### Core Application
*   **`legal_portal`**: The unified, in-house Python package containing all backend logic.
*   **`requests`**: For making HTTP requests to external APIs.
*   **`PyYAML`**: For parsing YAML configuration files.
*   **`python-dotenv`**: For managing environment variables.
*   **`ruff`**: For code linting and formatting, enforced via pre-commit hooks.
*   **`pytest`**: For running automated tests (Python).
*   **`vitest`**: For running automated tests (TypeScript/Svelte).

## 3. Codebase Structure

### Frontend (`frontend/`)
*   **Routes**: SvelteKit file-based routing in `frontend/src/routes/`
*   **Components**: Reusable Svelte components in `frontend/src/lib/components/`
*   **Stores**: Svelte stores for state management in `frontend/src/lib/stores/`
*   **Types**: TypeScript type definitions in `frontend/src/lib/types.ts`

### Backend (`src/legal_portal/`)
The consolidation has resulted in a single, installable Python package, `legal_portal`, located in the `src` directory. This promotes a clean, modern Python project structure.

*   **Namespace**: All backend code now resides under the `legal_portal` namespace.
    *   Example import: `from legal_portal.core.auth import authenticate_user`
*   **API**: FastAPI routes and dependencies in `src/legal_portal/api/`
    *   `main.py`: FastAPI application entry point
    *   `routes/`: API endpoint handlers (cases, documents, analysis, etc.)
    *   `dependencies.py`: Dependency injection (Supabase client, authentication)
*   **Configuration**:
    *   Service configurations and authentication details are managed in `src/legal_portal/config/`.
    *   The `config_manager.py` provides a centralized interface for accessing configuration values.
*   **Services**:
    *   All business logic is organized into services within `src/legal_portal/services/`.
    *   This includes specialized processors for different file types (`file_processors`), AI integrations (`openai_integration_service`), and core application workflows (`main_processor`).
*   **Core**: Core models and utilities in `src/legal_portal/core/`
    *   `data_models.py`: Pydantic models for data validation
    *   `document_processor.py`: Document processing orchestrator
*   **Utils**: Shared utilities in `src/legal_portal/utils/`
    *   `logging_config.py`: Centralized logging with structured output
    *   `security.py`: Security validation and sanitization
    *   `compression_utils.py`: File compression utilities

### Internal Tools (`src/legal_portal/ui/`)
*   Streamlit-based interfaces for development and administrative tasks

## 4. Development & CI/CD

*   **Dependency Management**: 
    *   Python: `pip` with `requirements.txt` and `requirements-dev.txt`, defined in `pyproject.toml`
    *   Frontend: `npm` with `package.json`
*   **Code Quality**: 
    *   Python: `ruff` is configured in `pyproject.toml` and run automatically via `pre-commit`
    *   TypeScript: ESLint and svelte-check
*   **Testing**: 
    *   Python: Unit and integration tests are located in the `tests/` directory and run with `pytest`
    *   Frontend: Tests use Vitest and Playwright for E2E testing
*   **Containerization**: Dockerfiles present for building production-ready container images
*   **Deployment**:
    *   Frontend: Vercel (automatic deployments from Git)
    *   Backend: Docker containers on Google Cloud or similar infrastructure