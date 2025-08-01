# Setup Guide

## Prerequisites

Before setting up the Legal Document Analysis Portal, ensure you have the following installed:

- **Python 3.9+** with pip
- **Node.js 16+** with npm (for frontend tooling)
- **Git** for version control
- **API Keys**:
  - OpenAI API key
  - PDF.co API key (optional, for advanced PDF processing)

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/legal-document-analysis-portal.git
cd legal-document-analysis-portal
```

### 2. Environment Setup

Copy the environment template and configure your settings:

```bash
cp config/.env.template .env
```

Edit `.env` with your actual API keys:

```bash
# Required
OPENAI_API_KEY=sk-proj-your-openai-api-key-here
PDFCO_API_KEY=your-pdfco-api-key-here

# Optional (defaults provided)
DEBUG=True
LOG_LEVEL=INFO
```

### 3. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn main:app --reload --port 8000
```

The backend will be available at: http://localhost:8000

### 4. Frontend Setup

Open a new terminal:

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies (if using Node.js tooling)
npm install

# Start the Streamlit frontend
streamlit run app.py --server.port 8501
```

The frontend will be available at: http://localhost:8501

## Development Environment

### Directory Structure

```
project/
├── frontend/           # Streamlit frontend application
├── backend/            # FastAPI backend services
├── shared/             # Shared code and types
├── config/             # Environment configurations
├── docs/               # Documentation
├── scripts/            # Build and deployment scripts
└── tests/              # End-to-end tests
```

### Development Scripts

Use the provided scripts for common development tasks:

```bash
# Frontend development
./scripts/frontend/start_dev.sh    # Start development server
./scripts/frontend/build.sh        # Build for production
./scripts/frontend/deploy.sh       # Deploy to production

# Backend development
./scripts/backend/start_dev.sh     # Start development server
./scripts/backend/build.sh         # Build for production
./scripts/backend/deploy.sh        # Deploy to production
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key for AI analysis |
| `PDFCO_API_KEY` | No | - | PDF.co API key for advanced PDF processing |
| `DEBUG` | No | `False` | Enable debug mode |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MAX_FILE_SIZE` | No | `100MB` | Maximum file upload size |
| `DATABASE_URL` | No | `sqlite:///./app.db` | Database connection string |

### File Upload Limits

- **Maximum file size**: 100MB total
- **Supported formats**: PDF, DOCX, DOC, TXT, EML
- **Maximum files per request**: 50

## Database Setup (Optional)

By default, the application uses in-memory storage. For persistent storage:

### SQLite (Development)

```bash
# Automatic setup - no configuration needed
# Database file will be created at ./app.db
```

### PostgreSQL (Production)

```bash
# Install PostgreSQL dependencies
pip install psycopg2-binary

# Set database URL
export DATABASE_URL="postgresql://user:password@localhost/dbname"

# Run migrations (when implemented)
alembic upgrade head
```

## Testing

### Running Tests

```bash
# Backend tests
cd backend
python -m pytest tests/ -v

# Frontend tests (if implemented)
cd frontend
python -m pytest tests/ -v

# End-to-end tests
cd tests
python -m pytest e2e/ -v
```

### Test Data

Sample test files are provided in the `samples/` directory:

- `samples/intake_form.pdf` - Sample client intake form
- `samples/contract.docx` - Sample contract document
- `samples/correspondence.eml` - Sample email correspondence

## Deployment

### Local Development

1. Start backend: `uvicorn backend.main:app --reload --port 8000`
2. Start frontend: `streamlit run frontend/app.py --server.port 8501`
3. Open browser to http://localhost:8501

### Production Deployment

#### Using Docker

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build individually
docker build -t legal-portal-backend ./backend
docker build -t legal-portal-frontend ./frontend
```

#### Using Railway (Recommended)

1. Connect your GitHub repository to Railway
2. Configure environment variables in Railway dashboard
3. Deploy backend and frontend as separate services

#### Environment-Specific Configs

- **Development**: Uses `config/.env.development`
- **Production**: Uses `config/.env.production`
- **Local Override**: Uses `.env` in project root

## Troubleshooting

### Common Issues

#### "ModuleNotFoundError" when starting backend

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

#### "OpenAI API key not found"

```bash
# Check environment variables
echo $OPENAI_API_KEY

# Verify .env file exists and contains valid key
cat .env | grep OPENAI_API_KEY
```

#### File upload errors

- Check file size limits (100MB total)
- Verify file formats are supported
- Ensure backend server is running on port 8000

#### Frontend not connecting to backend

```bash
# Verify backend is running
curl http://localhost:8000/health

# Check frontend configuration
# Ensure API_BASE_URL points to correct backend
```

### Performance Issues

#### Slow document processing

- Check internet connection (required for OpenAI API)
- Verify API rate limits haven't been exceeded
- Consider using smaller files for testing

#### High memory usage

- Monitor file sizes being processed
- Restart services if memory usage grows
- Consider implementing file streaming for large uploads

### Logging and Debugging

#### Enable debug logging

```bash
# In .env file
DEBUG=True
LOG_LEVEL=DEBUG
```

#### View logs

```bash
# Backend logs
tail -f backend/app.log

# Frontend logs (in terminal where Streamlit is running)
# Check terminal output
```

## Development Workflow

### Making Changes

1. **Create feature branch**: `git checkout -b feature/new-feature`
2. **Make changes** to frontend or backend
3. **Test locally** using development servers
4. **Run tests**: `pytest tests/`
5. **Commit changes**: `git commit -m "Add new feature"`
6. **Push and create PR**: `git push origin feature/new-feature`

### Code Style

- **Python**: Follow PEP 8, use `black` for formatting
- **TypeScript**: Follow standard TypeScript conventions
- **Documentation**: Update relevant .md files for significant changes

### API Development

When adding new API endpoints:

1. Add route to `backend/api/`
2. Update `project/docs/api_reference.md`
3. Add tests in `backend/tests/`
4. Update frontend to use new endpoint

## Support

### Getting Help

- **Documentation**: Check this guide and other docs in `project/docs/`
- **Issues**: Create GitHub issue with detailed description
- **Logs**: Include relevant log output when reporting issues

### Contributing

1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Update documentation
5. Submit pull request

### Version Information

- **Current Version**: 1.0.0
- **API Version**: v1
- **Python Version**: 3.9+
- **Node.js Version**: 16+