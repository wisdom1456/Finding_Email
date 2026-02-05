# Code Style and Conventions

## Python (Backend)
- **Linter**: Ruff
- **Line length**: 110 characters
- **Style**: PEP 8 with type hints throughout
- **Docstrings**: Required for public classes and functions (D100, D104, D107 ignored)
- **Quote style**: Double quotes

### Ruff Rules Enabled
- E: pycodestyle errors
- W: pycodestyle warnings
- F: pyflakes
- I: isort
- N: pep8-naming
- D: pydocstyle
- B: flake8-bugbear (B008 ignored for FastAPI Depends pattern)

## TypeScript/Svelte (Frontend)
- **Framework**: SvelteKit 2, Svelte 5 (Runes)
- **Type checking**: svelte-check
- **Styling**: Tailwind CSS
- **State**: Svelte 5 Runes ($state, $derived, $effect)

## Key Patterns
- Service layer pattern for business logic separation
- SSE for real-time progress updates
- Pydantic for data validation
- JWT-based authentication via Supabase
