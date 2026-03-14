"""Deadline Extraction Service - Multi-State Deadline Detection.

Extracts deadlines from documents and infers them from jurisdiction-specific statutes.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from legal_portal.core.data_models import DocumentSummaryStructured
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
from legal_portal.services.statute_validation_service import get_statute_validation_service
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


@dataclass
class Deadline:
    """A deadline extracted or inferred for the case."""

    date: datetime
    description: str
    source: str
    urgency: str  # "critical" (<30 days), "important" (30-90 days), "normal", "expired"
    deadline_type: str  # "contractual", "statutory", "inferred"
    statute_text: Optional[str] = None


class DeadlineExtractionService:
    """Extract deadlines from documents and infer from jurisdiction-specific statutes."""

    def __init__(self, jurisdiction: str = "Florida"):
        """Initialize with jurisdiction-specific statute services."""
        self.jurisdiction = jurisdiction
        self.validator = get_statute_validation_service(jurisdiction=jurisdiction)
        self.recommender = StatuteRecommendationService(validator=self.validator, jurisdiction=jurisdiction)
        logger.info(f"DeadlineExtractionService initialized for {jurisdiction}")

    def extract_deadlines(
        self, structured_summaries: List[DocumentSummaryStructured], case_type: str, case_facts: str
    ) -> List[Deadline]:
        """Extract and infer all relevant deadlines."""
        logger.info(f"Extracting deadlines for {self.jurisdiction}")
        deadlines = []

        # 1. Extract from documents
        deadlines.extend(self._extract_from_documents(structured_summaries))

        # 2. Get deadline-relevant statutes from corpus
        keywords = list(self.recommender._extract_keywords(case_facts, [], case_type))
        deadline_statutes = self.recommender.get_deadline_relevant_statutes(
            case_type=case_type, keywords=keywords
        )

        # 3. Infer statutory deadlines using corpus text
        deadlines.extend(self._infer_from_corpus_statutes(deadline_statutes, structured_summaries, case_type))

        # 4. Calculate urgency and sort
        now = datetime.now()
        for deadline in deadlines:
            days_until = (deadline.date - now).days
            if days_until < 0:
                deadline.urgency = "expired"
            elif days_until < 30:
                deadline.urgency = "critical"
            elif days_until < 90:
                deadline.urgency = "important"
            else:
                deadline.urgency = "normal"

        deadlines.sort(key=lambda d: d.date)
        logger.info(f"Identified {len(deadlines)} total deadlines for {self.jurisdiction}")

        return deadlines

    def _extract_from_documents(self, summaries: List[DocumentSummaryStructured]) -> List[Deadline]:
        """Extract explicit deadlines from document summaries."""
        deadlines = []

        for summary in summaries:
            for key_date in summary.key_dates:
                desc_lower = key_date.description.lower()

                # Check if this is a deadline
                is_deadline = any(
                    word in desc_lower
                    for word in [
                        "deadline",
                        "due",
                        "must",
                        "expire",
                        "expiration",
                        "last day",
                        "timely",
                        "notice period",
                    ]
                )

                if is_deadline:
                    try:
                        # Simple date parsing
                        dt = datetime.fromisoformat(key_date.date.replace("Z", "+00:00"))
                        deadlines.append(
                            Deadline(
                                date=dt,
                                description=key_date.description,
                                source=key_date.source_document or summary.document_name,
                                urgency="normal",
                                deadline_type="contractual"
                                if "contract" in summary.document_type.lower()
                                else "inferred",
                            )
                        )
                    except (ValueError, TypeError):
                        continue

        return deadlines

    def _infer_from_corpus_statutes(
        self,
        deadline_statutes: list,
        summaries: List[DocumentSummaryStructured],
        case_type: str,
    ) -> List[Deadline]:
        """Infer deadlines by matching statute requirements against case dates."""
        inferred = []

        # Extract all dates from documents for triggering
        all_dates = []
        for summary in summaries:
            for key_date in summary.key_dates:
                try:
                    dt = datetime.fromisoformat(key_date.date.replace("Z", "+00:00"))
                    all_dates.append({"date": dt, "desc": key_date.description, "doc": summary.document_name})
                except (ValueError, TypeError):
                    continue

        # Look for specific statutory patterns
        for statute in deadline_statutes:
            text = statute.summary.lower() + " " + statute.relevance_reason.lower()

            # Pattern: "within X days of Y"
            match = re.search(r"within (\d+) days", text)
            if match:
                days = int(match.group(1))

                # Try to find trigger date based on jurisdiction and case type
                trigger_event = ""
                if self.jurisdiction == "Florida":
                    if "construction" in case_type.lower() and "713" in statute.chapter:
                        trigger_event = "last work"
                    elif "landlord" in case_type.lower():
                        trigger_event = "vacate"
                elif self.jurisdiction == "New Mexico":
                    if "construction" in case_type.lower() and "48-2" in statute.chapter:
                        trigger_event = "completion of work"
                    elif "landlord" in case_type.lower():
                        trigger_event = "move-out"

                if trigger_event:
                    for d_info in all_dates:
                        if trigger_event in d_info["desc"].lower():
                            deadline_date = d_info["date"] + timedelta(days=days)
                            inferred.append(
                                Deadline(
                                    date=deadline_date,
                                    description=(
                                        f"Statutory deadline per {statute.citation}: "
                                        f"{days} days from {trigger_event}"
                                    ),
                                    source=statute.citation,
                                    urgency="normal",
                                    deadline_type="statutory",
                                    statute_text=statute.summary,
                                )
                            )

        return inferred

    def format_deadlines_for_prompt(self, deadlines: List[Deadline]) -> str:
        """Format deadlines for inclusion in AI prompt context."""
        if not deadlines:
            return ""

        context = f"**Critical Deadlines for {self.jurisdiction} ({len(deadlines)} identified):**\n\n"
        for i, d in enumerate(deadlines, 1):
            status = f"[{d.urgency.upper()}]" if d.urgency != "normal" else ""
            context += f"{i}. {d.date.strftime('%Y-%m-%d')} - {d.description} {status}\n"
            context += f"   Source: {d.source}\n"

        return context
