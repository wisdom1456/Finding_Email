#!/bin/bash

# ==============================================================================
# Legal Document Analysis Portal - Streamlit Application Startup Script
# ==============================================================================
# This script provides startup of the Streamlit application with proper
# environment validation for the Legal Document Analysis Portal.
#
# Usage: ./start_app.sh [options]
# Options:
#   --help, -h     Show this help message
#   --check-only   Only check dependencies and environment, don't start services
#   --kill-only    Only kill existing processes, don't start new ones
#   --verbose, -v  Enable verbose output
#
# Architecture:
#   Streamlit Application: http://localhost:8501
# ==============================================================================

set -e  # Exit on any error

# --- Configuration ---
FRONTEND_PORT=8501
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERBOSE=false

# ANSI color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# --- Helper Functions ---

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${PURPLE}[VERBOSE]${NC} $1"
    fi
}

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

show_help() {
    cat << EOF
Legal Document Analysis Portal - Startup Script

USAGE:
    ./start_app.sh [options]

OPTIONS:
    --help, -h      Show this help message
    --check-only    Only check dependencies and environment, don't start services
    --kill-only     Only kill existing processes, don't start new ones
    --verbose, -v   Enable verbose output

DESCRIPTION:
    This script starts the Legal Document Analysis Portal Streamlit application
    with proper environment validation.

    The script performs the following operations:
    1. Validates environment variables from .env file
    2. Checks system dependencies (Python, pip, required packages)
    3. Terminates any existing processes on port 8501
    4. Starts the Streamlit application

ENVIRONMENT VARIABLES:
    Required:
        OPENAI_API_KEY     OpenAI API key for document analysis

    Optional:
        PDFCO_API_KEY      PDF.co API key for document processing

PORTS:
    Streamlit Application: http://localhost:8501

STOPPING SERVICES:
    To stop the application, use:
        ./kill_server.sh 8501    # Stop Streamlit app

    Or close the terminal window manually.

EXAMPLES:
    ./start_app.sh                    # Normal startup
    ./start_app.sh --verbose          # Startup with detailed output
    ./start_app.sh --check-only       # Only validate environment
    ./start_app.sh --kill-only        # Only stop existing services

EOF
}

check_macos() {
    if [[ "$OSTYPE" != "darwin"* ]]; then
        log_warning "This script is optimized for macOS. Some features may not work on other systems."
        return 1
    fi
    return 0
}

check_command() {
    local cmd=$1
    local package=$2
    if ! command -v "$cmd" &> /dev/null; then
        log_error "$cmd not found. Please install $package"
        return 1
    fi
    log_verbose "$cmd found: $(command -v $cmd)"
    return 0
}

