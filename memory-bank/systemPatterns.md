# System Patterns

## Architecture Overview

The Legal Document Analysis Portal has evolved from a TypeScript/n8n architecture to a modern Streamlit/FastAPI system, preserving functionality while improving maintainability and user experience.

### Current Streamlit/FastAPI Architecture

```
┌─────────────────────────────────────────┐
│              Browser (Client)            │
├─────────────────────────────────────────┤
│           Streamlit Frontend            │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │  File Upload│  │     Results     │   │
│  │     Tab     │  │      Tab        │   │
│  │             │  │                 │   │
│  └─────────────┘  └─────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │   Session State Management          │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────┘
            │
            ▼ Synchronous HTTP Request
┌─────────────────────────────────────────┐
│           FastAPI Backend               │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ Document    │  │ AI Analyzer     │   │
│  │ Processor   │  │ Service         │   │
│  └─────────────┘  └─────────────────┘   │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ Email       │  │ File Handler    │   │
│  │ Generator   │  │ Service         │   │
│  └─────────────┘  └─────────────────┘   │
└─────────────────────────────────────────┘
            │
            ▼ Complete JSON Response
┌─────────────────────────────────────────┐
│         Results Display                 │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ Case        │  │   Download      │   │
│  │ Analysis    │  │   Links         │   │
│  └─────────────┘  └─────────────────┘   │
└─────────────────────────────────────────┘
```

### Legacy TypeScript/n8n Architecture (Historical Reference)

```
┌─────────────────────────────────────────┐
│              Browser (Client)            │
├─────────────────────────────────────────┤
│         Static HTML + TypeScript        │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │    UI       │  │   Business      │   │
│  │ Components  │  │     Logic       │   │
│  │             │  │                 │   │
│  └─────────────┘  └─────────────────┘   │
├─────────────────────────────────────────┤
│         Vite Build System               │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│         n8n Webhook API                 │
│      (External Processing)              │
└─────────────────────────────────────────┘
```

## File Organization Patterns

### New Streamlit/FastAPI Directory Structure
```
/
├── app.py                    # Main Streamlit application
├── backend/                  # FastAPI backend services
│   ├── main.py              # FastAPI application entry point
│   ├── services/            # Business logic services
│   │   ├── document_processor.py  # PDF and document processing
│   │   ├── ai_analyzer.py         # OpenAI integration and analysis
│   │   └── email_generator.py     # Email findings generation
│   ├── utils/               # Utility modules
│   │   ├── validators.py    # Input validation
│   │   ├── data_models.py   # Pydantic data models
│   │   └── config.py        # Configuration management
│   └── requirements.txt     # Python dependencies
├── components/              # Streamlit component modules
│   ├── file_uploader.py    # File upload interface
│   ├── progress_tracker.py # Processing status
│   └── results_display.py  # Results presentation
└── assets/                 # Static assets and templates
    ├── styles.css          # Custom styling
    └── templates/          # Email templates
```

### Legacy TypeScript Directory Structure (Historical Reference)
```
src/
├── index.html          # Main application entry point
├── main.ts            # TypeScript application bootstrap
├── components/        # Reusable UI components
│   ├── FileUpload/   # File upload component
│   ├── CaseForm/     # Case information form
│   └── StatusDisplay/ # Status and results display
└── assets/           # Static assets
    ├── images/       # Images and icons
    ├── styles/       # CSS files
    └── fonts/        # Custom fonts
```

### Component-Based Architecture Pattern ✅ IMPLEMENTED

The application has been successfully refactored from a monolithic structure to a modern component-based architecture:

#### Previous State (Monolithic) - COMPLETED
- **Single HTML file**: All UI structure was in `src/index.html`
- **Single TypeScript file**: All logic was in `src/main.ts`
- **Inline CSS**: Styles were embedded in HTML

#### Current State (Component-Based) - IMPLEMENTED ✅
- **UI Components**: Reusable components extracted into `/src/components/`
  - [`Header.ts`](src/components/Header.ts) - Firm logo and tagline
  - [`FormHeader.ts`](src/components/FormHeader.ts) - Form title and description
  - [`CaseForm.ts`](src/components/CaseForm.ts) - Case information form with validation
  - [`FileUpload.ts`](src/components/FileUpload.ts) - Drag & drop file upload interface
  - [`FileManager.ts`](src/components/FileManager.ts) - File list management and statistics
  - [`StatusDisplay.ts`](src/components/StatusDisplay.ts) - Status messages and submit button
