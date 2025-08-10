# Railway Configuration Files

This document contains all the configuration files needed for deploying the Legal Document Analysis Portal on Railway.

## 1. Railway.toml (Root Directory)

Create this file in your project root directory:

```toml
# Railway configuration for monorepo deployment
[build]
builder = "nixpacks"

[deploy]
numReplicas = 1

[[services]]
name = "backend"
root = "backend"
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"

[[services]]
name = "frontend"
root = "."
startCommand = "streamlit run app.py --server.port $PORT --server.address 0.0.0.0"
```

## 2. Requirements.txt (Root Directory)

Create this file for the Streamlit frontend dependencies:

```txt
streamlit>=1.28.0
requests>=2.31.0
python-dotenv>=1.0.0
```

## 3. Updated .env.template (Root Directory)

Replace the current .env.template with this secure version:

```bash
# Environment Variables Template
# Copy this file to .env and fill in your actual values
# NEVER commit the actual .env file to version control!

# API Keys (Required)
OPENAI_API_KEY=sk-proj-your-openai-api-key-here
PDFCO_API_KEY=your-pdfco-api-key-here

# Backend Configuration
DEBUG=False
LOG_LEVEL=INFO

# Frontend Configuration
BACKEND_API_URL=http://localhost:8000

# CORS Configuration (update with your Railway URLs)
CORS_ORIGINS=http://localhost:8501,http://localhost:3000

# Railway-specific (automatically set by Railway)
# PORT=<set-by-railway>
# RAILWAY_STATIC_URL=<set-by-railway>
```

## 4. Updated app.py Configuration

Add this configuration to the top of your app.py file:

```python
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BACKEND_URL = os.getenv('BACKEND_API_URL', 'http://localhost:8000')
API_TIMEOUT = 600  # 10 minutes for large document processing

# API endpoint
ANALYSIS_ENDPOINT = f"{BACKEND_URL}/api/v1/analysis/full-pipeline"
```

## 5. Railway Environment Variables

### Backend Service Variables

Set these in Railway dashboard for the backend service:

```bash
# Required API Keys
OPENAI_API_KEY=<your-actual-key>
PDFCO_API_KEY=<your-actual-key>

# CORS Configuration (update after frontend deploys)
CORS_ORIGINS=https://<your-frontend-domain>.railway.app

# Optional
DEBUG=False
LOG_LEVEL=INFO
```

### Frontend Service Variables

Set these in Railway dashboard for the frontend service:

```bash
# Backend API URL (use internal Railway URL for better performance)
BACKEND_API_URL=http://backend.railway.internal:8000

# Or use public URL if internal networking isn't available
# BACKEND_API_URL=https://<your-backend-domain>.railway.app
```

## 6. GitHub Actions Workflow (Optional)

For automated deployments, create `.github/workflows/railway-deploy.yml`:

```yaml
name: Deploy to Railway

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy to Railway
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: railway up
```

## 7. Dockerfile (Optional - for custom builds)

If you need more control over the build process:

### Backend Dockerfile (backend/Dockerfile)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$PORT"]
```

### Frontend Dockerfile (Dockerfile in root)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY assets ./assets
COPY components ./components

# Streamlit config
RUN mkdir -p ~/.streamlit
RUN echo '[server]\nheadless = true\n' > ~/.streamlit/config.toml

# Start command
CMD ["streamlit", "run", "app.py", "--server.port", "$PORT", "--server.address", "0.0.0.0"]
```

## 8. .gitignore Updates

Ensure your .gitignore includes:

```
# Environment files
.env
.env.local
.env.production

# API Keys
*.key
*.pem

# Railway
railway.json

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/

# Test results
test-results/
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

## Implementation Checklist

1. [ ] Create railway.toml in project root
2. [ ] Create requirements.txt in project root
3. [ ] Update .env.template with secure template
4. [ ] Update app.py with backend URL configuration
5. [ ] Set environment variables in Railway dashboard
6. [ ] Test deployment with sample documents
7. [ ] Update CORS_ORIGINS with production URLs
8. [ ] Set up monitoring and alerts

## Notes

- Railway automatically sets the PORT environment variable
- Use internal networking (*.railway.internal) for service-to-service communication
- Railway supports both Nixpacks and Docker builds
- Environment variables set in Railway dashboard override local .env files
