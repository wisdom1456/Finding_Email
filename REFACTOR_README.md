# Legal Document Analysis Portal - FastAPI + SvelteKit

This document describes the refactored architecture of the Legal Document Analysis Portal, migrated from Streamlit to a modern FastAPI backend with SvelteKit frontend.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    SvelteKit Frontend                    │
│              (TypeScript + Tailwind CSS)                 │
│                                                          │
│  - Authentication (Supabase Auth)                        │
│  - Case Management Dashboard                             │
│  - Document Upload Interface                             │
│  - Analysis Results Viewer                               │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ HTTP/REST
                   │
┌──────────────────▼──────────────────────────────────────┐
│                  FastAPI Backend                         │
│                   (Python 3.11+)                         │
│                                                          │
│  - REST API Endpoints                                    │
│  - Document Processing                                   │
│  - AI Analysis Orchestration                             │
│  - Background Tasks                                      │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │
      ┌────────────┼────────────┐
      │            │            │
      ▼            ▼            ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│Supabase │  │ OpenAI  │  │ Core    │
│         │  │   API   │  │Services │
│- Auth   │  │         │  │         │
│- DB     │  │- GPT-4  │  │- OCR    │
│- Storage│  │- Claude │  │- PDF    │
└─────────┘  └─────────┘  └─────────┘
```

## Directory Structure

```
Finding_Emails/
├── src/
│   └── legal_portal/
│       ├── api/                    # NEW: FastAPI application
│       │   ├── main.py            # FastAPI app entry point
│       │   ├── dependencies.py    # Dependency injection
│       │   └── routes/            # API route modules
│       │       ├── health.py      # Health checks
│       │       ├── cases.py       # Case management
│       │       ├── documents.py   # Document upload/management
│       │       └── analysis.py    # Analysis endpoints
│       ├── core/                  # Shared business logic
│       ├── services/              # Core processing services
│       └── ui/                    # Legacy Streamlit (for reference)
├── frontend/                      # NEW: SvelteKit application
│   ├── src/
│   │   ├── lib/
│   │   │   ├── supabase.ts       # Supabase client
│   │   │   └── database.types.ts  # TypeScript types
│   │   ├── routes/
│   │   │   ├── login/            # Authentication pages
│   │   │   ├── register/
│   │   │   └── app/              # Protected dashboard
│   │   │       ├── +page.svelte   # Dashboard home
│   │   │       └── cases/         # Case management
│   │   ├── app.css               # Tailwind styles
│   │   └── hooks.server.ts       # Server-side auth
│   ├── static/
│   ├── package.json
│   └── svelte.config.js
├── supabase/                      # NEW: Database schema
│   ├── schema.sql                # Database tables & RLS
│   └── README.md                 # Setup instructions
├── tests/
│   ├── api/                      # NEW: API endpoint tests
│   ├── integration/              # End-to-end workflow tests
│   └── unit/                     # Unit tests
└── requirements.txt              # Python dependencies
```

## Setup Instructions

### Prerequisites

- Python 3.11+
- Node.js 18+
- Supabase account
- OpenAI API key

### 1. Backend Setup (FastAPI)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
SUPABASE_ANON_KEY=your_anon_key
OPENAI_API_KEY=your_openai_key
EOF

# Run the API server
cd src
uvicorn legal_portal.api.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### 2. Database Setup (Supabase)

```bash
# Option A: Using Supabase Dashboard
# 1. Go to https://app.supabase.com
# 2. Create new project
# 3. Navigate to SQL Editor
# 4. Run the contents of supabase/schema.sql

# Option B: Using Supabase CLI
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

See `supabase/README.md` for detailed setup instructions.

### 3. Frontend Setup (SvelteKit)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Create .env file
cat > .env << EOF
PUBLIC_SUPABASE_URL=https://your-project.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your_anon_key
PUBLIC_API_URL=http://localhost:8000
EOF

# Run development server
npm run dev
```

The frontend will be available at `http://localhost:5173`

### 4. Running Tests

```bash
# Run all tests
pytest

# Run specific test suites
pytest tests/unit/
pytest tests/integration/
pytest tests/api/

# Run with coverage
pytest --cov=src/legal_portal --cov-report=html
```

## API Endpoints

### Authentication

All protected endpoints require a JWT token from Supabase Auth:

```
Authorization: Bearer <token>
```

### Health Checks

- `GET /` - Root endpoint
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed health with dependencies

### Cases

- `POST /api/cases` - Create new case
- `GET /api/cases` - List all cases
- `GET /api/cases/{id}` - Get case details
- `PATCH /api/cases/{id}` - Update case
- `DELETE /api/cases/{id}` - Delete case

### Documents

- `POST /api/documents/upload` - Upload document
- `GET /api/documents/case/{case_id}` - List documents for case
- `GET /api/documents/{id}` - Get document metadata
- `DELETE /api/documents/{id}` - Delete document

