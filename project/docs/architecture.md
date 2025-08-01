# System Architecture

## Overview

The Legal Document Analysis Portal is built using a modern, production-ready architecture with clear separation between frontend and backend components.

## High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Frontend     │────│     Backend     │────│  External APIs  │
│   (Streamlit)   │    │   (FastAPI)     │    │   (OpenAI, etc) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Frontend Architecture

### Technology Stack
- **Framework**: Streamlit
- **Language**: Python
- **UI Components**: Native Streamlit components
- **State Management**: Streamlit session state
- **File Handling**: Streamlit file uploader

### Directory Structure
```
frontend/
├── src/
│   ├── components/     # Reusable UI components
│   ├── pages/          # Application pages
│   ├── assets/         # Static assets
│   ├── services/       # API interaction services
│   ├── styles/         # Global styles and themes
│   └── utils/          # Utility functions
└── public/             # Static files
```

## Backend Architecture

### Technology Stack
- **Framework**: FastAPI
- **Language**: Python
- **API Documentation**: Automatic OpenAPI/Swagger
- **Async Support**: Full async/await support
- **Validation**: Pydantic models
- **File Processing**: Specialized processors per format

### Directory Structure
```
backend/
└── src/
    ├── api/            # API route definitions
    ├── controllers/    # Request handlers
    ├── services/       # Business logic
    ├── models/         # Database models/schemas
    ├── middleware/     # Request middleware
    └── utils/          # Utility functions
```

### Core Services

#### Document Processor Service
- Handles multiple file formats (PDF, DOCX, DOC, TXT, EML)
- Validates file types and sizes
- Extracts text content for analysis

#### AI Analyzer Service
- Integrates with OpenAI API
- Dual model strategy (GPT-4o and GPT-4o-mini)
- Rate limiting and error handling
- Structured response parsing

#### Email Generator Service
- Creates professional findings letters
- Multiple output formats (.eml, .txt)
- Template-based generation
- Quality validation

## Shared Components

### Directory Structure
```
shared/
├── types/              # Shared TypeScript/Python types
├── constants/          # Application constants
├── validators/         # Shared validation logic
└── contracts/          # API contracts and schemas
```

## Configuration Management

### Environment-Specific Configs
- Development: `.env.development`
- Production: `.env.production`
- Template: `.env.template`

### Configuration Categories
- API Keys and secrets
- Database connections
- External service endpoints
- Feature flags
- Performance tuning

## Security Considerations

### API Security
- Input validation with Pydantic
- File type and size restrictions
- Rate limiting
- Error handling without information leakage

### Data Protection
- Secure file handling
- API key management
- Environment variable isolation
- No sensitive data in logs

## Deployment Architecture

### Development Environment
- Local Streamlit server (port 8501)
- Local FastAPI server (port 8000)
- File-based storage

### Production Environment
- Containerized deployment
- Railway hosting for backend
- Environment variable management
- Monitoring and logging

## Data Flow

### Document Processing Flow
1. **Upload**: User uploads files via Streamlit interface
2. **Validation**: Backend validates file types and sizes
3. **Processing**: Extract text content from various formats
4. **Analysis**: AI analysis of extracted content
5. **Generation**: Create professional findings letters
6. **Delivery**: Download links provided to user

### API Communication
- RESTful API design
- JSON request/response format
- Proper HTTP status codes
- Comprehensive error handling

## Scalability Considerations

### Performance Optimization
- Async processing for concurrent requests
- Intelligent caching strategies
- Efficient file handling
- Resource management

### Future Enhancements
- Database integration for persistence
- Advanced caching with Redis
- Microservices architecture
- Load balancing