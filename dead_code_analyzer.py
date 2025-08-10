#!/usr/bin/env python3
"""
Dead Code Path Analyzer for Code Path Efficiency Analysis
Analyzes Python files to identify functions, methods, and classes that are never called
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Set

from utils.logging_config import setup_logging


logger = setup_logging("dead_code_analyzer")


class DeadCodeAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.definitions = {}  # {name: {'type': 'function/method/class', 'line': int, 'file': str}}
        self.calls = set()  # Set of called function/method names
        self.attributes = set()  # Set of attribute accesses
        self.current_file = ""
        self.current_class = None

    def set_file(self, file_path: str):
        self.current_file = file_path

    def visit_FunctionDef(self, node):
        # Record function definition
        if self.current_class:
            full_name = f"{self.current_class}.{node.name}"
            def_type = "method"
        else:
            full_name = node.name
            def_type = "function"

        self.definitions[full_name] = {
            "type": def_type,
            "line": node.lineno,
            "file": self.current_file,
            "name": node.name,
        }

        # Also record without class prefix for cross-reference
        if self.current_class and node.name not in self.definitions:
            self.definitions[node.name] = {
                "type": "method_variant",
                "line": node.lineno,
                "file": self.current_file,
                "name": node.name,
                "full_name": full_name,
            }

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        # Handle async functions the same way
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        # Record class definition
        old_class = self.current_class
        self.current_class = node.name

        self.definitions[node.name] = {
            "type": "class",
            "line": node.lineno,
            "file": self.current_file,
            "name": node.name,
        }

        self.generic_visit(node)
        self.current_class = old_class

    def visit_Call(self, node):
        # Record function calls
        if isinstance(node.func, ast.Name):
            self.calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.add(node.func.attr)
            if isinstance(node.func.value, ast.Name):
                self.calls.add(f"{node.func.value.id}.{node.func.attr}")

        self.generic_visit(node)

    def visit_Attribute(self, node):
        # Record attribute access (could be method calls)
        self.attributes.add(node.attr)
        if isinstance(node.value, ast.Name):
            self.attributes.add(f"{node.value.id}.{node.attr}")
        self.generic_visit(node)


def analyze_string_references(file_path: Path, definitions: Dict) -> Set[str]:
    """Find function names referenced in strings (templates, getattr, etc.)"""
    string_refs = set()
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Look for function names in strings
        for name in definitions:
            if isinstance(name, str):
                # Check for the name in string literals
                patterns = [
                    f'"{name}"',
                    f"'{name}'",
                    f"getattr.*{name}",
                    f"hasattr.*{name}",
                    f'"{name}.*"',  # Template references
                    f"'{name}.*'",
                ]

                for pattern in patterns:
                    if re.search(pattern, content):
                        string_refs.add(name)

    except Exception:
        pass

    return string_refs


def analyze_file_for_dead_code(file_path: Path) -> Dict:
    """Analyze a single file for dead code"""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)
        analyzer = DeadCodeAnalyzer()
        analyzer.set_file(str(file_path))
        analyzer.visit(tree)

        return {
            "file": str(file_path),
            "definitions": analyzer.definitions,
            "calls": analyzer.calls,
            "attributes": analyzer.attributes,
        }

    except Exception as e:
        return {
            "file": str(file_path),
            "error": str(e),
            "definitions": {},
            "calls": set(),
            "attributes": set(),
        }


def find_cross_file_references(file_results: List[Dict]) -> Set[str]:
    """Find names that are referenced across files (imports, etc.)"""
    cross_refs = set()

    # Collect all calls and attributes from all files
    all_calls = set()
    all_attributes = set()

    for result in file_results:
        if "calls" in result:
            all_calls.update(result["calls"])
        if "attributes" in result:
            all_attributes.update(result["attributes"])

    cross_refs.update(all_calls)
    cross_refs.update(all_attributes)

    # Look for import statements that might reference functions
    for result in file_results:
        file_path = Path(result["file"])
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Find import statements
            import_patterns = [
                r"from\s+\S+\s+import\s+([^,\n]+)",
                r"import\s+\S+\.(\w+)",
                r'getattr\([^,]+,\s*["\'](\w+)["\']',
                r'hasattr\([^,]+,\s*["\'](\w+)["\']',
            ]

            for pattern in import_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, str):
                        cross_refs.add(match.strip())

        except Exception:
            pass

    return cross_refs


def find_special_methods() -> Set[str]:
    """Return set of special Python methods that shouldn't be considered dead"""
    return {
        "__init__",
        "__str__",
        "__repr__",
        "__len__",
        "__iter__",
        "__next__",
        "__enter__",
        "__exit__",
        "__call__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__contains__",
        "__eq__",
        "__ne__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__add__",
        "__sub__",
        "__mul__",
        "__div__",
        "__truediv__",
        "__floordiv__",
        "__mod__",
        "__pow__",
        "__and__",
        "__or__",
        "__xor__",
        "__lshift__",
        "__rshift__",
        "__invert__",
        "__pos__",
        "__neg__",
        "__abs__",
        "__complex__",
        "__int__",
        "__float__",
        "__hash__",
        "__bool__",
        "__bytes__",
        "__format__",
        "__getattr__",
        "__setattr__",
        "__delattr__",
        "__dir__",
        "__get__",
        "__set__",
        "__delete__",
        "__instancecheck__",
        "__subclasscheck__",
        "__new__",
        "__del__",
        "__reduce__",
        "__reduce_ex__",
        "__getnewargs__",
        "__getstate__",
        "__setstate__",
        "main",
    }


