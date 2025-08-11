# Concrete Refactor Plan with Git Operations

## Overview

This document provides a comprehensive, executable refactor plan with specific git commands to transform the current fragmented codebase into the unified production-grade directory structure. The plan includes backup strategies, validation steps, and rollback procedures.

## Pre-Refactor Checklist

### Safety Measures
- [ ] Create git branch: `git checkout -b refactor-consolidation-v2`
- [ ] Create backup tag: `git tag -a backup-pre-refactor-v2 -m "Backup before second refactor"`
- [ ] Verify clean working directory: `git status`
- [ ] Run existing tests: `pytest tests/` (if any pass)
- [ ] Verify Streamlit app starts: `streamlit run app.py`

### Dependency Installation
```bash
# Ensure all dependencies are installed
pip install -r requirements.txt

# Install development dependencies
pip install pytest ruff mypy black isort
```

## Phase 1: Create New Directory Structure

### 1.1 Create Core Directories
```bash
# Create main source structure
mkdir -p src/legal_portal/{core,services,utils,config,ui}
mkdir -p src/legal_portal/config/{prompts,templates}
mkdir -p src/legal_portal/ui/{components,pages}

# Create test structure
mkdir -p tests/{unit,integration,e2e,fixtures}
mkdir -p tests/unit/{core,services,utils}
mkdir -p tests/fixtures/{sample_documents,mock_responses,test_configs}

# Create documentation structure
mkdir -p docs/{architecture,development,deployment,user_guides,api}

# Create script directories
mkdir -p scripts/{setup,maintenance,development,migration}

# Create data directories (git-ignored)
mkdir -p data/{cache,uploads,outputs,logs}
mkdir -p data/outputs/{findings_letters,analysis_reports,appendices}

# Create build and test artifact directories (git-ignored)
mkdir -p .build/{dist,wheels,coverage}
mkdir -p .test/{results,reports,coverage,benchmarks}

# Create memory bank specialized directory
mkdir -p memory-bank/specialized
mkdir -p memory-bank/archive/{2025-08-11,historical,superseded}
```

### 1.2 Create Package Structure
```bash
# Create __init__.py files for proper Python packaging
touch src/__init__.py
touch src/legal_portal/__init__.py
touch src/legal_portal/core/__init__.py
touch src/legal_portal/services/__init__.py
touch src/legal_portal/utils/__init__.py
touch src/legal_portal/config/__init__.py
touch src/legal_portal/ui/__init__.py
touch src/legal_portal/ui/components/__init__.py
touch src/legal_portal/ui/pages/__init__.py

# Test package structure
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch tests/e2e/__init__.py
touch tests/fixtures/__init__.py
touch tests/unit/core/__init__.py
touch tests/unit/services/__init__.py
touch tests/unit/utils/__init__.py

# Script package structure
touch scripts/__init__.py
```

## Phase 2: Move Core Application Files

### 2.1 Move Core Business Logic
```bash
# Move core modules to new structure
git mv core/main_processor.py src/legal_portal/core/
git mv core/ai_analyzer.py src/legal_portal/core/
git mv core/document_processor.py src/legal_portal/core/
git mv core/email_generator.py src/legal_portal/core/
git mv core/audio_processor.py src/legal_portal/core/
git mv core/video_processor.py src/legal_portal/core/
git mv core/citation_tracking_service.py src/legal_portal/core/
git mv core/data_models.py src/legal_portal/core/
git mv core/logging_config.py src/legal_portal/utils/
git mv core/helpers.py src/legal_portal/utils/

# Move remaining core files
git mv core/cost_session_manager.py src/legal_portal/services/
git mv core/json_processing_service.py src/legal_portal/services/
git mv core/openai_client.py src/legal_portal/services/
```

### 2.2 Move Service Files
```bash
# Note: services/ directory appears to be empty in current structure
# Create any missing service files if they exist elsewhere
if [ -d "services" ]; then
    find services -name "*.py" -exec git mv {} src/legal_portal/services/ \;
fi
```

### 2.3 Move Utility Files
```bash
# Move utils to new location (these should already be consolidated)
git mv utils/security.py src/legal_portal/utils/
git mv utils/pii_sanitizer.py src/legal_portal/utils/
git mv utils/cache_manager.py src/legal_portal/utils/
git mv utils/api_optimizer.py src/legal_portal/utils/

# Move any remaining utility files
find utils -name "*.py" -not -name "__init__.py" -exec git mv {} src/legal_portal/utils/ \;
```

