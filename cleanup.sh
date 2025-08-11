#!/bin/bash

# ==============================================================================
# Finding Emails - Repository Cleanup and Refactoring Script (v3)
#
# Description:
#   This script automates the structural refactoring of the repository. It
#   consolidates duplicated code, unifies the testing framework, standardizes
#   configuration, and removes legacy directories and files.
#   Version 3 uses 'git rm -rf' to forcefully remove directories with
#   uncommitted local changes.
#
# Usage:
#   ./cleanup.sh [--dry-run | --execute]
#
# Options:
#   --dry-run   : Print the commands that would be executed without running them.
#   --execute   : Execute the refactoring commands.
#
# !!! WARNING !!!
# This script performs destructive file operations (git rm, git mv).
# Ensure your working directory is clean and all changes are committed
# before running with the --execute flag.
# ==============================================================================

# --- Configuration ---
set -e # Exit immediately if a command exits with a non-zero status.

# --- Functions ---

# Print a message to the console.
# @param {string} message - The message to print.
# @param {string} type - The type of message (header, success, error, warning, info).
function log() {
    local message="$1"
    local type="${2:-info}"
    local color_header="\033[1;35m" # Magenta
    local color_success="\033[1;32m" # Green
    local color_error="\033[1;31m"   # Red
    local color_warning="\033[1;33m" # Yellow
    local color_info="\033[0;36m"    # Cyan
    local color_reset="\033[0m"

    case "$type" in
        header)
            printf "
${color_header}=== %s ===${color_reset}
" "$message"
            ;;
        success)
            printf "${color_success}✔ %s${color_reset}
" "$message"
            ;;
        error)
            printf "${color_error}✖ %s${color_reset}
" "$message" >&2
            ;;
        warning)
            printf "${color_warning}⚠ %s${color_reset}
" "$message"
            ;;
        *)
            printf "${color_info}  %s${color_reset}
" "$message"
            ;;
    esac
}

# Execute a command or print it if in dry-run mode.
# @param {string} cmd - The command to execute.
function run_cmd() {
    local cmd="$1"
    log "$cmd"
    if [ "$DRY_RUN" = "false" ]; then
        eval "$cmd" || true
    fi
}

# --- Main Execution ---

# Parse command-line arguments
if [ "$1" == "--dry-run" ]; then
    DRY_RUN="true"
    log "--- DRY RUN MODE ---" "warning"
elif [ "$1" == "--execute" ]; then
    DRY_RUN="false"
    log "--- EXECUTE MODE ---" "warning"
    log "This will permanently alter the repository structure." "error"
    read -p "Are you sure you want to continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Execution cancelled." "error"
        exit 1
    fi
else
    log "Usage: ./cleanup.sh [--dry-run | --execute]" "error"
    exit 1
fi


# --- Phase 1: Consolidate Core Logic ---
log "Phase 1: Consolidating Core Logic" "header"
run_cmd "git rm -rf backend/"
run_cmd "git rm -rf backend_backup/"
run_cmd "git rm -rf backend_logic_backup/"
run_cmd "git rm -rf services/services"
run_cmd "mkdir -p services && touch services/__init__.py"

# --- Phase 2: Unify Configuration ---
log "Phase 2: Unifying Configuration" "header"
run_cmd "git mv config/settings.py config/default.py"

# --- Phase 3: Restructure Tests ---
log "Phase 3: Restructuring Tests" "header"
run_cmd "mkdir -p tests/e2e tests/integration tests/unit/core tests/unit/utils"
run_cmd "git mv backend_backup/tests/unit/test_ai_analyzer.py tests/unit/core/test_ai_analyzer.py || true"
run_cmd "git mv backend_backup/tests/unit/test_document_processor.py tests/unit/core/test_document_processor.py || true"
run_cmd "git mv backend_backup/tests/unit/test_email_generator.py tests/unit/core/test_email_generator.py || true"
run_cmd "git mv utils/tests/test_pii_sanitizer.py tests/unit/utils/test_pii_sanitizer.py || true"
run_cmd "git mv utils/tests/test_security.py tests/unit/utils/test_security.py || true"
run_cmd "git mv backend_backup/tests/e2e/test_devlin_workflow.py tests/integration/test_email_generation_pipeline.py || true"
run_cmd "git rm -rf tests/"
run_cmd "git rm -rf backend/tests/"
run_cmd "git rm -rf backend_backup/tests/"
run_cmd "git rm -rf utils/tests/"

# --- Phase 4: Clean Up Output Directories ---
log "Phase 4: Cleaning Up Output Directories" "header"
run_cmd "git rm -rf test_results/"
run_cmd "git rm -rf test-results/"
run_cmd "git rm -rf validation_output/"
run_cmd "mkdir -p .test_results && echo '*' > .test_results/.gitignore"


# --- Phase 5: Update .gitignore ---
log "Phase 5: Updating .gitignore" "header"
run_cmd "echo '

# Refactor Script Outputs
.test_results/
cost_sessions/' >> .gitignore"

log "Cleanup script finished." "success"
log "Please review the changes and run tests before committing." "warning"
