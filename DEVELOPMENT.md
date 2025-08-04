# Development Guide

## Development Environment Setup

### Prerequisites
- Python 3.8+ (tested with Python 3.9-3.11)
- Git for version control
- Code editor with Python support (VS Code recommended)

### Initial Setup
```bash
# Clone the repository
git clone <repository-url>
cd legal-document-analysis-portal

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment configuration
cp .env.example .env
# Edit .env with your API keys
```

### Environment Variables
```bash
# Required API Keys
OPENAI_API_KEY=your_openai_api_key
PDFCO_API_KEY=your_pdfco_api_key

# Optional Configuration
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_HEADLESS=true
LOG_LEVEL=INFO
```

## Development Workflow

### Unified Architecture Principles
The application follows a unified Streamlit-Python architecture with these key principles:

1. **Direct Function Calls**: No HTTP APIs between components
2. **Standard Python Imports**: Conventional module organization
3. **Session State Management**: Streamlit session state for application state
4. **Memory-Only Processing**: No persistent storage of sensitive data

### Development Patterns

#### Module Organization
```python
# Standard import pattern for backend logic
from backend_logic.document_processor import DocumentProcessor
from backend_logic.ai_analyzer import AIAnalyzer
from backend_logic.email_generator import EmailGenerator

# Utility imports
from utils.data_models import CaseData, CaseResults
from utils.validators import validate_file_upload
```

#### Error Handling Pattern
```python
# Direct exception handling in Streamlit
def process_with_error_handling():
    try:
        # Processing logic
        result = process_documents(files)
        st.session_state.results = result
        st.success("Processing completed successfully!")
        
    except OpenAIError as e:
        st.error(f"AI analysis failed: {e}")
        logger.error(f"OpenAI error: {e}")
        
    except ValidationError as e:
        st.error(f"Data validation failed: {e}")
        logger.warning(f"Validation error: {e}")
        
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        logger.exception("Unexpected error in processing")
```

#### Session State Management
```python
# Initialize session state
def init_session_state():
    if 'processing_state' not in st.session_state:
        st.session_state.processing_state = 'idle'
    if 'case_data' not in st.session_state:
        st.session_state.case_data = None
    if 'results' not in st.session_state:
        st.session_state.results = None

# Access session state
def get_current_case():
    return st.session_state.get('case_data')

# Update session state
def update_processing_state(state: str):
    st.session_state.processing_state = state
    st.rerun()  # Trigger UI update
```

## Code Structure Guidelines

### Directory Organization

#### Frontend Components (`app.py` and `components/`)
```python
# app.py - Main application orchestration
def main():
    st.set_page_config(page_title="Legal Document Analysis")
    init_session_state()
    
    # Component coordination
    if st.session_state.processing_state == 'upload':
        display_upload_interface()
    elif st.session_state.processing_state == 'processing':
        display_processing_status()
    elif st.session_state.processing_state == 'results':
        display_results_interface()

# components/ - Reusable UI components
class FileUploader:
    def __init__(self):
        self.validator = FileValidator()
    
    def display(self) -> Optional[List[UploadedFile]]:
        # Upload interface implementation
        pass
```

#### Backend Logic (`backend_logic/`)
```python
# backend_logic/document_processor.py
class DocumentProcessor:
    def __init__(self):
        self.file_processors = {
            '.pdf': PDFProcessor(),
            '.docx': DOCXProcessor(),
            '.txt': TXTProcessor(),
            '.eml': EMLProcessor()
        }
    
    def process_documents(self, files: List[UploadedFile]) -> List[ProcessedDocument]:
        """Process multiple uploaded files"""
        processed = []
        for file in files:
            processor = self._get_processor(file.name)
            content = processor.extract_content(file)
            processed.append(ProcessedDocument(
                file_name=file.name,
                content=content,
                file_type=file.type,
                metadata=processor.extract_metadata(file)
            ))
        return processed
```