def main():
    """Main analysis function"""
    root_dir = Path()
    exclude_dirs = [
        ".ruff_cache",
        "__pycache__",
        ".git",
        "test_data",
        "validation_output",
    ]

    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith(".py"):
                python_files.append(Path(root) / file)

        logger.info(f"🔍 Analyzing {len(python_files)} Python files for dead code...")

    # Analyze each file
    file_results = []
    all_definitions = {}
    all_calls = set()
    all_attributes = set()

    for file_path in python_files:
        result = analyze_file_for_dead_code(file_path)
        if "error" not in result:
            file_results.append(result)
            all_definitions.update(result["definitions"])
            all_calls.update(result["calls"])
            all_attributes.update(result["attributes"])

    # Find cross-file references
    cross_refs = find_cross_file_references(file_results)
    all_calls.update(cross_refs)

    # Find string references
    string_refs = set()
    for file_path in python_files:
        string_refs.update(analyze_string_references(file_path, all_definitions))

    all_calls.update(string_refs)

    # Get special methods to exclude
    special_methods = find_special_methods()

    # Find potentially dead code
    dead_functions = []
    dead_classes = []

    for name, definition in all_definitions.items():
        is_referenced = (
            name in all_calls
            or name in all_attributes
            or definition["name"] in all_calls
            or definition["name"] in all_attributes
            or definition["name"] in special_methods
            or name.startswith("_")  # Private methods might be called dynamically
            or "test_" in definition["file"]  # Test functions
            or definition["file"].endswith("__init__.py")  # Module imports
        )

        if not is_referenced:
            if definition["type"] == "class":
                dead_classes.append(definition)
            elif definition["type"] in ["function", "method"]:
                dead_functions.append(definition)

    # Focus on backend_logic directory
    backend_dead_functions = [f for f in dead_functions if "backend_logic" in f["file"]]
    backend_dead_classes = [c for c in dead_classes if "backend_logic" in c["file"]]

    logger.info("\n📊 DEAD CODE ANALYSIS SUMMARY")
    logger.info(f"├── Total definitions analyzed: {len(all_definitions)}")
    logger.info(f"├── Potentially dead functions: {len(dead_functions)}")
    logger.info(f"├── Potentially dead classes: {len(dead_classes)}")
    logger.info(f"├── Backend logic dead functions: {len(backend_dead_functions)}")
    logger.info(f"└── Backend logic dead classes: {len(backend_dead_classes)}")

    # Display findings
    if dead_functions:
        logger.info("\n🗑️ POTENTIALLY DEAD FUNCTIONS:")
        for func in sorted(dead_functions, key=lambda x: x["file"]):
            logger.info(
                f"   📁 {func['file']}:{func['line']} - {func['type']} '{func['name']}'"
            )

    if dead_classes:
        logger.info("\n🗑️ POTENTIALLY DEAD CLASSES:")
        for cls in sorted(dead_classes, key=lambda x: x["file"]):
            logger.info(f"   📁 {cls['file']}:{cls['line']} - class '{cls['name']}'")

    if backend_dead_functions:
        logger.info("\n🎯 BACKEND_LOGIC DEAD FUNCTIONS:")
        for func in sorted(backend_dead_functions, key=lambda x: x["file"]):
            logger.info(
                f"   📁 {func['file']}:{func['line']} - {func['type']} '{func['name']}'"
            )

    # Save results
    results = {
        "summary": {
            "total_definitions": len(all_definitions),
            "dead_functions": len(dead_functions),
            "dead_classes": len(dead_classes),
            "backend_dead_functions": len(backend_dead_functions),
            "backend_dead_classes": len(backend_dead_classes),
        },
        "dead_functions": dead_functions,
        "dead_classes": dead_classes,
        "backend_dead_functions": backend_dead_functions,
        "backend_dead_classes": backend_dead_classes,
    }

    with open("dead_code_analysis_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("\n💾 Detailed results saved to: dead_code_analysis_results.json")

    return results


if __name__ == "__main__":
    main()
