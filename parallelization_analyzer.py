#!/usr/bin/env python3
"""
Parallelization Opportunities Analyzer for Code Path Efficiency Analysis
Analyzes Python files to identify sequential I/O-bound and CPU-bound operations that can be parallelized
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import List

from utils.logging_config import setup_logging


logger = setup_logging("parallelization_analyzer")


class ParallelizationOpportunity:
    def __init__(
        self,
        opportunity_type: str,
        file_path: str,
        line_start: int,
        line_end: int,
        code_snippet: str,
        description: str,
        potential_benefit: str,
        implementation_suggestion: str,
    ):
        self.opportunity_type = opportunity_type
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
        self.code_snippet = code_snippet
        self.description = description
        self.potential_benefit = potential_benefit
        self.implementation_suggestion = implementation_suggestion


class ParallelizationAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.opportunities = []
        self.current_file = ""
        self.file_content_lines = []
        self.loops_with_io = []
        self.sequential_api_calls = []
        self.file_operations = []
        self.independent_operations = []

    def set_file(self, file_path: str, content_lines: List[str]):
        self.current_file = file_path
        self.file_content_lines = content_lines

    def visit_For(self, node):
        """Analyze for loops for parallelization opportunities"""
        self._analyze_loop(node, "for")
        self.generic_visit(node)

    def visit_While(self, node):
        """Analyze while loops for potential parallelization"""
        self._analyze_loop(node, "while")
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Analyze function definitions for I/O patterns"""
        self._analyze_function_for_io_patterns(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        """Analyze async functions that might benefit from better concurrency"""
        self._analyze_async_function(node)
        self.generic_visit(node)

    def _analyze_loop(self, node, loop_type: str):
        """Analyze loops for parallelization opportunities"""
        loop_body = ast.unparse(node) if hasattr(ast, "unparse") else str(node.lineno)

        # Check for I/O operations in loop
        io_indicators = [
            "requests.",
            "urllib.",
            "httpx.",
            "aiohttp.",  # HTTP requests
            "open(",
            "with open",
            "file.read",
            "file.write",  # File I/O
            "json.load",
            "json.dump",
            "csv.reader",
            "csv.writer",  # Data I/O
            "time.sleep",
            "asyncio.sleep",  # Delays
            "openai.",
            "client.",
            "api.",  # API calls
            "sql",
            "database",
            "db.",  # Database operations
            "Path(",
            ".read_text(",
            ".write_text(",  # File path operations
        ]

        has_io = any(indicator in loop_body.lower() for indicator in io_indicators)

        if has_io:
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line + 5)
            code_snippet = self._extract_code_snippet(start_line, end_line)

            opportunity = ParallelizationOpportunity(
                opportunity_type="loop_with_io",
                file_path=self.current_file,
                line_start=start_line,
                line_end=end_line,
                code_snippet=code_snippet,
                description=f"{loop_type.capitalize()} loop with I/O operations",
                potential_benefit="High - I/O operations can be parallelized",
                implementation_suggestion="Use concurrent.futures.ThreadPoolExecutor or asyncio.gather()",
            )
            self.opportunities.append(opportunity)

    def _analyze_function_for_io_patterns(self, node):
        """Analyze functions for sequential I/O patterns"""
        func_body = ast.unparse(node) if hasattr(ast, "unparse") else ""

        # Look for sequential API calls
        api_call_patterns = [
            r"openai\..*create\(",
            r"client\..*\(",
            r"requests\.get\(",
            r"requests\.post\(",
            r"urllib\..*\(",
            r"httpx\..*\(",
            r"aiohttp\..*\(",
        ]

        api_calls = []
        for pattern in api_call_patterns:
            matches = re.finditer(pattern, func_body)
            api_calls.extend(matches)

        if len(api_calls) >= 2:
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line + 20)
            code_snippet = self._extract_code_snippet(
                start_line, min(end_line, start_line + 10)
            )

            opportunity = ParallelizationOpportunity(
                opportunity_type="sequential_api_calls",
                file_path=self.current_file,
                line_start=start_line,
                line_end=end_line,
                code_snippet=code_snippet,
                description=f"Function '{node.name}' contains {len(api_calls)} sequential API calls",
                potential_benefit="High - API calls can be parallelized if independent",
                implementation_suggestion="Use asyncio.gather() or concurrent.futures for parallel execution",
            )
            self.opportunities.append(opportunity)

        # Look for file processing patterns
        file_processing_patterns = [
            r"with open\(",
            r"\.read_text\(\)",
            r"\.write_text\(",
            r"json\.load\(",
            r"json\.dump\(",
            r"csv\.reader\(",
            r"pdf.*extract",
            r"docx.*Document\(",
        ]

        file_ops = []
        for pattern in file_processing_patterns:
            matches = re.finditer(pattern, func_body, re.IGNORECASE)
            file_ops.extend(matches)

        if len(file_ops) >= 2:
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line + 20)
            code_snippet = self._extract_code_snippet(
                start_line, min(end_line, start_line + 10)
            )

            opportunity = ParallelizationOpportunity(
                opportunity_type="sequential_file_operations",
                file_path=self.current_file,
                line_start=start_line,
                line_end=end_line,
                code_snippet=code_snippet,
                description=f"Function '{node.name}' contains {len(file_ops)} file operations",
                potential_benefit="Medium - File operations can be parallelized if independent",
                implementation_suggestion="Use concurrent.futures.ThreadPoolExecutor for I/O-bound file operations",
            )
            self.opportunities.append(opportunity)

    def _analyze_async_function(self, node):
        """Analyze async functions for better concurrency opportunities"""
        func_body = ast.unparse(node) if hasattr(ast, "unparse") else ""

        # Look for sequential awaits that could be gathered
        await_pattern = r"await\s+\w+"
        awaits = re.findall(await_pattern, func_body)

        if len(awaits) >= 2 and "asyncio.gather" not in func_body:
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line + 20)
            code_snippet = self._extract_code_snippet(
                start_line, min(end_line, start_line + 10)
            )

            opportunity = ParallelizationOpportunity(
                opportunity_type="sequential_awaits",
                file_path=self.current_file,
                line_start=start_line,
                line_end=end_line,
                code_snippet=code_snippet,
                description=f"Async function '{node.name}' has {len(awaits)} sequential awaits",
                potential_benefit="Medium - Sequential awaits can be parallelized if independent",
                implementation_suggestion="Use asyncio.gather() to run independent async operations concurrently",
            )
            self.opportunities.append(opportunity)

    def _extract_code_snippet(self, start_line: int, end_line: int) -> str:
        """Extract code snippet from file content"""
        try:
            start_idx = max(0, start_line - 1)
            end_idx = min(len(self.file_content_lines), end_line)
            lines = self.file_content_lines[start_idx:end_idx]
            return "\n".join(lines[:10])  # Limit to 10 lines for readability
        except:
            return f"Lines {start_line}-{end_line}"


