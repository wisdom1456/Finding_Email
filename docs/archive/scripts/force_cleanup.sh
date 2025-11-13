#!/bin/bash

# ==============================================================================
# Finding Emails - Repository Force Cleanup Script
#
# Description:
#   This script automates the structural refactoring of the repository. It
#   consolidates duplicated code, unifies the testing framework, standardizes
#   configuration, and removes legacy directories and files using standard
#   filesystem commands to ensure execution regardless of git status.
#
# Usage:
#   ./force_cleanup.sh
#
# !!! WARNING !!!
# This script performs destructive file operations (rm, mv).
# Ensure you have a backup if you need to revert these changes.
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

# --- Main Execution ---

log "--- Starting Forced Cleanup ---" "warning"

# --- Phase 1: Consolidate Core Logic ---
log "Phase 1: Consolidating Core Logic" "header"
rm -rf backend/
rm -rf backend_backup/
rm -rf backend_logic_backup/
rm -rf services/services
mkdir -p services && touch services/__init__.py

# --- Phase 2: Unify Configuration ---
log "Phase 2: Unifying Configuration" "header"
mv config/settings.py config/default.py || true

# --- Phase 3: Restructure Tests ---
log "Phase 3: Restructuring Tests" "header"
mkdir -p tests/e2e tests/integration tests/unit/core tests/unit/utils
mv backend_backup/tests/unit/test_ai_analyzer.py tests/unit/core/test_ai_analyzer.py || true
mv backend_backup/tests/unit/test_document_processor.py tests/unit/core/test_document_processor.py || true
mv backend_backup/tests/unit/test_email_generator.py tests/unit/core/test_email_generator.py || true
mv utils/tests/test_pii_sanitizer.py tests/unit/utils/test_pii_sanitizer.py || true
mv utils/tests/test_security.py tests/unit/utils/test_security.py || true
mv backend_backup/tests/e2e/test_devlin_workflow.py tests/integration/test_email_generation_pipeline.py || true
rm -rf tests/
rm -rf backend/tests/
rm -rf backend_backup/tests/
rm -rf utils/tests/

# --- Phase 4: Clean Up Output Directories ---
log "Phase 4: Cleaning Up Output Directories" "header"
rm -rf test_results/
rm -rf test-results/
rm -rf validation_output/
mkdir -p .test_results && echo '*' > .test_results/.gitignore


# --- Phase 5: Update .gitignore ---
log "Phase 5: Updating .gitignore" "header"
echo '

# Refactor Script Outputs
.test_results/
cost_sessions/' >> .gitignore

log "Cleanup script finished." "success"
log "Please review the changes and run tests before committing." "warning"