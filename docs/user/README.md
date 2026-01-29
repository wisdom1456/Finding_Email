# Legal Document Analysis Portal - User Guide

A modern **SvelteKit and FastAPI application** deployed on **Vercel** that automates the processing of legal case documents through advanced AI integration and professional output generation. The portal uses a multi-model AI architecture for optimal speed and quality.

## 🚀 Key Features

### Core Capabilities
- **Automated Document Analysis**: AI-powered extraction of key legal information from intake forms and case documents
- **Professional Output Generation**: Client-ready findings emails with verified statute citations
- **Multi-Format Support**: Process PDF, DOCX, images (with OCR), CSV, TXT, EML, and HTML files
- **Clio Integration**: Direct import of matters, documents, and communications from Clio
- **Verified Legal Corpus**: 51 Florida statutes + 42 New Mexico statutes prevent AI hallucination

### AI Architecture
- **GPT-4o**: Fast document extraction and OCR (0.5s latency)
- **GPT-4o-mini**: Quick legal issue identification
- **GPT-4.1**: High-quality multi-stage case analysis
- **GPT-5.2**: Professional letter generation with reasoning
- **Multi-model optimization**: Each task uses the best model for speed and quality

### User Experience
- **Real-time Progress**: Server-Sent Events (SSE) streaming for live updates
- **Intuitive Interface**: Modern SvelteKit 2 frontend with Svelte 5 Runes
- **Case Management**: Organize and track unlimited cases
- **Statute Validation**: Every citation verified against legal corpus

## 🏗️ Architecture

**Modern Full-Stack Application with Serverless Deployment**

```
┌─────────────────────────────────────────┐
│      SvelteKit Frontend (Vercel)        │
│   • Modern Svelte 5 + TypeScript        │
│   • Real-time SSE progress updates      │
│   • Tailwind CSS styling                │
└─────────────────────────────────────────┘
                    │
                    ↓ (REST API + SSE)
┌─────────────────────────────────────────┐
│   FastAPI Backend (Vercel Serverless)   │
│   • api/index.py (Vercel entry point)   │
│   • SSE streaming for progress          │
│   • JWT authentication via Supabase     │
└─────────────────────────────────────────┘
                    │
    ┌───────────────┴───────────────┐
    │      Service Layer            │
    ├────────────────────────────────┤
    │ • multi_stage_analyzer.py     │
    │ • json_processing_service.py  │
    │ • statute_services/           │
    │ • file_processors/            │
    └────────────────────────────────┘
                    │
    ┌───────────────┴───────────────┐
    │    External Services          │
    ├────────────────────────────────┤
    │ • OpenAI (GPT-4.1, 4o, 5.2)   │
    │ • Supabase (PostgreSQL + Auth)│
    │ • Clio API (OAuth integration)│
    └────────────────────────────────┘
```

## 📁 Project Structure

```
Finding_Emails/
├── frontend/                    # SvelteKit frontend
│   ├── src/
│   │   ├── lib/                # Shared components & utilities
│   │   │   ├── components/     # Svelte UI components
│   │   │   ├── stores/         # State management
│   │   │   └── utils/          # Frontend utilities
│   │   └── routes/             # SvelteKit routes
│   │       ├── app/            # Main application routes
│   │       │   ├── cases/      # Case management
│   │       │   ├── help/       # Help documentation
│   │       │   └── settings/   # User settings
│   │       ├── login/          # Authentication
│   │       └── register/       # User registration
│   └── package.json
├── src/legal_portal/           # Python backend
│   ├── api/                    # FastAPI routes
│   │   ├── main.py            # FastAPI app entry
│   │   └── routes/            # API endpoints
│   ├── services/              # Service layer
│   │   ├── multi_stage_analyzer.py
│   │   ├── json_processing_service.py
│   │   ├── statute_services/
│   │   └── file_processors/
│   ├── core/                  # Business logic & data models
│   └── utils/                 # Utilities
│       ├── openai_client.py
│       └── token_manager.py
├── api/                       # Vercel serverless entry
│   └── index.py              # Vercel backend entry point
├── florida_legal_corpus/     # Florida statute corpus (51 statutes)
├── new_mexico_legal_corpus/  # New Mexico statute corpus (42 statutes)
├── docs/                     # Documentation
│   ├── user/                 # User guides
│   └── developer/            # Developer docs
├── requirements.txt          # Python dependencies (local)
├── api/requirements.txt      # Python dependencies (Vercel)
└── vercel.json              # Vercel configuration
```

## 🚀 Getting Started

### For Users
This application is deployed and accessible at your organization's URL. Simply:

1. **Create an account** or log in with your credentials
2. **Create a new case** from the Dashboard
3. **Upload documents** - drag and drop your case files
4. **Start analysis** and watch real-time progress
5. **Review and generate** your findings email