def analyze_file_for_parallelization(
    file_path: Path,
) -> List[ParallelizationOpportunity]:
    """Analyze a single file for parallelization opportunities"""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            content_lines = content.split("\n")

        tree = ast.parse(content)
        analyzer = ParallelizationAnalyzer()
        analyzer.set_file(str(file_path), content_lines)
        analyzer.visit(tree)

        # Additional pattern-based analysis
        additional_opportunities = analyze_code_patterns(str(file_path), content)
        analyzer.opportunities.extend(additional_opportunities)

        return analyzer.opportunities

    except Exception as e:
        logger.error(f"Error analyzing {file_path}: {e}")
        return []


def analyze_code_patterns(
    file_path: str, content: str
) -> List[ParallelizationOpportunity]:
    """Analyze code for specific parallelization patterns using regex"""
    opportunities = []
    lines = content.split("\n")

    # Pattern 1: Multiple independent document processing
    doc_processing_pattern = (
        r"(for\s+\w+\s+in\s+.*(?:files|documents|docs).*:.*(?:process|analyze|extract))"
    )
    matches = list(
        re.finditer(doc_processing_pattern, content, re.IGNORECASE | re.DOTALL)
    )

    for match in matches:
        line_num = content[: match.start()].count("\n") + 1

        opportunity = ParallelizationOpportunity(
            opportunity_type="document_processing_loop",
            file_path=file_path,
            line_start=line_num,
            line_end=line_num + 5,
            code_snippet=match.group(0)[:200],
            description="Document processing loop that could be parallelized",
            potential_benefit="High - Independent document processing is highly parallelizable",
            implementation_suggestion="Use multiprocessing.Pool or concurrent.futures.ProcessPoolExecutor",
        )
        opportunities.append(opportunity)

    # Pattern 2: Sequential sleep/delay operations
    sleep_pattern = r"time\.sleep\(\d+\)|asyncio\.sleep\(\d+\)"
    sleep_matches = list(re.finditer(sleep_pattern, content))

    if len(sleep_matches) >= 2:
        first_match = sleep_matches[0]
        line_num = content[: first_match.start()].count("\n") + 1

        opportunity = ParallelizationOpportunity(
            opportunity_type="sequential_delays",
            file_path=file_path,
            line_start=line_num,
            line_end=line_num + 10,
            code_snippet=f"Found {len(sleep_matches)} delay operations",
            description="Multiple delay operations found - may indicate rate limiting that could be optimized",
            potential_benefit="Medium - Rate limiting can often be optimized with batching or async patterns",
            implementation_suggestion="Consider batching operations or using async queues with controlled concurrency",
        )
        opportunities.append(opportunity)

    # Pattern 3: Sequential data transformation operations
    transform_pattern = (
        r"for\s+\w+\s+in\s+.*:.*(?:transform|convert|normalize|process)\("
    )
    transform_matches = list(re.finditer(transform_pattern, content, re.IGNORECASE))

    for match in transform_matches:
        line_num = content[: match.start()].count("\n") + 1

        opportunity = ParallelizationOpportunity(
            opportunity_type="data_transformation_loop",
            file_path=file_path,
            line_start=line_num,
            line_end=line_num + 5,
            code_snippet=match.group(0)[:200],
            description="Data transformation loop that could benefit from parallelization",
            potential_benefit="Medium - CPU-bound transformations can be parallelized",
            implementation_suggestion="Use multiprocessing.Pool for CPU-bound transformations",
        )
        opportunities.append(opportunity)

    return opportunities