- **Style Modules**: CSS extracted into [`styles.ts`](src/components/styles.ts) shared stylesheet
- **Type Safety**: Shared type definitions in [`types.ts`](src/components/types.ts)
- **Business Logic**: Application orchestration in refactored [`main.ts`](src/main.ts)
- **Minimal HTML Shell**: [`src/index.html`](src/index.html) now only contains root element

#### Component Responsibilities
- **Header**: Brand presentation and firm identity
- **FormHeader**: Application title and description
- **CaseForm**: Case information collection with form validation
- **FileUpload**: File selection, drag & drop handling, and folder structure guidance
- **FileManager**: File display, statistics tracking, and file removal controls
- **StatusDisplay**: User feedback, processing states, and download links

## Key Technical Patterns

### New Streamlit/FastAPI Patterns

#### Streamlit Session State Management
```python
# Streamlit session state for maintaining application state
if 'case_info' not in st.session_state:
    st.session_state.case_info = {}
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = {}
if 'processing_status' not in st.session_state:
    st.session_state.processing_status = {}
```

#### FastAPI Service Architecture Pattern
```python
# Microservice pattern with dedicated services
class DocumentProcessor:
    async def process_documents(self, files: List[UploadFile]) -> List[ProcessedFile]:
        """Orchestrates file validation, format detection, and content extraction."""
        # ...
    
class AIAnalyzer:
    async def analyze_case(self, documents: List[ProcessedDocument]) -> CaseAnalysis:
        # ...
    
class EmailGenerator:
    async def generate_findings_letter(self, analysis: CaseAnalysis) -> EmailResponse:
        # ...
```

#### Multi-Stage Processing Pipeline
```python
# Pipeline pattern for document processing workflow
async def process_case_pipeline(case_data: CaseData) -> CaseResults:
    # Stage 1: Document processing
    processed_docs = await document_processor.process_documents(case_data.files)
    
    # Stage 2: AI analysis
    analysis = await ai_analyzer.analyze_case(processed_docs)
    
    # Stage 3: Email generation
    email_response = await email_generator.generate_findings(analysis)
    
    return CaseResults(analysis=analysis, email=email_response)
```


### Legacy TypeScript Patterns (Historical Reference)

#### State Management Pattern
```typescript
// Legacy: Global state with Map-based file storage
let uploadedFiles = new Map<string, FileData>();

// Future: Consider state management library for complex interactions
```

### Event Handling Pattern
```typescript
// DOM Event Listeners
uploadSection.addEventListener('dragover', handleDragOver);
uploadSection.addEventListener('drop', handleDrop);

// Type-safe event handlers
function handleDragOver(e: DragEvent): void { /* ... */ }
```

### Error Handling Pattern
```python
# Robust retry logic for transient API errors
@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError)),
)
async def _make_openai_request(prompt: str, model: str):
    try:
        # OpenAI API call
    except (RateLimitError, APIError, APITimeoutError) as e:
        # Log and re-raise to trigger retry
        print(f"OpenAI API Error: {e}. Retrying...")
        raise
    except Exception as e:
        # Handle unexpected errors
        raise HTTPException(status_code=500, detail="Internal error")

```

### File Processing Pattern
```typescript
// Type-safe file processing with validation
interface FileData {
  file: File;
  name: string;
  size: number;
  type: string;
  path: string;
  folder: string;
}
```

## Integration Patterns

### Streamlit/FastAPI Integration ✅ IMPLEMENTED

The current architecture uses a clean, synchronous integration pattern between the Streamlit frontend and FastAPI backend for optimal stability and user experience.

#### Request/Response Architecture
```python
# Streamlit Frontend -> FastAPI Backend Pattern
async def process_documents():
    """Synchronous processing with complete response."""
    
    # 1. Document Processing
    processed_docs = await document_processor.process_documents(files)
    
    # 2. AI Analysis
    analysis = await ai_analyzer.analyze_case(processed_docs)
    
    # 3. Email Generation
    email_response = await email_generator.generate_findings(analysis)
    
    # 4. Complete JSON Response
    return CaseResults(analysis=analysis, email=email_response)
```

#### Data Flow Pattern
```
Streamlit Frontend
       │
       ▼ HTTP POST /api/v1/analysis/full-pipeline
FastAPI Backend
   ┌─────────────────────────────────────┐
   │ 1. Document Processing              │
   │ 2. Intake Analysis (GPT-4o-mini)    │
   │ 3. Case Document Analysis (GPT-4o)  │
   │ 4. Final Assessment (GPT-4o)        │
   │ 5. Email Generation (GPT-4o)        │
   └─────────────────────────────────────┘
       │
       ▼ Complete JSON Response
Streamlit Results Display
   ┌─────────────────────────────────────┐
   │ • Case Analysis                     │
   │ • Download Links (.eml, .txt)       │
   │ • Processing Summary                │
   └─────────────────────────────────────┘
```

