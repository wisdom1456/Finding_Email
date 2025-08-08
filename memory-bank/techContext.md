# Tech Context

## Development Environment

The Legal Document Analysis Portal is built on a unified Streamlit-Python stack with a recently implemented **modular service-oriented backend architecture**. The development environment emphasizes maintainability, testability, and adherence to modern Python development practices.

### Core Technologies

*   **Framework**: Streamlit - Python-based web framework enabling rapid application development and deployment
*   **Language**: Python 3.12+ - Modern Python with comprehensive type hints and asynchronous support
*   **Architecture**: Service-Oriented Design - Modular backend services following Single Responsibility Principle
*   **Data Models**: Pydantic for data validation and structured data models ensuring robustness and consistency

### Modular Backend Architecture

The application features a sophisticated service-oriented backend architecture:

#### Service Layer Structure
*   **Package Organization**: Services organized under `backend_logic/email_generation/services/`
*   **Service Classes**: 7 focused service classes replacing monolithic EmailGeneratorV2 (5,466 → 335 lines)
*   **Orchestration Pattern**: Lightweight orchestrator coordinates service interactions
*   **Dependency Injection**: Loose coupling between services through dependency injection

#### Service Components
*   **ConfigurationManager**: YAML configuration loading and template management (132 lines)
*   **TextProcessingService**: Simplified text processing without complex simplification pipeline (165 lines)
*   **JSONArchitectureService**: JSON operations and structured data handling (229 lines)
*   **TemplateRenderingService**: Jinja2 template operations and rendering (232 lines)
*   **ContentGenerationService**: Section-specific content orchestration (254 lines)
*   **OpenAIIntegrationService**: AI API calls and response processing (266 lines)
*   **FallbackGenerationService**: Error recovery and graceful degradation (255 lines)

### Key Dependencies

The application relies on a curated set of libraries optimized for the service architecture:

#### Core Framework Dependencies
*   **Streamlit**: Foundation of the web application interface
*   **Jinja2**: Template rendering engine isolated in TemplateRenderingService
*   **PyYAML**: Configuration management through ConfigurationManager service
*   **Pydantic**: Data validation and modeling across all services

#### AI and Processing Dependencies
*   **OpenAI**: AI-powered analysis and content generation through OpenAIIntegrationService
*   **Google Cloud**: Advanced video and audio processing capabilities
    *   `google-cloud-aiplatform`: Vertex AI integration for video analysis
    *   `google-cloud-speech`: Speech-to-Text API for audio transcription
*   **tiktoken**: Accurate token counting for API limit management

#### Document Processing Dependencies
*   **Document Processors**: Multi-format document handling suite
    *   `python-docx`: Microsoft Word document processing
    *   `PyPDF2`: PDF document extraction and analysis
    *   `pyth`: Rich text format support
*   **Media Processing**: Image and audio manipulation capabilities
    *   `Pillow`: Image processing and manipulation
    *   `pydub`: Audio file processing and conversion

#### Testing and Quality Dependencies
*   **pytest**: Comprehensive testing framework for service validation
*   **Integration Testing**: Custom test harness for service integration validation
*   **Type Checking**: mypy for static type analysis across service interfaces

### Service Architecture Benefits

#### Development Experience
*   **Modular Development**: Each service can be developed and tested independently
*   **Clear Boundaries**: Service interfaces provide clear contracts and responsibilities
*   **Enhanced Debugging**: Issues can be isolated to specific services rather than monolithic code
*   **Easier Onboarding**: New developers can understand focused service responsibilities

#### Code Quality Improvements
*   **94% Code Reduction**: Main orchestrator reduced from 5,466 to 335 lines
*   **Single Responsibility**: Each service handles exactly one functional area
*   **Testability**: Services can be unit tested in isolation with mocked dependencies
*   **Maintainability**: Changes to one service don't affect others when interfaces are preserved

## Deployment

The unified Streamlit application with modular backend is designed for straightforward deployment:

*   **Platform**: Optimized for Streamlit Cloud deployment with Docker containerization support
*   **Environment Configuration**: All configuration managed through single `.env` file loaded via `python-dotenv`
*   **Service Discovery**: Services automatically discovered through package imports and dependency injection
*   **Backward Compatibility**: All existing interfaces preserved during architectural refactoring

## Google Cloud Integration

Advanced video processing capabilities maintained through service architecture:

*   **Project Setup**: Google Cloud project with Vertex AI, Speech-to-Text, and Cloud Storage APIs enabled
*   **Service Account**: Properly configured service account with necessary IAM roles:
    *   `Vertex AI User`: For video analysis capabilities
    *   `Storage Object Admin`: For temporary video file storage
    *   `Speech Service Agent`: For audio transcription services
*   **Bucket Configuration**: Dedicated Cloud Storage bucket with 24-hour lifecycle policy for temporary storage
*   **Service Integration**: Video processing seamlessly integrated into service architecture without affecting other components

## Configuration Management

Enhanced configuration system through dedicated ConfigurationManager service:

*   **YAML-Based Configuration**: Centralized configuration files for all service behaviors
*   **Template Management**: Jinja2 templates organized and loaded through configuration service
*   **Environment Isolation**: Development, testing, and production configurations managed separately
*   **Service-Specific Config**: Each service can define its own configuration requirements while maintaining central management

## Testing Architecture

Comprehensive testing strategy supporting the modular service architecture:

*   **Unit Testing**: Each service tested in isolation with mocked dependencies
*   **Integration Testing**: Service interaction testing with 100% success rate validation
*   **Backward Compatibility Testing**: Ensures refactoring doesn't break existing functionality
*   **Error Path Testing**: Validates graceful degradation and error recovery patterns