#!/usr/bin/env python3
"""
Automated print statement replacement script for structured logging migration.

This script systematically replaces print() calls with appropriate structured
logging calls using the centralized logging configuration.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# Add utils to path to access logging config
sys.path.append(".")
from utils.logging_config import setup_logging


class PrintReplacementAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze print statements and their context."""

    def __init__(self, source_code: str):
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.print_calls = []

    def visit_Call(self, node):
        """Visit function calls to find print statements."""
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            # Extract print call details
            line_no = node.lineno
            line_content = (
                self.lines[line_no - 1].strip() if line_no <= len(self.lines) else ""
            )

            # Determine appropriate log level based on content
            log_level = self._determine_log_level(line_content, node)

            # Extract arguments
            args = []
            for arg in node.args:
                if isinstance(arg, ast.Constant):
                    args.append(repr(arg.value))
                elif isinstance(arg, ast.Str):  # Python < 3.8 compatibility
                    args.append(repr(arg.s))
                else:
                    # For complex expressions, use the source code directly
                    try:
                        args.append(ast.unparse(arg))
                    except AttributeError:
                        # Fallback for older Python versions
                        args.append("...")

            self.print_calls.append(
                {
                    "line_no": line_no,
                    "line_content": line_content,
                    "log_level": log_level,
                    "args": args,
                    "indentation": len(line_content) - len(line_content.lstrip()),
                }
            )

        self.generic_visit(node)

    def _determine_log_level(self, line_content: str, node: ast.Call) -> str:
        """Determine appropriate log level based on content analysis."""
        content_lower = line_content.lower()

        # Check for error indicators
        error_patterns = [
            "error",
            "failed",
            "failure",
            "exception",
            "traceback",
            "critical",
            "fatal",
            "crash",
            "abort",
        ]
        if any(pattern in content_lower for pattern in error_patterns):
            return "error"

        # Check for warning indicators
        warning_patterns = [
            "warning",
            "warn",
            "deprecated",
            "caution",
            "notice",
            "skip",
            "ignore",
            "retry",
            "fallback",
        ]
        if any(pattern in content_lower for pattern in warning_patterns):
            return "warning"

        # Check for debug indicators
        debug_patterns = [
            "debug",
            "trace",
            "dump",
            "raw",
            "parsing",
            "processing",
            "step",
            "iteration",
            "loop",
            "checking",
            "validating",
        ]
        if any(pattern in content_lower for pattern in debug_patterns):
            return "debug"

        # Check if it's in a try/except block (likely error handling)
        if "except" in content_lower or "catch" in content_lower:
            return "error"

        # Default to info for general output
        return "info"


def analyze_file(file_path: Path) -> List[Dict]:
    """Analyze a Python file for print statements."""
    try:
        with open(file_path, encoding="utf-8") as f:
            source_code = f.read()

        # Skip if file doesn't contain print statements
        if "print(" not in source_code:
            return []

        # Parse AST and analyze
        tree = ast.parse(source_code)
        analyzer = PrintReplacementAnalyzer(source_code)
        analyzer.visit(tree)

        return analyzer.print_calls
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"⚠️  Could not analyze {file_path}: {e}")
        return []


def infer_service_name(file_path: Path) -> str:
    """Infer service name from file path."""
    path_str = str(file_path)

    # Service mapping based on directory structure
    service_mapping = {
        "backend/email_generator": "email_generator_v2",
        "backend/ai_analyzer": "ai_analyzer",
        "backend_logic/email_generation/services/configuration_manager": "configuration_manager",
        "backend_logic/email_generation/services/text_processing_service": "text_processing_service",
        "backend_logic/email_generation/services/json_architecture_service": "json_architecture_service",
        "backend_logic/email_generation/services/template_rendering_service": "template_rendering_service",
        "backend_logic/email_generation/services/openai_integration_service": "openai_integration_service",
        "backend_logic/email_generation/services/content_generation_service": "content_generation_service",
        "backend_logic/email_generation/services/fallback_generation_service": "fallback_generation_service",
        "app.py": "streamlit_app",
        "main.py": "main_processor",
    }

    # Check exact filename matches
    if file_path.name in service_mapping:
        return service_mapping[file_path.name]

    # Check path-based matches
    for path_pattern, service in service_mapping.items():
        if path_pattern in path_str:
            return service

    # Default service name
    return "unknown_service"


