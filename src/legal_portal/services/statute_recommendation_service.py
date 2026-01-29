"""Statute Recommendation Service - Multi-State AI-Powered Statute Suggestions.

This service analyzes case facts and issues to recommend relevant statutes
from jurisdiction-specific corpora that should be cited in the findings email.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from legal_portal.services.statute_validation_service import (
    StatuteValidationService,
    get_statute_validation_service,
)
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


@dataclass
class StatuteRecommendation:
    """A recommended statute for citation."""

    citation: str
    title: str
    summary: str
    relevance_score: float
    relevance_reason: str
    tags: List[str]
    chapter: str
    section: str


class StatuteRecommendationService:
    """Service for recommending relevant statutes based on case facts and issues."""

    # Keyword mappings for common legal issues to statute chapters, jurisdiction-specific
    ISSUE_TO_CHAPTER_MAPPING = {
        "Florida": {
            # Landlord-Tenant
            "landlord": ["83"],
            "tenant": ["83"],
            "lease": ["83"],
            "eviction": ["83"],
            "rental": ["83"],
            "security deposit": ["83"],
            "habitability": ["83"],
            "rent": ["83"],
            # Construction Defects
            "construction": ["558", "713"],
            "defect": ["558"],
            "contractor": ["558", "713"],
            "building": ["558"],
            "repair": ["558", "713"],
            "workmanship": ["558"],
            "mechanic": ["713"],
            "lien": ["713"],
            "subcontractor": ["713"],
            # Consumer Protection
            "consumer": ["501"],
            "deceptive": ["501"],
            "fraud": ["501", "95"],
            "unfair practice": ["501"],
            "false advertising": ["501"],
            "misrepresentation": ["501"],
            "warranty": ["672", "501"],
            # Contract Law
            "contract": ["672", "671", "95"],
            "breach": ["672", "95"],
            "agreement": ["672", "671"],
            "sale of goods": ["672"],
            "UCC": ["672", "671"],
            # Foreclosure
            "foreclosure": ["702"],
            "mortgage": ["702"],
            "deed": ["702"],
            # Statute of Limitations
            "statute of limitations": ["95"],
            "time limit": ["95"],
            "deadline": ["95"],
            "limitation period": ["95"],
            # Attorney Fees
            "attorney fees": ["57"],
            "sanctions": ["57"],
            "frivolous": ["57"],
            "bad faith": ["57"],
        },
        "New Mexico": {
            # Consumer Protection
            "consumer": ["57-12"],
            "unfair practices act": ["57-12"],
            "deceptive": ["57-12"],
            "fraud": ["57-12", "37-1"],
            # Landlord-Tenant
            "landlord": ["47-8"],
            "tenant": ["47-8"],
            "lease": ["47-8"],
            "eviction": ["47-8"],
            "rental": ["47-8"],
            "security deposit": ["47-8"],
            "habitability": ["47-8"],
            "rent": ["47-8"],
            # Construction & Liens
            "construction": ["56-7", "48-2", "37-1"],
            "defect": ["56-7"],
            "contractor": ["56-7", "48-2"],
            "mechanic's lien": ["48-2"],
            "lien": ["48-2"],
            "indemnification": ["56-7"],
            # Real Estate & Foreclosure
            "foreclosure": ["48-7", "39-5"],
            "mortgage": ["48-7"],
            "redemption": ["39-5"],
            # Insurance & Damages
            "insurance": ["59A-16"],
            "unfair claims practices": ["59A-16"],
            "personal injury": ["41-3A", "37-1"],
            "torts": ["41-3A"],
            # Civil Procedure Rules (using rule prefixes as 'chapters')
            "civil procedure": ["1-0", "2-4", "3-4", "12-2", "11-1"],
            "rules of civil procedure": ["1-0"],
            "magistrate court": ["2-4"],
            "metropolitan court": ["3-4"],
            "appellate procedure": ["12-2"],
            "rules of evidence": ["11-1"],
            # Statute of Limitations (general)
            "statute of limitations": ["37-1"],
            "time limit": ["37-1"],
            "deadline": ["37-1"],
        },
    }

    # Tag-based mappings, jurisdiction-specific
    TAG_TO_KEYWORDS = {
        "Florida": {
            "landlord-tenant": ["landlord", "tenant", "lease", "rent", "eviction"],
            "construction defects": ["construction", "defect", "contractor", "building"],
            "mechanic's lien": ["lien", "mechanic", "contractor", "subcontractor"],
            "FDUTPA": ["consumer", "deceptive", "unfair", "fraud"],
            "consumer protection": ["consumer", "fraud", "false advertising"],
            "contract": ["contract", "breach", "agreement"],
            "statute of limitations": ["limitation", "deadline", "time limit"],
        },
        "New Mexico": {
            "consumer protection": ["consumer", "unfair practices act", "deceptive", "fraud"],
            "landlord-tenant": ["landlord", "tenant", "lease", "rent", "eviction"],
            "construction defects": ["construction", "defect", "contractor"],
            "mechanic's lien": ["lien", "mechanic", "contractor"],
            "foreclosure": ["foreclosure", "mortgage", "redemption"],
            "insurance": ["insurance", "unfair claims practices"],
            "torts": ["personal injury", "comparative fault"],
            "civil procedure": ["rule", "court", "procedure"],
            "statute of limitations": ["limitation", "deadline", "time limit"],
        },
    }

    def __init__(self, validator: Optional[StatuteValidationService] = None, jurisdiction: str = "Florida"):
        """Initialize the recommendation service for a given jurisdiction."""
        self.jurisdiction = jurisdiction
        self.validator = validator or get_statute_validation_service(jurisdiction=self.jurisdiction)
        logger.info(f"StatuteRecommendationService initialized for {self.jurisdiction}")

    def recommend_statutes(
        self,
        case_facts: str,
        legal_issues: Optional[List[str]] = None,
        case_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[StatuteRecommendation]:
        """Recommend relevant statutes for a case."""
        logger.info(f"Generating statute recommendations for {self.jurisdiction} (limit: {limit})")

        keywords = self._extract_keywords(case_facts, legal_issues, case_type)
        logger.debug(f"Extracted keywords: {keywords}")

        relevant_chapters = self._identify_relevant_chapters(keywords)
        logger.debug(f"Relevant chapters for {self.jurisdiction}: {relevant_chapters}")

        recommendations = []
        for citation, statute in self.validator.statutes.items():
            if not citation.startswith("statute:") and not citation.startswith("rule:"):
                continue

            # For New Mexico, rules also have 'chapter' (which is rule prefix)
            statute_chapter = statute.get("chapter") or statute.get("rule_number", "").split("-")[0]
            if relevant_chapters and statute_chapter not in relevant_chapters:
                continue

            score, reason = self._calculate_relevance_score(statute, keywords, case_facts, legal_issues)

            if score > 0.2:
                recommendations.append(
                    StatuteRecommendation(
                        citation=statute["citation_text"]
                        if "citation_text" in statute
                        else statute["citation_key"],
                        title=statute["title"],
                        summary=statute.get("summary", ""),
                        relevance_score=score,
                        relevance_reason=reason,
                        tags=statute.get("tags", []),
                        chapter=statute.get("chapter") or statute.get("rule_number", "").split("-")[0],
                        section=statute.get("section") or statute.get("rule_number", ""),
                    )
                )

        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
        recommendations = recommendations[:limit]

        logger.info(
            f"Generated {len(recommendations)} statute recommendations for {self.jurisdiction}",
            extra={"recommendation_count": len(recommendations)},
        )

        return recommendations

    def _extract_keywords(
        self,
        case_facts: str,
        legal_issues: Optional[List[str]],
        case_type: Optional[str],
    ) -> Set[str]:
        """Extract relevant keywords from case information."""
        keywords = set()

        if case_type:
            keywords.add(case_type.lower())

        if legal_issues:
            for issue in legal_issues:
                keywords.add(issue.lower())
                keywords.update(issue.lower().split())

        case_facts_lower = case_facts.lower()
        jurisdiction_mapping = self.ISSUE_TO_CHAPTER_MAPPING.get(self.jurisdiction, {})
        for keyword in jurisdiction_mapping.keys():
            if keyword in case_facts_lower:
                keywords.add(keyword)

        # Remove common stopwords
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "is",
            "was",
            "are",
            "were",
        }
        keywords = keywords - stopwords

        return keywords

    def _identify_relevant_chapters(self, keywords: Set[str]) -> Set[str]:
        """Identify relevant statute chapters based on keywords for the current jurisdiction."""
        chapters = set()
        jurisdiction_mapping = self.ISSUE_TO_CHAPTER_MAPPING.get(self.jurisdiction, {})

        for keyword in keywords:
            if keyword in jurisdiction_mapping:
                chapters.update(jurisdiction_mapping[keyword])

        return chapters

    def _calculate_relevance_score(
        self,
        statute: Dict,
        keywords: Set[str],
        case_facts: str,
        legal_issues: Optional[List[str]],
    ) -> tuple[float, str]:
        """Calculate relevance score for a statute."""
        score = 0.0
        reasons = []

        title_lower = statute["title"].lower()
        title_matches = sum(1 for kw in keywords if kw in title_lower)
        if title_matches > 0:
            score += min(title_matches * 0.15, 0.3)
            reasons.append(f"title match ({title_matches} keywords)")

        summary_lower = statute.get("summary", "").lower()
        summary_matches = sum(1 for kw in keywords if kw in summary_lower)
        if summary_matches > 0:
            score += min(summary_matches * 0.1, 0.25)
            reasons.append(f"summary match ({summary_matches} keywords)")

        statute_tags = [tag.lower() for tag in statute.get("tags", [])]
        tag_matches = sum(1 for kw in keywords if any(kw in tag for tag in statute_tags))
        if tag_matches > 0:
            score += min(tag_matches * 0.2, 0.4)
            reasons.append(f"tag match ({tag_matches} keywords)")

        section = statute.get("section") or statute.get("rule_number", "")
        if "definition" in title_lower or section.endswith("01") or section.endswith("001"):
            score += 0.1
            reasons.append("foundational statute")

        chapter = statute.get("chapter") or statute.get("rule_number", "").split("-")[0]
        commonly_cited = (
            ["47", "57", "56", "37", "48"]
            if self.jurisdiction == "New Mexico"
            else ["83", "501", "558", "95", "713"]
        )
        if chapter in commonly_cited:
            score += 0.05
            reasons.append("commonly cited chapter")

        score = min(score, 1.0)
        reason = "; ".join(reasons) if reasons else "general relevance"
        return score, reason

    def get_statute_context_for_prompt(
        self,
        recommendations: List[StatuteRecommendation],
        max_statutes: int = 5,
    ) -> str:
        """Format statute recommendations for AI prompt context."""
        if not recommendations:
            return ""

        context = f"**Verified {self.jurisdiction} Statutes (for your reference):**\n\n"
        context += f"The following {self.jurisdiction} statutes are relevant to this case and are verified in our legal database. You may cite these statutes confidently. Other legitimate statutes may also apply.\n\n"  # noqa: E501

        for i, rec in enumerate(recommendations[:max_statutes], 1):
            context += f"{i}. **{rec.citation}** - {rec.title}\n"
            context += f"   - Summary: {rec.summary}\n"
            context += f"   - Relevance: {rec.relevance_reason}\n"
            context += f"   - Tags: {', '.join(rec.tags[:5])}\n\n"

        return context

    def get_deadline_relevant_statutes(
        self, case_type: str, keywords: List[str]
    ) -> List[StatuteRecommendation]:
        """Get statutes specifically relevant for deadline calculation for the current jurisdiction."""
        deadline_relevant_chapters = []

        if self.jurisdiction == "Florida":
            if "construction" in case_type.lower():
                deadline_relevant_chapters = ["558", "713", "95"]
            elif "landlord" in case_type.lower() or "tenant" in case_type.lower():
                deadline_relevant_chapters = ["83", "95"]
            elif "foreclosure" in case_type.lower():
                deadline_relevant_chapters = ["702", "95"]
            else:
                deadline_relevant_chapters = ["95"]
        elif self.jurisdiction == "New Mexico":
            if "construction" in case_type.lower():
                deadline_relevant_chapters = ["56-7", "48-2", "37-1"]
            elif "landlord" in case_type.lower() or "tenant" in case_type.lower():
                deadline_relevant_chapters = ["47-8", "37-1"]
            elif "foreclosure" in case_type.lower():
                deadline_relevant_chapters = ["48-7", "39-5", "37-1"]
            else:
                deadline_relevant_chapters = ["37-1"]

        recommendations = []
        for citation, statute in self.validator.statutes.items():
            if not citation.startswith("statute:") and not citation.startswith("rule:"):
                continue

            statute_chapter = statute.get("chapter") or statute.get("rule_number", "").split("-")[0]
            if statute_chapter in deadline_relevant_chapters:
                statute_text = statute.get("text", "").lower()
                has_deadline = any(
                    phrase in statute_text
                    for phrase in [
                        "within",
                        "days",
                        "months",
                        "years",
                        "deadline",
                        "not later than",
                        "prior to",
                        "before",
                        "after",
                    ]
                )

                if has_deadline:
                    recommendations.append(
                        StatuteRecommendation(
                            citation=statute["citation_text"]
                            if "citation_text" in statute
                            else statute["citation_key"],
                            title=statute["title"],
                            summary=statute.get("summary", ""),
                            relevance_score=1.0,
                            relevance_reason="Contains deadline language",
                            tags=statute.get("tags", []),
                            chapter=statute.get("chapter") or statute.get("rule_number", "").split("-")[0],
                            section=statute.get("section") or statute.get("rule_number", ""),
                        )
                    )

        return recommendations

    def get_deadline_context_for_prompt(
        self, deadline_statutes: List[StatuteRecommendation], max_statutes: int = 3
    ) -> str:
        """Format deadline-relevant statutes for prompt."""
        if not deadline_statutes:
            return ""

        context = f"**Deadline-Relevant {self.jurisdiction} Statutes:**\n\n"
        context += "The following statutes contain specific deadline requirements:\n\n"

        for i, statute in enumerate(deadline_statutes[:max_statutes], 1):
            context += f"{i}. **{statute.citation}** - {statute.title}\n"
            context += f"   - {statute.summary}\n\n"

        context += (
            "IMPORTANT: Extract specific deadlines from these statutes and calculate "
            "dates based on case facts.\n\n"
        )

        return context
