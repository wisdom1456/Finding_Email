# Project Architecture

This document describes the architecture and directory structure of the Legal Document Analysis Portal after the SvelteKit + FastAPI migration.

## Technology Stack

- **Frontend**: SvelteKit 2, Svelte 5 (Runes), TypeScript, Tailwind CSS v4
- **Backend**: FastAPI, Python 3.11+, Pydantic
- **Database**: Supabase (PostgreSQL) with Row Level Security
- **Authentication**: Supabase Auth (JWT)
- **AI/ML**: OpenAI GPT-5.2, GPT-5-mini, GPT-4.1, GPT-4o Vision
- **Document Processing**: PyMuPDF, python-docx, Pillow, Google Cloud Vision (OCR)
- **Deployment**: Vercel (SvelteKit frontend + Python serverless backend)

## Directory Structure

```
Finding_Emails/
├── frontend/                      # SvelteKit frontend
│   ├── src/
│   │   ├── lib/
│   │   │   ├── components/        # Svelte components
│   │   │   │   ├── ui/            # Reusable UI (AsyncButton, LoadingOverlay, etc.)
│   │   │   │   ├── ClioConnect.svelte
│   │   │   │   ├── ClioMatterSearch.svelte
│   │   │   │   ├── ClioImportProgressModal.svelte
│   │   │   │   └── ProgressIndicator.svelte
│   │   │   ├── stores/            # Svelte stores (progress, toast, loading)
│   │   │   ├── utils/             # Client utilities (SSE client, polling)
│   │   │   ├── config.ts          # Frontend configuration
│   │   │   └── supabase.ts        # Supabase client init
│   │   └── routes/
│   │       ├── +layout.svelte     # Root layout
│   │       ├── app/
│   │       │   ├── cases/         # Case list and creation
│   │       │   │   ├── [id]/      # Case detail, analysis, results
│   │       │   │   └── new/       # New case form
│   │       │   └── +layout.svelte # Authenticated layout
│   │       ├── login/             # Login page
│   │       └── register/          # Registration page
│   ├── static/                    # Static assets
│   ├── svelte.config.js           # SvelteKit + Vercel adapter config
│   ├── vite.config.ts             # Vite configuration
│   └── package.json
│
├── src/
│   └── legal_portal/              # Python backend package
│       ├── api/
│       │   ├── main.py            # FastAPI app entry point
│       │   ├── routes/            # API endpoint modules
│       │   │   ├── analysis.py    # Analysis endpoints
│       │   │   ├── cases.py       # Case CRUD endpoints
│       │   │   ├── clio.py        # Clio integration endpoints
│       │   │   ├── documents.py   # Document upload/management
│       │   │   └── progress.py    # SSE progress streaming
│       │   ├── dependencies.py    # FastAPI dependency injection
│       │   └── services/          # API-level services (Clio client)
│       ├── core/                  # Business logic
│       │   ├── letter_prompts.py  # AI prompt templates
│       │   └── logging_config.py  # Structured logging
│       ├── services/              # Service layer
│       │   ├── analysis_service.py
│       │   ├── chunk_state_manager.py
│       │   ├── content_extractor.py
│       │   ├── document_formatter.py
│       │   ├── json_processing_service.py
│       │   ├── main_processor.py
│       │   ├── progress_manager.py
│       │   └── qa_service.py
│       ├── utils/                 # Shared utilities
│       └── config/                # Configuration management
│
├── api/                           # Vercel serverless entry point
│   └── index.py                   # Routes requests to FastAPI app
│
├── florida_legal_corpus/          # Florida statute corpus (51 statutes)
├── new_mexico_legal_corpus/       # New Mexico statute corpus (42 + 8 rules)
├── tests/                         # Python test suites
│   ├── unit/
│   ├── integration/
│   ├── api/
│   └── conftest.py
│
├── scripts/                       # Utility scripts
├── docs/                          # Documentation
├── supabase/                      # Database schema and migrations
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # Python project config
└── vercel.json                    # Vercel deployment config
```

## Key Design Patterns

### Service Layer

Backend follows a service-oriented architecture:
- **Routes** handle HTTP concerns (request parsing, response formatting)
- **Services** contain business logic (analysis orchestration, document processing)
- **Dependencies** manage shared resources (Supabase client, auth validation)

### SSE Progress Streaming

Real-time progress updates use Server-Sent Events:
- Backend `ProgressManager` publishes events during long operations
- Frontend `sseClient.ts` connects to `/api/progress/analysis/{id}`
- `progressStore` provides reactive state to components
- Automatic fallback to polling if SSE connection fails

### Document Processing Pipeline

1. Documents uploaded to Supabase Storage
2. Content extraction (PyMuPDF for PDF, python-docx for DOCX, GPT-4o Vision for images)
3. AI analysis with structured JSON output
4. Gap analysis across all documents
5. Letter generation with two-pass formatting
6. Citation validation against legal corpus

### Frontend State Management

- **Svelte 5 Runes**: `$state`, `$derived`, `$effect` for reactive state
- **Stores**: Shared state via Svelte stores (progress, toast, loading)
- **SSR**: Server-side data loading via `+page.server.ts` for fast initial render

### Authentication Flow

1. Supabase Auth handles registration, login, JWT issuance
2. Frontend stores JWT in browser, attaches to API requests
3. Backend validates JWT via Supabase client
4. Row Level Security (RLS) enforces data access at database level

## API Structure

All backend endpoints are prefixed with `/api/`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Health check |
| `/api/cases` | GET/POST | List and create cases |
| `/api/cases/{id}` | GET/PUT/DELETE | Case CRUD |
| `/api/cases/{id}/documents` | POST | Upload documents |
| `/api/cases/{id}/analyze` | POST | Start analysis |
| `/api/progress/analysis/{id}` | GET (SSE) | Stream analysis progress |
| `/api/clio/status` | GET | Clio connection status |
| `/api/clio/callback` | GET | OAuth callback |
| `/api/clio/matters` | GET | Search Clio matters |
