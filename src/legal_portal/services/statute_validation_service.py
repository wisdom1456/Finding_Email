"""Statute Validation Service - Florida Legal Corpus Integration.

This service validates statute citations in generated letters against the
Florida Legal Corpus to prevent hallucinations and ensure citation accuracy.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import streamlit as st
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


@dataclass
class StatuteReference:
    """A statute reference found in a letter."""

    original_text: str
    normalized_citation: Optional[str] = None
    statute_id: Optional[str] = None
    chapter: Optional[str] = None
    section: Optional[str] = None
    confidence: float = 0.0
    is_verified: bool = False
    corpus_entry: Optional[Dict] = None


@dataclass
class ValidationResult:
    """Results of statute citation validation."""

    total_citations: int = 0
    verified_citations: int = 0
    unverified_citations: int = 0
    suspicious_citations: int = 0
    verified: List[StatuteReference] = field(default_factory=list)
    unverified: List[StatuteReference] = field(default_factory=list)
    suspicious: List[StatuteReference] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "total_citations": self.total_citations,
            "verified_citations": self.verified_citations,
            "unverified_citations": self.unverified_citations,
            "suspicious_citations": self.suspicious_citations,
            "verified": [
                {
                    "original_text": ref.original_text,
                    "normalized_citation": ref.normalized_citation,
                    "statute_id": ref.statute_id,
                    "is_verified": ref.is_verified,
                }
                for ref in self.verified
            ],
            "unverified": [
                {
                    "original_text": ref.original_text,
                    "normalized_citation": ref.normalized_citation,
                }
                for ref in self.unverified
            ],
            "suspicious": [
                {
                    "original_text": ref.original_text,
                    "reason": "Suspicious format or content",
                }
                for ref in self.suspicious
            ],
            "warnings": self.warnings,
            "errors": self.errors,
        }


class StatuteValidationService:
    """Service for validating statute citations against Florida Legal Corpus."""

    # Regex patterns for detecting Florida statute citations
    CITATION_PATTERNS = [
        # Standard formats
        re.compile(r"Fla\.\s*Stat\.\s*§\s*(\d+)\.(\d+)", re.IGNORECASE),
        re.compile(r"F\.S\.\s*§?\s*(\d+)\.(\d+)", re.IGNORECASE),
        re.compile(r"Florida\s+Statute[s]?\s*§?\s*(\d+)\.(\d+)", re.IGNORECASE),
        re.compile(r"Section\s+(\d+)\.(\d+)", re.IGNORECASE),
        re.compile(r"s\.\s*(\d+)\.(\d+)", re.IGNORECASE),
        # Handle variations without section symbol
        re.compile(r"Fla\.\s*Stat\.\s*(\d+)\.(\d+)", re.IGNORECASE),
        re.compile(r"F\.S\.\s*(\d+)\.(\d+)", re.IGNORECASE),
    ]

    # Florida Rule citation patterns
    RULE_PATTERNS = [
        re.compile(r"Fla\.\s*R\.\s*Civ\.\s*P\.\s*(\d+)\.(\d+)", re.IGNORECASE),
        re.compile(r"Florida\s+Rules?\s+of\s+Civil\s+Procedure\s*(\d+)\.(\d+)", re.IGNORECASE),
    ]

    def __init__(self, corpus_dir: Optional[Path] = None):
        """Initialize the validation service with corpus directory.

        Args:
        ----
            corpus_dir: Path to Florida Legal Corpus directory

        """
        if corpus_dir is None:
            # Default to project corpus directory
            project_root = Path(__file__).parents[3]
            corpus_dir = project_root / "florida_legal_corpus"

        self.corpus_dir = Path(corpus_dir)
        self.statutes: Dict[str, Dict] = {}
        self.aliases: Dict[str, str] = {}  # Maps alias text -> normalized citation
        self.rules: Dict[str, Dict] = {}
        self._load_corpus()

    def _load_corpus(self):
        """Load the Florida Legal Corpus from JSONL files."""
        logger.info(f"Loading Florida Legal Corpus from {self.corpus_dir}")

        try:
            # Load statutes
            statutes_file = self.corpus_dir / "statutes.jsonl"
            if statutes_file.exists():
                with open(statutes_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            statute = json.loads(line)
                            self.statutes[statute["citation_text"]] = statute
                            self.statutes[statute["id"]] = statute
                logger.info(f"Loaded {len(self.statutes) // 2} statutes")
            else:
                logger.warning(f"Statutes file not found: {statutes_file}")

            # Load aliases
            aliases_file = self.corpus_dir / "statute_aliases.jsonl"
            if aliases_file.exists():
                with open(aliases_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            alias = json.loads(line)
                            normalized = alias["normalized"]
                            # Map each pattern to normalized citation
                            for pattern in alias.get("patterns", []):
                                self.aliases[pattern.lower()] = normalized
                            # Also map the alias_text itself
                            self.aliases[alias["alias_text"].lower()] = normalized
                logger.info(f"Loaded {len(self.aliases)} alias mappings")
            else:
                logger.warning(f"Aliases file not found: {aliases_file}")

            # Load Florida Rules
            rules_file = self.corpus_dir / "florida_refs.jsonl"
            if rules_file.exists():
                with open(rules_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            rule = json.loads(line)
                            self.rules[rule["citation_key"]] = rule
                            self.rules[rule["id"]] = rule
                logger.info(f"Loaded {len(self.rules) // 2} Florida rules")
            else:
                logger.warning(f"Rules file not found: {rules_file}")

        except Exception as e:
            logger.error(f"Error loading corpus: {e}", exc_info=True)

    def validate_letter(self, letter_content: str) -> ValidationResult:
        """Validate all statute citations in a letter.

        Args:
        ----
            letter_content: The letter text to validate

        Returns:
        -------
            ValidationResult with detailed validation information

        """
        logger.info("Starting statute citation validation")
        result = ValidationResult()

        # Extract citations from letter
        citations = self._extract_citations(letter_content)
        result.total_citations = len(citations)

        if result.total_citations == 0:
            result.warnings.append("No statute citations found in letter")
            logger.info("No statute citations found to validate")
            return result

        logger.info(f"Found {result.total_citations} statute citations to validate")

        # Validate each citation
        for citation_text in citations:
            ref = self._validate_citation(citation_text)

            if ref.is_verified:
                result.verified.append(ref)
                result.verified_citations += 1
            elif ref.confidence < 0.5:
                result.suspicious.append(ref)
                result.suspicious_citations += 1
                result.warnings.append(f"Suspicious citation: {citation_text}")
            else:
                result.unverified.append(ref)
                result.unverified_citations += 1
                result.warnings.append(f"Unverified citation: {citation_text}")

        logger.info(
            f"Validation complete: {result.verified_citations} verified, "
            f"{result.unverified_citations} unverified, "
            f"{result.suspicious_citations} suspicious"
        )

        return result

    def _extract_citations(self, text: str) -> Set[str]:
        """Extract all Florida statute citations from text.

        Args:
        ----
            text: Text to extract citations from

        Returns:
        -------
            Set of unique citation strings found

        """
        citations = set()

        # Remove HTML tags for cleaner extraction
        clean_text = re.sub(r"<[^>]+>", "", text)

        # Extract statute citations
        for pattern in self.CITATION_PATTERNS:
            for match in pattern.finditer(clean_text):
                citation_text = match.group(0)
                citations.add(citation_text)

        # Extract rule citations
        for pattern in self.RULE_PATTERNS:
            for match in pattern.finditer(clean_text):
                citation_text = match.group(0)
                citations.add(citation_text)

        return citations

    def _validate_citation(self, citation_text: str) -> StatuteReference:
        """Validate a single citation.

        Args:
        ----
            citation_text: The citation text to validate

        Returns:
        -------
            StatuteReference with validation results

        """
        ref = StatuteReference(original_text=citation_text)

        # Try to normalize the citation
        normalized = self._normalize_citation(citation_text)
        ref.normalized_citation = normalized

        if not normalized:
            ref.confidence = 0.3
            return ref

        # Check if normalized citation exists in corpus
        if normalized in self.statutes:
            ref.is_verified = True
            ref.confidence = 1.0
            ref.corpus_entry = self.statutes[normalized]
            ref.statute_id = self.statutes[normalized]["id"]
            ref.chapter = self.statutes[normalized]["chapter"]
            ref.section = self.statutes[normalized]["section"]
            logger.debug(f"Verified citation: {citation_text} -> {normalized}")
        elif normalized in self.rules:
            ref.is_verified = True
            ref.confidence = 1.0
            ref.corpus_entry = self.rules[normalized]
            ref.statute_id = self.rules[normalized]["id"]
            logger.debug(f"Verified rule citation: {citation_text} -> {normalized}")
        else:
            # Format looks good but not in corpus
            ref.confidence = 0.6
            logger.debug(f"Unverified citation (format OK): {citation_text} -> {normalized}")

        return ref

    def _normalize_citation(self, citation_text: str) -> Optional[str]:
        """Normalize a citation to canonical format.

        Args:
        ----
            citation_text: Raw citation text

        Returns:
        -------
            Normalized citation or None if format is invalid

        """
        # Check aliases first
        citation_lower = citation_text.lower().strip()
        if citation_lower in self.aliases:
            return self.aliases[citation_lower]

        # Try to extract chapter and section with patterns
        for pattern in self.CITATION_PATTERNS:
            match = pattern.search(citation_text)
            if match:
                chapter = match.group(1)
                section = match.group(2)
                return f"Fla. Stat. § {chapter}.{section}"

        # Try rule patterns
        for pattern in self.RULE_PATTERNS:
            match = pattern.search(citation_text)
            if match:
                rule_num = match.group(1)
                subrule = match.group(2)
                return f"Fla. R. Civ. P. {rule_num}.{subrule}"

        return None

    def get_statute_by_citation(self, citation: str) -> Optional[Dict]:
        """Get statute information by citation.

        Args:
        ----
            citation: Citation text or ID

        Returns:
        -------
            Statute dictionary or None if not found

        """
        # Normalize first
        normalized = self._normalize_citation(citation)
        if normalized and normalized in self.statutes:
            return self.statutes[normalized]

        # Try direct lookup
        if citation in self.statutes:
            return self.statutes[citation]

        return None

    def find_statute_by_keyword(self, keyword: str, limit: int = 10) -> List[Dict]:
        """Find statutes by keyword search.

        Args:
        ----
            keyword: Keyword to search for
            limit: Maximum number of results

        Returns:
        -------
            List of matching statute dictionaries

        """
        keyword_lower = keyword.lower()
        matches = []

        # Search in statutes
        for citation, statute in self.statutes.items():
            if not citation.startswith("statute:"):  # Skip ID entries
                continue

            # Search in title, summary, and tags
            title = statute.get("title", "").lower()
            summary = statute.get("summary", "").lower()
            tags = " ".join(statute.get("tags", [])).lower()

            if keyword_lower in title or keyword_lower in summary or keyword_lower in tags:
                matches.append(statute)

            if len(matches) >= limit:
                break

        return matches


@st.cache_resource
def get_statute_validation_service() -> StatuteValidationService:
    """Get cached instance of StatuteValidationService.

    Returns
    -------
        Cached StatuteValidationService instance

    """
    return StatuteValidationService()