def generate_replacement_content(file_path: Path, print_calls: List[Dict]) -> str:
    """Generate the replacement content for a file."""
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    service_name = infer_service_name(file_path)

    # Add import at the top if not already present
    has_logging_import = False
    for line in lines:
        if "from utils.logging_config import" in line or "setup_logging" in line:
            has_logging_import = True
            break

    if not has_logging_import:
        # Find the best place to add the import
        import_line = "from utils.logging_config import setup_logging\n"
        logger_line = f"logger = setup_logging('{service_name}')\n\n"

        # Insert after existing imports
        insert_index = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(
                ("import ", "from ")
            ) and not line.strip().startswith("#"):
                insert_index = i + 1
            elif line.strip() == "" and insert_index > 0:
                continue
            elif insert_index > 0:
                break

        lines.insert(insert_index, import_line)
        lines.insert(insert_index + 1, logger_line)

        # Adjust line numbers for print calls
        for call in print_calls:
            call["line_no"] += 2

    # Replace print statements (in reverse order to maintain line numbers)
    for call in sorted(print_calls, key=lambda x: x["line_no"], reverse=True):
        line_idx = call["line_no"] - 1
        if line_idx < len(lines):
            original_line = lines[line_idx]
            indent = " " * call["indentation"]

            # Generate logger call
            if len(call["args"]) == 0:
                new_line = f"{indent}logger.{call['log_level']}('')\n"
            elif len(call["args"]) == 1:
                new_line = f"{indent}logger.{call['log_level']}({call['args'][0]})\n"
            else:
                # Multiple arguments - join with spaces
                args_str = ' + " " + '.join(call["args"])
                new_line = f"{indent}logger.{call['log_level']}({args_str})\n"

            lines[line_idx] = new_line

    return "".join(lines)


def scan_and_replace():
    """Main function to scan and replace print statements."""
    print("🔍 Scanning for Python files with print statements...")

    # Define directories to scan
    scan_dirs = [
        Path(),
    ]

    exclude_patterns = [
        ".*",  # Hidden directories
        "__pycache__",
        "node_modules",
        "venv",
        "env",
        ".git",
        "test_logging_config.py",  # Our test file
        "replace_print_statements.py",  # This script
    ]

    python_files = []
    for scan_dir in scan_dirs:
        for file_path in scan_dir.rglob("*.py"):
            # Skip excluded patterns
            if any(pattern in str(file_path) for pattern in exclude_patterns):
                continue
            python_files.append(file_path)

    print(f"📁 Found {len(python_files)} Python files to analyze")

    # Analyze files
    replacement_plan = {}
    total_prints = 0

    for file_path in python_files:
        print_calls = analyze_file(file_path)
        if print_calls:
            replacement_plan[file_path] = print_calls
            total_prints += len(print_calls)
            print(f"   📄 {file_path}: {len(print_calls)} print statements")

    if not replacement_plan:
        print("✅ No print statements found!")
        return

    print("\n📊 REPLACEMENT SUMMARY:")
    print(f"   Files to modify: {len(replacement_plan)}")
    print(f"   Total print statements: {total_prints}")
    print("\n🔧 REPLACEMENT PLAN:")

    for file_path, print_calls in replacement_plan.items():
        service_name = infer_service_name(file_path)
        print(f"\n📁 {file_path} → {service_name}")

        level_counts = {}
        for call in print_calls:
            level = call["log_level"]
            level_counts[level] = level_counts.get(level, 0) + 1

        for level, count in level_counts.items():
            print(f"   • {count}x logger.{level}()")

    # Execute replacements
    print("\n🚀 Executing replacements...")

    modified_files = []
    for file_path, print_calls in replacement_plan.items():
        try:
            new_content = generate_replacement_content(file_path, print_calls)

            # Write the modified content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            modified_files.append(file_path)
            print(f"   ✅ {file_path}: {len(print_calls)} print statements replaced")

        except Exception as e:
            print(f"   ❌ {file_path}: Failed to replace - {e}")

    print("\n🎉 REPLACEMENT COMPLETE!")
    print(f"   Modified files: {len(modified_files)}")
    print(f"   Total print statements replaced: {total_prints}")
    print("\n📋 Next Steps:")
    print("   1. Review the changes in the modified files")
    print("   2. Test the application to ensure logging works correctly")
    print("   3. Check log files in the 'logs/' directory")
    print("   4. Run any existing tests to verify functionality")


if __name__ == "__main__":
    try:
        scan_and_replace()
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
    except Exception as e:
        print(f"❌ Error during replacement: {e}")
        import traceback

        traceback.print_exc()