### 2.4 Move Configuration Files
```bash
# Move configuration to new structure
git mv config/default.py src/legal_portal/config/settings.py

# Move YAML configuration files
if [ -d "config" ]; then
    find config -name "*.yaml" -exec git mv {} src/legal_portal/config/prompts/ \;
    find config -name "*.yml" -exec git mv {} src/legal_portal/config/prompts/ \;
fi

# Move template files
if [ -d "backend/assets/templates" ]; then
    git mv backend/assets/templates/* src/legal_portal/config/templates/
elif [ -d "assets/templates" ]; then
    git mv assets/templates/* src/legal_portal/config/templates/
fi
```

## Phase 3: Consolidate and Clean Up Test Structure

### 3.1 Move Existing Tests
```bash
# Move tests from current tests/ directory
if [ -d "tests" ]; then
    # Move unit tests
    find tests -name "test_*.py" -path "*/unit/*" -exec git mv {} tests/unit/ \;
    
    # Move integration tests  
    find tests -name "test_*.py" -path "*/integration/*" -exec git mv {} tests/integration/ \;
    find tests -name "test_*.py" -path "*/e2e/*" -exec git mv {} tests/e2e/ \;
    
    # Move any remaining tests to appropriate location
    find tests -maxdepth 1 -name "test_*.py" -exec git mv {} tests/unit/ \;
fi

# Move specific test files mentioned in analysis
if [ -f "tests/test_citation_enhancement.py" ]; then
    git mv tests/test_citation_enhancement.py tests/integration/
fi

if [ -f "tests/test_appendix_fix.py" ]; then
    git mv tests/test_appendix_fix.py tests/integration/
fi

if [ -f "tests/test_critical_fixes.py" ]; then
    git mv tests/test_critical_fixes.py tests/integration/
fi
```

### 3.2 Clean Up Legacy Test Directories
```bash
# Remove legacy backend test directories (should be empty after move)
if [ -d "backend/tests" ]; then
    git rm -rf backend/tests/
fi

if [ -d "backend_backup/tests" ]; then
    git rm -rf backend_backup/tests/
fi

if [ -d "utils/tests" ]; then
    git rm -rf utils/tests/
fi
```

## Phase 4: Remove Legacy and Duplicate Directories

### 4.1 Remove Legacy Backend Directories
```bash
# Remove backend directories (should be empty after moves)
if [ -d "backend" ] && [ "$(find backend -type f | wc -l)" -eq 0 ]; then
    git rm -rf backend/
fi

if [ -d "backend_backup" ]; then
    git rm -rf backend_backup/
fi

if [ -d "backend_logic" ]; then
    git rm -rf backend_logic/
fi

if [ -d "backend_logic_backup" ]; then
    git rm -rf backend_logic_backup/
fi

# Remove services/services if it exists
if [ -d "services/services" ]; then
    git rm -rf services/services/
fi

# Remove empty legacy directories
for dir in services utils config; do
    if [ -d "$dir" ] && [ "$(find $dir -type f | wc -l)" -eq 0 ]; then
        git rm -rf $dir/
    fi
done
```

### 4.2 Clean Up Output Directories
```bash
# Remove legacy output directories
git rm -rf test_results/ || true
git rm -rf test-results/ || true
git rm -rf validation_output/ || true

# Add gitkeep files to new directories
echo "*" > data/.gitignore
echo "*" > .build/.gitignore  
echo "*" > .test/.gitignore
touch data/cache/.gitkeep
touch data/uploads/.gitkeep
touch data/logs/.gitkeep
```

## Phase 5: Reorganize Memory Bank

### 5.1 Restore Core Memory Bank Files
```bash
# Copy core files from archive to root (if they exist)
if [ -f "memory-bank/archive/projectbrief_2025-08-11.md" ]; then
    cp memory-bank/archive/projectbrief_2025-08-11.md memory-bank/projectbrief.md
fi

if [ -f "memory-bank/archive/productContext_2025-08-11.md" ]; then
    cp memory-bank/archive/productContext_2025-08-11.md memory-bank/productContext.md  
fi

if [ -f "memory-bank/archive/systemPatterns_2025-08-11.md" ]; then
    cp memory-bank/archive/systemPatterns_2025-08-11.md memory-bank/systemPatterns.md
fi

if [ -f "memory-bank/archive/techContext_2025-08-11.md" ]; then
    cp memory-bank/archive/techContext_2025-08-11.md memory-bank/techContext.md
fi

if [ -f "memory-bank/archive/activeContext_2025-08-11.md" ]; then
    cp memory-bank/archive/activeContext_2025-08-11.md memory-bank/activeContext.md
fi

if [ -f "memory-bank/archive/progress_2025-08-11.md" ]; then
    cp memory-bank/archive/progress_2025-08-11.md memory-bank/progress.md
fi
```