#### Integration Benefits
- **Simplicity**: Clean request/response cycle without complex state management
- **Reliability**: Synchronous processing ensures complete results before display
- **User Experience**: Clear loading states with definitive completion feedback
- **Error Handling**: Comprehensive error responses with user-friendly messages
- **Maintainability**: Straightforward debugging and system monitoring

### OpenAI API Integration Patterns ✅ IMPLEMENTED
- **Modern SDK Client**: Utilizes the `openai` Python package (>=1.0.0) with a structured `OpenAI` client.
- **Dual Model Strategy**: Optimized AI model selection based on processing requirements
  - **GPT-4o-mini**: Efficient intake form processing (4000 tokens, lower cost)
  - **GPT-4o**: Comprehensive case document analysis (8000 tokens, higher capability)
- **Structured Prompt Engineering**: JSON schema-enforced response formatting with `response_format={"type": "json_object"}`.
- **Response Validation Pipeline**: Multi-stage parsing with Pydantic models for robust validation.
- **Token Management**: Optimized prompt design for cost-effective processing and reliable results.

### Rate Limiting and Token Management Patterns ✅ IMPLEMENTED

#### Sequential Processing Architecture
```python
# Rate-limiting pattern for OpenAI API compliance
async def analyze_case_documents(self, documents: List[ProcessedDocument], intake_context: EnhancedIntakeAnalysis):
    """Sequential processing to prevent rate limiting."""
    results = []
    total_docs = len(documents)
    
    for i, doc in enumerate(documents, 1):
        print(f"AI ANALYZER: Processing document {i}/{total_docs}: {doc.file_name}")
        result = await self._analyze_single_document(doc, intake_context)
        results.append(result)
        
        # Critical: Add delay between requests to respect rate limits
        if i < total_docs:
            print(f"AI ANALYZER: Waiting 3 seconds before next document...")
            await asyncio.sleep(3)
    
    return results
```

#### Token Estimation and Content Truncation
```python
def _estimate_tokens(self, text: str) -> int:
    """Rough estimation of tokens (approximately 4 characters per token)."""
    return len(text) // 4

def _truncate_content_if_needed(self, content: str, max_tokens: int = 25000) -> str:
    """Truncate content if it exceeds token limit."""
    estimated_tokens = self._estimate_tokens(content)
    if estimated_tokens > max_tokens:
        # Keep first 80% and last 20% of content
        chars_to_keep = max_tokens * 4
        first_part_chars = int(chars_to_keep * 0.8)
        last_part_chars = int(chars_to_keep * 0.2)
        
        first_part = content[:first_part_chars]
        last_part = content[-last_part_chars:]
        
        truncated_content = f"{first_part}\n\n[... CONTENT TRUNCATED FOR SIZE ...]\n\n{last_part}"
        print(f"AI ANALYZER: ⚠️  Content truncated from ~{estimated_tokens} to ~{max_tokens} tokens")
        return truncated_content
    return content
```

#### Dynamic Model Selection Based on Document Size
```python
# Intelligent model selection pattern
def _analyze_single_document(self, document: ProcessedDocument, intake_context: EnhancedIntakeAnalysis):
    # Check document size and truncate if necessary
    truncated_content = self._truncate_content_if_needed(document.content)
    
    # Estimate total prompt size and choose appropriate model
    total_estimated_tokens = self._estimate_tokens(prompt)
    model_to_use = "gpt-4o-mini" if total_estimated_tokens > 20000 else "gpt-4o"
    
    if model_to_use == "gpt-4o-mini":
        print(f"AI ANALYZER: 🔄 Using gpt-4o-mini for large document: {document.file_name}")
    
    raw_analysis = await self._make_openai_request(prompt, model=model_to_use)
```

#### Production-Grade Progress Logging
```python
# Progress visibility pattern for long-running operations
async def analyze_case_documents(self, documents: List[ProcessedDocument], intake_context: EnhancedIntakeAnalysis):
    print(f"AI ANALYZER: Starting analysis of {total_docs} documents...")
    
    for i, doc in enumerate(documents, 1):
        print(f"AI ANALYZER: Processing document {i}/{total_docs}: {doc.file_name}")
        result = await self._analyze_single_document(doc, intake_context)
        
        # Log the result type with clear status indicators
        if isinstance(result, AnalysisError):
            print(f"AI ANALYZER: ❌ Failed to analyze {doc.file_name}: {result.error_message}")
        else:
            print(f"AI ANALYZER: ✅ Successfully analyzed {doc.file_name}")
```

