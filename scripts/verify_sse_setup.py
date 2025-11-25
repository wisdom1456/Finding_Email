#!/usr/bin/env python3
"""Quick verification script for SSE implementation."""

import sys
from pathlib import Path


def check_file_exists(filepath: str, description: str) -> bool:
    """Check if a file exists."""
    if Path(filepath).exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} MISSING: {filepath}")
        return False


def check_import(module_path: str, description: str) -> bool:
    """Check if a Python module can be imported."""
    try:
        __import__(module_path)
        print(f"✅ {description} imports successfully")
        return True
    except ImportError as e:
        print(f"❌ {description} FAILED: {e}")
        return False


def main():
    print("=" * 60)
    print("SSE Implementation Verification")
    print("=" * 60)
    print()

    checks_passed = 0
    checks_total = 0

    print("Backend Files:")
    print("-" * 60)
    checks = [
        ("src/legal_portal/services/progress_manager.py", "Progress Manager"),
        ("src/legal_portal/api/routes/progress.py", "Progress Router"),
    ]
    for filepath, desc in checks:
        checks_total += 1
        if check_file_exists(filepath, desc):
            checks_passed += 1

    print()
    print("Frontend Files:")
    print("-" * 60)
    checks = [
        ("frontend/src/lib/utils/sseClient.ts", "SSE Client"),
        ("frontend/src/lib/stores/progressStore.ts", "Progress Store"),
    ]
    for filepath, desc in checks:
        checks_total += 1
        if check_file_exists(filepath, desc):
            checks_passed += 1

    print()
    print("Python Imports:")
    print("-" * 60)

    # Check sse-starlette
    checks_total += 1
    if check_import("sse_starlette", "sse-starlette library"):
        checks_passed += 1
    else:
        print("   → Run: pip install sse-starlette==2.1.3")

    # Check progress manager
    checks_total += 1
    if check_import("legal_portal.services.progress_manager", "Progress Manager"):
        checks_passed += 1

    # Check progress router
    checks_total += 1
    if check_import("legal_portal.api.routes.progress", "Progress Router"):
        checks_passed += 1

    print()
    print("=" * 60)
    print(f"Results: {checks_passed}/{checks_total} checks passed")
    print("=" * 60)

    if checks_passed == checks_total:
        print()
        print("🎉 All checks passed! Ready to restart servers.")
        print()
        print("Next steps:")
        print("1. Restart backend: uvicorn src.legal_portal.api.main:app --reload")
        print("2. Restart frontend: cd frontend && npm run dev")
        return 0
    else:
        print()
        print("⚠️  Some checks failed. Review the errors above.")
        print()
        print("Common fixes:")
        print("- Install dependencies: pip install -r requirements.txt")
        print("- Check file paths are correct")
        return 1


if __name__ == "__main__":
    sys.exit(main())
