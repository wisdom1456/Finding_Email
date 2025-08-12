#!/bin/bash

# Post-Consolidation Fix Script
# Complete the migration that partially failed during consolidation

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1${NC}"
}

debug() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $1${NC}"
}

# Function to safely move files
safe_move() {
    local src="$1"
    local dest="$2"
    
    if [[ -f "$src" ]]; then
        debug "Moving: $src -> $dest"
        if mv "$src" "$dest" 2>/dev/null; then
            log "✅ Moved: $src -> $dest"
        else
            error "❌ Failed to move: $src -> $dest"
            return 1
        fi
    else
        warn "⚠️  Source file not found: $src"
    fi
}

# Function to safely copy files (fallback)
safe_copy() {
    local src="$1"
    local dest="$2"
    
    if [[ -f "$src" ]]; then
        debug "Copying: $src -> $dest"
        if cp "$src" "$dest" 2>/dev/null; then
            log "✅ Copied: $src -> $dest"
        else
            error "❌ Failed to copy: $src -> $dest"
            return 1
        fi
    else
        warn "⚠️  Source file not found: $src"
    fi
}

log "Starting post-consolidation fix..."

# Ensure we're in the right directory
if [[ ! -d "core" ]] || [[ ! -d "src/legal_portal" ]]; then
    error "❌ Not in the correct directory. Expected core/ and src/legal_portal/ to exist."
    exit 1
fi

log "=== Moving remaining core files ==="

# Move core files to src/legal_portal/core/
core_files=(
    "email_generator_core.py"
)

for file in "${core_files[@]}"; do
    safe_move "core/$file" "src/legal_portal/core/$file"
done

# Move service files to src/legal_portal/services/
service_files=(
    "text_processing_service.py"
    "content_extraction_service.py"
    "template_rendering_service.py"
    "content_generation_service.py"
    "content_formatting_service.py"
    "fallback_generation_service.py"
    "citation_tracking_service.py"
    "json_architecture_service.py"
    "json_processing_service.py"
    "openai_integration_service.py"
    "prompt_and_api_service.py"
)

for file in "${service_files[@]}"; do
    safe_move "core/$file" "src/legal_portal/services/$file"
done

# Move utility files to src/legal_portal/utils/
util_files=(
    "audit_logger.py"
    "structured_logger.py"
    "cache_manager.py"
    "security.py"
    "session_manager.py"
    "token_manager.py"
    "cost_calculator.py"
    "cost_estimator.py"
    "cost_exporter.py"
    "cost_session_manager.py"
    "validators.py"
    "helpers.py"
    "shared_utils.py"
    "pii_sanitizer.py"
    "enhanced_file_validator.py"
    "metrics.py"
    "tracing.py"
    "logging_config.py"
)

for file in "${util_files[@]}"; do
    safe_move "core/$file" "src/legal_portal/utils/$file"
done

# Move config files to src/legal_portal/config/
config_files=(
    "config_and_template_loader.py"
    "config_manager.py"
    "configuration_manager.py"
)

for file in "${config_files[@]}"; do
    safe_move "core/$file" "src/legal_portal/config/$file"
done

# Move file_processors directory
if [[ -d "core/file_processors" ]]; then
    log "Moving file_processors directory..."
    if mv "core/file_processors" "src/legal_portal/services/" 2>/dev/null; then
        log "✅ Moved: core/file_processors -> src/legal_portal/services/"
    else
        error "❌ Failed to move file_processors directory"
    fi
fi

log "=== Moving remaining files to appropriate locations ==="

# Move remaining core files that don't fit the main categories
remaining_files=(
    "ai_analyzer_refactored.py"
    "api_optimizer.py"
    "async_processor.py"
    "async_streamlit.py"
    "audio_processor.py"
    "auth.py"
    "data_models.py"
    "email_generator_v2.py"
    "email_generator.py"
    "main_processor.py"
    "media_processor.py"
    "oauth.py"
    "openai_client.py"
    "prompt_builder.py"
    "timeline_analyzer.py"
    "video_processor.py"
)

for file in "${remaining_files[@]}"; do
    if [[ -f "core/$file" ]]; then
        # Determine appropriate location based on file type
        if [[ "$file" == *"_service.py" ]] || [[ "$file" == "main_processor.py" ]] || [[ "$file" == "*_processor.py" ]]; then
            safe_move "core/$file" "src/legal_portal/services/$file"
        elif [[ "$file" == "auth.py" ]] || [[ "$file" == "oauth.py" ]] || [[ "$file" == "data_models.py" ]]; then
            safe_move "core/$file" "src/legal_portal/core/$file"
        else
            safe_move "core/$file" "src/legal_portal/utils/$file"
        fi
    fi
done

log "=== Creating setup.py for proper package installation ==="

cat > setup.py << 'EOF'
from setuptools import setup, find_packages

setup(
    name="legal-portal",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "streamlit",
        "openai",
        "python-dotenv",
        "pyyaml",
        "requests",
        # Add other dependencies as needed
    ],
)
EOF

log "✅ Created setup.py"

log "=== Creating PYTHONPATH configuration ==="

# Create a .env file to set PYTHONPATH
cat > .env << 'EOF'
# Python path configuration for src-layout
PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
EOF

log "✅ Created .env file for PYTHONPATH"

# Update pyproject.toml to ensure proper package discovery
log "=== Updating pyproject.toml ==="

cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "legal-portal"
version = "0.1.0"
description = "Legal Document Analysis Portal"
requires-python = ">=3.8"
dependencies = [
    "streamlit>=1.28.0",
    "openai>=1.0.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = "src"
EOF

log "✅ Updated pyproject.toml"

log "=== Validating new structure ==="

# Check if key files exist in new locations
key_files=(
    "src/legal_portal/__init__.py"
    "src/legal_portal/core/__init__.py"
    "src/legal_portal/services/__init__.py"
    "src/legal_portal/utils/__init__.py"
    "src/legal_portal/config/__init__.py"
    "src/legal_portal/core/ai_analyzer.py"
    "src/legal_portal/core/document_processor.py"
)

validation_errors=0
for file in "${key_files[@]}"; do
    if [[ ! -f "$file" ]]; then
        error "❌ Missing required file: $file"
        ((validation_errors++))
    else
        debug "✅ Found: $file"
    fi
done

if [[ $validation_errors -eq 0 ]]; then
    log "✅ Structure validation passed"
else
    error "❌ Structure validation failed with $validation_errors errors"
fi

log "=== Creating Python path helper script ==="

cat > run_app.sh << 'EOF'
#!/bin/bash

# Helper script to run the Streamlit app with correct Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

echo "Starting Streamlit app with PYTHONPATH: $PYTHONPATH"
streamlit run app/main.py "$@"
EOF

chmod +x run_app.sh

log "✅ Created run_app.sh helper script"

log "=== Post-consolidation fix completed ==="
log "Next steps:"
log "1. Run: export PYTHONPATH=\"\${PYTHONPATH}:\$(pwd)/src\""
log "2. Test: python -c \"import legal_portal; print('Import successful')\""
log "3. Run app: ./run_app.sh"

log "✅ Post-consolidation fix completed successfully!"