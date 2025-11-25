# Legal Document Analysis Portal

A modern full-stack application for analyzing legal documents and generating professional findings letters, built with SvelteKit and FastAPI.

## 📚 Documentation

For comprehensive documentation, see the [Documentation Index](docs/README.md).

## 🚀 Quick Start

### Prerequisites

1. **Node.js 20+** (for frontend)

   ```bash
   node --version  # Should be 20 or higher
   ```

2. **Python 3.11+** (for backend)

   ```bash
   python3 --version  # Should be 3.11 or higher
   ```

3. **System Dependencies** (macOS)

   ```bash
   brew install ghostscript  # Required for PDF compression
   ```

### Environment Setup

```bash
# Copy and configure environment variables
cp .env.template .env
# Edit .env and add your API keys:
# - OPENAI_API_KEY
# - SUPABASE_URL
# - SUPABASE_SERVICE_KEY
# - SUPABASE_ANON_KEY
```

### Installation & Running

#### Backend (FastAPI)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Start the backend server
cd src && uvicorn legal_portal.api.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

#### Frontend (SvelteKit)

```bash
# Install frontend dependencies
cd frontend
npm install

# Start the development server
npm run dev
```

The application will be available at `http://localhost:5173`.

### Production Deployment

The application is deployed on **Vercel**:

- Frontend: SvelteKit with Vercel adapter
- Backend: FastAPI as Vercel serverless function (`/api/index.py`)

```bash
# Deploy to Vercel
vercel --prod
```

## 📋 Features

### Document Processing

- **Multi-format Support**: PDF, DOCX, DOC, CSV, TXT, EML, images (JPG, PNG)
- **Batch Processing**: Process multiple documents simultaneously
- **OCR Support**: Extract text from images using GPT-4o Vision
- **Smart Citation Tracking**: Automatically tracks source documents for citations

### AI-Powered Analysis

- **Document Analysis**: Comprehensive legal document analysis using OpenAI GPT-4o
- **Quality Validation**: Built-in QA service for data quality checks
- **Structured Output**: JSON-based structured data extraction
- **Token Management**: Cost tracking and optimization
- **AI Auto-Fill**: Automatic pre-selection of most likely legal issue

### Clio Integration

- **Matter Import**: Import cases directly from Clio
- **Document Sync**: Automatically import communications and documents
- **OAuth Authentication**: Secure connection to Clio accounts

### Letter Generation

- **Professional Formatting**: Generate attorney-style findings letters
- **Citation Management**: Clean filename citations with document tracking
- **Client-Friendly Output**: Review and edit letters before finalization
- **Multiple Export Formats**: HTML output

### Florida Legal Corpus Integration

- **Citation Validation**: Verify statute citations against 51+ verified Florida statutes
- **Anti-Hallucination**: Prevent AI from generating false or incorrect statute references
- **Statute Recommendations**: AI-powered suggestions for relevant Florida statutes
- **100% Coverage**: Complete coverage in 4 primary practice areas

## ⚖️ Supported Practice Areas

**This application is optimized for Florida civil litigation matters only.**

### Covered Practice Areas

1. **Consumer Protection & Business Misconduct**
   - Contract disputes (UCC Ch. 671-672)
   - Consumer protection violations (FDUTPA - Ch. 501 Part II)
   - Business organization disputes (Ch. 605 LLC, Ch. 607 Corp)

2. **Real Estate & Property Disputes**
   - Landlord-tenant disputes (Ch. 83)
   - Foreclosure defense (Ch. 702)
   - Property damage and insurance claims (Ch. 627)
   - Construction defects (Ch. 558)
   - Mechanic's liens (Ch. 713)

3. **Civil Litigation & Administrative Law**
   - Statutes of limitation (Ch. 95)
   - Administrative procedure matters (Ch. 120)
   - Attorney fees and sanctions (Ch. 57)

4. **Selective Personal Injury**
   - Motorcycle accidents (Ch. 316 traffic law)
   - Limited medical malpractice matters (Ch. 766)

### Important Limitations

⚠️ **Not Supported:**

- Federal claims or federal court matters
- Criminal law
- Immigration law
- Bankruptcy (federal jurisdiction)
- Patent/trademark law (federal jurisdiction)
- Out-of-state matters

## 📁 Project Structure