### Analysis

- `POST /api/analysis/start` - Start analysis (background task)
- `GET /api/analysis/status/{case_id}` - Get analysis status
- `GET /api/analysis/results/{case_id}` - Get completed results

## Frontend Routes

### Public

- `/login` - User login
- `/register` - User registration

### Protected (requires authentication)

- `/app` - Dashboard home
- `/app/cases` - Cases list
- `/app/cases/new` - Create new case
- `/app/cases/[id]` - Case detail (upload, analyze)
- `/app/cases/[id]/results` - Analysis results

## Key Features

### 1. Authentication & Authorization

- Supabase Auth for user management
- Row Level Security (RLS) on all database tables
- JWT-based API authentication
- Protected routes on frontend

### 2. Document Management

- Multi-file upload support
- Supabase Storage for file persistence
- Support for PDF, DOCX, images
- OCR for scanned documents

### 3. AI Analysis

- Asynchronous background processing
- Real-time status updates
- OpenAI/Anthropic integration
- Cost tracking and reporting

### 4. Resumable Sessions

- All state persisted in database
- No session loss on page refresh
- Multiple device access
- Collaborative case management

## Database Schema

### Tables

- **profiles** - User profiles (extends Supabase Auth)
- **cases** - Legal cases for analysis
- **documents** - Uploaded documents metadata
- **analysis_results** - AI analysis results and status

### Row Level Security (RLS)

All tables have RLS enabled:
- Users can only access their own data
- Access to documents/analysis through case ownership
- Service role bypasses RLS for background tasks

See `supabase/schema.sql` for complete schema definition.

## Environment Variables

### Backend (.env)

```env
SUPABASE_URL=              # Supabase project URL
SUPABASE_SERVICE_KEY=      # Service role key (for admin operations)
SUPABASE_ANON_KEY=         # Anon key (for client operations)
OPENAI_API_KEY=            # OpenAI API key
ANTHROPIC_API_KEY=         # Optional: Anthropic API key
```

### Frontend (.env)

```env
PUBLIC_SUPABASE_URL=       # Supabase project URL
PUBLIC_SUPABASE_ANON_KEY=  # Anon key (public, safe to expose)
PUBLIC_API_URL=            # Backend API URL
```

## Deployment

### Backend (FastAPI)

Deploy to any Python hosting service:

- **Vercel** - Serverless functions
- **Railway** - Container deployment
- **Fly.io** - Global app platform
- **AWS Lambda** - Serverless with API Gateway

Example for Vercel:

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel --prod
```

### Frontend (SvelteKit)

Deploy to static hosting or SSR platform:

- **Vercel** - Automatic deployment from Git
- **Netlify** - Static site hosting
- **Cloudflare Pages** - Global CDN

Example for Vercel:

```bash
cd frontend
vercel --prod
```

### Database (Supabase)

Supabase is already hosted. Just ensure:
1. Production environment variables are set
2. RLS policies are properly configured
3. Storage buckets have correct policies

## Migration from Streamlit

### What Changed

1. **Session State** → Supabase Database
   - All `st.session_state` replaced with database persistence
   - Cases, documents, and results stored permanently

2. **File Uploads** → Supabase Storage
   - Files stored in cloud storage instead of temp directory
   - Accessible across devices and sessions

3. **Authentication** → Supabase Auth
   - Multi-user support with proper isolation
   - Email/password, social logins, magic links

4. **UI** → SvelteKit + Tailwind
   - Faster, more responsive interface
   - Better mobile experience
   - Real-time updates

### What Stayed the Same

- Core processing logic (`src/legal_portal/services/`)
- AI analysis pipeline
- Document extraction and OCR
- Statute validation and corpus coverage
- Cost calculation

## Testing Strategy

### Unit Tests

Test individual functions and classes:
- Document processors
- Cost calculators
- Statute validators

### Integration Tests

Test complete workflows:
- Document upload → extraction → analysis
- Letter generation with citations
- Cost tracking across services

### API Tests

Test REST endpoints:
- Authentication flows
- CRUD operations
- Error handling
- Response formats

## Troubleshooting

### Backend Issues

1. **Import errors** - Check Python path includes `src/`
2. **Database connection** - Verify Supabase credentials
3. **CORS errors** - Update allowed origins in `main.py`

### Frontend Issues

1. **Build errors** - Clear `.svelte-kit` and rebuild
2. **Auth errors** - Check Supabase URL and keys
3. **API calls fail** - Verify `PUBLIC_API_URL` is correct

### Database Issues

1. **RLS blocks queries** - Check policies in schema
2. **Storage upload fails** - Verify storage bucket exists
3. **Missing tables** - Re-run schema.sql

## Contributing

1. Follow existing code style
2. Write tests for new features
3. Update documentation
4. Run linters before committing

## License

[Your License Here]