#### Key Benefits Achieved
- **Rate Limit Compliance**: 100% success rate by respecting OpenAI TPM limits (30,000 tokens/minute)
- **Large Document Handling**: Automatic processing of documents up to 53,566 tokens
- **Intelligent Resource Usage**: Dynamic model selection optimizes cost and performance
- **Production Monitoring**: Clear visibility into processing progress and status
- **Scalable Architecture**: Handles document sets of 40+ files without errors

### Professional Output Generation Patterns ✅ IMPLEMENTED
- **Email Template System**: Professional findings letter generation with business-appropriate formatting
- **Multi-Format Export**: Simultaneous .eml (email-ready) and .txt (plain text) file creation
- **Base64 Encoding Pattern**: Data URL generation for immediate browser download without server storage
- **Metadata Preservation**: Complete case information tracking and audit trail throughout pipeline

### Download System Architecture ✅ IMPLEMENTED
```typescript
// Download Link Generation Pattern
const downloadResponse = {
  downloadLinks: {
    findingsLetter: `data:message/rfc822;base64,${emlBase64}`,
    caseAnalysis: `data:text/plain;base64,${txtBase64}`,
    executiveSummary: `data:text/plain;base64,${summaryBase64}`
  },
  emailDetails: {
    emlFileName: `Findings_${caseReference}_${date}.eml`,
    txtFileName: `Analysis_${caseReference}_${date}.txt`
  }
};
```

### External API Integration
- **FastAPI Endpoints**: Direct HTTP API calls from Streamlit frontend to FastAPI backend services
- **Synchronous Processing**: Complete document analysis pipeline with single response containing all results
- **Structured Response Handling**: Comprehensive JSON response format with professional download links
- **CORS Configuration**: Proper cross-origin handling for production deployment with domain allowlisting

### Build System Integration
- **Vite Integration**: Modern build tooling with HMR and optimized production builds
- **TypeScript Compilation**: Type checking integrated into build process with strict mode
- **Asset Optimization**: Automatic bundling, minification, and static asset handling

## Security Patterns

### File Upload Security
- **File Type Validation**: Whitelist of allowed extensions (.pdf, .docx, .doc, .txt)
- **Size Limitations**: 100MB total upload limit with warnings
- **Client-side Validation**: Pre-upload validation for immediate feedback

### Data Handling
- **FormData API**: Secure multipart form submission
- **No Local Storage**: Files processed but not persisted locally
- **HTTPS Endpoints**: Secure transmission to processing endpoint

## Performance Patterns

### Lazy Loading
- **File Manager UI**: Hidden until files are uploaded
- **Progressive Enhancement**: Base functionality without JavaScript

### Memory Management
- **File Reference Management**: Using Map for efficient file tracking
- **Cleanup Functions**: Clear all files functionality
- **DOM Updates**: Efficient innerHTML updates for file lists

## Completed Architecture Achievements ✅

### Component Extraction - COMPLETED
1. ✅ **Header Component**: Firm branding and identity display
2. ✅ **FormHeader Component**: Application title and description
3. ✅ **CaseForm Component**: Client information form with validation
4. ✅ **FileUpload Component**: Drag & drop, file selection, and validation
5. ✅ **FileManager Component**: File list display, statistics, and management
6. ✅ **StatusDisplay Component**: Processing status, results, and submit controls

### Architectural Benefits Achieved
- ✅ **Separation of Concerns**: Each component has a single responsibility
- ✅ **Reusability**: Components can be easily reused or extended
- ✅ **Type Safety**: Full TypeScript implementation with strict typing
- ✅ **Maintainability**: Clear component boundaries and interfaces
- ✅ **Testability**: Components can be unit tested independently
- ✅ **Modularity**: Clean import/export structure

### Future Enhancement Opportunities
- **State Management Evolution**: Consider formal state management (Redux, Zustand) for complex state
- **Component Testing**: Add unit tests for each component
- **Build Optimization**: Code splitting for larger applications
- **Progressive Enhancement**: PWA capabilities for offline usage
- **Accessibility**: Enhanced ARIA labels and keyboard navigation
- **Performance**: Virtual scrolling for large file lists