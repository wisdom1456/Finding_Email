# Legal Document Analysis Portal

A Streamlit-based application for analyzing legal documents and generating professional findings letters.

## 🚀 Quick Start

### Prerequisites

1. **System Dependencies** (macOS)
   ```bash
   brew install ghostscript  # Required for PDF compression
   ```

2. **Python 3.11+**
   ```bash
   python3 --version  # Should be 3.11 or higher
   ```

3. **Environment Setup**
   ```bash
   # Copy and configure environment variables
   cp .env.template .env
   # Edit .env and add your OPENAI_API_KEY
   ```

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Finding_Emails

# Install Python dependencies
pip install -r requirements.txt

# Start the application
streamlit run run_app.py
```

The application will open automatically in your browser at `http://localhost:8501`.

### Using the Startup Script

For a more comprehensive startup with environment validation:

```bash
./start_app.sh
```

This script will:
- Validate environment variables
- Check dependencies
- Kill any existing processes on port 8501
- Start the Streamlit application

## 📋 Features

### Document Processing
- **Multi-format Support**: PDF, DOCX, DOC, CSV, TXT, EML, images (JPG, PNG)
- **Batch Processing**: Process multiple documents simultaneously
- **OCR Support**: Extract text from images using GPT-4o Vision
- **Smart Citation Tracking**: Automatically tracks source documents for citations

### AI-Powered Analysis
- **Document Analysis**: Comprehensive legal document analysis using OpenAI GPT-4o
- **Quality Validation**: Built-in QA service for data quality checks
- **Structured Output**: JSON-based structured data extraction
- **Token Management**: Cost tracking and optimization

### Letter Generation
- **Professional Formatting**: Generate attorney-style findings letters
- **Citation Management**: Clean filename citations with document tracking
- **Client-Friendly Output**: Review and edit letters before finalization
- **Multiple Export Formats**: HTML and PDF output

### Cost Tracking
- **Session Management**: Track costs per processing session
- **Token Usage**: Detailed breakdown of API usage
- **Historical Data**: View past sessions and costs
- **Export Capability**: Export cost data for analysis

### Florida Legal Corpus Integration
- **Citation Validation**: Verify statute citations against 40+ verified Florida statutes
- **Anti-Hallucination**: Prevent AI from generating false or incorrect statute references
- **Statute Recommendations**: AI-powered suggestions for relevant Florida statutes based on case facts
- **Citation Normalization**: Automatic normalization of citation formats using 40+ aliases
- **Comprehensive Coverage**: Spans consumer protection, landlord-tenant, foreclosure, construction, liens, insurance, and civil litigation

## ⚖️ Supported Practice Areas

**This application is optimized for Florida civil litigation matters only.** Federal claims and non-Florida jurisdictions are not currently supported.

### Covered Practice Areas

#### 1. Consumer Protection & Business Misconduct (Florida law only)
- Contract disputes and breach claims (UCC Ch. 671-672)
- Consumer protection violations (FDUTPA - Ch. 501 Part II)
- Business organization disputes (Ch. 605 LLC, Ch. 607 Corp)
- Timeshare disputes and related matters

#### 2. Real Estate & Property Disputes
- Landlord-tenant disputes (Ch. 83)
- Foreclosure defense and procedures (Ch. 702)
- Property damage and insurance claims (Ch. 627)
- Construction defects (Ch. 558)
- Mechanic's liens (Ch. 713)

#### 3. Civil Litigation & Administrative Law (Florida-specific)
- Statutes of limitation (Ch. 95)
- Administrative procedure matters (Ch. 120)
- Copyright matters (only insofar as Florida law intersects)
- Attorney fees and sanctions (Ch. 57)

#### 4. Selective Personal Injury
- Motorcycle accidents (Ch. 316 traffic law)
- Limited medical malpractice matters (Ch. 766)

### Important Limitations

⚠️ **This tool currently supports Florida civil matters only.**

**Not Supported:**
- Federal claims or federal court matters
- Criminal law
- Immigration law
- Bankruptcy (federal jurisdiction)
- Patent/trademark law (federal jurisdiction)
- Out-of-state matters

**Why this matters:**
- The Florida Legal Corpus contains only Florida statutes and rules
- Citation validation is accurate only for Florida law
- AI analysis is optimized for Florida legal standards
- Statute recommendations are limited to Florida-specific provisions

If your case involves federal law or multi-jurisdiction issues, please consult with the attorney before using this tool.

## 📁 Project Structure

```
Finding_Emails/
├── src/
│   └── legal_portal/
│       ├── core/              # Business logic
│       │   ├── ai_analyzer.py
│       │   ├── auth.py
│       │   ├── data_models.py
│       │   └── document_processor.py
│       ├── services/          # Service layer
│       │   ├── content_extraction_service.py
│       │   ├── content_generation_service.py
│       │   ├── json_processing_service.py
│       │   └── file_processors/
│       ├── ui/                # Streamlit UI
│       │   ├── main.py
│       │   └── components/
│       ├── utils/             # Utilities
│       │   ├── cost_calculator.py
│       │   ├── cache_manager.py
│       │   └── token_manager.py
│       └── config/            # Configuration
│           └── prompts_and_settings.json
├── docs/                      # Documentation
│   ├── user/                  # User guides
│   ├── developer/             # Developer docs
│   └── archive/               # Historical docs
├── tests/                     # Test suites
├── scripts/                   # Utility scripts
├── output/                    # Generated outputs
├── requirements.txt           # Python dependencies
├── run_app.py                # Main entry point
├── start_app.sh              # Startup script
└── README.md                 # This file
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# Required
OPENAI_API_KEY=sk-proj-xxxxx              # OpenAI API key

# Optional
ANTHROPIC_API_KEY=xxxxx                    # Anthropic API key (if using Claude)
LOG_LEVEL=INFO                             # Logging level
ENVIRONMENT=development                    # Environment (development/production)
```