### 5.2 Organize Archive
```bash
# Move dated files to organized archive
git mv memory-bank/archive/*_2025-08-11.md memory-bank/archive/2025-08-11/ 2>/dev/null || true

# Move specialized docs to specialized directory
for doc in deployment_guide testing_plan testing_results unit_testing_framework_design; do
    if [ -f "memory-bank/archive/${doc}.md" ]; then
        git mv memory-bank/archive/${doc}.md memory-bank/specialized/
    fi
done
```

## Phase 6: Update Critical Configuration Files

### 6.1 Update Streamlit App
```bash
# Create updated app.py that imports from new structure
cat > app_new.py << 'EOF'
"""
Legal Document Analysis Portal - Main Streamlit Application
"""
import streamlit as st
import sys
from pathlib import Path

# Add src to Python path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import from new structure
from legal_portal.core.main_processor import process_case_documents
from legal_portal.config.settings import get_settings

# Continue with existing app.py content...
EOF

# Backup original and replace (manual step - needs content merge)
git mv app.py app_original.py
# Manual step: Merge app_new.py with app_original.py content
```

### 6.2 Update Requirements and Configuration
```bash
# Create pyproject.toml for modern Python packaging
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "legal-document-portal"
version = "1.0.0"
description = "Legal Document Analysis Portal"
authors = [{name = "Legal Portal Team"}]
dependencies = [
    "streamlit>=1.28.0",
    "openai>=1.3.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["legal_portal*"]

[tool.ruff]
line-length = 88
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "D", "UP"]
ignore = ["D100", "D101", "D102", "D103", "D104", "D105"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "legal_portal.*"
ignore_missing_imports = true
EOF
```

### 6.3 Update pytest Configuration
```bash
# Update pytest.ini for new structure
cat > pytest.ini << 'EOF'
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
pythonpath = src
addopts = 
    --verbose
    --tb=short
    --strict-markers
    --disable-warnings
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow tests
EOF
```

### 6.4 Update .gitignore
```bash
# Add new directories to .gitignore
cat >> .gitignore << 'EOF'

# Build and test artifacts
.build/
.test/
data/
*.egg-info/
dist/
build/
.coverage
.pytest_cache/

# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd
.Python

# Environment
.env
.venv/
venv/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
EOF
```

## Phase 7: Import Path Updates

### 7.1 Update Import Statements
```bash
# This requires a comprehensive find-and-replace operation
# Create a script to update all import statements

cat > scripts/migration/update_imports.py << 'EOF'
#!/usr/bin/env python3
"""
Update import statements for new package structure
"""
import os
import re
from pathlib import Path

def update_imports_in_file(file_path):
    """Update import statements in a single file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Import mappings
    mappings = {
        r'from core\.': 'from legal_portal.core.',
        r'import core\.': 'import legal_portal.core.',
        r'from services\.': 'from legal_portal.services.',
        r'import services\.': 'import legal_portal.services.',
        r'from utils\.': 'from legal_portal.utils.',
        r'import utils\.': 'import legal_portal.utils.',
        r'from config\.': 'from legal_portal.config.',
        r'import config\.': 'import legal_portal.config.',
        r'from config\.default': 'from legal_portal.config.settings',
        r'import config\.default': 'import legal_portal.config.settings',
    }
    
    # Apply mappings
    for old_pattern, new_pattern in mappings.items():
        content = re.sub(old_pattern, new_pattern, content)
    
    # Write back
    with open(file_path, 'w') as f:
        f.write(content)

def main():
    """Update all Python files."""
    # Find all Python files
    for root, dirs, files in os.walk('.'):
        # Skip certain directories
        if any(skip in root for skip in ['.git', '__pycache__', '.venv', 'venv']):
            continue
            
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                print(f"Updating: {file_path}")
                update_imports_in_file(file_path)

if __name__ == "__main__":
    main()
EOF

# Make script executable and run it
chmod +x scripts/migration/update_imports.py
python scripts/migration/update_imports.py
```

## Phase 8: Validation and Testing

