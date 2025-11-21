"""Statute Recommendation Service - AI-Powered Statute Suggestions.

This service analyzes case facts and issues to recommend relevant Florida statutes
from the corpus that should be cited in the findings letter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from legal_portal.services.statute_validation_service import StatuteValidationService
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


# Keyword mappings for common legal issues to statute chapters
ISSUE_TO_CHAPTER_MAPPING = {
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
}

# Tag-based mappings
TAG_TO_KEYWORDS = {
    "landlord-tenant": ["landlord", "tenant", "lease", "rent", "eviction"],
    "construction defects": ["construction", "defect", "contractor", "building"],
    "mechanic's lien": ["lien", "mechanic", "contractor", "subcontractor"],
    "FDUTPA": ["consumer", "deceptive", "unfair", "fraud"],
    "consumer protection": ["consumer", "fraud", "false advertising"],
    "contract": ["contract", "breach", "agreement"],
    "statute of limitations": ["limitation", "deadline", "time limit"],
}


class StatuteRecommendationService:
    """Service for recommending relevant statutes based on case facts and issues."""

    def __init__(self, validator: Optional[StatuteValidationService] = None):
        """Initialize the recommendation service.

        Args:
        ----
            validator: Optional StatuteValidationService for accessing corpus

        """
        self.validator = validator or StatuteValidationService()
        logger.info("StatuteRecommendationService initialized")

    def recommend_statutes(
        self,
        case_facts: str,
        legal_issues: Optional[List[str]] = None,
        case_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[StatuteRecommendation]:
        """Recommend relevant statutes for a case.

        Args:
        ----
            case_facts: Summary of case facts and circumstances
            legal_issues: List of identified legal issues
            case_type: Type of case (e.g., "landlord-tenant", "construction")
            limit: Maximum number of recommendations

        Returns:
        -------
            List of recommended statutes, sorted by relevance

        """
        logger.info(f"Generating statute recommendations (limit: {limit})")

        # Extract keywords from case facts and issues
        keywords = self._extract_keywords(case_facts, legal_issues, case_type)
        logger.debug(f"Extracted keywords: {keywords}")

        # Find relevant chapters based on keywords
        relevant_chapters = self._identify_relevant_chapters(keywords)
        logger.debug(f"Relevant chapters: {relevant_chapters}")

        # Score all statutes in the corpus
        recommendations = []
        for citation, statute in self.validator.statutes.items():
            if not citation.startswith("statute:"):  # Skip ID entries
                continue

            # Skip if chapter is not relevant
            if relevant_chapters and statute["chapter"] not in relevant_chapters:
                continue

            # Calculate relevance score
            score, reason = self._calculate_relevance_score(statute, keywords, case_facts, legal_issues)

            if score > 0.2:  # Minimum relevance threshold
                recommendations.append(
                    StatuteRecommendation(
                        citation=statute["citation_text"],
                        title=statute["title"],
                        summary=statute.get("summary", ""),
                        relevance_score=score,
                        relevance_reason=reason,
                        tags=statute.get("tags", []),
                        chapter=statute["chapter"],
                        section=statute["section"],
                    )
                )

        # Sort by relevance score and limit
        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
        recommendations = recommendations[:limit]

        logger.info(
            f"Generated {len(recommendations)} statute recommendations",
            extra={"recommendation_count": len(recommendations)},
        )

        return recommendations

    def _extract_keywords(
        self,
        case_facts: str,
        legal_issues: Optional[List[str]],
        case_type: Optional[str],
    ) -> Set[str]:
        """Extract relevant keywords from case information.

        Args:
        ----
            case_facts: Case facts text
            legal_issues: List of legal issues
            case_type: Case type

        Returns:
        -------
            Set of relevant keywords

        """
        keywords = set()

        # Add case type as keyword
        if case_type:
            keywords.add(case_type.lower())

        # Add legal issues
        if legal_issues:
            for issue in legal_issues:
                keywords.add(issue.lower())
                # Add individual words from multi-word issues
                keywords.update(issue.lower().split())

        # Extract keywords from case facts
        case_facts_lower = case_facts.lower()
        for keyword in ISSUE_TO_CHAPTER_MAPPING.keys():
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
        """Identify relevant statute chapters based on keywords.

        Args:
        ----
            keywords: Set of keywords

        Returns:
        -------
            Set of relevant chapter numbers

        """
        chapters = set()

        for keyword in keywords:
            if keyword in ISSUE_TO_CHAPTER_MAPPING:
                chapters.update(ISSUE_TO_CHAPTER_MAPPING[keyword])

        return chapters

    def _calculate_relevance_score(
        self,
        statute: Dict,
        keywords: Set[str],
        case_facts: str,
        legal_issues: Optional[List[str]],
    ) -> tuple[float, str]:
        """Calculate relevance score for a statute.

        Args:
        ----
            statute: Statute dictionary from corpus
            keywords: Extracted keywords
            case_facts: Case facts text
            legal_issues: Legal issues list

        Returns:
        -------
            Tuple of (score, reason) where score is 0-1

        """
        score = 0.0
        reasons = []

        # Check title match
        title_lower = statute["title"].lower()
        title_matches = sum(1 for kw in keywords if kw in title_lower)
        if title_matches > 0:
            title_score = min(title_matches * 0.15, 0.3)
            score += title_score
            reasons.append(f"title match ({title_matches} keywords)")

        # Check summary match
        summary_lower = statute.get("summary", "").lower()
        summary_matches = sum(1 for kw in keywords if kw in summary_lower)
        if summary_matches > 0:
            summary_score = min(summary_matches * 0.1, 0.25)
            score += summary_score
            reasons.append(f"summary match ({summary_matches} keywords)")

        # Check tag match
        statute_tags = [tag.lower() for tag in statute.get("tags", [])]
        tag_matches = sum(1 for kw in keywords if any(kw in tag for tag in statute_tags))
        if tag_matches > 0:
            tag_score = min(tag_matches * 0.2, 0.4)
            score += tag_score
            reasons.append(f"tag match ({tag_matches} keywords)")

        # Boost score for foundational statutes (definitions, key provisions)
        if (
            "definition" in title_lower
            or statute["section"].endswith("01")
            or statute["section"].endswith("001")
        ):
            score += 0.1
            reasons.append("foundational statute")

        # Boost score for frequently cited statutes
        chapter = statute["chapter"]
        if chapter in ["83", "501", "558", "95", "713"]:
            score += 0.05
            reasons.append("commonly cited chapter")

        # Cap score at 1.0
        score = min(score, 1.0)

        reason = "; ".join(reasons) if reasons else "general relevance"
        return score, reason

    def get_statute_context_for_prompt(
        self,
        recommendations: List[StatuteRecommendation],
        max_statutes: int = 5,
    ) -> str:
        """Format statute recommendations for AI prompt context.

        Args:
        ----
            recommendations: List of recommended statutes
            max_statutes: Maximum number to include in context

        Returns:
        -------
            Formatted string for prompt context

        """
        if not recommendations:
            return ""

        context = "**Verified Florida Statutes (for your reference):**\n\n"
        context += "The following Florida statutes are relevant to this case and are verified in our legal database. You may cite these statutes confidently. Other legitimate statutes may also apply.\n\n"  # noqa: E501

        for i, rec in enumerate(recommendations[:max_statutes], 1):
            context += f"{i}. **{rec.citation}** - {rec.title}\n"
            context += f"   - Summary: {rec.summary}\n"
            context += f"   - Relevance: {rec.relevance_reason}\n"
            context += f"   - Tags: {', '.join(rec.tags[:5])}\n\n"

        return context

    def get_deadline_relevant_statutes(
        self, case_type: str, keywords: List[str]
    ) -> List[StatuteRecommendation]:
        """Get statutes specifically relevant for deadline calculation.

        Args:
        ----
            case_type: Type of case
            keywords: Keywords from case facts

        Returns:
        -------
            List of statutes with deadline language
        """
        deadline_relevant_chapters = []

        # Map case types to deadline-critical chapters
        if "construction" in case_type.lower():
            deadline_relevant_chapters = ["558", "713", "95"]
        elif "landlord" in case_type.lower() or "tenant" in case_type.lower():
            deadline_relevant_chapters = ["83", "95"]
        elif "foreclosure" in case_type.lower():
            deadline_relevant_chapters = ["702", "95"]
        else:
            deadline_relevant_chapters = ["95"]  # Always include statute of limitations

        # Get statutes from these chapters
        recommendations = []
        for citation, statute in self.validator.statutes.items():
            if not citation.startswith("statute:"):
                continue

            if statute["chapter"] in deadline_relevant_chapters:
                # Check if statute text contains deadline language
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
                            citation=f"Fla. Stat. § {statute['chapter']}.{statute['section']}",
                            title=statute["title"],
                            summary=statute["summary"],
                            relevance_score=1.0,
                            relevance_reason="Contains deadline language",
                            tags=statute.get("tags", []),
                            chapter=statute["chapter"],
                            section=statute["section"],
                        )
                    )

        return recommendations

    def get_deadline_context_for_prompt(
        self, deadline_statutes: List[StatuteRecommendation], max_statutes: int = 3
    ) -> str:
        """Format deadline-relevant statutes for prompt.

        Args:
        ----
            deadline_statutes: Statutes containing deadline language
            max_statutes: Maximum to include

        Returns:
        -------
            Formatted context for prompt
        """
        if not deadline_statutes:
            return ""

        context = "**Deadline-Relevant Florida Statutes:**\n\n"
        context += "The following statutes contain specific deadline requirements:\n\n"

        for i, statute in enumerate(deadline_statutes[:max_statutes], 1):
            context += f"{i}. **{statute.citation}** - {statute.title}\n"
            context += f"   - {statute.summary}\n\n"

        context += "IMPORTANT: Extract specific deadlines from these statutes and calculate dates based on case facts.\n\n"

        return context