```text
Finding_Emails/
├── frontend/                  # SvelteKit frontend
│   ├── src/
│   │   ├── lib/              # Shared components & utilities
│   │   │   ├── components/   # Svelte components
│   │   │   ├── stores/       # Svelte stores
│   │   │   └── utils/        # Utility functions
│   │   └── routes/           # SvelteKit routes
│   └── package.json
├── src/
│   └── legal_portal/         # Python backend
│       ├── api/              # FastAPI routes
│       │   ├── main.py       # FastAPI app entry
│       │   └── routes/       # API endpoints
│       ├── core/             # Business logic
│       ├── services/         # Service layer
│       ├── utils/            # Utilities
│       └── config/           # Configuration
├── api/                      # Vercel serverless entry
│   └── index.py
├── florida_legal_corpus/     # Florida statute corpus
├── tests/                    # Test suites
├── scripts/                  # Utility scripts
├── docs/                     # Documentation
├── requirements.txt          # Python dependencies
├── pyproject.toml           # Python project config
└── vercel.json              # Vercel configuration
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# Required - Backend
OPENAI_API_KEY=sk-proj-xxxxx
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=xxxxx
SUPABASE_ANON_KEY=xxxxx

# Required - Frontend (in frontend/.env)
PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
PUBLIC_SUPABASE_ANON_KEY=xxxxx

# Optional - Clio Integration
CLIO_CLIENT_ID=xxxxx
CLIO_CLIENT_SECRET=xxxxx

# Optional
LOG_LEVEL=INFO
ENVIRONMENT=development
```

## 🧪 Testing

### Backend Tests

```bash
# Run Python tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/legal_portal
```

### Frontend Tests

```bash
cd frontend

# Run unit tests
npm run test

# Run E2E tests
npm run test:e2e
```

### Corpus Validation

```bash
cd florida_legal_corpus
python validate_corpus.py
```

## 🏗️ Architecture

### Technology Stack

- **Frontend**: SvelteKit 2, Svelte 5 (Runes), TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python 3.11+, Pydantic
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth
- **AI/ML**: OpenAI GPT-4o, GPT-4o Vision
- **Document Processing**: PyMuPDF, python-docx, Pillow
- **Deployment**: Vercel (frontend + serverless backend)

### Key Design Patterns

- **Service Layer**: Separation of concerns with dedicated services
- **SSE Progress**: Real-time progress updates via Server-Sent Events
- **Svelte 5 Runes**: Modern reactive state management
- **Type Safety**: Full TypeScript frontend, Python type hints

## 🔐 Security

- **Supabase Auth**: JWT-based authentication
- **Row Level Security**: Database-level access control
- **API Key Management**: Environment-based secret management
- **Input Validation**: Comprehensive file and data validation

## 📊 Project Status

### ✅ Completed

- SvelteKit + FastAPI architecture migration
- Supabase authentication integration
- Clio integration with OAuth
- Document processing pipeline
- GPT-4o Vision integration
- Florida Legal Corpus (51 statutes)
- Real-time progress with SSE
- Vercel deployment

### 🔄 In Progress

- Test coverage expansion
- Performance optimization

### 📋 Planned

- Additional document format support
- Enhanced analytics dashboard
- Multi-user workspace support

## 🤝 Contributing

### Development Setup

```bash
# Install all dependencies
pip install -r requirements-dev.txt
cd frontend && npm install

# Run linting
ruff check src/
cd frontend && npm run check

# Run tests
pytest tests/
cd frontend && npm run test
```

### Code Quality

- **Python**: Use `ruff` for linting, type hints throughout
- **TypeScript**: Use `svelte-check` for type checking
- **Testing**: Write tests for new features

## 📝 Recent Changes

### November 2025

- ✅ Migrated to SvelteKit + FastAPI architecture
- ✅ Integrated Supabase authentication
- ✅ Added Clio integration with OAuth
- ✅ Implemented SSE for real-time progress
- ✅ Deployed to Vercel
- ✅ Florida Legal Corpus v2.2 (51 statutes)
- ✅ Technical debt cleanup

## 📄 License

[Add license information here]

## 📞 Support

For issues, questions, or contributions:

1. Check the [documentation](docs/)
2. Review [troubleshooting](#-troubleshooting) section
3. Open an issue in the repository

---

**Last Updated**: November 25, 2025

**Version**: 3.0.0

**Status**: ✅ Production Ready
