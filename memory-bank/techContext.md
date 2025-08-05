# Tech Context

## Development Environment

### Unified Streamlit-Python Stack

#### Frontend Technology
- **Framework**: Streamlit - Python-based web framework for rapid application development
- **Language**: Python 3.12+ - Modern Python with type hints and async support
- **UI Components**: Native Streamlit components with custom styling capabilities
- **Session Management**: Built-in Streamlit session state management

#### Backend Technology
- **Architecture**: Direct Python modules integrated with Streamlit application
- **Language**: Python 3.12+ with standard library and third-party modules
- **Data Models**: Pydantic models for data validation and structure
- **Processing**: Direct function calls for immediate processing and response

#### Key Dependencies (Unified Stack)
```python
# Frontend Framework
streamlit>=1.28.0        # Web application framework

# HTTP Client and API Integration
requests>=2.31.0         # HTTP client for external APIs
openai>=1.3.0           # AI integration

# Configuration Management
python-dotenv>=1.0.0    # Environment variable loading
pydantic-settings>=2.0.0 # Settings management
PyYAML>=6.0             # YAML configuration files

# Document Processing Libraries
python-docx>=1.1.0      # Word document processing
docx2txt>=0.8           # .doc file processing
PyPDF2>=3.0.1          # PDF processing
PyMuPDF>=1.23.0         # Advanced PDF processing
python-magic>=0.4.27    # File type detection
weasyprint>=60.0        # HTML to PDF conversion
pyth>=0.7.0             # RTF processing

# Image Processing and OCR
Pillow>=10.0.0          # Image processing
pytesseract>=0.3.10     # OCR capabilities

# Audio and Video Processing - Production Validated
google-cloud-storage>=2.10.0        # Google Cloud Storage for temporary video file handling
google-cloud-aiplatform>=1.38.0     # Vertex AI integration with Gemini-2.5-flash model
google-cloud-speech>=2.21.0         # Speech-to-Text API for pure audio files
vertexai>=0.0.1                     # Vertex AI Python SDK for generative models
tenacity>=8.2.3                     # Enhanced retry logic for Google Cloud service provisioning
python-magic>=0.4.27                # File type detection for video/audio processing
pydub>=0.25.1                       # Audio manipulation and format conversion

# Criminal Law Video Processing Enhancement
tiktoken>=0.5.1                     # Token counting for criminal video data preservation
# Note: Criminal law capabilities built on existing video processing stack

# Utility Libraries
tenacity>=8.2.3         # Retry logic for robust API calls
```

### Legacy TypeScript/n8n Stack (Historical Reference)
- **Build Tool**: Vite 5.0.10 - Modern build tool with fast HMR and optimized production builds
- **Language**: TypeScript 5.3.3 - Strict typing for better code quality and maintainability
- **Module System**: ES2020 modules with bundler resolution
- **Package Manager**: npm (compatible with Node.js ecosystem)
- **Workflow Engine**: n8n - Visual workflow automation platform

## Python Path Configuration

### Import Resolution for Unified Architecture

With the unified Streamlit-Python architecture, all modules are imported directly within the same application context. The Streamlit application can import backend logic modules using standard Python import statements without complex path manipulation.

### Current Import Pattern

Backend logic modules are imported directly in the Streamlit application:

```python
# Direct imports from backend_logic modules
from backend_logic.document_processor import DocumentProcessor
from backend_logic.ai_analyzer import AIAnalyzer
from backend_logic.email_generator import EmailGenerator
from utils.data_models import CaseData, CaseResults
```

### Benefits of Unified Imports

This approach provides:
1. **Simplified Dependencies**: No complex path resolution needed
2. **Direct Debugging**: Full stack traces and debugging capabilities
3. **Standard Python Patterns**: Uses conventional Python module imports
4. **Development Efficiency**: Single application context for all logic

## File Structure

