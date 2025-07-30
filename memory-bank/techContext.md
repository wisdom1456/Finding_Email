# Tech Context

## Development Environment

### New Streamlit/FastAPI Stack

#### Frontend Technology
- **Framework**: Streamlit - Python-based web framework for rapid application development
- **Language**: Python 3.12+ - Modern Python with type hints and async support
- **UI Components**: Native Streamlit components with custom styling capabilities
- **Session Management**: Built-in Streamlit session state management

#### Backend Technology
- **Framework**: FastAPI - Modern, fast web framework for building APIs with Python
- **Language**: Python 3.12+ with async/await support
- **API Documentation**: Automatic OpenAPI/Swagger documentation generation
- **Validation**: Pydantic models for request/response validation
- **ASGI Server**: Uvicorn for production-ready async server

#### Key Dependencies (New Stack)
```python
# Backend (FastAPI)
fastapi>=0.104.1          # Modern web framework
uvicorn[standard]>=0.24.0 # ASGI server
pydantic>=2.5.0          # Data validation
openai>=1.3.0            # AI integration
tenacity>=8.2.3          # Retry logic for robust API calls
python-multipart>=0.0.6  # File upload support
python-docx>=1.1.0       # Word document processing
docx2txt>=0.8            # .doc file processing
PyPDF2>=3.0.1           # PDF processing
python-magic>=0.4.27     # File type detection
email>=6.0.0            # Email handling

# Frontend (Streamlit)
streamlit>=1.28.0        # Web application framework
streamlit-aggrid>=0.3.4  # Enhanced data grids
```

### Legacy TypeScript/n8n Stack (Historical Reference)
- **Build Tool**: Vite 5.0.10 - Modern build tool with fast HMR and optimized production builds
- **Language**: TypeScript 5.3.3 - Strict typing for better code quality and maintainability
- **Module System**: ES2020 modules with bundler resolution
- **Package Manager**: npm (compatible with Node.js ecosystem)
- **Workflow Engine**: n8n - Visual workflow automation platform

## File Structure

### New Streamlit/FastAPI Structure
```
/
├── app.py                 # Main Streamlit application entry point
├── backend/               # FastAPI backend services
│   ├── main.py           # FastAPI application entry point
│   ├── services/         # Business logic services
│   │   ├── document_processor.py
│   │   ├── ai_analyzer.py
│   │   └── email_generator.py
│   ├── utils/            # Utility modules
│   │   ├── validators.py
│   │   ├── data_models.py
│   │   └── config.py
│   ├── requirements.txt  # Python dependencies
│   └── .env             # Environment configuration
├── components/           # Streamlit component modules
│   ├── file_uploader.py
│   ├── progress_tracker.py
│   └── results_display.py
├── assets/              # Static assets and templates
│   ├── styles.css
│   └── templates/
├── memory-bank/         # Project documentation
└── samples/            # Sample documents for testing
```

### Legacy TypeScript Structure (Historical Reference)
```
src/
├── components/         # Reusable UI components
├── assets/            # Static assets
├── index.html         # Main HTML entry point
├── main.ts            # TypeScript application entry point
├── package.json       # Dependencies and scripts
├── tsconfig.json      # TypeScript configuration
└── vite.config.ts     # Vite build configuration
```

## Deployment

### New Streamlit/FastAPI Deployment

#### Backend Deployment (Railway)
- **Platform**: Railway - Modern cloud platform for backend services
- **Runtime**: Python 3.12+ with FastAPI and Uvicorn
- **Environment**: Production-ready with environment variable management
- **Database**: Optional PostgreSQL integration for future enhancements
- **API Documentation**: Automatic Swagger/OpenAPI documentation at `/docs`

#### Frontend Deployment Options
- **Option 1**: Streamlit Cloud - Official Streamlit hosting platform
- **Option 2**: Railway - Combined frontend/backend deployment
- **Option 3**: Docker containerization for flexible deployment

#### Development Environment
```bash
# Backend development
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend development
streamlit run app.py --server.port 8501
```

#### Environment Configuration
```env
# Backend (.env)
OPENAI_API_KEY=your_openai_key
PDFCO_API_KEY=your_pdfco_key
RAILWAY_STATIC_URL=your_backend_url
CORS_ORIGINS=["http://localhost:8501", "https://your-streamlit-app.com"]
```

### Legacy Deployment (Historical Reference)
- **Platform**: Kinsta - Static site hosting
- **Build Output**: Vite-generated `dist/` directory
- **Frontend**: TypeScript/HTML static files
- **Backend**: n8n workflow automation platform