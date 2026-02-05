# Development Commands

## Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Start backend (local mode)
make backend
# Or: source venv/bin/activate && uvicorn api.index:app --host 0.0.0.0 --port 8000 --reload

# Start backend (Vercel simulation)
make debug

# Run tests
pytest tests/
pytest tests/ --cov=src/legal_portal
```

## Frontend
```bash
cd frontend
npm install
npm run dev          # Development server
npm run test         # Unit tests
npm run test:e2e     # E2E tests
npm run check        # Type checking
```

## Quality Checks
```bash
# Python linting
ruff check src/
ruff check src/ --fix

# Pre-deployment verification
make verify

# Full pre-push check
make pre-push
```

## Testing Tools
```bash
make pull-case NAME="Client Name"  # Pull case from Supabase
make list-cases                     # List available cases
make run-analysis                   # Run analysis on snapshot
make step-test                      # Step-by-step analysis
make test-api                       # Test OpenAI API
make clean-test                     # Clean test data
```
