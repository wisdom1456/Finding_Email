#!/usr/bin/env python3
"""Verify import dependency rules are not violated.

Enforces the architectural boundary: routes -> services -> core -> utils -> config

Usage:
    python scripts/check_import_rules.py
"""

import ast
import sys
from pathlib import Path

# (source_pattern, forbidden_import_pattern, rule_name)
RULES = [
    ("api/routes/", "api/routes/", "R1: route imports route"),
    ("services/", "api/routes/", "R2: service imports route"),
    ("services/", "api/dependencies", "R3: service imports dependencies"),
    ("utils/", "services/", "R4: utils imports service"),
    ("core/models/", "services/", "R5: model imports service"),
    ("core/", "api/", "R6: core imports api"),
    ("config/", "api/", "R7: config imports api"),
    ("config/", "services/", "R7: config imports service"),
    ("config/", "core/", "R7: config imports core"),
]

# Known exceptions
ALLOWED = {
    # R1: _analysis_helpers is a private module shared by analysis route files
    # After split, route files import from _analysis_helpers — this is allowed
    # because _analysis_helpers is a utility module, not a route handler
    ("api/routes/_analysis_helpers.py", "api/dependencies"),  # R9 exception
}

# Self-imports (same file) are always allowed
SELF_IMPORT_PATTERNS = [
    ("api/routes/__init__.py", "api/routes/"),
]


def check_file(filepath: Path, src_root: Path) -> list[str]:
    violations = []
    rel = str(filepath.relative_to(src_root))

    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        module = None

        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
        else:
            continue

        if not module or not module.startswith("legal_portal."):
            continue

        import_path = module.replace("legal_portal.", "").replace(".", "/")

        for src_pat, forbidden_pat, rule in RULES:
            if src_pat not in rel:
                continue
            if forbidden_pat not in import_path:
                continue

            # Check if it's a self-import (e.g., __init__.py importing its own submodules)
            is_self = any(
                sp in rel and fp in import_path
                for sp, fp in SELF_IMPORT_PATTERNS
            )
            if is_self:
                continue

            # Check allowed exceptions
            if (rel, import_path) in ALLOWED:
                continue

            # For R1, allow route files to import from _analysis_helpers
            if rule.startswith("R1") and "_analysis_helpers" in import_path:
                continue

            violations.append(f"  {rel}:{node.lineno} -> {module}  [{rule}]")

    return violations


def main():
    src_root = Path(__file__).parent.parent / "src" / "legal_portal"

    if not src_root.exists():
        print(f"ERROR: Source root not found: {src_root}")
        sys.exit(1)

    all_violations = []

    for py_file in src_root.rglob("*.py"):
        all_violations.extend(check_file(py_file, src_root))

    if all_violations:
        print(f"IMPORT VIOLATIONS ({len(all_violations)}):")
        for v in sorted(set(all_violations)):
            print(v)
        sys.exit(1)
    else:
        print("All import rules pass.")
        sys.exit(0)


if __name__ == "__main__":
    main()
