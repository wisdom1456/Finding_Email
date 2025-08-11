# Legal Document Portal

A Streamlit-based application for legal document analysis and findings email generation.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Documentation

- [User Guide](docs/user/)
- [Developer Documentation](docs/developer/)
- [API Reference](docs/api/)

## Architecture

This application follows a modern Python package structure:

```
src/legal_portal/
├── core/           # Business logic modules
├── services/       # External service interfaces  
├── utils/          # Utility functions
├── config/         # Configuration and settings
└── ui/             # Streamlit UI components
```

For detailed information, see [Architecture Documentation](docs/developer/ARCHITECTURE.md).