### Application Settings

Configuration is managed through:
- **prompts_and_settings.json**: AI prompts and processing settings
- **auth_config.yaml**: Authentication configuration
- **pins.json**: PIN-based access control

## 🧪 Testing

The application starts successfully and imports all required modules:

```bash
# Quick import test
python3 -c "import sys; sys.path.insert(0, 'src'); from legal_portal.ui.main import main; print('✅ Import successful')"
```

For comprehensive testing:
```bash
pytest tests/
```

## 📚 Documentation

### For Users
- [User Guide](docs/user/README.md) - Complete user documentation
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deployment instructions
- [ENV_SETUP_GUIDE.md](ENV_SETUP_GUIDE.md) - Environment setup details

### For Developers
- [Architecture](docs/developer/ARCHITECTURE.md) - System architecture
- [Performance](docs/developer/PERFORMANCE.md) - Performance considerations
- [Security](docs/developer/SECURITY.md) - Security guidelines

### Additional Resources
- [GitHub Authentication Setup](GITHUB_AUTH_SETUP.md) - Git authentication help
- [Cleanup Plan](CLEANUP_PLAN.md) - Recent cleanup activities

## 🏗️ Architecture

### Technology Stack
- **Frontend**: Streamlit 1.28+
- **Backend**: Python 3.11+
- **AI/ML**: OpenAI GPT-4o, GPT-4o Vision
- **Document Processing**: PyMuPDF, python-docx, Pillow
- **Authentication**: Streamlit-authenticator, PyJWT
- **Output Generation**: WeasyPrint, html2text

### Key Design Patterns
- **Service Layer**: Separation of concerns with dedicated services
- **Dependency Injection**: Configurable components
- **Caching**: Smart caching for performance optimization
- **Structured Logging**: Comprehensive logging with JSON output

## 🔐 Security

- **PIN Authentication**: Basic access control via PIN
- **API Key Management**: Environment-based secret management
- **Input Validation**: Comprehensive file and data validation
- **Audit Logging**: Track all document processing activities

## 💰 Cost Management

The application includes built-in cost tracking:

- **Real-time Monitoring**: Track API costs as you work
- **Session History**: View historical cost data
- **Token Usage**: Detailed token consumption metrics
- **Export Reports**: Export cost data for analysis

## 🐛 Troubleshooting

### Common Issues

**App won't start**
```bash
# Check dependencies
./start_app.sh --check-only

# View verbose output
./start_app.sh --verbose
```

**Import errors**
```bash
# Verify Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
pip install -r requirements.txt
```

**Ghostscript errors**
```bash
# macOS
brew install ghostscript

# Linux
sudo apt-get install ghostscript
```

**Port already in use**
```bash
# Kill existing process
lsof -ti:8501 | xargs kill -9

# Or use the startup script
./start_app.sh --kill-only
```

## 🚢 Deployment

### Google Cloud Run

The application can be deployed to Google Cloud Run:

```bash
# See comprehensive guide
cat DEPLOYMENT_GUIDE.md

# Quick deploy
./deploy.sh
```

### Docker

Build and run locally:

```bash
docker build -t legal-portal .
docker run -p 8501:8501 \
  -e OPENAI_API_KEY="your-key" \
  legal-portal
```

## 📊 Project Status

### ✅ Completed
- Core document processing pipeline
- GPT-4o Vision integration with batch processing
- Citation tracking system
- Cost tracking and reporting
- Quality validation service
- Letter generation and review
- Project cleanup and documentation

### 🔄 In Progress
- Code quality improvements
- Comprehensive test coverage
- Performance optimization

### 📋 Planned
- Additional document format support
- Enhanced analytics dashboard
- Automated testing pipeline
- Multi-user support with authentication

## 🤝 Contributing

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run linting
ruff check .

# Run tests
pytest tests/
```

### Code Quality

- **Linting**: Use `ruff` for Python linting
- **Type Hints**: Use type annotations throughout
- **Documentation**: Document all public functions
- **Testing**: Write tests for new features

## 📝 Recent Changes

### November 2025 - Project Cleanup
- ✅ Moved 52+ implementation notes to archive
- ✅ Consolidated documentation structure
- ✅ Removed obsolete log files and scripts
- ✅ Updated project documentation
- ✅ Verified application startup

### October 2025 - Major Updates
- GPT-4o Vision API migration
- Batch image processing
- Enhanced data quality validation
- Citation tracking improvements
- Structured JSON processing

## 📄 License

[Add license information here]

## 📞 Support

For issues, questions, or contributions:
1. Check the [documentation](docs/)
2. Review [troubleshooting](#troubleshooting) section
3. Open an issue in the repository

---

**Last Updated**: November 13, 2025

**Version**: 1.0.0

**Status**: ✅ Production Ready