#### Utility Modules (`utils/`)
```python
# utils/data_models.py - Pydantic models
class CaseData(BaseModel):
    case_info: Dict[str, Any]
    uploaded_files: List[UploadedFile]
    processing_options: ProcessingOptions
    
    class Config:
        arbitrary_types_allowed = True

# utils/validators.py - Input validation
def validate_file_upload(file: UploadedFile) -> ValidationResult:
    """Validate uploaded file against security and size constraints"""
    if not _is_allowed_file_type(file.name):
        return ValidationResult(valid=False, error="Unsupported file type")
    
    if file.size > MAX_FILE_SIZE:
        return ValidationResult(valid=False, error="File too large")
    
    return ValidationResult(valid=True)
```

### Data Models and Validation

#### Core Data Models
```python
# Input validation models
class ProcessingOptions(BaseModel):
    analysis_depth: Literal['basic', 'detailed', 'comprehensive'] = 'detailed'
    output_format: Literal['email', 'report', 'both'] = 'email'
    include_attachments: bool = True

# Processing models
class ProcessedDocument(BaseModel):
    file_name: str
    content: str
    file_type: str
    metadata: Dict[str, Any]
    processing_timestamp: datetime

# Analysis models
class DocumentAnalysis(BaseModel):
    document_type: str
    key_findings: List[str]
    legal_issues: List[str]
    recommendations: List[str]
    confidence_score: float

# Output models
class EmailResponse(BaseModel):
    eml_content: str
    txt_content: str
    subject: str
    recipient_info: Dict[str, str]
    attachments: List[str] = []
```

#### Validation Patterns
```python
# Custom validators
@validator('confidence_score')
def validate_confidence(cls, v):
    if not 0.0 <= v <= 1.0:
        raise ValueError('Confidence score must be between 0 and 1')
    return v

# Usage in processing
def validate_analysis_result(analysis: DocumentAnalysis) -> None:
    try:
        # Pydantic validation automatically called
        validated = DocumentAnalysis(**analysis.dict())
    except ValidationError as e:
        logger.error(f"Analysis validation failed: {e}")
        raise ProcessingError(f"Invalid analysis result: {e}")
```

## Feature Development

### Adding New File Processors

1. **Create Processor Class**
```python
# utils/file_processors/new_processor.py
class NewFormatProcessor(BaseFileProcessor):
    def extract_content(self, file: UploadedFile) -> str:
        """Extract text content from new format"""
        # Implementation specific to format
        pass
    
    def extract_metadata(self, file: UploadedFile) -> Dict[str, Any]:
        """Extract metadata from new format"""
        pass
    
    def validate_format(self, file: UploadedFile) -> bool:
        """Validate file format integrity"""
        pass
```

2. **Register in Document Processor**
```python
# backend_logic/document_processor.py
def __init__(self):
    self.file_processors = {
        '.pdf': PDFProcessor(),
        '.docx': DOCXProcessor(),
        '.txt': TXTProcessor(),
        '.eml': EMLProcessor(),
        '.new': NewFormatProcessor(),  # Add new processor
    }
```

3. **Update Validation**
```python
# utils/validators.py
ALLOWED_FILE_TYPES = {
    '.pdf', '.docx', '.doc', '.txt', '.eml', '.new'  # Add new type
}
```

### Adding New Analysis Features

1. **Extend Analysis Models**
```python
# utils/data_models.py
class EnhancedAnalysis(DocumentAnalysis):
    new_feature_data: Optional[Dict[str, Any]] = None
    feature_confidence: Optional[float] = None
```

2. **Update AI Analyzer**
```python
# backend_logic/ai_analyzer.py
def analyze_with_new_feature(self, document: ProcessedDocument) -> EnhancedAnalysis:
    """Enhanced analysis with new feature"""
    base_analysis = self.analyze_document(document)
    
    # New feature implementation
    feature_result = self._process_new_feature(document.content)
    
    return EnhancedAnalysis(
        **base_analysis.dict(),
        new_feature_data=feature_result,
        feature_confidence=feature_result.get('confidence', 0.0)
    )
```

3. **Update UI Components**
```python
# components/results_display.py
def display_enhanced_results(self, analysis: EnhancedAnalysis):
    """Display results with new feature data"""
    # Base results display
    self.display_base_results(analysis)
    
    # New feature display
    if analysis.new_feature_data:
        st.subheader("New Feature Results")
        st.json(analysis.new_feature_data)
```

