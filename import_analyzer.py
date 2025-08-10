#!/usr/bin/env python3
"""
Import Dependency Analyzer for Code Path Efficiency Analysis
Analyzes Python files to identify unused imports and dependencies
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Dict, List

from utils.logging_config import setup_logging


logger = setup_logging("import_analyzer")


class ImportAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.imports = {}  # {module_name: line_number}
        self.from_imports = {}  # {(module, name): line_number}
        self.used_names = set()  # Names used in the code

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports[name] = node.lineno

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.from_imports[(module, name)] = node.lineno

    def visit_Name(self, node):
        self.used_names.add(node.id)

    def visit_Attribute(self, node):
        # Handle module.attribute usage
        if isinstance(node.value, ast.Name):
            self.used_names.add(node.value.id)
        self.generic_visit(node)


def analyze_file(file_path: Path) -> Dict:
    """Analyze a single Python file for import usage"""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)
        analyzer = ImportAnalyzer()
        analyzer.visit(tree)

        # Find unused imports
        unused_imports = []
        for name, line_no in analyzer.imports.items():
            if name not in analyzer.used_names:
                unused_imports.append({"type": "import", "name": name, "line": line_no})

        # Find unused from imports
        for (module, name), line_no in analyzer.from_imports.items():
            if name not in analyzer.used_names and name != "*":
                unused_imports.append(
                    {
                        "type": "from_import",
                        "module": module,
                        "name": name,
                        "line": line_no,
                    }
                )

        return {
            "file": str(file_path),
            "total_imports": len(analyzer.imports) + len(analyzer.from_imports),
            "unused_imports": unused_imports,
            "import_count": len(analyzer.imports),
            "from_import_count": len(analyzer.from_imports),
        }

    except Exception as e:
        return {
            "file": str(file_path),
            "error": str(e),
            "total_imports": 0,
            "unused_imports": [],
        }


def find_python_files(root_dir: Path, exclude_dirs: List[str] = None) -> List[Path]:
    """Find all Python files, excluding specified directories"""
    if exclude_dirs is None:
        exclude_dirs = [
            ".ruff_cache",
            "__pycache__",
            ".git",
            "test_data",
            "validation_output",
        ]

    python_files = []
    for root, dirs, files in os.walk(root_dir):
        # Remove excluded directories from search
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            if file.endswith(".py"):
                python_files.append(Path(root) / file)

    return python_files


def main():
    """Main analysis function"""
    root_dir = Path()
    python_files = find_python_files(root_dir)

    logger.info(
        f"🔍 Analyzing {len(python_files)} Python files for import efficiency..."
    )

    results = []
    total_unused = 0
    files_with_unused = 0

    for file_path in python_files:
        analysis = analyze_file(file_path)
        if "error" not in analysis:
            results.append(analysis)
            if analysis["unused_imports"]:
                files_with_unused += 1
                total_unused += len(analysis["unused_imports"])

    # Sort by number of unused imports (descending)
    results.sort(key=lambda x: len(x["unused_imports"]), reverse=True)

    logger.info("\n📊 IMPORT ANALYSIS SUMMARY")
    logger.info(f"├── Total Python files analyzed: {len(results)}")
    logger.info(f"├── Files with unused imports: {files_with_unused}")
    logger.info(f"├── Total unused imports found: {total_unused}")
    logger.info(
        f"└── Efficiency opportunity: {total_unused} import statements can be removed"
    )

    # Display detailed results
    logger.info("\n🔧 DETAILED FINDINGS:")

    for result in results:
        if result["unused_imports"]:
            logger.info(f"\n📁 {result['file']}")
            logger.info(f"   └── {len(result['unused_imports'])} unused imports:")

            for unused in result["unused_imports"]:
                if unused["type"] == "import":
                    logger.info(
                        f"       ├── Line {unused['line']}: import {unused['name']}"
                    )
                else:
                    logger.info(
                        f"       ├── Line {unused['line']}: from {unused['module']} import {unused['name']}"
                    )

    # Focus on backend_logic files specifically
    backend_files = [
        r for r in results if "backend_logic" in r["file"] and r["unused_imports"]
    ]
    if backend_files:
        logger.info(
            f"\n🎯 BACKEND_LOGIC FOCUS ({len(backend_files)} files with issues):"
        )
        for result in backend_files:
            logger.info(
                f"   📁 {result['file']}: {len(result['unused_imports'])} unused imports"
            )

    # Save detailed results to JSON for further analysis
    with open("import_analysis_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("\n💾 Detailed results saved to: import_analysis_results.json")

    return results


if __name__ == "__main__":
    main()
