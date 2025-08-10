#!/usr/bin/env python3
"""
Redundant Logic Analyzer for Code Path Efficiency Analysis
Analyzes Python files to identify duplicated logic, similar functions, and consolidation opportunities
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List

from utils.logging_config import setup_logging


logger = setup_logging("redundant_logic_analyzer")


class CodeBlock:
    def __init__(
        self,
        name: str,
        file_path: str,
        line_start: int,
        line_end: int,
        code: str,
        function_type: str = "function",
    ):
        self.name = name
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
        self.code = code
        self.function_type = function_type
        self.normalized_code = self._normalize_code(code)
        self.code_hash = hashlib.md5(self.normalized_code.encode()).hexdigest()

    def _normalize_code(self, code: str) -> str:
        """Normalize code for comparison by removing comments, whitespace, variable names"""
        # Remove comments
        code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
        # Remove docstrings
        code = re.sub(r'""".*?"""', "", code, flags=re.DOTALL)
        code = re.sub(r"'''.*?'''", "", code, flags=re.DOTALL)
        # Normalize whitespace
        code = re.sub(r"\s+", " ", code)
        # Remove common variable patterns (replace with generic names)
        code = re.sub(r"\b[a-z_][a-z0-9_]*\b", "VAR", code)
        return code.strip()

    def similarity_score(self, other: CodeBlock) -> float:
        """Calculate similarity score between two code blocks"""
        return SequenceMatcher(
            None, self.normalized_code, other.normalized_code
        ).ratio()


class RedundantLogicAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.code_blocks = []
        self.current_file = ""
        self.file_content_lines = []

    def set_file(self, file_path: str, content_lines: List[str]):
        self.current_file = file_path
        self.file_content_lines = content_lines

    def visit_FunctionDef(self, node):
        self._extract_function_code(node, "function")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self._extract_function_code(node, "async_function")
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        # Extract class methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function_code(item, "method", class_name=node.name)
        self.generic_visit(node)

    def _extract_function_code(self, node, function_type: str, class_name: str = None):
        """Extract function code for analysis"""
        start_line = node.lineno - 1  # Convert to 0-based
        end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 10

        end_line = min(end_line, len(self.file_content_lines))

        function_lines = self.file_content_lines[start_line:end_line]
        code = "\n".join(function_lines)

        name = f"{class_name}.{node.name}" if class_name else node.name

        code_block = CodeBlock(
            name=name,
            file_path=self.current_file,
            line_start=start_line + 1,  # Convert back to 1-based
            line_end=end_line,
            code=code,
            function_type=function_type,
        )

        self.code_blocks.append(code_block)


def analyze_file_for_redundancy(file_path: Path) -> List[CodeBlock]:
    """Analyze a single file for redundant logic"""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            content_lines = content.split("\n")

        tree = ast.parse(content)
        analyzer = RedundantLogicAnalyzer()
        analyzer.set_file(str(file_path), content_lines)
        analyzer.visit(tree)

        return analyzer.code_blocks

    except Exception as e:
        logger.error(f"Error analyzing {file_path}: {e}")
        return []


def find_exact_duplicates(code_blocks: List[CodeBlock]) -> List[Dict]:
    """Find functions with identical normalized code"""
    hash_groups = {}

    for block in code_blocks:
        if len(block.normalized_code) > 50:  # Only consider substantial functions
            if block.code_hash not in hash_groups:
                hash_groups[block.code_hash] = []
            hash_groups[block.code_hash].append(block)

    duplicates = []
    for code_hash, blocks in hash_groups.items():
        if len(blocks) > 1:
            duplicates.append(
                {
                    "type": "exact_duplicate",
                    "count": len(blocks),
                    "blocks": [
                        {
                            "name": block.name,
                            "file": block.file_path,
                            "lines": f"{block.line_start}-{block.line_end}",
                            "type": block.function_type,
                        }
                        for block in blocks
                    ],
                }
            )

    return duplicates


def find_similar_functions(
    code_blocks: List[CodeBlock], threshold: float = 0.8
) -> List[Dict]:
    """Find functions with similar logic"""
    similar_groups = []
    processed = set()

    for i, block1 in enumerate(code_blocks):
        if i in processed or len(block1.normalized_code) < 30:
            continue

        similar_blocks = [block1]

        for j, block2 in enumerate(code_blocks[i + 1 :], i + 1):
            if j in processed or len(block2.normalized_code) < 30:
                continue

            similarity = block1.similarity_score(block2)
            if similarity >= threshold:
                similar_blocks.append(block2)
                processed.add(j)

        if len(similar_blocks) > 1:
            processed.add(i)
            similar_groups.append(
                {
                    "type": "similar_logic",
                    "similarity_score": min(
                        block1.similarity_score(block) for block in similar_blocks[1:]
                    ),
                    "count": len(similar_blocks),
                    "blocks": [
                        {
                            "name": block.name,
                            "file": block.file_path,
                            "lines": f"{block.line_start}-{block.line_end}",
                            "type": block.function_type,
                        }
                        for block in similar_blocks
                    ],
                }
            )

    return similar_groups


def find_repeated_patterns(code_blocks: List[CodeBlock]) -> List[Dict]:
    """Find repeated code patterns that could be extracted"""
    patterns = {}

    # Look for common patterns in function names and logic
    pattern_indicators = [
        (r"validate_.*", "validation_pattern"),
        (r"parse_.*", "parsing_pattern"),
        (r"process_.*", "processing_pattern"),
        (r"extract_.*", "extraction_pattern"),
        (r"format_.*", "formatting_pattern"),
        (r"generate_.*", "generation_pattern"),
        (r"create_.*", "creation_pattern"),
        (r"get_.*", "getter_pattern"),
        (r"set_.*", "setter_pattern"),
        (r"_.*_error.*", "error_handling_pattern"),
        (r".*_config.*", "configuration_pattern"),
        (r".*_template.*", "template_pattern"),
    ]

    for block in code_blocks:
        for pattern_regex, pattern_name in pattern_indicators:
            if re.match(pattern_regex, block.name.lower()):
                if pattern_name not in patterns:
                    patterns[pattern_name] = []
                patterns[pattern_name].append(block)

    repeated_patterns = []
    for pattern_name, blocks in patterns.items():
        if len(blocks) >= 3:  # At least 3 functions following the same pattern
            repeated_patterns.append(
                {
                    "type": "repeated_pattern",
                    "pattern_name": pattern_name,
                    "count": len(blocks),
                    "blocks": [
                        {
                            "name": block.name,
                            "file": block.file_path,
                            "lines": f"{block.line_start}-{block.line_end}",
                            "type": block.function_type,
                        }
                        for block in blocks
                    ],
                }
            )

    return repeated_patterns


def analyze_data_transformations(code_blocks: List[CodeBlock]) -> List[Dict]:
    """Find similar data transformation patterns"""
    transformation_indicators = [
        "json.loads",
        "json.dumps",
        ".to_dict()",
        ".from_dict()",
        "str(",
        "int(",
        "float(",
        "list(",
        "dict(",
        ".split(",
        ".join(",
        ".strip(",
        ".replace(",
        ".format(",
        'f"',
        "f'",
        ".lower(",
        ".upper(",
    ]

    transformation_blocks = []
    for block in code_blocks:
        transformation_count = sum(
            1 for indicator in transformation_indicators if indicator in block.code
        )
        if transformation_count >= 3:  # Functions with significant data transformation
            transformation_blocks.append(
                {
                    "name": block.name,
                    "file": block.file_path,
                    "lines": f"{block.line_start}-{block.line_end}",
                    "transformation_indicators": transformation_count,
                    "code_snippet": block.code[:200] + "..."
                    if len(block.code) > 200
                    else block.code,
                }
            )

    return transformation_blocks


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

    logger.info(f"🔍 Analyzing {len(python_files)} Python files for redundant logic...")

    # Analyze all files
    all_code_blocks = []
    backend_logic_blocks = []

    for file_path in python_files:
        blocks = analyze_file_for_redundancy(file_path)
        all_code_blocks.extend(blocks)

        if "backend_logic" in str(file_path):
            backend_logic_blocks.extend(blocks)

    logger.info(f"📊 Extracted {len(all_code_blocks)} code blocks for analysis")
    logger.info(f"🎯 {len(backend_logic_blocks)} blocks from backend_logic")

    # Analyze redundancies
    exact_duplicates = find_exact_duplicates(all_code_blocks)
    similar_functions = find_similar_functions(all_code_blocks)
    repeated_patterns = find_repeated_patterns(all_code_blocks)
    data_transformations = analyze_data_transformations(backend_logic_blocks)

    # Focus on backend_logic
    backend_exact_duplicates = find_exact_duplicates(backend_logic_blocks)
    backend_similar_functions = find_similar_functions(backend_logic_blocks)
    backend_repeated_patterns = find_repeated_patterns(backend_logic_blocks)

    logger.info("\n📊 REDUNDANT LOGIC ANALYSIS SUMMARY")
    logger.info(f"├── Total exact duplicates found: {len(exact_duplicates)}")
    logger.info(f"├── Similar function groups found: {len(similar_functions)}")
    logger.info(f"├── Repeated patterns identified: {len(repeated_patterns)}")
    logger.info(f"├── Data transformation functions: {len(data_transformations)}")
    logger.info(f"├── Backend exact duplicates: {len(backend_exact_duplicates)}")
    logger.info(f"├── Backend similar functions: {len(backend_similar_functions)}")
    logger.info(f"└── Backend repeated patterns: {len(backend_repeated_patterns)}")

    # Display findings
    if exact_duplicates:
        logger.info("\n🔄 EXACT DUPLICATE FUNCTIONS:")
        for duplicate in exact_duplicates:
            logger.info(f"   📁 {duplicate['count']} identical functions:")
            for block in duplicate["blocks"]:
                logger.info(
                    f"      ├── {block['file']}:{block['lines']} - {block['name']} ({block['type']})"
                )

    if similar_functions:
        logger.info("\n🔄 SIMILAR FUNCTION GROUPS:")
        for group in similar_functions:
            logger.info(
                f"   📁 {group['count']} similar functions (similarity: {group['similarity_score']:.2f}):"
            )
            for block in group["blocks"]:
                logger.info(
                    f"      ├── {block['file']}:{block['lines']} - {block['name']} ({block['type']})"
                )

    if repeated_patterns:
        logger.info("\n🔄 REPEATED PATTERNS:")
        for pattern in repeated_patterns:
            logger.info(
                f"   📁 {pattern['pattern_name']}: {pattern['count']} functions"
            )
            for block in pattern["blocks"][:5]:  # Show first 5
                logger.info(
                    f"      ├── {block['file']}:{block['lines']} - {block['name']}"
                )
            if len(pattern["blocks"]) > 5:
                logger.info(f"      └── ... and {len(pattern['blocks']) - 5} more")

    if data_transformations:
        logger.info("\n🔄 DATA TRANSFORMATION FUNCTIONS (Backend Logic):")
        for transform in data_transformations[:10]:  # Show top 10
            logger.info(
                f"   📁 {transform['file']}:{transform['lines']} - {transform['name']}"
            )
            logger.info(
                f"      └── {transform['transformation_indicators']} transformation operations"
            )

    # Focus on backend_logic findings
    if backend_exact_duplicates or backend_similar_functions:
        logger.info("\n🎯 BACKEND_LOGIC CONSOLIDATION OPPORTUNITIES:")

        if backend_exact_duplicates:
            logger.info(
                f"   📁 Exact Duplicates ({len(backend_exact_duplicates)} groups):"
            )
            for duplicate in backend_exact_duplicates:
                logger.info(
                    f"      ├── {duplicate['count']} identical functions can be consolidated"
                )

        if backend_similar_functions:
            logger.info(
                f"   📁 Similar Functions ({len(backend_similar_functions)} groups):"
            )
            for group in backend_similar_functions:
                logger.info(
                    f"      ├── {group['count']} functions with {group['similarity_score']:.0%} similarity"
                )

    # Save results
    results = {
        "summary": {
            "total_code_blocks": len(all_code_blocks),
            "backend_logic_blocks": len(backend_logic_blocks),
            "exact_duplicates": len(exact_duplicates),
            "similar_functions": len(similar_functions),
            "repeated_patterns": len(repeated_patterns),
            "data_transformations": len(data_transformations),
            "backend_exact_duplicates": len(backend_exact_duplicates),
            "backend_similar_functions": len(backend_similar_functions),
            "backend_repeated_patterns": len(backend_repeated_patterns),
        },
        "exact_duplicates": exact_duplicates,
        "similar_functions": similar_functions,
        "repeated_patterns": repeated_patterns,
        "data_transformations": data_transformations,
        "backend_exact_duplicates": backend_exact_duplicates,
        "backend_similar_functions": backend_similar_functions,
        "backend_repeated_patterns": backend_repeated_patterns,
    }

    with open("redundant_logic_analysis_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("\n💾 Detailed results saved to: redundant_logic_analysis_results.json")

    return results


if __name__ == "__main__":
    main()