### Adding New UI Components

1. **Create Component Module**
```python
# components/new_component.py
class NewComponent:
    def __init__(self):
        self.state_key = "new_component_state"
    
    def display(self) -> Any:
        """Render component and return user input"""
        with st.container():
            st.subheader("New Component")
            # Component implementation
            return user_input
    
    def get_state(self) -> Dict[str, Any]:
        """Get component state from session"""
        return st.session_state.get(self.state_key, {})
    
    def update_state(self, state: Dict[str, Any]) -> None:
        """Update component state"""
        st.session_state[self.state_key] = state
```

2. **Integrate in Main App**
```python
# app.py
from components.new_component import NewComponent

def main():
    # Initialize components
    new_component = NewComponent()
    
    # Display in appropriate workflow step
    if st.session_state.processing_state == 'new_step':
        result = new_component.display()
        if result:
            # Process component result
            handle_new_component_result(result)
```

## Testing Framework

### Direct Function Testing Pattern
```python
# tests/test_document_processor.py
import pytest
from backend_logic.document_processor import DocumentProcessor
from utils.data_models import ProcessedDocument

class TestDocumentProcessor:
    def setup_method(self):
        """Setup for each test method"""
        self.processor = DocumentProcessor()
    
    def test_pdf_processing(self):
        """Test PDF document processing"""
        # Load test file
        with open('samples/test_document.pdf', 'rb') as f:
            file_content = f.read()
        
        # Create mock uploaded file
        mock_file = MockUploadedFile(
            name='test_document.pdf',
            content=file_content,
            content_type='application/pdf'
        )
        
        # Process document
        result = self.processor.process_documents([mock_file])
        
        # Assertions
        assert len(result) == 1
        assert isinstance(result[0], ProcessedDocument)
        assert result[0].file_name == 'test_document.pdf'
        assert len(result[0].content) > 0
    
    def test_validation_error_handling(self):
        """Test handling of invalid files"""
        mock_file = MockUploadedFile(
            name='invalid.xyz',
            content=b'invalid content',
            content_type='application/octet-stream'
        )
        
        with pytest.raises(ValidationError):
            self.processor.process_documents([mock_file])
```

### Integration Testing
```python
# tests/test_integration.py
def test_complete_processing_pipeline():
    """Test complete document processing pipeline"""
    # Setup test data
    case_data = CaseData(
        case_info={'client_name': 'Test Client'},
        uploaded_files=[load_test_file('sample_legal_doc.pdf')],
        processing_options=ProcessingOptions()
    )
    
    # Initialize processors
    doc_processor = DocumentProcessor()
    ai_analyzer = AIAnalyzer()
    email_generator = EmailGenerator()
    
    # Process pipeline
    processed_docs = doc_processor.process_documents(case_data.uploaded_files)
    analysis = ai_analyzer.analyze_case(processed_docs)
    email = email_generator.generate_findings(analysis)
    
    # Validate results
    assert isinstance(analysis, CaseAnalysis)
    assert isinstance(email, EmailResponse)
    assert len(email.eml_content) > 0
    assert email.subject
```

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_document_processor.py

# Run with coverage
python -m pytest tests/ --cov=backend_logic --cov=utils

# Run integration tests only
python -m pytest tests/test_integration.py -v
```

## Error Handling Guidelines

### Exception Hierarchy
```python
# Custom exception classes
class ProcessingError(Exception):
    """Base exception for processing errors"""
    pass

class ValidationError(ProcessingError):
    """Raised when data validation fails"""
    pass

class APIError(ProcessingError):
    """Raised when external API calls fail"""
    pass

class OpenAIError(APIError):
    """Specific to OpenAI API issues"""
    pass

class FileProcessingError(ProcessingError):
    """Raised when file processing fails"""
    pass
