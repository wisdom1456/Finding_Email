#!/usr/bin/env bash
# Run all validation checks after a refactor phase.
# Usage: ./scripts/validate_refactor.sh [phase-name]

set -euo pipefail

PHASE="${1:-unknown}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check() {
    local label="$1"
    shift
    printf "  %-45s" "$label"
    if "$@" > /tmp/refactor_check_output 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
    else
        echo -e "${RED}FAIL${NC}"
        head -5 /tmp/refactor_check_output
        ((FAIL++))
    fi
}

warn_check() {
    local label="$1"
    shift
    printf "  %-45s" "$label"
    if "$@" > /tmp/refactor_check_output 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
    else
        echo -e "${YELLOW}WARN${NC}"
        head -3 /tmp/refactor_check_output
        ((WARN++))
    fi
}

echo "=========================================="
echo "  Refactor Validation - Phase: $PHASE"
echo "=========================================="
echo ""

echo "1. Import Checks"
check "App imports cleanly"              python -c "from legal_portal.api.main import app"
check "All route modules import"         python -c "from legal_portal.api.routes import analysis"
warn_check "Import rules pass"           python scripts/check_import_rules.py

echo ""
echo "2. Test Suite"
check "Unit tests pass"                  python -m pytest tests/unit/ -x -q --tb=short
check "API tests pass"                   python -m pytest tests/api/ -x -q --tb=short
warn_check "Integration tests pass"      python -m pytest tests/integration/ -x -q --tb=short

echo ""
echo "3. Endpoint Validation"
check "Endpoint count unchanged"         python scripts/validate_endpoints.py --check

echo ""
echo "4. Syntax & Structure"
check "No syntax errors in main.py"      python -m py_compile src/legal_portal/api/main.py
warn_check "No circular imports"         python -c "
import sys
sys.path.insert(0, 'src')
from legal_portal.api.routes import analysis
from legal_portal.api.routes import cases
from legal_portal.api.routes import documents
from legal_portal.api.routes import clio
print('All route imports OK')
"

echo ""
echo "=========================================="
echo -e "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VALIDATION FAILED - DO NOT MERGE${NC}"
    exit 1
else
    echo -e "${GREEN}VALIDATION PASSED${NC}"
    exit 0
fi
