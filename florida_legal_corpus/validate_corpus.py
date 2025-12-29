#!/usr/bin/env python3
"""Florida Legal Corpus Validation Script (Stage A4).

Validates the integrity and completeness of the Florida Legal Corpus files:
- statutes.jsonl
- statute_aliases.jsonl
- florida_refs.jsonl

Checks for:
- Required fields present
- Canonical citation format
- No duplicate citations
- Data type correctness
- Alias target existence
- URL accessibility (optional)
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


class CorpusValidator:
    """Validates Florida Legal Corpus integrity."""

    # Required fields for each file type
    STATUTE_REQUIRED_FIELDS = [
        "id",
        "citation_text",
        "statute_number",
        "title",
        "chapter",
        "section",
        "text",
        "summary",
        "tags",
        "effective_date",
        "repealed",
        "source_urls",
        "source_doc_version",
        "last_verified_at",
    ]

    ALIAS_REQUIRED_FIELDS = ["statute_id", "alias_text", "normalized", "patterns"]

    RULE_REQUIRED_FIELDS = [
        "id",
        "ref_type",
        "citation_key",
        "title",
        "text",
        "summary",
        "tags",
        "source_urls",
        "source_doc_version",
        "last_verified_at",
        "repealed",
    ]

    # Citation format regex patterns
    STATUTE_CITATION_PATTERN = re.compile(r"^Fla\. Stat\. § \d+\.\d+$")
    RULE_CITATION_PATTERN = re.compile(r"^Fla\. R\. Civ\. P\. \d+\.\d+$")

    def __init__(self, corpus_dir: Path):
        """Initialize validator with corpus directory."""
        self.corpus_dir = corpus_dir
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.stats: Dict[str, int] = defaultdict(int)

    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """Validate all corpus files.

        Returns
        -------
            Tuple of (success: bool, errors: List[str], warnings: List[str])

        """
        print("=" * 70)
        print("FLORIDA LEGAL CORPUS VALIDATION")
        print("=" * 70)
        print(f"Corpus Directory: {self.corpus_dir}")
        print(f"Validation Time: {datetime.now().isoformat()}")
        print()

        # Validate each file
        statutes = self._validate_statutes()
        aliases = self._validate_aliases(statutes)
        self._validate_rules()  # Validates but doesn't need return value

        # Cross-validation
        self._cross_validate_aliases(statutes, aliases)

        # Print results
        self._print_results()

        return len(self.errors) == 0, self.errors, self.warnings

    def _validate_statutes(self) -> Dict[str, dict]:
        """Validate statutes.jsonl."""
        print("Validating statutes.jsonl...")
        statutes_file = self.corpus_dir / "statutes.jsonl"

        if not statutes_file.exists():
            self.errors.append(f"Missing file: {statutes_file}")
            return {}

        statutes = {}
        line_num = 0
        seen_ids = set()
        seen_citations = set()

        with open(statutes_file, "r", encoding="utf-8") as f:
            for line in f:
                line_num += 1
                if not line.strip():
                    continue

                try:
                    statute = json.loads(line)
                except json.JSONDecodeError as e:
                    self.errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue

                # Check required fields
                missing = [f for f in self.STATUTE_REQUIRED_FIELDS if f not in statute]
                if missing:
                    self.errors.append(f"Line {line_num}: Missing fields: {missing}")
                    continue

                # Validate ID format
                statute_id = statute.get("id", "")
                if not statute_id.startswith("statute:fl:"):
                    self.errors.append(f"Line {line_num}: Invalid ID format: {statute_id}")

                # Check for duplicate IDs
                if statute_id in seen_ids:
                    self.errors.append(f"Line {line_num}: Duplicate ID: {statute_id}")
                seen_ids.add(statute_id)

                # Validate citation format
                citation = statute.get("citation_text", "")
                if not self.STATUTE_CITATION_PATTERN.match(citation):
                    self.errors.append(f"Line {line_num}: Invalid citation format: {citation}")

                # Check for duplicate citations
                if citation in seen_citations:
                    self.errors.append(f"Line {line_num}: Duplicate citation: {citation}")
                seen_citations.add(citation)

                # Validate boolean fields
                if not isinstance(statute.get("repealed"), bool):
                    self.errors.append(f"Line {line_num}: 'repealed' must be boolean")

                if statute.get("repealed") is True:
                    self.warnings.append(f"Line {line_num}: Repealed statute in corpus: {citation}")

                # Validate arrays
                if not isinstance(statute.get("tags"), list):
                    self.errors.append(f"Line {line_num}: 'tags' must be array")

                if not isinstance(statute.get("source_urls"), list):
                    self.errors.append(f"Line {line_num}: 'source_urls' must be array")
                elif len(statute.get("source_urls", [])) == 0:
                    self.warnings.append(f"Line {line_num}: No source URLs for {citation}")

                # Validate effective_date format (if present)
                effective_date = statute.get("effective_date")
                if effective_date and effective_date not in ["", "unknown"]:
                    try:
                        datetime.strptime(effective_date, "%Y-%m-%d")
                    except ValueError:
                        self.errors.append(
                            f"Line {line_num}: Invalid effective_date format: {effective_date}"
                        )

                # Validate last_verified_at format
                last_verified = statute.get("last_verified_at", "")
                if last_verified:
                    try:
                        datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
                    except ValueError:
                        self.errors.append(
                            f"Line {line_num}: Invalid last_verified_at format: {last_verified}"
                        )

                # Check text length
                text = statute.get("text", "")
                if len(text) < 50:
                    self.warnings.append(f"Line {line_num}: Suspiciously short text for {citation}")

                # Store statute
                statutes[statute_id] = statute
                self.stats["statutes"] += 1

        print(f"  ✓ Found {self.stats['statutes']} statutes")
        return statutes

    def _validate_aliases(self, statutes: Dict[str, dict]) -> Dict[str, dict]:
        """Validate statute_aliases.jsonl."""
        print("Validating statute_aliases.jsonl...")
        aliases_file = self.corpus_dir / "statute_aliases.jsonl"

        if not aliases_file.exists():
            self.errors.append(f"Missing file: {aliases_file}")
            return {}

        aliases = {}
        line_num = 0

        with open(aliases_file, "r", encoding="utf-8") as f:
            for line in f:
                line_num += 1
                if not line.strip():
                    continue

                try:
                    alias = json.loads(line)
                except json.JSONDecodeError as e:
                    self.errors.append(f"Aliases line {line_num}: Invalid JSON - {e}")
                    continue

                # Check required fields
                missing = [f for f in self.ALIAS_REQUIRED_FIELDS if f not in alias]
                if missing:
                    self.errors.append(f"Aliases line {line_num}: Missing fields: {missing}")
                    continue

                # Validate patterns is array
                if not isinstance(alias.get("patterns"), list):
                    self.errors.append(f"Aliases line {line_num}: 'patterns' must be array")

                # Store alias
                statute_id = alias.get("statute_id", "")
                aliases[statute_id] = alias
                self.stats["aliases"] += 1

        print(f"  ✓ Found {self.stats['aliases']} alias entries")
        return aliases

    def _validate_rules(self) -> Dict[str, dict]:
        """Validate florida_refs.jsonl."""
        print("Validating florida_refs.jsonl...")
        rules_file = self.corpus_dir / "florida_refs.jsonl"

        if not rules_file.exists():
            self.errors.append(f"Missing file: {rules_file}")
            return {}

        rules = {}
        line_num = 0
        seen_ids = set()
        seen_citations = set()

        with open(rules_file, "r", encoding="utf-8") as f:
            for line in f:
                line_num += 1
                if not line.strip():
                    continue

                try:
                    rule = json.loads(line)
                except json.JSONDecodeError as e:
                    self.errors.append(f"Rules line {line_num}: Invalid JSON - {e}")
                    continue

                # Check required fields
                missing = [f for f in self.RULE_REQUIRED_FIELDS if f not in rule]
                if missing:
                    self.errors.append(f"Rules line {line_num}: Missing fields: {missing}")
                    continue

                # Validate ID
                rule_id = rule.get("id", "")
                if not rule_id.startswith("rule:fl:"):
                    self.errors.append(f"Rules line {line_num}: Invalid ID format: {rule_id}")

                # Check for duplicates
                if rule_id in seen_ids:
                    self.errors.append(f"Rules line {line_num}: Duplicate ID: {rule_id}")
                seen_ids.add(rule_id)

                # Validate citation format
                citation = rule.get("citation_key", "")
                if not self.RULE_CITATION_PATTERN.match(citation):
                    self.warnings.append(f"Rules line {line_num}: Non-standard citation format: {citation}")

                # Check for duplicate citations
                if citation in seen_citations:
                    self.errors.append(f"Rules line {line_num}: Duplicate citation: {citation}")
                seen_citations.add(citation)

                # Validate ref_type
                if rule.get("ref_type") != "rule":
                    self.errors.append(f"Rules line {line_num}: ref_type must be 'rule'")

                # Store rule
                rules[rule_id] = rule
                self.stats["rules"] += 1

        print(f"  ✓ Found {self.stats['rules']} rules")
        return rules

    def _cross_validate_aliases(self, statutes: Dict[str, dict], aliases: Dict[str, dict]):
        """Cross-validate that all aliases reference existing statutes."""
        print("Cross-validating aliases...")

        for statute_id, _alias in aliases.items():
            if statute_id not in statutes:
                self.errors.append(f"Alias references non-existent statute: {statute_id}")

        # Check for statutes without aliases
        statutes_without_aliases = set(statutes.keys()) - set(aliases.keys())
        if statutes_without_aliases:
            for statute_id in statutes_without_aliases:
                citation = statutes[statute_id].get("citation_text", "")
                self.warnings.append(f"Statute has no alias entry: {citation}")

        print("  ✓ Cross-validation complete")

    def _print_results(self):
        """Print validation results."""
        print()
        print("=" * 70)
        print("VALIDATION RESULTS")
        print("=" * 70)
        print()

        print("Statistics:")
        print(f"  Statutes: {self.stats['statutes']}")
        print(f"  Aliases:  {self.stats['aliases']}")
        print(f"  Rules:    {self.stats['rules']}")
        print(f"  Total:    {sum(self.stats.values())}")
        print()

        if self.errors:
            print(f"❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  • {error}")
            print()
        else:
            print("✅ No errors found!")
            print()

        if self.warnings:
            print(f"⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  • {warning}")
            print()
        else:
            print("✅ No warnings!")
            print()

        if not self.errors:
            print("=" * 70)
            print("✅ CORPUS VALIDATION PASSED")
            print("=" * 70)
        else:
            print("=" * 70)
            print("❌ CORPUS VALIDATION FAILED")
            print("=" * 70)


def main():
    """Run corpus validation."""
    # Determine corpus directory
    corpus_dir = Path(__file__).parent

    # Run validation
    validator = CorpusValidator(corpus_dir)
    success, errors, warnings = validator.validate_all()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
