#!/usr/bin/env python3
"""Validate that endpoint count and paths are unchanged after refactoring.

Compares the current endpoint list against a saved baseline.
Exits with code 1 if any endpoints are missing or paths changed.

Usage:
    # Save baseline (run once before refactoring)
    python scripts/validate_endpoints.py --save-baseline

    # Validate against baseline (run after each phase)
    python scripts/validate_endpoints.py --check
"""

import argparse
import json
import sys
from pathlib import Path


BASELINE_FILE = (
    Path(__file__).parent.parent / "docs" / "plans" / "baselines" / "endpoint-baseline.json"
)


def get_current_endpoints() -> list[dict]:
    """Get all registered endpoints from the FastAPI app."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from legal_portal.api.main import app

    endpoints = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in sorted(route.methods):
                if method == "HEAD":
                    continue
                endpoints.append(
                    {
                        "method": method,
                        "path": route.path,
                        "name": getattr(route, "name", ""),
                    }
                )

    return sorted(endpoints, key=lambda e: (e["path"], e["method"]))


def save_baseline():
    endpoints = get_current_endpoints()
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps(endpoints, indent=2))
    print(f"Saved {len(endpoints)} endpoints to {BASELINE_FILE}")
    for ep in endpoints:
        print(f"  {ep['method']:6s} {ep['path']}")


def check_against_baseline():
    if not BASELINE_FILE.exists():
        print(f"ERROR: No baseline found at {BASELINE_FILE}")
        print("Run with --save-baseline first.")
        sys.exit(1)

    baseline = json.loads(BASELINE_FILE.read_text())
    current = get_current_endpoints()

    baseline_set = {(e["method"], e["path"]) for e in baseline}
    current_set = {(e["method"], e["path"]) for e in current}

    missing = baseline_set - current_set
    added = current_set - baseline_set

    if not missing and not added:
        print(f"PASS: All {len(baseline)} endpoints match baseline.")
        sys.exit(0)

    if missing:
        print(f"\nMISSING ENDPOINTS ({len(missing)}):")
        for method, path in sorted(missing):
            print(f"  - {method:6s} {path}")

    if added:
        print(f"\nNEW ENDPOINTS ({len(added)}):")
        for method, path in sorted(added):
            print(f"  + {method:6s} {path}")

    if missing:
        print(f"\nFAIL: {len(missing)} endpoint(s) missing from baseline.")
        sys.exit(1)
    else:
        print(
            f"\nWARN: {len(added)} new endpoint(s) added (not in baseline). "
            "No endpoints missing."
        )
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Validate endpoints against baseline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--save-baseline",
        action="store_true",
        help="Save current endpoints as baseline",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Check current endpoints against baseline",
    )
    args = parser.parse_args()

    if args.save_baseline:
        save_baseline()
    else:
        check_against_baseline()


if __name__ == "__main__":
    main()
