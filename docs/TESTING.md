# Testing Guide

This document is the consolidated reference for running and writing tests across the
Finding Emails legal document analysis platform. It covers backend (Python/pytest),
frontend (Vitest), and end-to-end (Playwright) testing.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Backend Testing](#backend-testing)
3. [Frontend Testing](#frontend-testing)
4. [Writing New Tests](#writing-new-tests)
5. [Test Categories](#test-categories)
6. [CI/CD Integration](#cicd-integration)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

Run the full test suites from the project root:

```bash
# Backend tests
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 -m pytest tests/ -q

# Frontend tests
cd frontend
npx vitest run

# Frontend with coverage
npx vitest run --coverage
```

**Current status (as of 2026-03-15):**

| Suite    | Passed | Failed | Errors | Skipped |
|----------|--------|--------|--------|---------|
| Backend  | 831    | 6      | 33     | --      |
| Frontend | 518    | --     | --     | 1       |

---

## Backend Testing

### Framework

Python tests use **pytest**. The test root is `tests/` at the project top level.

### Directory Structure

```
tests/
  conftest.py          # Shared fixtures (DB mocks, auth helpers, API clients)
  unit/                # Isolated function and class tests
  integration/         # Service interaction and workflow tests
  api/                 # Endpoint tests using FastAPI TestClient
```

### Running Tests

```bash
# Run all backend tests
python3 -m pytest tests/ -q

# Run a specific test file
pytest tests/unit/test_clio_client.py -v

# Run tests matching a keyword
pytest tests/ -k "analysis" -v

# Run only unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/ --cov=src/legal_portal

# Run with coverage and HTML report
pytest tests/ --cov=src/legal_portal --cov-report=html
```

### Key Test Areas

- **API routes** -- endpoint contracts, request validation, auth guards
- **Services** -- analysis pipeline, letter generation, Clio client integration
- **Utils** -- helper functions, date formatting, text processing
- **Core business logic** -- document parsing, gap analysis, findings extraction

### Fixtures

Shared fixtures live in `tests/conftest.py`. Common fixtures include:

- Database session mocks
- Authenticated request clients
- Sample document payloads
- Mock responses for external APIs (OpenAI, Supabase, Clio)

Import fixtures by name in any test function signature; pytest discovers them
automatically from `conftest.py`.

---

## Frontend Testing

### Framework

Frontend tests use **Vitest** with **@testing-library/svelte** for component
rendering and interaction.

### Test File Locations

Test files are colocated with source code using one of two patterns:

- Sibling files: `ComponentName.test.ts` next to `ComponentName.svelte`
- Test directories: `__tests__/` folders alongside the modules they cover

### Running Tests

```bash
cd frontend

# Run all frontend tests
npm run test
# or
npx vitest run

# Run in watch mode during development
npx vitest

# Run a specific test file
npx vitest run src/lib/stores/progressStore.test.ts

# Run tests matching a pattern
npx vitest run --reporter=verbose -t "toast"

# Run with coverage
npx vitest run --coverage
```

### Key Test Areas

- **Components** -- rendering, user interaction, conditional display logic
- **Stores** -- Svelte store state management and derived values
- **Utils** -- polling client, SSE client, helper functions
- **API client** -- request formation, error handling, response parsing

---

## Writing New Tests

### Backend

1. Place the test file in the appropriate directory (`unit/`, `integration/`, or `api/`).
2. Name it `test_<feature>.py`.
3. Use pytest fixtures for setup and teardown. Add reusable fixtures to `conftest.py`.
4. Mock all external service calls -- never hit live APIs in tests.

```python
# tests/unit/test_document_parser.py

import pytest
from unittest.mock import patch, MagicMock
from src.legal_portal.services.document_parser import parse_document


@pytest.fixture
def sample_document():
    return {"id": "doc-1", "content": "Sample legal text..."}


def test_parse_document_extracts_findings(sample_document):
    result = parse_document(sample_document)
    assert "findings" in result
    assert len(result["findings"]) > 0


@patch("src.legal_portal.services.document_parser.openai_client")
def test_parse_document_handles_api_error(mock_openai, sample_document):
    mock_openai.chat.completions.create.side_effect = Exception("API down")
    with pytest.raises(Exception, match="API down"):
        parse_document(sample_document)
```

**External APIs to mock:**

- OpenAI (`openai` client)
- Supabase (`supabase` client)
- Clio (`httpx` or `requests` calls to Clio API)

### Frontend

1. Create test files as `<feature>.test.ts` next to the source file.
2. Use `@testing-library/svelte` for component tests.
3. Mock `fetch` calls and external dependencies.

```typescript
// src/lib/stores/progressStore.test.ts

import { describe, it, expect, vi } from 'vitest';
import { progressStore } from './progressStore';
import { get } from 'svelte/store';

describe('progressStore', () => {
  it('initializes with zero progress', () => {
    const state = get(progressStore);
    expect(state.progress).toBe(0);
  });

  it('updates progress value', () => {
    progressStore.setProgress(50);
    const state = get(progressStore);
    expect(state.progress).toBe(50);
  });
});
```

```typescript
// src/lib/components/PageHeader.test.ts

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import PageHeader from './PageHeader.svelte';

describe('PageHeader', () => {
  it('renders the title', () => {
    render(PageHeader, { props: { title: 'Cases' } });
    expect(screen.getByText('Cases')).toBeTruthy();
  });
});
```

### Naming Conventions

| Layer    | Pattern                  | Example                        |
|----------|--------------------------|--------------------------------|
| Backend  | `test_<feature>.py`      | `test_clio_client.py`          |
| Frontend | `<feature>.test.ts`      | `progressStore.test.ts`        |
| E2E      | `<feature>.spec.ts`      | `case-creation.spec.ts`        |

---

## Test Categories

### Unit Tests

Isolated tests for individual functions, classes, or components. No external
dependencies; all I/O is mocked.

- **Backend:** `tests/unit/`
- **Frontend:** colocated `*.test.ts` files

### Integration Tests

Tests that verify interactions between multiple services or modules. May use
in-memory databases or mocked API boundaries.

- **Backend:** `tests/integration/`

### API Tests

Endpoint-level tests using FastAPI's `TestClient`. Validate request/response
contracts, status codes, and error handling.

- **Backend:** `tests/api/`

### End-to-End Tests

Full browser-based tests using Playwright. These exercise the complete stack
from UI through API to (mocked or staging) backends.

- **Location:** see [docs/PLAYWRIGHT_TESTING.md](PLAYWRIGHT_TESTING.md)

---

## CI/CD Integration

Tests run automatically on every push via **GitHub Actions**.

- Backend and frontend test suites execute as independent jobs.
- Both suites must pass before a pull request can merge.
- Coverage reports are generated but not currently gated (no minimum threshold enforced).

Workflow summary:

```
push / PR --> GitHub Actions
               |
               +-- Backend job:  python3 -m pytest tests/ -q
               |
               +-- Frontend job: cd frontend && npx vitest run
```

---

## Troubleshooting

### Backend (pytest)

**ImportError or ModuleNotFoundError**

The most common cause is running pytest from the wrong directory or missing the
package install. Run from the project root:

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 -m pytest tests/ -q
```

If the error persists, verify the package is installed in editable mode:

```bash
pip install -e .
```

**Fixture not found**

- Confirm the fixture is defined in `conftest.py` at the correct level (root or
  subdirectory).
- Check for typos in the fixture name in the test function signature.
- Ensure `conftest.py` is not excluded by a `.pytest` configuration.

**Tests pass locally but fail in CI**

- Check for environment-dependent paths or secrets.
- Verify Python version matches between local and CI (check `.python-version`
  or the workflow YAML).
- Look for tests that depend on execution order -- use `pytest-randomly` to
  surface these.

### Frontend (Vitest)

**Module resolution errors**

Vitest must resolve Svelte components and path aliases. Ensure `vite.config.ts`
(or `vitest.config.ts`) includes the correct `resolve.alias` entries matching
`svelte.config.js`.

**Svelte component mocking**

When a component import causes side effects or relies on browser APIs, mock it:

```typescript
vi.mock('$lib/components/HeavyComponent.svelte', () => ({
  default: vi.fn()
}));
```

**Store state leaking between tests**

Svelte stores persist across tests in the same file. Reset store state in
`beforeEach` or create fresh store instances per test.

**Timeout errors**

For async operations, increase the test timeout:

```typescript
it('completes long operation', async () => {
  // ...
}, 10_000); // 10 second timeout
```