### Current Unified Streamlit-Python Structure
```
/
├── app.py                 # Main Streamlit application entry point
├── backend_logic/         # Backend business logic modules
│   ├── document_processor.py  # Document processing and validation
│   ├── audio_processor.py     # Audio transcription (OpenAI Whisper)
│   ├── video_processor.py     # Video analysis (Vertex AI)
│   ├── ai_analyzer.py         # OpenAI integration and analysis
│   ├── email_generator.py     # Email findings generation
│   ├── quality_validator.py   # Quality assurance
│   └── task_manager.py        # Task coordination
├── components/            # Streamlit component modules
│   ├── file_uploader.py
│   ├── progress_tracker.py
│   └── results_display.py
├── utils/                # Utility modules
│   ├── data_models.py    # Pydantic data models
│   ├── validators.py     # Input validation
│   └── file_processors/  # Format-specific processors
├── tests/                # Unified test framework
│   ├── test_*.py         # Direct function tests
│   └── utils/            # Testing utilities
├── assets/              # Static assets and templates
│   └── templates/        # Email templates
├── memory-bank/         # Project documentation
├── samples/            # Sample documents for testing
└── requirements.txt    # Consolidated Python dependencies
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

### Unified Streamlit-Python Deployment

#### Streamlit Cloud Deployment
- **Platform**: Streamlit Cloud - Official Streamlit hosting platform
- **Runtime**: Python 3.12+ with unified application stack
- **Environment**: Production-ready with environment variable management
- **Simplicity**: Single application deployment with no backend separation

#### Alternative Deployment Options
- **Option 1**: Railway - Single application deployment
- **Option 2**: Heroku - Streamlit application hosting
- **Option 3**: Docker containerization for flexible deployment

#### Development Environment
```bash
# Unified development
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

#### Environment Configuration
```env
# Application (.env) - Production Validated
OPENAI_API_KEY=your_openai_key
PDFCO_API_KEY=your_pdfco_key

# Google Cloud Configuration - Required for Video Processing
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-file.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_BUCKET_NAME=your-findings-videos-bucket

# Google Cloud Service Setup Requirements (One-time)
# 1. Enable Vertex AI API: https://console.developers.google.com/apis/api/aiplatform.googleapis.com
# 2. Enable Speech-to-Text API: https://console.developers.google.com/apis/api/speech.googleapis.com
# 3. Enable Cloud Storage API: https://console.developers.google.com/apis/api/storage.googleapis.com
# 4. Create service account with roles:
#    - Vertex AI User (roles/aiplatform.user)
#    - Storage Object Admin (roles/storage.objectAdmin)
#    - Speech Service Agent (roles/cloudspeech.serviceAgent)
```

#### Google Cloud Integration Requirements ✅ PRODUCTION-VALIDATED
- **Project Setup**: Google Cloud project with enabled APIs (Vertex AI, Speech-to-Text, Cloud Storage)
- **Service Account**: Properly configured with required IAM roles for video processing
- **Bucket Configuration**: Cloud Storage bucket for temporary video file handling with 24-hour lifecycle
- **Regional Considerations**: Vertex AI initialized with us-central1 region for optimal performance
- **One-time Setup**: Initial Google Cloud service agent provisioning may take 5-10 minutes

### Legacy Deployment (Historical Reference)
- **Platform**: Kinsta - Static site hosting
- **Build Output**: Vite-generated `dist/` directory
- **Frontend**: TypeScript/HTML static files
- **Backend**: n8n workflow automation platform

## Environment Variable Management

### Streamlined Environment Configuration

The unified Streamlit-Python application uses standard Python environment variable loading patterns with the `python-dotenv` library for simplified configuration management.

### Application Startup Pattern

Environment variables are loaded directly within the Streamlit application:

```python
# Standard Python environment loading pattern
from dotenv import load_dotenv
import os

# Load environment variables at application startup
load_dotenv()

# Access environment variables throughout the application
openai_api_key = os.getenv('OPENAI_API_KEY')
pdfco_api_key = os.getenv('PDFCO_API_KEY')
```

### Simplified Deployment

- **Single Application Context**: All environment variables loaded in one place
- **Standard Python Patterns**: Uses conventional `python-dotenv` loading
- **Streamlit Integration**: Environment variables available throughout the Streamlit session
- **Development Simplicity**: No complex startup scripts or server coordination required

### Configuration Benefits

This unified approach provides:
1. **Simplified Setup**: Single `.env` file for all configuration
2. **Development Efficiency**: Standard Python environment variable patterns
3. **Deployment Simplicity**: No complex server startup coordination
4. **Error Prevention**: Direct environment loading with clear error messages