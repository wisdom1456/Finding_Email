#!/usr/bin/env python3
"""Collect performance baseline metrics before refactoring.

Run this script before each refactor phase to establish baselines.
Results are saved to docs/plans/baselines/ as timestamped JSON files.

Usage:
    python scripts/collect_performance_baseline.py [--phase PHASE_NAME]
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def measure_import_time() -> dict:
    """Measure how long it takes to import key modules."""
    results = {}
    modules = [
        "legal_portal.api.main",
        "legal_portal.core.data_models",
        "legal_portal.services.main_processor",
        "legal_portal.api.routes.analysis",
    ]
    for mod in modules:
        start = time.perf_counter()
        try:
            importlib.import_module(mod)
            elapsed = time.perf_counter() - start
            results[mod] = {"import_time_s": round(elapsed, 4), "status": "ok"}
        except Exception as e:
            elapsed = time.perf_counter() - start
            results[mod] = {"import_time_s": round(elapsed, 4), "status": f"error: {e}"}
    return results


def measure_test_suite_time() -> dict:
    """Measure total test suite runtime."""
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    elapsed = time.perf_counter() - start

    lines = result.stdout.strip().split("\n")
    summary_line = lines[-1] if lines else ""

    return {
        "total_time_s": round(elapsed, 2),
        "exit_code": result.returncode,
        "summary": summary_line,
    }


def measure_startup_time() -> dict:
    """Measure FastAPI app startup time in a subprocess."""
    script = (
        "import time; start = time.perf_counter(); "
        "from legal_portal.api.main import app; "
        "elapsed = time.perf_counter() - start; "
        "print(f'{elapsed:.4f}')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    try:
        startup_s = float(result.stdout.strip())
    except ValueError:
        startup_s = -1.0

    return {
        "startup_time_s": startup_s,
        "stderr": result.stderr[:500] if result.stderr else "",
    }


def measure_codebase_stats() -> dict:
    """Measure codebase size metrics."""
    src_root = Path(__file__).parent.parent / "src" / "legal_portal"
    test_root = Path(__file__).parent.parent / "tests"

    py_files = list(src_root.rglob("*.py"))
    test_files = list(test_root.rglob("*.py"))

    total_loc = 0
    for f in py_files:
        try:
            total_loc += len(f.read_text().splitlines())
        except Exception:
            pass

    test_loc = 0
    for f in test_files:
        try:
            test_loc += len(f.read_text().splitlines())
        except Exception:
            pass

    analysis_py = src_root / "api" / "routes" / "analysis.py"
    analysis_loc = len(analysis_py.read_text().splitlines()) if analysis_py.exists() else 0

    return {
        "source_files": len(py_files),
        "source_loc": total_loc,
        "test_files": len(test_files),
        "test_loc": test_loc,
        "analysis_py_loc": analysis_loc,
        "analysis_py_exists": analysis_py.exists(),
    }


def measure_memory_usage() -> dict:
    """Measure memory after importing the app."""
    script = (
        "import resource, json; "
        "from legal_portal.api.main import app; "
        "usage = resource.getrusage(resource.RUSAGE_SELF); "
        "print(json.dumps({'max_rss_kb': usage.ru_maxrss}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    try:
        # Filter out JSON log lines from app initialization, find the actual output
        output_lines = [l for l in result.stdout.strip().split("\n") if l and not l.startswith('{"timestamp"')]
        return json.loads(output_lines[-1]) if output_lines else {"max_rss_kb": -1}
    except (json.JSONDecodeError, ValueError, IndexError):
        return {"max_rss_kb": -1, "stderr": result.stderr[:500]}


def count_endpoints() -> dict:
    """Count registered FastAPI endpoints."""
    script = (
        "from legal_portal.api.main import app; "
        "routes = [r for r in app.routes if hasattr(r, 'methods')]; "
        "print(len(routes)); "
        "[print(f'{sorted(r.methods)} {r.path}') for r in sorted(routes, key=lambda r: r.path)]"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    # Filter out JSON log lines from app initialization
    lines = [l for l in result.stdout.strip().split("\n") if l and not l.startswith("{")]
    count = int(lines[0]) if lines else 0
    endpoints = lines[1:] if len(lines) > 1 else []

    return {
        "endpoint_count": count,
        "endpoints": endpoints,
    }


def main():
    parser = argparse.ArgumentParser(description="Collect performance baselines")
    parser.add_argument(
        "--phase",
        default="pre-refactor",
        help="Phase name (e.g., 'pre-refactor', 'phase-1')",
    )
    args = parser.parse_args()

    print(f"Collecting baseline metrics for phase: {args.phase}")
    print("=" * 60)

    metrics = {
        "phase": args.phase,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
    }

    print("  Measuring codebase stats...")
    metrics["codebase"] = measure_codebase_stats()

    print("  Measuring import times...")
    metrics["imports"] = measure_import_time()

    print("  Measuring app startup...")
    metrics["startup"] = measure_startup_time()

    print("  Counting endpoints...")
    metrics["endpoints"] = count_endpoints()

    print("  Measuring memory...")
    metrics["memory"] = measure_memory_usage()

    print("  Running test suite...")
    metrics["tests"] = measure_test_suite_time()

    # Save results
    baselines_dir = Path(__file__).parent.parent / "docs" / "plans" / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = baselines_dir / f"baseline-{args.phase}-{timestamp}.json"
    output_file.write_text(json.dumps(metrics, indent=2))

    print(f"\nResults saved to: {output_file}")
    print(f"\n{'=' * 60}")
    print(f"SUMMARY — {args.phase}")
    print(f"{'=' * 60}")
    print(f"  Source files:      {metrics['codebase']['source_files']}")
    print(f"  Source LOC:        {metrics['codebase']['source_loc']:,}")
    print(f"  analysis.py LOC:   {metrics['codebase']['analysis_py_loc']:,}")
    print(f"  Test files:        {metrics['codebase']['test_files']}")
    print(f"  Endpoint count:    {metrics['endpoints']['endpoint_count']}")
    print(f"  App startup:       {metrics['startup']['startup_time_s']}s")
    print(f"  Memory (RSS):      {metrics['memory'].get('max_rss_kb', '?')} KB")
    print(f"  Test suite:        {metrics['tests']['total_time_s']}s (exit {metrics['tests']['exit_code']})")


if __name__ == "__main__":
    main()