See the [Help & Documentation](#-help--documentation) section below for detailed guides.

### For Developers

**Prerequisites:**
- Python 3.11+ (backend)
- Node.js 20+ (frontend)
- Supabase account
- OpenAI API key
- Optional: Clio API credentials

**Quick Start:**
```bash
# Backend
pip install -r requirements.txt
cd src && uvicorn legal_portal.api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

The frontend will be at `http://localhost:5173`, backend at `http://localhost:8000`.

For production deployment instructions, see [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md).

## ⚙️ Configuration

### Required Environment Variables

**Backend (.env in project root):**
```env
# OpenAI Configuration (Required)
OPENAI_API_KEY=sk-proj-xxxxx

# Supabase Configuration (Required)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=xxxxx
SUPABASE_ANON_KEY=xxxxx

# Clio Integration (Optional)
CLIO_CLIENT_ID=xxxxx
CLIO_CLIENT_SECRET=xxxxx

# Application Settings
LOG_LEVEL=INFO
ENVIRONMENT=development
```

**Frontend (frontend/.env):**
```env
PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
PUBLIC_SUPABASE_ANON_KEY=xxxxx
PUBLIC_API_URL=http://localhost:8000  # For local development
```

## 🚀 Deployment

This project is deployed on **Vercel**:

- **Frontend**: SvelteKit with Vercel adapter
- **Backend**: FastAPI as Vercel serverless function (`api/index.py`)

### Deployment Process
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy to production
vercel --prod
```

### Environment Variables in Vercel
Configure these in the Vercel dashboard (Settings → Environment Variables):
- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_ANON_KEY`
- `CLIO_CLIENT_ID` (optional)
- `CLIO_CLIENT_SECRET` (optional)

For detailed deployment instructions, see [VERCEL_DEPLOYMENT_INSTRUCTIONS.md](../VERCEL_DEPLOYMENT_INSTRUCTIONS.md).

## 📊 Performance Characteristics

| Operation | Model | Typical Speed | Notes |
|-----------|-------|---------------|-------|
| **Document Extraction** | GPT-4o | 0.5s per document | Fast extraction, supports OCR |
| **Legal Issue ID** | GPT-4o-mini | 0.5s | Quick classification |
| **Multi-Stage Analysis** | GPT-4.1 | 0.5s | Quality synthesis without reasoning overhead |
| **Letter Generation** | GPT-5.2 | 30-60s | Professional output with reasoning |
| **Total Case Analysis** | Multi-model | 2-5 minutes | Depends on document count |

## 🔒 Security Features

- **Supabase Authentication**: JWT-based secure user authentication
- **Row Level Security**: Database-level access control ensures users only see their data
- **File Upload Security**: Size limits (50MB), format validation, secure storage
- **Input Validation**: Comprehensive validation on all user inputs
- **API Security**: Rate limiting and token management
- **Environment-based Secrets**: No hardcoded credentials in code

## 🧪 Testing (For Developers)

**Backend Tests:**
```bash
pytest tests/
pytest tests/ --cov=src/legal_portal  # With coverage
```

**Frontend Tests:**
```bash
cd frontend
npm run test        # Unit tests
npm run test:e2e    # E2E with Playwright
```

**Corpus Validation:**
```bash
cd florida_legal_corpus && python validate_corpus.py
cd new_mexico_legal_corpus && python validate_corpus.py
```

## 📚 Help & Documentation

### In-App Help
Access comprehensive help documentation within the application:
- Click **"Help"** in the navigation menu
- Browse Getting Started, Features & Guides, and FAQ sections
- Step-by-step tutorials for all features

### Additional Documentation
- [FUNCTIONALITY.md](../../FUNCTIONALITY.md) - Complete feature overview and value proposition
- [Auto-Fill Legal Issue Guide](AUTO_FILL_LEGAL_ISSUE_USER_GUIDE.md) - How AI identifies legal issues
- [Vercel Deployment Guide](../VERCEL_DEPLOYMENT_INSTRUCTIONS.md) - Production deployment
- [Florida Legal Corpus](../../florida_legal_corpus/README.md) - 51 verified statutes
- [New Mexico Legal Corpus](../../new_mexico_legal_corpus/README.md) - 42 verified statutes

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guide
- Use type hints for all functions
- Write tests for new features
- Update documentation as needed
- Use structured logging with `loguru`

## 📈 Roadmap

### Current Version (v2.0)
- ✅ Streamlit monolithic architecture
- ✅ 14.3x performance improvement
- ✅ Comprehensive security implementation
- ✅ Service-oriented internal design

### Upcoming (v3.0)
- [ ] End-to-end encryption
- [ ] Multi-factor authentication
- [ ] Advanced threat detection
- [ ] Distributed processing support

### Future (v4.0)
- [ ] Microservices architecture
- [ ] Kubernetes deployment
- [ ] GraphQL API
- [ ] Real-time collaboration

## 📄 License

This project is proprietary software. All rights reserved.

## 🆘 Support

### Getting Help
1. **In-App Help**: Click "Help" in the navigation menu for comprehensive guides
2. **System Administrator**: Contact your organization's admin for account or access issues
3. **IT Support**: Report technical issues to your IT support team

### Feedback & Feature Requests
Contact your administrator who can relay feedback to the development team.

---

## 🎯 Current Status

- **Architecture**: ✅ Modern SvelteKit + FastAPI on Vercel
- **AI Models**: ✅ Multi-model architecture (GPT-4.1, 4o, 5.2)
- **Legal Corpus**: ✅ 51 Florida + 42 New Mexico statutes verified
- **Clio Integration**: ✅ OAuth-based matter import
- **Production**: ✅ Deployed and operational

---

**Last Updated**: January 21, 2026  
**Version**: 3.0.0  
**Status**: ✅ Production Ready
# Product Overview

## Why This Application Exists

The **Legal Document Analysis Portal** addresses the time-consuming challenges law firms face in case intake and document analysis. Legal professionals traditionally spend hours manually reviewing documents, extracting facts, researching statutes, and drafting findings emails.

### Key Problems Solved

#### Time Efficiency
- **Automated Analysis**: What takes 3-5 hours manually now takes 5-10 minutes with AI assistance
- **Quick Turnaround**: Clients receive professional findings emails in minutes, not days
- **Batch Processing**: Handle multiple documents simultaneously

#### Quality & Consistency
- **Verified Citations**: 51 Florida + 42 New Mexico statutes prevent AI hallucination
- **Professional Output**: Attorney-quality letters with proper structure and citations
- **Standardized Analysis**: Consistent quality across all cases and staff

#### Workflow Integration
- **Clio Integration**: Import matters and documents directly from your practice management system
- **Real-time Updates**: Watch analysis progress in real-time via SSE streaming
- **Case Management**: Organize and access all case analyses in one place

## How It Works

### Simple 5-Step Process

1. **Create Case**: Enter client name and optional reference number
2. **Upload Documents**: Drag and drop intake forms and supporting documents (PDF, DOCX, images, etc.)
3. **AI Analysis**: Multi-stage AI processing extracts facts, identifies issues, validates statutes
4. **Review Results**: Verify AI findings, check citations, make any needed adjustments
5. **Generate Email**: Professional findings email ready for client delivery

### Multi-Stage AI Analysis Pipeline

The system uses specialized AI models for different tasks:

1. **Document Extraction** (GPT-4o): Fast text extraction including OCR for scanned documents
2. **Legal Issue Identification** (GPT-4o-mini): Auto-selects most likely practice area from 30+ options
3. **Fact Matrix** (GPT-4.1): Structured extraction of parties, timeline, financial items, key documents
4. **Legal Analysis** (GPT-4.1): Comprehensive analysis applying relevant statutes to case facts
5. **Email Generation** (GPT-5.2): Professional findings email with proper citations and structure

## Target Users & Benefits

### Primary Users
**Attorneys, Paralegals, and Legal Assistants** handling case intake and initial document analysis

### Key Benefits

#### Time Savings
- **80% reduction** in initial case assessment time (3-5 hours → 5-10 minutes)
- **Instant legal issue identification** from intake forms
- **Parallel document processing** for faster results

#### Quality & Accuracy
- **Verified statute citations** from legal corpus (51 FL + 42 NM statutes)
- **Professional formatting** ready for client delivery
- **Consistent analysis** across all cases

#### Easy to Use
- **No training required** - intuitive drag-and-drop interface
- **Real-time progress** - watch analysis happen via SSE streaming
- **In-app help** - comprehensive documentation built-in

#### Workflow Integration
- **Clio integration** - import matters with one click
- **Case management** - organize and track all analyses
- **Flexible exports** - HTML letters for further editing## Supported Practice Areas

This application is optimized for **Florida and New Mexico civil litigation** matters.

### Florida Coverage (51 statutes)
- **Consumer Protection** (FDUTPA, UCC) - 6 statutes at 100% coverage
- **Landlord-Tenant** (Ch. 83) - 12 statutes at 100% coverage
- **Construction Defects** (Ch. 558) - 6 statutes at 100% coverage
- **Mechanic's Liens** (Ch. 713) - 7 statutes at 100% coverage
- **Foreclosure Defense** (Ch. 702)
- **Property Insurance Claims** (Ch. 627)
- **Personal Injury & Damages** (Ch. 768)
- **Civil Litigation** (Statutes of Limitation, Attorney Fees)

### New Mexico Coverage (42 statutes + 8 rules)
- **Consumer Protection** (Unfair Practices Act - Ch. 57-12)
- **Landlord-Tenant** (UORRA - Ch. 47-8)
- **Construction & Liens** (Ch. 56-7, Ch. 48-2)
- **Foreclosure** (Ch. 48-7, Ch. 39-5)
- **Insurance & Torts** (Ch. 59A-16, Ch. 41-3A)
- **Civil Procedure Rules** (NMRA)

### Not Supported
❌ Federal claims or federal court matters  
❌ Criminal law  
❌ Immigration law  
❌ Bankruptcy (federal jurisdiction)  
❌ Patent/trademark law (federal jurisdiction)