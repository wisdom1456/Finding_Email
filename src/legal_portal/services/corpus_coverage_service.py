"""Service for detecting whether a case falls within jurisdiction-specific Legal Corpus coverage areas."""

from __future__ import annotations

from typing import Dict, List, Optional

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class CorpusCoverageService:
    """Determine if a case type is covered by the legal corpus for a given jurisdiction."""

    # Define coverage areas aligned with the corpus for each jurisdiction
    JURISDICTION_COVERAGE_AREAS = {
        "Florida": {
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
        },
        "New Mexico": {
            "consumer_protection": {
                "keywords": [
                    "consumer",
                    "unfair practices act",
                    "deceptive",
                    "unfair trade",
                    "false advertising",
                    "breach of contract",
                    "breach of warranty",
                    "fraud",
                    "misrepresentation",
                ],
                "statutes": ["57-12"],
                "name": "Consumer Protection (New Mexico)",
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
                    "uniform owner-resident relations act",
                ],
                "statutes": ["47-8"],
                "name": "Landlord-Tenant Disputes (New Mexico)",
            },
            "construction": {
                "keywords": [
                    "construction defect",
                    "mechanic's lien",
                    "contractor",
                    "subcontractor",
                    "lien",
                    "indemnification",
                    "building",
                    "repair",
                ],
                "statutes": ["37-1", "56-7", "48-2"],
                "name": "Construction & Liens (New Mexico)",
            },
            "real_estate_foreclosure": {
                "keywords": [
                    "foreclosure",
                    "mortgage",
                    "redemption",
                    "power of sale",
                    "deed of trust",
                ],
                "statutes": ["48-7", "39-5"],
                "name": "Real Estate & Foreclosure (New Mexico)",
            },
            "insurance_damages": {
                "keywords": [
                    "insurance",
                    "unfair claims practices",
                    "property damage",
                    "bad faith",
                    "several liability",
                    "comparative fault",
                    "torts",
                ],
                "statutes": ["59A-16", "41-3A"],
                "name": "Insurance & Damages (New Mexico)",
            },
            "civil_procedure": {
                "keywords": [
                    "civil procedure",
                    "rules of civil procedure",
                    "magistrate court",
                    "metropolitan court",
                    "appellate procedure",
                    "rules of evidence",
                    "sanctions",
                    "default",
                ],
                "statutes": ["1-0", "2-4", "3-4", "12-2", "11-1"],  # Rule prefixes
                "name": "Civil Procedure Rules (New Mexico)",
            },
        },
    }

    # Explicitly unsupported areas (jurisdiction-agnostic)
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
        self,
        case_type: Optional[str] = None,
        case_facts: str = "",
        legal_issues: Optional[List[str]] = None,
        jurisdiction: str = "Florida",
    ) -> Dict:
        """Analyze whether a case falls within corpus coverage for a given jurisdiction."""
        text_to_analyze = f"{case_type or ''} {case_facts} {' '.join(legal_issues or [])}".lower()

        matched_coverage = []
        matched_unsupported = []

        # Check for unsupported areas first (higher priority)
        for _area_id, area_info in self.UNSUPPORTED_AREAS.items():
            if self._matches_keywords(text_to_analyze, area_info["keywords"]):
                matched_unsupported.append(area_info["name"])
                logger.warning(f"Detected unsupported area: {area_info['name']}")

        # Get jurisdiction-specific coverage areas
        jurisdiction_areas = self.JURISDICTION_COVERAGE_AREAS.get(jurisdiction)
        if not jurisdiction_areas:
            logger.warning(f"No coverage areas defined for jurisdiction: {jurisdiction}")
            return {
                "is_covered": False,
                "coverage_areas": [],
                "unsupported_areas": matched_unsupported,
                "confidence": 0.0,
                "warnings": [f"No legal corpus or coverage defined for {jurisdiction}."],
            }

        # Check for supported coverage areas within the specified jurisdiction
        for _area_id, area_info in jurisdiction_areas.items():
            if self._matches_keywords(text_to_analyze, area_info["keywords"]):
                matched_coverage.append(area_info["name"])

        # Determine overall coverage status
        is_covered = len(matched_coverage) > 0 and len(matched_unsupported) == 0
        confidence = self._calculate_confidence(matched_coverage, matched_unsupported, text_to_analyze)

        warnings = []
        if matched_unsupported:
            warnings.append(
                f"⚠️ This case appears to involve unsupported areas: {', '.join(matched_unsupported)}. "
                f"The {jurisdiction} Legal Corpus does not cover these topics. "
                "Citations may not be validated."
            )
        elif not matched_coverage:
            supported_list = ", ".join(
                [area["name"].replace(f" ({jurisdiction})", "") for area in jurisdiction_areas.values()]
            )
            warnings.append(
                f"⚠️ Could not determine specific practice area from case information for {jurisdiction}. "
                f"The {jurisdiction} Legal Corpus covers: {supported_list}."
            )

        result = {
            "is_covered": is_covered,
            "coverage_areas": matched_coverage,
            "unsupported_areas": matched_unsupported,
            "confidence": confidence,
            "warnings": warnings,
        }

        logger.info(
            f"Coverage analysis for {jurisdiction}: is_covered={is_covered}, "
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
            return 0.0

        if not matched_coverage:
            return 0.3

        if len(matched_coverage) == 1:
            return 0.7

        if len(matched_coverage) >= 2:
            return 0.9

        return 0.5

    def get_coverage_summary(self, jurisdiction: str = "Florida") -> str:
        """Get a formatted summary of corpus coverage areas for a given jurisdiction."""
        summary_lines = [f"**{jurisdiction} Legal Corpus Coverage:**", ""]

        jurisdiction_areas = self.JURISDICTION_COVERAGE_AREAS.get(jurisdiction)
        if not jurisdiction_areas:
            summary_lines.append(f"No coverage areas defined for jurisdiction: {jurisdiction}.")
        else:
            for _area_id, area_info in jurisdiction_areas.items():
                summary_lines.append(f"✅ **{area_info['name']}**")

        summary_lines.extend(["", "**Not Supported (General):**", ""])

        for _area_id, area_info in self.UNSUPPORTED_AREAS.items():
            summary_lines.append(f"❌ {area_info['name']}")

        return "\n".join(summary_lines)
