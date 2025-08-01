# Legal Document Analysis Portal

A production-ready, full-stack web application for automated legal document analysis and professional findings letter generation.

## Overview

The Legal Document Analysis Portal streamlines the process of analyzing legal case documents and generating professional findings letters for law firms. Built with modern technologies and following enterprise-level best practices.

### Key Features

- **Multi-Format Document Processing**: Support for PDF, DOCX, DOC, TXT, and EML files
- **AI-Powered Analysis**: Intelligent extraction of legal entities, timelines, and case insights
- **Professional Output**: Automated generation of client-ready findings letters
- **Modern Architecture**: Streamlit frontend with FastAPI backend
- **Production-Ready**: Containerized deployment with comprehensive monitoring

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 16+ (for tooling)
- OpenAI API key
- PDF.co API key (optional)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/legal-document-analysis-portal.git
   cd legal-document-analysis-portal
   ```

2. **Configure environment**
   ```bash
   cp config/.env.template .env
   # Edit .env with your API keys
   ```

3. **Start development servers**
   ```bash
   # Backend (Terminal 1)
   ./scripts/backend/start_dev.sh
   
   # Frontend (Terminal 2)
   ./scripts/frontend/start_dev.sh
   ```

4. **Access the application**
   - Frontend: http://localhost:8501
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## Architecture

### Technology Stack

**Frontend:**
- Streamlit (Python web framework)
- Python 3.9+
- Session state management

**Backend:**
- FastAPI (Python API framework)
- OpenAI API integration
- Pydantic data validation
- Async/await processing

**Deployment:**
- Docker containerization
- Railway hosting
- Environment-based configuration

### Directory Structure

```
project/
├── frontend/           # Streamlit frontend application
│   ├── src/           # Source code
│   ├── public/        # Static files
│   └── dist/          # Build output
├── backend/           # FastAPI backend services
│   ├── src/           # Source code
│   ├── services/      # Business logic
│   ├── utils/         # Utility functions
│   └── dist/          # Build output
├── shared/            # Shared code and types
├── config/            # Environment configurations
├── docs/              # Documentation
├── scripts/           # Build and deployment scripts
│   ├── frontend/      # Frontend scripts
│   └── backend/       # Backend scripts
└── tests/             # End-to-end tests
```

## Development

### Development Scripts

**Frontend Development:**
```bash
./scripts/frontend/start_dev.sh    # Start development server
./scripts/frontend/build.sh        # Build for production
./scripts/frontend/deploy.sh       # Deploy to production
```

**Backend Development:**
```bash
./scripts/backend/start_dev.sh     # Start development server
./scripts/backend/build.sh         # Build for production
./scripts/backend/deploy.sh        # Deploy to production
```

### Environment Configuration

The application supports multiple environments:

- **Development**: `.env.development` - Debug mode, verbose logging
- **Production**: `.env.production` - Optimized for performance
- **Local Override**: `.env` - Local development customization

### API Documentation

The backend provides comprehensive API documentation:

- **Interactive Docs**: http://localhost:8000/docs (Swagger UI)
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

## Deployment

### Supported Platforms

- **Railway** (Recommended)
- **Docker/Docker Compose**
- **Heroku**
- **Fly.io**
- **Render**

### Railway Deployment

1. **Build the applications**
   ```bash
   ./scripts/frontend/build.sh
   ./scripts/backend/build.sh
   ```

2. **Deploy backend**
   ```bash
   ./scripts/backend/deploy.sh railway production
   ```

3. **Deploy frontend**
   ```bash
   ./scripts/frontend/deploy.sh railway production
   ```

### Docker Deployment

```bash
# Build Docker images
./scripts/backend/deploy.sh docker
./scripts/frontend/deploy.sh docker

# Run with Docker Compose
docker-compose up --build
```

## Configuration

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for AI analysis |
| `PDFCO_API_KEY` | No | PDF.co API key for advanced PDF processing |
| `DEBUG` | No | Enable debug mode (default: False) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |

### File Upload Limits

- Maximum file size: 100MB total
- Supported formats: PDF, DOCX, DOC, TXT, EML
- Maximum files per request: 50

## Testing

### Running Tests

```bash
# Backend tests
cd backend && python -m pytest tests/ -v

# Frontend tests (if available)
cd frontend && python -m pytest tests/ -v

# End-to-end tests
cd tests && python -m pytest e2e/ -v
```

### Test Data

Sample test files are available in the `samples/` directory for development and testing.

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[Architecture Guide](docs/architecture.md)** - System design and components
- **[API Reference](docs/api_reference.md)** - Complete API documentation
- **[Setup Guide](docs/setup_guide.md)** - Detailed setup instructions

## Contributing

### Development Workflow

1. Create a feature branch: `git checkout -b feature/new-feature`
2. Make your changes with tests
3. Update documentation if needed
4. Run tests: `pytest tests/`
5. Submit a pull request

### Code Standards

- **Python**: Follow PEP 8, use `black` for formatting
- **Documentation**: Update relevant markdown files
- **Testing**: Include tests for new functionality

## Monitoring and Logging

### Health Checks

- Backend health: `GET /health`
- Frontend monitoring via Streamlit built-in health checks

### Logging

- Development: Console output with debug information
- Production: Structured logging with rotation
- Error tracking: Integration-ready for Sentry

## Security

### Best Practices

- Environment variables for sensitive data
- Input validation with Pydantic
- File type and size restrictions
- Rate limiting on API endpoints
- Secure CORS configuration

## Support

### Getting Help

- **Issues**: Create GitHub issues with detailed descriptions
- **Documentation**: Check the `docs/` directory
- **API**: Use the interactive documentation at `/docs`

### Performance

- Typical processing time: 2-5 minutes for standard cases
- Large cases (40+ documents): 5-15 minutes
- Concurrent processing supported

## License

This project is proprietary software for law firm use.

## Version History

### v1.0.0 (Current)
- Initial production release
- Complete document analysis pipeline
- Professional findings letter generation
- Multi-platform deployment support
- Comprehensive documentation

---

**Built with ❤️ for legal professionals**

For technical support or feature requests, please contact the development team.