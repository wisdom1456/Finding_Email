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

## Python Path Configuration

### ModuleNotFoundError Resolution

When running the FastAPI backend using `uvicorn` from the `backend` directory, Python encounters a `ModuleNotFoundError` because the application's root directory is not in Python's system path. This prevents Python from correctly importing the `backend` module and its sub-modules.

### Solution Implementation

The issue is resolved in `backend/main.py` with the following code that must be executed before any other imports:

```python
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

### How It Works

This code adds the project's root directory to Python's system path by:
1. Getting the absolute path of the current file (`backend/main.py`)
2. Getting the parent directory (`backend/`)
3. Getting the parent of that directory (project root `/`)
4. Appending this root directory to `sys.path`

This ensures that when `uvicorn` runs from the `backend` directory, Python can correctly resolve imports like `from backend.services import email_generator` by finding the `backend` module in the project root.

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

## Environment Variable Management

### Critical Requirement: Environment Variable Loading

The backend FastAPI server will fail to start with a `ValidationError` if environment variables from the `.env` file are not properly loaded before the application initializes. This is a critical technical requirement that must be addressed at the startup level.

### Start Script Implementation

The `start_servers.sh` script is now responsible for explicitly loading environment variables **before** executing `uvicorn`. This ensures that all required configurations are available to the application at runtime:

```bash
# Load environment variables from .env file
set -a  # automatically export all variables
source .env
set +a  # disable automatic export

# Start the backend server with environment variables loaded
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Why This Approach is Required

- **API Key Availability**: Ensures that `OPENAI_API_KEY`, `PDFCO_API_KEY`, and other critical API keys are available when the FastAPI application initializes
- **Configuration Loading**: Makes all environment-specific configurations accessible to Pydantic settings validation
- **Validation Prevention**: Prevents `ValidationError` exceptions that occur when required environment variables are missing during application startup
- **Runtime Reliability**: Guarantees that the application has access to all necessary configurations before processing any requests

### Technical Implementation Notes

This environment variable loading mechanism is the **required method** for ensuring proper application initialization. Alternative approaches (such as loading environment variables within the Python application itself) have proven insufficient for this particular deployment configuration.
```