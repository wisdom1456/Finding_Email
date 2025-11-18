"""Service for detecting whether a case falls within Florida Legal Corpus coverage areas."""

from __future__ import annotations

from typing import Dict, List, Optional

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class CorpusCoverageService:
    """Determine if a case type is covered by the Florida Legal Corpus."""

    # Define coverage areas aligned with the corpus
    COVERAGE_AREAS = {
        "consumer_protection": {
            "keywords": [
                "consumer",
                "fdutpa",
                "deceptive",
                "unfair trade",
                "false advertising",
                "breach of contract",
                "breach of warranty",
                "ucc",
                "sale of goods",
                "timeshare",
                "business dispute",
                "fraud",
                "misrepresentation",
            ],
            "statutes": ["501", "672", "605", "607"],
            "name": "Consumer Protection & Business Misconduct (Florida)",
        },
        "landlord_tenant": {
            "keywords": [
                "landlord",
                "tenant",
                "eviction",
                "lease",
                "rental",
                "security deposit",
                "habitability",
                "rent",
                "possession",
                "unlawful detainer",
            ],
            "statutes": ["83"],
            "name": "Landlord-Tenant Disputes (Florida)",
        },
        "foreclosure": {
            "keywords": [
                "foreclosure",
                "mortgage",
                "lis pendens",
                "mediation",
                "deficiency",
                "deed in lieu",
                "loan modification",
            ],
            "statutes": ["702"],
            "name": "Foreclosure Defense (Florida)",
        },
        "construction": {
            "keywords": [
                "construction defect",
                "mechanic's lien",
                "contractor",
                "subcontractor",
                "lien",
                "notice to owner",
                "claim of lien",
                "building",
                "construction",
                "repair",
            ],
            "statutes": ["558", "713"],
            "name": "Construction Defects & Mechanic's Liens (Florida)",
        },
        "insurance": {
            "keywords": [
                "insurance",
                "property damage",
                "hurricane",
                "windstorm",
                "claim denial",
                "bad faith",
                "homeowner",
                "coverage",
                "insurer",
            ],
            "statutes": ["627"],
            "name": "Property Insurance Claims (Florida)",
        },
        "civil_litigation": {
            "keywords": [
                "statute of limitations",
                "attorney fees",
                "offer of judgment",
                "sanctions",
                "frivolous",
                "civil procedure",
            ],
            "statutes": ["95", "57"],
            "name": "Civil Litigation & Attorney Fees (Florida)",
        },
    }

    # Explicitly unsupported areas
    UNSUPPORTED_AREAS = {
        "federal": {
            "keywords": [
                "federal",
                "usc",
                "u.s.c.",
                "united states code",
                "cfr",
                "code of federal regulations",
                "federal court",
                "federal claim",
                "federal law",
            ],
            "name": "Federal Claims (Not Supported)",
        },
        "criminal": {
            "keywords": [
                "criminal",
                "felony",
                "misdemeanor",
                "prosecution",
                "defendant",
                "plea",
                "sentencing",
                "criminal law",
            ],
            "name": "Criminal Law (Not Supported)",
        },
        "immigration": {
            "keywords": [
                "immigration",
                "visa",
                "deportation",
                "uscis",
                "asylum",
                "green card",
                "citizenship",
            ],
            "name": "Immigration Law (Not Supported)",
        },
        "bankruptcy": {
            "keywords": [
                "bankruptcy",
                "chapter 7",
                "chapter 11",
                "chapter 13",
                "discharge",
                "debtor",
                "creditor",
                "trustee",
            ],
            "name": "Bankruptcy (Not Supported - Federal Jurisdiction)",
        },
        "patent_trademark": {
            "keywords": [
                "patent",
                "trademark",
                "copyright registration",
                "uspto",
                "patent infringement",
                "trademark infringement",
            ],
            "name": "Patent/Trademark Law (Not Supported - Federal Jurisdiction)",
        },
    }

    def analyze_coverage(
        self, case_type: Optional[str] = None, case_facts: str = "", legal_issues: Optional[List[str]] = None
    ) -> Dict:
        """Analyze whether a case falls within corpus coverage.

        Args:
        ----
            case_type: Optional case type string
            case_facts: Case facts/intake text
            legal_issues: Optional list of legal issues

        Returns:
        -------
            Dict with coverage analysis including:
            - is_covered: bool
            - coverage_areas: List of matching coverage areas
            - unsupported_areas: List of detected unsupported areas
            - confidence: float (0.0-1.0)
            - warnings: List of warning messages
        """
        text_to_analyze = f"{case_type or ''} {case_facts} {' '.join(legal_issues or [])}".lower()

        matched_coverage = []
        matched_unsupported = []

        # Check for unsupported areas first (higher priority)
        for _area_id, area_info in self.UNSUPPORTED_AREAS.items():
            if self._matches_keywords(text_to_analyze, area_info["keywords"]):
                matched_unsupported.append(area_info["name"])
                logger.warning(f"Detected unsupported area: {area_info['name']}")

        # Check for supported coverage areas
        for _area_id, area_info in self.COVERAGE_AREAS.items():
            if self._matches_keywords(text_to_analyze, area_info["keywords"]):
                matched_coverage.append(area_info["name"])

        # Determine overall coverage status
        is_covered = len(matched_coverage) > 0 and len(matched_unsupported) == 0
        confidence = self._calculate_confidence(matched_coverage, matched_unsupported, text_to_analyze)

        warnings = []
        if matched_unsupported:
            warnings.append(
                f"⚠️ This case appears to involve unsupported areas: {', '.join(matched_unsupported)}. "
                "The Florida Legal Corpus does not cover these topics. Citations may not be validated."
            )
        elif not matched_coverage:
            warnings.append(
                "⚠️ Could not determine specific practice area from case information. "
                "The Florida Legal Corpus covers: Consumer Protection, Landlord-Tenant, "
                "Foreclosure, Construction, Insurance, and Civil Litigation matters under Florida law only."
            )

        result = {
            "is_covered": is_covered,
            "coverage_areas": matched_coverage,
            "unsupported_areas": matched_unsupported,
            "confidence": confidence,
            "warnings": warnings,
        }

        logger.info(
            f"Coverage analysis: is_covered={is_covered}, "
            f"areas={len(matched_coverage)}, "
            f"unsupported={len(matched_unsupported)}, "
            f"confidence={confidence:.2f}"
        )

        return result

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if any keywords match the text."""
        return any(keyword.lower() in text for keyword in keywords)

    def _calculate_confidence(
        self, matched_coverage: List[str], matched_unsupported: List[str], text: str
    ) -> float:
        """Calculate confidence score for coverage determination."""
        if matched_unsupported:
            return 0.0  # No confidence if unsupported areas detected

        if not matched_coverage:
            return 0.3  # Low confidence if no matches

        if len(matched_coverage) == 1:
            return 0.7  # Medium-high confidence for single match

        if len(matched_coverage) >= 2:
            return 0.9  # High confidence for multiple matches

        return 0.5  # Default medium confidence

    def get_coverage_summary(self) -> str:
        """Get a formatted summary of corpus coverage areas."""
        summary_lines = ["**Florida Legal Corpus Coverage:**", ""]

        for _area_id, area_info in self.COVERAGE_AREAS.items():
            summary_lines.append(f"✅ **{area_info['name']}**")

        summary_lines.extend(["", "**Not Supported:**", ""])

        for _area_id, area_info in self.UNSUPPORTED_AREAS.items():
            summary_lines.append(f"❌ {area_info['name']}")

        return "\n".join(summary_lines)