```

### Error Handling Patterns

#### At Component Level
```python
# components/file_uploader.py
def process_upload(self, files: List[UploadedFile]) -> Optional[List[ProcessedDocument]]:
    try:
        # Validation
        for file in files:
            if not self.validator.validate_file(file):
                st.error(f"Invalid file: {file.name}")
                return None
        
        # Processing
        return self.processor.process_documents(files)
        
    except FileProcessingError as e:
        st.error(f"File processing failed: {e}")
        logger.error(f"File processing error: {e}")
        return None
    
    except Exception as e:
        st.error("An unexpected error occurred during file processing")
        logger.exception("Unexpected error in file upload processing")
        return None
```

#### At Backend Level
```python
# backend_logic/ai_analyzer.py
def analyze_document(self, document: ProcessedDocument) -> DocumentAnalysis:
    try:
        # API call with retries
        response = self._call_openai_with_retry(document.content)
        
        # Parse and validate response
        analysis = self._parse_analysis_response(response)
        return DocumentAnalysis(**analysis)
        
    except OpenAIError as e:
        logger.error(f"OpenAI API error for {document.file_name}: {e}")
        raise APIError(f"AI analysis failed: {e}")
    
    except ValidationError as e:
        logger.error(f"Analysis validation failed for {document.file_name}: {e}")
        raise ProcessingError(f"Invalid analysis result: {e}")
    
    except Exception as e:
        logger.exception(f"Unexpected error analyzing {document.file_name}")
        raise ProcessingError(f"Document analysis failed: {e}")
```

#### At Application Level
```python
# app.py
def handle_processing_errors():
    """Global error handler for processing operations"""
    try:
        # Main processing logic
        yield from process_case_pipeline()
        
    except APIError as e:
        st.error("External service error. Please try again later.")
        logger.error(f"API error: {e}")
        
    except ValidationError as e:
        st.error("Data validation failed. Please check your inputs.")
        logger.warning(f"Validation error: {e}")
        
    except ProcessingError as e:
        st.error("Processing failed. Please contact support if the issue persists.")
        logger.error(f"Processing error: {e}")
        
    except Exception as e:
        st.error("An unexpected error occurred. Please contact support.")
        logger.exception("Unexpected application error")
        
        # Optional: Reset application state
        reset_session_state()
```

## Performance Guidelines

### Optimization Strategies

#### Memory Management
```python
# Efficient file processing
def process_large_document(file: UploadedFile) -> ProcessedDocument:
    """Process large documents with memory optimization"""
    # Stream processing for large files
    content_chunks = []
    
    with file as f:
        while True:
            chunk = f.read(8192)  # Read in chunks
            if not chunk:
                break
            processed_chunk = process_chunk(chunk)
            content_chunks.append(processed_chunk)
    
    # Combine chunks
    full_content = ''.join(content_chunks)
    
    # Clear intermediate data
    del content_chunks
    
    return ProcessedDocument(
        file_name=file.name,
        content=full_content,
        file_type=file.type,
        metadata=extract_metadata(file)
    )
```

#### AI API Optimization
```python
# Rate limiting and intelligent retries
class OpenAIManager:
    def __init__(self):
        self.rate_limiter = RateLimiter(max_calls=60, time_window=60)
        self.retry_strategy = ExponentialBackoff(max_retries=3)
    
    def call_api(self, prompt: str, model: str = "gpt-4o-mini") -> str:
        """Make API call with rate limiting and retries"""
        @self.rate_limiter.limit
        @self.retry_strategy.retry
        def _make_call():
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.1
            )
            return response.choices[0].message.content
        
        return _make_call()
```

#### Session State Optimization
```python
# Efficient session state management
def optimize_session_state():
    """Clean up session state to prevent memory leaks"""
    # Remove large processed files after processing
    if 'processed_documents' in st.session_state:
        # Keep only essential metadata
        essential_data = [
            {
                'file_name': doc.file_name,
                'file_type': doc.file_type,
                'processing_timestamp': doc.processing_timestamp
            }
            for doc in st.session_state.processed_documents
        ]
        st.session_state.processed_documents_metadata = essential_data
        del st.session_state.processed_documents
    
    # Clear temporary processing data
    temp_keys = [key for key in st.session_state.keys() if key.startswith('temp_')]
    for key in temp_keys:
        del st.session_state[key]
