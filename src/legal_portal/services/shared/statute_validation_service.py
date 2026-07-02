"""Statute Validation Service - Multi-State Legal Corpus Integration.

This service validates statute citations in generated letters against jurisdiction-specific
legal corpora to prevent hallucinations and ensure citation accuracy.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set

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
    """Service for validating statute citations against a legal corpus."""

    # Regex patterns for detecting statute citations, dynamically loaded
    CITATION_PATTERNS: Dict[str, List[re.Pattern]] = {
        "Florida": [
            re.compile(r"Fla\.\s*Stat\.\s*§\s*(\d+)\.(\d+)", re.IGNORECASE),
            re.compile(r"F\.S\.\s*§?\s*(\d+)\.(\d+)", re.IGNORECASE),
            re.compile(r"Florida\s+Statute[s]?\s*§?\s*(\d+)\.(\d+)", re.IGNORECASE),
            re.compile(r"Section\s+(\d+)\.(\d+)", re.IGNORECASE),
            re.compile(r"s\.\s*(\d+)\.(\d+)", re.IGNORECASE),
            re.compile(r"Fla\.\s*Stat\.\s*(\d+)\.(\d+)", re.IGNORECASE),
            re.compile(r"F\.S\.\s*(\d+)\.(\d+)", re.IGNORECASE),
        ],
        "New Mexico": [
            re.compile(r"N\.M\.\s*Stat\.\s*Ann\.\s*§\s*([\w.-]+)", re.IGNORECASE),
            re.compile(r"NMSA\s*1978\s*§\s*([\w.-]+)", re.IGNORECASE),
            re.compile(r"NM\s*Stat\.\s*§\s*([\w.-]+)", re.IGNORECASE),
            re.compile(r"Section\s*([\w.-]+)\s*NMSA", re.IGNORECASE),
        ],
    }

    # Rule citation patterns, dynamically loaded
    RULE_PATTERNS: Dict[str, List[re.Pattern]] = {
        "Florida": [
            re.compile(r"Fla\.\s*R\.\s*Civ\.\s*P\.\s*(\d+)\.(\d+)", re.IGNORECASE),
            re.compile(r"Florida\s+Rules?\s+of\s+Civil\s+Procedure\s*(\d+)\.(\d+)", re.IGNORECASE),
        ],
        "New Mexico": [
            re.compile(r"Rule\s*([\w.-]+)\s*NMRA", re.IGNORECASE),
            re.compile(r"N\.M\.\s*R\.\s*Civ\.\s*P\.\s*([\w.-]+)", re.IGNORECASE),
        ],
    }

    JURISDICTION_CONFIG = {
        "Florida": {
            "corpus_path": "florida_legal_corpus",
            "statutes_file": "statutes.jsonl",
            "aliases_file": "statute_aliases.jsonl",
            "rules_file": "florida_refs.jsonl",
            "statute_prefix": "Fla. Stat. §",
            "rule_prefix": "Fla. R. Civ. P.",
        },
        "New Mexico": {
            "corpus_path": "new_mexico_legal_corpus",
            "statutes_file": "statutes.jsonl",
            "aliases_file": "statute_aliases.jsonl",
            "rules_file": "nm_rules.jsonl",
            "statute_prefix": "N.M. Stat. Ann. §",
            "rule_prefix": "Rule",  # Rules are cited as "Rule X-XXX NMRA"
        },
    }

    def __init__(self, jurisdiction: str = "Florida", corpus_dir: Optional[Path] = None):
        """Initialize the validation service with corpus directory and jurisdiction."""
        self.jurisdiction = jurisdiction
        self.config = self.JURISDICTION_CONFIG.get(jurisdiction)
        if not self.config:
            raise ValueError(f"Unsupported jurisdiction: {jurisdiction}")

        if corpus_dir is None:
            # Walk upward from this file until the corpus directory is found.
            # (A fixed parents[N] index silently broke here: from
            # services/shared/ parents[3] is src/, not the repo root, so the
            # corpus never loaded and every citation validated as unverified.)
            for parent in Path(__file__).resolve().parents:
                candidate = parent / self.config["corpus_path"]
                if candidate.is_dir():
                    corpus_dir = candidate
                    break
            else:
                corpus_dir = Path(__file__).resolve().parents[3] / self.config["corpus_path"]
                logger.error(
                    f"Corpus directory '{self.config['corpus_path']}' not found in any "
                    f"ancestor of {Path(__file__).resolve()} — citation validation will "
                    f"treat every citation as unverified"
                )

        self.corpus_dir = Path(corpus_dir)
        self.statutes: Dict[str, Dict] = {}
        self.aliases: Dict[str, str] = {}
        self.rules: Dict[str, Dict] = {}
        self._load_corpus()

    def _load_corpus(self):
        """Load the legal corpus for the specified jurisdiction from JSONL files."""
        logger.info(f"Loading {self.jurisdiction} Legal Corpus from {self.corpus_dir}")

        try:
            # Load statutes
            statutes_file = self.corpus_dir / self.config["statutes_file"]
            if statutes_file.exists():
                with open(statutes_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            statute = json.loads(line)
                            self.statutes[statute["citation_text"]] = statute
                            self.statutes[statute["id"]] = statute
                logger.info(f"Loaded {len(self.statutes) // 2} {self.jurisdiction} statutes")
            else:
                logger.warning(f"Statutes file not found for {self.jurisdiction}: {statutes_file}")

            # Load aliases
            aliases_file = self.corpus_dir / self.config["aliases_file"]
            if aliases_file.exists():
                with open(aliases_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            alias = json.loads(line)
                            normalized = alias["normalized"]
                            for pattern in alias.get("patterns", []):
                                self.aliases[pattern.lower()] = normalized
                            self.aliases[alias["alias_text"].lower()] = normalized
                logger.info(f"Loaded {len(self.aliases)} {self.jurisdiction} alias mappings")
            else:
                logger.warning(f"Aliases file not found for {self.jurisdiction}: {aliases_file}")

            # Load Rules
            rules_file = self.corpus_dir / self.config["rules_file"]
            if rules_file.exists():
                with open(rules_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            rule = json.loads(line)
                            # Handle different key names between FL and NM
                            citation_key = rule.get("citation_key") or rule.get("citation_text")
                            if citation_key:
                                self.rules[citation_key] = rule
                            self.rules[rule["id"]] = rule
                logger.info(f"Loaded {len(self.rules) // 2} {self.jurisdiction} rules")
            else:
                logger.warning(f"Rules file not found for {self.jurisdiction}: {rules_file}")

        except Exception as e:
            logger.error(f"Error loading {self.jurisdiction} corpus: {e}", exc_info=True)

    def validate_letter(self, letter_content: str) -> ValidationResult:
        """Validate all statute citations in a letter."""
        logger.info(f"Starting statute citation validation for {self.jurisdiction}")
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

    UNVERIFIED_MARKER = ' <sup class="citation-unverified">[unverified]</sup>'

    def annotate_unverified_citations(self, letter_markdown: str) -> tuple[str, "ValidationResult"]:
        """Mark every unverified/suspicious statute citation inline.

        Appends a visible superscript marker after each citation that failed
        corpus verification, so the reviewing attorney sees the risk in the
        letter itself rather than in a warnings array. Returns the annotated
        markdown and the validation result.
        """
        result = self.validate_letter(letter_markdown)

        annotated = letter_markdown
        flagged_texts = {ref.original_text for ref in [*result.unverified, *result.suspicious]}
        # Drop any flagged text that is a substring of a longer flagged text —
        # annotating both would insert a marker inside the longer citation.
        flagged = sorted(
            (t for t in flagged_texts if t and not any(t != o and t in o for o in flagged_texts)),
            key=len,
            reverse=True,
        )
        for text in flagged:
            if text in annotated:
                annotated = annotated.replace(text + self.UNVERIFIED_MARKER, text)  # idempotence guard
                annotated = annotated.replace(text, text + self.UNVERIFIED_MARKER)

        if flagged_texts:
            logger.warning(
                f"Annotated {len(flagged_texts)} unverified/suspicious citation(s) "
                f"in letter for {self.jurisdiction}"
            )
        return annotated, result

    def _extract_citations(self, text: str) -> Set[str]:
        """Extract all statute and rule citations from text for the current jurisdiction."""
        citations = set()
        clean_text = re.sub(r"<[^>]+>", "", text)

        # Extract statute citations
        for pattern in self.CITATION_PATTERNS.get(self.jurisdiction, []):
            for match in pattern.finditer(clean_text):
                citations.add(match.group(0))

        # Extract rule citations
        for pattern in self.RULE_PATTERNS.get(self.jurisdiction, []):
            for match in pattern.finditer(clean_text):
                citations.add(match.group(0))

        return citations

    def _validate_citation(self, citation_text: str) -> StatuteReference:
        """Validate a single citation."""
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
        """Normalize a citation to canonical format for the current jurisdiction."""
        citation_lower = citation_text.lower().strip()
        if citation_lower in self.aliases:
            return self.aliases[citation_lower]

        # Try to extract chapter and section with patterns for statutes
        for pattern in self.CITATION_PATTERNS.get(self.jurisdiction, []):
            match = pattern.search(citation_text)
            if match:
                if self.jurisdiction == "Florida":
                    chapter = match.group(1)
                    section = match.group(2)
                    return f"{self.config['statute_prefix']} {chapter}.{section}"
                elif self.jurisdiction == "New Mexico":
                    # New Mexico statutes can have alphanumeric sections
                    section_number = match.group(1)
                    return f"{self.config['statute_prefix']} {section_number}"

        # Try rule patterns
        for pattern in self.RULE_PATTERNS.get(self.jurisdiction, []):
            match = pattern.search(citation_text)
            if match:
                if self.jurisdiction == "Florida":
                    rule_num = match.group(1)
                    subrule = match.group(2)
                    return f"{self.config['rule_prefix']} {rule_num}.{subrule}"
                elif self.jurisdiction == "New Mexico":
                    rule_number = match.group(1)
                    return f"{self.config['rule_prefix']} {rule_number} NMRA"

        return None

    def get_statute_by_citation(self, citation: str) -> Optional[Dict]:
        """Get statute information by citation."""
        normalized = self._normalize_citation(citation)
        if normalized and normalized in self.statutes:
            return self.statutes[normalized]

        if citation in self.statutes:
            return self.statutes[citation]

        return None

    def find_statute_by_keyword(self, keyword: str, limit: int = 10) -> List[Dict]:
        """Find statutes by keyword search."""
        keyword_lower = keyword.lower()
        matches = []

        for citation, statute in self.statutes.items():
            if not citation.startswith("statute:"):
                continue

            title = statute.get("title", "").lower()
            summary = statute.get("summary", "").lower()
            tags = " ".join(statute.get("tags", [])).lower()

            if keyword_lower in title or keyword_lower in summary or keyword_lower in tags:
                matches.append(statute)

            if len(matches) >= limit:
                break

        return matches


@lru_cache(maxsize=16)
def get_statute_validation_service(jurisdiction: str = "Florida") -> StatuteValidationService:
    """Get cached instance of StatuteValidationService for a specific jurisdiction."""
    return StatuteValidationService(jurisdiction=jurisdiction)