kill_process_on_port() {
    local port=$1
    log_step "Checking for existing processes on port $port..."

    local pid=$(lsof -t -i:$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        log_warning "Found process $pid on port $port. Terminating..."
        kill -9 $pid 2>/dev/null || true
        sleep 1

        # Double-check if process is still running
        if lsof -t -i:$port &> /dev/null; then
            log_error "Failed to terminate process on port $port"
            return 1
        else
            log_success "Process on port $port terminated"
        fi
    else
        log_verbose "No process found on port $port"
    fi
    return 0
}

validate_env_file() {
    log_step "Validating environment configuration..."

    if [ ! -f ".env" ]; then
        log_error ".env file not found!"
        log_info "Please copy .env.template to .env and configure your API keys:"
        log_info "  cp .env.template .env"
        log_info "  # Edit .env with your API keys"
        return 1
    fi

    log_verbose "Found .env file, loading environment variables..."

    # Load environment variables with proper parsing
    set -a  # automatically export all variables
    source .env 2>/dev/null || {
        log_error "Failed to load .env file. Please check syntax."
        return 1
    }
    set +a  # disable automatic export

    # Validate required environment variables
    local required_vars=("OPENAI_API_KEY")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        else
            log_verbose "$var is configured"
        fi
    done

    if [ ${#missing_vars[@]} -gt 0 ]; then
        log_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            log_error "  - $var"
        done
        log_info "Please update your .env file with the required values."
        return 1
    fi

    # Validate API key format (basic check)
    if [[ ! "$OPENAI_API_KEY" =~ ^sk-proj- ]] && [[ ! "$OPENAI_API_KEY" =~ ^sk- ]]; then
        log_warning "OPENAI_API_KEY format appears invalid (should start with 'sk-' or 'sk-proj-')"
    fi

    log_success "Environment variables validated successfully"
    return 0
}

check_dependencies() {
    log_step "Checking system dependencies..."

    local failed=false

    # Set required environment variables for WeasyPrint and other system dependencies
    export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
    log_verbose "Set DYLD_LIBRARY_PATH for WeasyPrint system dependencies"

    # Check basic system requirements
    check_command "python3" "Python 3" || failed=true
    check_command "pip3" "pip (Python package manager)" || failed=true

    # Check for Streamlit
    if ! DYLD_LIBRARY_PATH="$DYLD_LIBRARY_PATH" python3 -c "import streamlit" 2>/dev/null; then
        log_error "Streamlit not found. Install with: pip3 install streamlit"
        failed=true
    else
        log_verbose "Streamlit is installed"
    fi

    # Check for application dependencies in requirements.txt
    if [ -f "requirements.txt" ]; then
        log_verbose "Checking application dependencies..."
        local missing_packages=()

        while IFS= read -r package; do
            # Skip empty lines and comments
            [[ -z "$package" || "$package" =~ ^#.*$ ]] && continue

            # Extract package name (before any version specifiers)
            local pkg_name=$(echo "$package" | sed 's/[<>=!].*//' | sed 's/\[.*\]//')

            # Map pip package names to Python import names
            local import_name="$pkg_name"
            case "$pkg_name" in
                "python-multipart") import_name="multipart" ;;
                "python-dotenv") import_name="dotenv" ;;
                "python-docx") import_name="docx" ;;
                "python-magic") import_name="magic" ;;
                "PyMuPDF") import_name="fitz" ;;
                "pydantic-settings") import_name="pydantic_settings" ;;
                "Pillow") import_name="PIL" ;;
                "sseclient-py") import_name="sseclient" ;;
            esac

            log_verbose "Testing import for package: $pkg_name (import as: $import_name)"

            # Use environment variable for packages that need system libraries (like WeasyPrint)
            if ! DYLD_LIBRARY_PATH="$DYLD_LIBRARY_PATH" python3 -c "import $import_name" 2>/dev/null; then
                log_verbose "❌ Failed to import: $pkg_name"
                missing_packages+=("$package")
            else
                log_verbose "✅ Successfully imported: $pkg_name"
            fi
        done < "requirements.txt"

        if [ ${#missing_packages[@]} -gt 0 ]; then
            log_warning "Missing application dependencies:"
            for missing_pkg in "${missing_packages[@]}"; do
                log_warning "  - $missing_pkg"
            done
            log_info "Install with: pip3 install -r requirements.txt"
            failed=true
        else
            log_verbose "All application dependencies are installed"
        fi
    else
        log_warning "requirements.txt not found"
    fi

    if [ "$failed" = true ]; then
        log_error "Dependency check failed. Please install missing dependencies."
        return 1
    fi

    log_success "All dependencies satisfied"
    return 0
}

wait_for_backend() {
    log_step "Waiting for backend to become ready..."

    local attempt=0
    local max_attempts=$((BACKEND_STARTUP_TIMEOUT / HEALTH_CHECK_INTERVAL))

    while [ $attempt -lt $max_attempts ]; do
        log_verbose "Health check attempt $((attempt + 1))/$max_attempts"

        if curl -s "http://localhost:$BACKEND_PORT/docs" > /dev/null 2>&1; then
            log_success "Backend is ready at http://localhost:$BACKEND_PORT"
            return 0
        fi

        sleep $HEALTH_CHECK_INTERVAL
        attempt=$((attempt + 1))
    done

    log_error "Backend failed to start within $BACKEND_STARTUP_TIMEOUT seconds"
    log_info "Check the backend terminal for error messages"
    return 1
}

start_backend() {
    log_step "Starting FastAPI backend server..."

    # Verify backend directory and main.py exist
    if [ ! -d "backend" ]; then
        log_error "Backend directory not found"
        return 1
    fi

    if [ ! -f "backend/main.py" ]; then
        log_error "Backend main.py not found"
        return 1
    fi

    # Create backend startup script with proper environment loading
    local backend_script=$(cat << 'EOF'
#!/bin/bash
echo "🚀 Starting FastAPI Backend Server"
echo "=================================="
echo "Port: 8000"
echo "API Documentation: http://localhost:8000/docs"
echo "Environment: Development"
echo ""

# Load environment variables
if [ -f ../.env ]; then
    echo "📄 Loading environment variables from .env..."
    set -a
    source ../.env
    set +a
    echo "✅ Environment variables loaded"
else
    echo "⚠️  Warning: .env file not found"
fi

# Set library path for WeasyPrint and other system dependencies
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
echo "✅ Set DYLD_LIBRARY_PATH for system dependencies"

echo ""
echo "🔧 Starting uvicorn server..."
echo "Press Ctrl+C to stop the server"
echo ""

cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
EOF
    )

    # Check if we're on macOS for Terminal.app integration
    if check_macos; then
        log_verbose "Using macOS Terminal.app for backend"

        # Create temporary script file
        local temp_script="/tmp/start_backend_$$"
        echo "$backend_script" > "$temp_script"
        chmod +x "$temp_script"

        # Open new Terminal window with the backend script
        osascript << EOF
tell application "Terminal"
    do script "cd '$SCRIPT_DIR' && $temp_script; rm -f $temp_script"
    activate
end tell
EOF
    else
        log_verbose "Using generic terminal approach"
        # Fallback for non-macOS systems
        echo "$backend_script" | bash &
    fi

    # Wait for backend to be ready
    wait_for_backend || return 1

    log_success "Backend started successfully"
    return 0
}

start_frontend() {
    log_step "Starting Streamlit application..."

    # Verify app.py exists
    if [ ! -f "app.py" ]; then
        log_error "Application app.py not found"
        return 1
    fi

    # Create application startup script
    local app_script=$(cat << 'EOF'
#!/bin/bash
echo "🎨 Starting Legal Document Analysis Portal"
echo "=========================================="
echo "Port: 8501"
echo "Application URL: http://localhost:8501"
echo ""

# Load environment variables
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env..."
    set -a
    source .env
    set +a
    echo "✅ Environment variables loaded"
else
    echo "⚠️  Warning: .env file not found"
fi

# Set library path for WeasyPrint and other system dependencies
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
echo "✅ Set DYLD_LIBRARY_PATH for system dependencies"

echo ""
echo "🚀 Launching Streamlit application..."
echo "The browser should open automatically"
echo "Press Ctrl+C to stop the application"
echo ""

python3 -m streamlit run app.py --server.port 8501 --server.headless false
EOF
    )

    # Check if we're on macOS for Terminal.app integration
    if check_macos; then
        log_verbose "Using macOS Terminal.app for application"

        # Create temporary script file
        local temp_script="/tmp/start_app_$$"
        echo "$app_script" > "$temp_script"
        chmod +x "$temp_script"

        # Open new Terminal window with the application script
        osascript << EOF
tell application "Terminal"
    do script "cd '$SCRIPT_DIR' && $temp_script; rm -f $temp_script"
    activate
end tell
EOF
    else
        log_verbose "Using generic terminal approach"
        # Fallback for non-macOS systems
        echo "$app_script" | bash &
    fi

    log_success "Application started successfully"
    return 0
}

cleanup() {
    log_step "Cleaning up temporary files..."
    rm -f "/tmp/start_app_$$" 2>/dev/null || true
}

# --- Main Script Logic ---

main() {
    local check_only=false
    local kill_only=false

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --check-only)
                check_only=true
                shift
                ;;
            --kill-only)
                kill_only=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                log_info "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    # Set trap for cleanup
    trap cleanup EXIT

    echo ""
    echo "🏛️  Legal Document Analysis Portal"
    echo "=================================="
    echo "Streamlit Application Environment"
    echo ""

    # Kill existing processes if requested or as part of normal startup
    if [ "$kill_only" = true ] || [ "$check_only" = false ]; then
        kill_process_on_port $FRONTEND_PORT || exit 1

        if [ "$kill_only" = true ]; then
            log_success "Application processes terminated"
            exit 0
        fi
    fi

    # Validate environment and dependencies
    validate_env_file || exit 1
    check_dependencies || exit 1

    if [ "$check_only" = true ]; then
        log_success "All checks passed. Environment is ready for startup."
        exit 0
    fi

    # Start application
    echo ""
    log_info "🚀 Starting Legal Document Analysis Portal..."
    echo ""

    # Start the Streamlit application
    start_application || {
        log_error "Failed to start application."
        exit 1
    }

    echo ""
    log_success "🎉 Startup complete!"
    echo ""
    echo "📋 Application Information:"
    echo "  📱 Application: http://localhost:$FRONTEND_PORT"
    echo ""
    echo "💡 Usage Instructions:"
    echo "  • A new terminal window has opened for the application"
    echo "  • The Streamlit app should open in your browser automatically"
    echo "  • The application will reload automatically when you make changes"
    echo "  • Press Ctrl+C in the terminal to stop the application"
    echo ""
    echo "🛑 To stop the application:"
    echo "  ./kill_server.sh $FRONTEND_PORT   # Stop application"
    echo ""

    # Give final instructions
    log_info "✨ Ready for development! Check the terminal window for application output."
}

# Execute main function with all arguments
main "$@"