### 8.1 Validate New Structure
```bash
# Check that all expected files exist
echo "Validating new structure..."

# Core files should exist
for file in main_processor.py ai_analyzer.py document_processor.py email_generator.py; do
    if [ ! -f "src/legal_portal/core/$file" ]; then
        echo "ERROR: Missing src/legal_portal/core/$file"
    else
        echo "✓ Found src/legal_portal/core/$file"
    fi
done

# Configuration should exist
if [ ! -f "src/legal_portal/config/settings.py" ]; then
    echo "ERROR: Missing src/legal_portal/config/settings.py"
else
    echo "✓ Found src/legal_portal/config/settings.py"
fi

# Tests should exist
if [ -d "tests/unit" ] && [ -d "tests/integration" ]; then
    echo "✓ Test structure created"
else
    echo "ERROR: Test structure missing"
fi
```

### 8.2 Test Application Startup
```bash
# Test that the application can import the new structure
python -c "
import sys
sys.path.insert(0, 'src')
try:
    from legal_portal.core.main_processor import process_case_documents
    from legal_portal.config.settings import get_settings
    print('✓ Import test passed')
except ImportError as e:
    print(f'✗ Import test failed: {e}')
"

# Test Streamlit app startup (if updated)
echo "Testing Streamlit app startup..."
timeout 10s streamlit run app.py --server.headless true --server.port 8502 &
APP_PID=$!
sleep 5
if kill -0 $APP_PID 2>/dev/null; then
    echo "✓ Streamlit app started successfully"
    kill $APP_PID
else
    echo "✗ Streamlit app failed to start"
fi
```

## Phase 9: Create Documentation Structure

### 9.1 Create Basic Documentation
```bash
# Create documentation structure
cat > docs/README.md << 'EOF'
# Legal Document Analysis Portal Documentation

## Structure

- [Architecture](architecture/) - System design and architecture
- [Development](development/) - Development guides and standards  
- [Deployment](deployment/) - Deployment and operations
- [User Guides](user_guides/) - End-user documentation
- [API](api/) - API and module documentation

## Quick Start

See [Development Setup Guide](development/setup_guide.md) for getting started.
EOF

# Create placeholder documentation files
touch docs/architecture/overview.md
touch docs/development/setup_guide.md
touch docs/deployment/local_development.md
touch docs/user_guides/getting_started.md
```

## Phase 10: Final Cleanup and Commit

### 10.1 Final Git Operations
```bash
# Add all new files
git add .

# Commit the refactor
git commit -m "feat: consolidate codebase into unified production structure

- Move all core modules to src/legal_portal/ package structure
- Consolidate configuration in src/legal_portal/config/
- Unify test structure under tests/ with unit/integration/e2e organization  
- Remove legacy backend/, backend_logic/, backend_backup/ directories
- Clean up duplicate output directories
- Create modern Python packaging with pyproject.toml
- Update import paths throughout codebase
- Establish docs/ structure for comprehensive documentation
- Add proper .gitignore for new directory structure

This refactor eliminates code duplication and establishes a clean,
maintainable, production-ready codebase structure."
```

### 10.2 Create Rollback Tag
```bash
# Create tag for this refactor state
git tag -a refactor-complete-v2 -m "Completed second consolidation refactor"
```

## Rollback Procedure

If issues are discovered, rollback using:

```bash
# Rollback to pre-refactor state
git checkout backup-pre-refactor-v2
git checkout -b rollback-branch

# Or reset to previous state
git reset --hard backup-pre-refactor-v2
```

## Post-Refactor Tasks

### Immediate Tasks
1. **Update CI/CD pipelines** to use new structure
2. **Update deployment scripts** for new package layout
3. **Run comprehensive test suite** to validate functionality  
4. **Update documentation** with new import patterns
5. **Verify all file paths** in configuration and scripts

### Validation Checklist
- [ ] Streamlit app starts without errors
- [ ] All imports resolve correctly
- [ ] Configuration loads properly
- [ ] Tests can be discovered and run
- [ ] No critical files missing
- [ ] Documentation structure complete

## Success Metrics

1. **Structure Compliance**: All code follows src/legal_portal/ pattern
2. **Import Consistency**: All imports use legal_portal.module pattern  
3. **Test Organization**: Tests properly organized in unit/integration/e2e
4. **Configuration Consolidation**: Single settings.py for all config
5. **Documentation Structure**: Comprehensive docs/ organization
6. **Application Functionality**: App starts and works as before
7. **No Duplication**: No redundant directories or files

This refactor plan transforms the fragmented codebase into a clean, maintainable, production-ready structure while preserving all functionality.