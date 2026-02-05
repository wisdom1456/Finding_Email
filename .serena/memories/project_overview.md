# Legal Document Analysis Portal

## Purpose
A full-stack application for legal document analysis that:
- Processes legal documents (PDF, DOCX, images, etc.)
- Extracts key facts using AI (OpenAI GPT-5.2, GPT-5-mini, GPT-4.1)
- Validates citations against Florida and New Mexico legal corpus
- Generates professional findings emails and demand letters
- Integrates with Clio for matter management

## Tech Stack
- **Frontend**: SvelteKit 2, Svelte 5 (Runes), TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python 3.11+, Pydantic
- **Database**: Supabase (PostgreSQL)
- **AI/ML**: OpenAI GPT-5.2, GPT-5-mini, GPT-4.1, GPT-4o Vision
- **Document Processing**: PyMuPDF, python-docx, Pillow
- **Deployment**: Vercel (frontend + serverless backend)

## Project Structure
```
Finding_Emails/
├── frontend/          # SvelteKit frontend
├── src/legal_portal/  # Python backend
│   ├── api/          # FastAPI routes
│   ├── core/         # Business logic
│   ├── services/     # Service layer
│   └── utils/        # Utilities
├── api/              # Vercel serverless entry
├── florida_legal_corpus/    # Florida statutes
├── new_mexico_legal_corpus/ # New Mexico statutes
├── tests/            # Test suites
└── docs/             # Documentation
```
