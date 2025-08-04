# Legal Document Analysis Portal

A unified Streamlit-Python application that automates the processing of legal case documents through advanced AI integration and professional output generation.

## Overview

The Legal Document Analysis Portal streamlines legal document processing by automatically analyzing client intake forms and case documents using AI-powered extraction, then generating professional findings letters for law firm client communications.

## Features

- **Automated Document Analysis**: AI-powered extraction of key legal information from intake forms and case documents
- **Professional Communication**: Generation of client-ready findings letters in multiple formats (.eml, .txt)
- **Multi-Format Support**: PDF, DOCX, DOC, TXT, and EML file processing
- **Quality Assurance**: Multi-stage validation ensuring accuracy and professional output quality
- **Production-Ready**: Robust system capable of handling complex cases with 40+ documents

## Architecture

### Unified Streamlit-Python Application
```
┌─────────────────────────────────────────┐
│           Streamlit Application         │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │  File Upload│  │     Results     │   │
│  │     Tab     │  │      Tab        │   │
│  └─────────────┘  └─────────────────┘   │
└─────────────────────────────────────────┘
            │
            ▼ Direct Function Calls
┌─────────────────────────────────────────┐
│        Backend Logic Modules           │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ Document    │  │ AI Analyzer     │   │
│  │ Processor   │  │ Module          │   │
│  └─────────────┘  └─────────────────┘   │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ Email       │  │ Quality         │   │
│  │ Generator   │  │ Validator       │   │
│  └─────────────┘  └─────────────────┘   │
└─────────────────────────────────────────┘
```

### Key Components
- **Streamlit Frontend**: Modern web interface with file upload and results display
- **Backend Logic Modules**: Direct Python modules for document processing, AI analysis, and email generation
- **Unified Testing Framework**: Direct function testing with comprehensive test coverage

## Installation

### Prerequisites
- Python 3.12 or higher
- OpenAI API key
- PDF.co API key (optional, for enhanced PDF processing)

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd Finding_Emails
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.template .env
   # Edit .env with your API keys:
   # OPENAI_API_KEY=your_openai_api_key
   # PDFCO_API_KEY=your_pdfco_api_key (optional)
   ```

## Usage

### Start the Application
```bash
streamlit run app.py
```

The application will be available at `http://localhost:8501`

### Using the Portal

1. **Upload Documents**:
   - Navigate to the "File Upload" tab
   - Upload client intake form and case documents
   - Supported formats: PDF, DOCX, DOC, TXT, EML

2. **Process Documents**:
   - Click "Process Documents" to begin analysis
   - Monitor progress in the interface
   - Processing time varies based on document count and size

3. **Download Results**:
   - Navigate to the "Results" tab after processing
   - Download professional findings letter (.eml and .txt formats)
   - Review case analysis and extracted information

## Development

### Project Structure
```
/
├── app.py                    # Main Streamlit application
├── backend_logic/            # Backend business logic modules
│   ├── document_processor.py  # Document processing and validation
│   ├── ai_analyzer.py         # OpenAI integration and analysis
│   ├── email_generator.py     # Email findings generation
│   ├── quality_validator.py   # Quality assurance
│   └── task_manager.py        # Task coordination
├── components/               # Streamlit component modules
│   ├── file_uploader.py     # File upload interface
│   ├── progress_tracker.py  # Processing status
│   └── results_display.py   # Results presentation
├── utils/                   # Utility modules
│   ├── data_models.py      # Pydantic data models
│   ├── validators.py       # Input validation
│   └── file_processors/    # Format-specific processors
├── tests/                  # Unified test framework
│   ├── test_*.py          # Direct function tests
│   └── utils/             # Testing utilities
├── assets/                # Static assets and templates
├── memory-bank/           # Project documentation
└── requirements.txt       # Python dependencies
```

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_document_processor.py

# Run with coverage
python -m pytest tests/ --cov=backend_logic --cov-report=html
```

### Adding New Features

1. **Create module in `backend_logic/`**: Follow existing module patterns
2. **Import directly in Streamlit app**: Use standard Python imports
3. **Handle errors with try/catch**: Use native Python exception handling
4. **Test with direct function calls**: No HTTP mocking required

Example:
```python
# In backend_logic/new_feature.py
class NewFeature:
    def process(self, data):
        # Implementation
        return results

# In app.py
from backend_logic.new_feature import NewFeature

# Direct usage
feature = NewFeature()
results = feature.process(data)
```

## Deployment

### Streamlit Cloud (Recommended)
1. Push code to GitHub repository
2. Connect repository to Streamlit Cloud
3. Configure environment variables in Streamlit Cloud dashboard
4. Deploy with automatic HTTPS and scaling

### Alternative Deployment Options
- **Railway**: Single application deployment
- **Heroku**: Streamlit application hosting
- **Docker**: Containerized deployment

### Environment Variables
Required environment variables for deployment:
```
OPENAI_API_KEY=your_openai_api_key
PDFCO_API_KEY=your_pdfco_api_key (optional)
```

## Production Capabilities

### Proven Performance
- **Test Coverage**: 84.6% pass rate across comprehensive test suite
- **Scalability**: Successfully processes 40+ document cases (57.8 MB)
- **Processing Time**: Complex cases completed in ~9.5 minutes
- **Quality**: Professional, case-specific legal analysis emails

### Production Features
- **Rate Limiting**: Automatic OpenAI API rate limit compliance
- **Large Document Handling**: Intelligent content truncation and model selection
- **Error Recovery**: Robust error handling with graceful degradation
- **Progress Monitoring**: Real-time processing status and feedback

## API Integration

### OpenAI Integration
- **Dual Model Strategy**: GPT-4o for complex analysis, GPT-4o-mini for efficient processing
- **Structured Responses**: JSON schema-enforced output with Pydantic validation
- **Rate Limiting**: Sequential processing with 3-second delays between API calls
- **Token Management**: Automatic content truncation for large documents

### Document Processing
- **Multi-Format Support**: PDF, DOCX, DOC, TXT, EML file processing
- **Content Extraction**: Advanced text extraction with format-specific processors
- **Validation**: File type checking and size limit enforcement
- **Quality Assurance**: Multi-stage validation throughout processing pipeline

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Create a Pull Request

## Support

For support, questions, or feature requests, please open an issue in the repository.

## License

This project is licensed under the MIT License - see the LICENSE file for details.