def find_backend_logic_opportunities(
    opportunities: List[ParallelizationOpportunity],
) -> List[ParallelizationOpportunity]:
    """Filter opportunities specific to backend_logic directory"""
    return [opp for opp in opportunities if "backend_logic" in opp.file_path]


def prioritize_opportunities(
    opportunities: List[ParallelizationOpportunity],
) -> List[ParallelizationOpportunity]:
    """Prioritize opportunities by potential benefit"""
    priority_order = {"High": 3, "Medium": 2, "Low": 1}

    def get_priority(opp):
        benefit = (
            opp.potential_benefit.split(" - ")[0]
            if " - " in opp.potential_benefit
            else "Low"
        )
        return priority_order.get(benefit, 1)

    return sorted(opportunities, key=get_priority, reverse=True)


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

    logger.info(
        f"🔍 Analyzing {len(python_files)} Python files for parallelization opportunities..."
    )

    # Analyze all files
    all_opportunities = []

    for file_path in python_files:
        opportunities = analyze_file_for_parallelization(file_path)
        all_opportunities.extend(opportunities)

    # Filter and prioritize
    backend_opportunities = find_backend_logic_opportunities(all_opportunities)
    prioritized_opportunities = prioritize_opportunities(all_opportunities)
    prioritized_backend = prioritize_opportunities(backend_opportunities)

    # Group by type
    opportunity_types = {}
    for opp in all_opportunities:
        if opp.opportunity_type not in opportunity_types:
            opportunity_types[opp.opportunity_type] = []
        opportunity_types[opp.opportunity_type].append(opp)

    logger.info("\n📊 PARALLELIZATION ANALYSIS SUMMARY")
    logger.info(f"├── Total opportunities found: {len(all_opportunities)}")
    logger.info(f"├── Backend logic opportunities: {len(backend_opportunities)}")
    logger.info(
        f"├── High-benefit opportunities: {len([o for o in all_opportunities if 'High' in o.potential_benefit])}"
    )
    logger.info(
        f"├── Medium-benefit opportunities: {len([o for o in all_opportunities if 'Medium' in o.potential_benefit])}"
    )
    logger.info(f"└── Opportunity types found: {len(opportunity_types)}")

    # Display opportunities by type
    logger.info("\n🚀 PARALLELIZATION OPPORTUNITIES BY TYPE:")

    for opp_type, opps in opportunity_types.items():
        logger.info(
            f"\n📁 {opp_type.upper().replace('_', ' ')} ({len(opps)} opportunities):"
        )
        for opp in opps[:5]:  # Show first 5 of each type
            logger.info(f"   📄 {opp.file_path}:{opp.line_start}")
            logger.info(f"      ├── {opp.description}")
            logger.info(f"      ├── {opp.potential_benefit}")
            logger.info(f"      └── {opp.implementation_suggestion}")

        if len(opps) > 5:
            logger.info(f"   └── ... and {len(opps) - 5} more")

    # Focus on high-priority backend opportunities
    high_priority_backend = [
        opp for opp in prioritized_backend if "High" in opp.potential_benefit
    ]

    if high_priority_backend:
        logger.info("\n🎯 HIGH-PRIORITY BACKEND_LOGIC OPPORTUNITIES:")
        for opp in high_priority_backend[:10]:
            logger.info(f"   📄 {opp.file_path}:{opp.line_start}-{opp.line_end}")
            logger.info(f"      ├── Type: {opp.opportunity_type}")
            logger.info(f"      ├── {opp.description}")
            logger.info(f"      └── Implementation: {opp.implementation_suggestion}")

    # Performance impact estimation
    high_impact_count = len(
        [o for o in all_opportunities if "High" in o.potential_benefit]
    )
    medium_impact_count = len(
        [o for o in all_opportunities if "Medium" in o.potential_benefit]
    )

    logger.info("\n⚡ PERFORMANCE IMPACT ESTIMATION:")
    logger.info(
        f"├── High-impact opportunities: {high_impact_count} (could significantly improve performance)"
    )
    logger.info(
        f"├── Medium-impact opportunities: {medium_impact_count} (moderate performance gains)"
    )
    logger.info(
        f"├── Total backend opportunities: {len(backend_opportunities)} (core application improvements)"
    )
    logger.info(
        f"└── Estimated overall benefit: {('High' if high_impact_count > 5 else 'Medium' if high_impact_count > 0 else 'Low')}"
    )

    # Save results
    results = {
        "summary": {
            "total_opportunities": len(all_opportunities),
            "backend_opportunities": len(backend_opportunities),
            "high_benefit_count": high_impact_count,
            "medium_benefit_count": medium_impact_count,
            "opportunity_types": list(opportunity_types.keys()),
        },
        "all_opportunities": [
            {
                "type": opp.opportunity_type,
                "file": opp.file_path,
                "lines": f"{opp.line_start}-{opp.line_end}",
                "description": opp.description,
                "benefit": opp.potential_benefit,
                "implementation": opp.implementation_suggestion,
                "code_snippet": opp.code_snippet[:300],  # Limit snippet size
            }
            for opp in prioritized_opportunities
        ],
        "backend_opportunities": [
            {
                "type": opp.opportunity_type,
                "file": opp.file_path,
                "lines": f"{opp.line_start}-{opp.line_end}",
                "description": opp.description,
                "benefit": opp.potential_benefit,
                "implementation": opp.implementation_suggestion,
                "code_snippet": opp.code_snippet[:300],
            }
            for opp in prioritized_backend
        ],
        "opportunity_types": {
            opp_type: len(opps) for opp_type, opps in opportunity_types.items()
        },
    }

    with open("parallelization_analysis_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("\n💾 Detailed results saved to: parallelization_analysis_results.json")

    return results


if __name__ == "__main__":
    main()