```

### Performance Monitoring
```python
# Performance tracking decorator
import time
import functools

def track_performance(func):
    """Decorator to track function performance"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            success = True
            return result
        except Exception as e:
            success = False
            raise
        finally:
            end_time = time.time()
            duration = end_time - start_time
            
            # Log performance metrics
            logger.info(f"Performance: {func.__name__} took {duration:.2f}s (success: {success})")
            
            # Store in session state for debugging
            if 'performance_metrics' not in st.session_state:
                st.session_state.performance_metrics = []
            
            st.session_state.performance_metrics.append({
                'function': func.__name__,
                'duration': duration,
                'success': success,
                'timestamp': time.time()
            })
    
    return wrapper

# Usage
@track_performance
def analyze_document(document: ProcessedDocument) -> DocumentAnalysis:
    # Function implementation
    pass
```

## Debugging Guidelines

### Logging Configuration
```python
# logging_config.py
import logging
import streamlit as st

def setup_logging():
    """Configure application logging"""
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('app.log'),
            logging.StreamHandler()
        ]
    )
    
    # Reduce noise from external libraries
    logging.getLogger('openai').setLevel(logging.WARNING)
    logging.getLogger('streamlit').setLevel(logging.WARNING)

# Usage in modules
logger = logging.getLogger(__name__)
```

### Debug Interface
```python
# Debug sidebar for development
def display_debug_info():
    """Display debug information in Streamlit sidebar"""
    if st.sidebar.checkbox("Debug Mode"):
        st.sidebar.subheader("Session State")
        st.sidebar.json(dict(st.session_state))
        
        st.sidebar.subheader("Performance Metrics")
        if 'performance_metrics' in st.session_state:
            for metric in st.session_state.performance_metrics[-5:]:  # Last 5
                st.sidebar.text(f"{metric['function']}: {metric['duration']:.2f}s")
        
        st.sidebar.subheader("Processing State")
        st.sidebar.text(f"Current State: {st.session_state.get('processing_state', 'Unknown')}")
        
        if st.sidebar.button("Clear Session State"):
            st.session_state.clear()
            st.rerun()
```

## Deployment

### Production Configuration
```python
# config.py
import os
from typing import Dict, Any

class Config:
    """Application configuration"""
    
    # API Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    PDFCO_API_KEY = os.getenv('PDFCO_API_KEY')
    
    # Streamlit Configuration
    STREAMLIT_SERVER_PORT = int(os.getenv('STREAMLIT_SERVER_PORT', 8501))
    STREAMLIT_SERVER_HEADLESS = os.getenv('STREAMLIT_SERVER_HEADLESS', 'true').lower() == 'true'
    
    # Processing Configuration
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 10 * 1024 * 1024))  # 10MB
    MAX_FILES_PER_UPLOAD = int(os.getenv('MAX_FILES_PER_UPLOAD', 5))
    
    # Performance Configuration
    OPENAI_RATE_LIMIT = int(os.getenv('OPENAI_RATE_LIMIT', 60))
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration"""
        required = ['OPENAI_API_KEY', 'PDFCO_API_KEY']
        missing = [key for key in required if not getattr(cls, key)]
        
        if missing:
            raise ValueError(f"Missing required environment variables: {missing}")
```

### Health Checks
```python
# health.py
def check_application_health() -> Dict[str, Any]:
    """Check application health and dependencies"""
    health_status = {
        'status': 'healthy',
        'checks': {}
    }
    
    # Check API connectivity
    try:
        # Test OpenAI API
        openai.Model.list()
        health_status['checks']['openai'] = 'healthy'
    except Exception as e:
        health_status['checks']['openai'] = f'unhealthy: {e}'
        health_status['status'] = 'unhealthy'
    
    # Check file processing
    try:
        # Test file processors
        processor = DocumentProcessor()
        health_status['checks']['file_processing'] = 'healthy'
    except Exception as e:
        health_status['checks']['file_processing'] = f'unhealthy: {e}'
        health_status['status'] = 'unhealthy'
    
    return health_status
```

This development guide provides comprehensive guidelines for working with the unified Streamlit-Python architecture, ensuring consistent development practices and maintainable code.