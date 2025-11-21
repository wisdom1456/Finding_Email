"""Deadline Extraction Service - Extract deadlines from documents and infer from FL statutes."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from legal_portal.core.data_models import DocumentSummaryStructured
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
from legal_portal.services.statute_validation_service import StatuteValidationService
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


@dataclass
class Deadline:
    """A deadline extracted or inferred for the case."""

    date: datetime
    description: str
    source: str  # "Contract.pdf" or "Fla. Stat. § 558.004"
    urgency: str  # "critical" (<30 days), "important" (30-90 days), "normal"
    deadline_type: str  # "contractual", "statutory", "inferred"
    statute_text: Optional[str] = None  # Actual statute text if statutory


class DeadlineExtractionService:
    """Extract deadlines from documents and infer from Florida statutes."""

    def __init__(self):
        """Initialize with statute services."""
        self.validator = StatuteValidationService()
        self.recommender = StatuteRecommendationService(validator=self.validator)
        logger.info("DeadlineExtractionService initialized with corpus access")

    def extract_deadlines(
        self, structured_summaries: List[DocumentSummaryStructured], case_type: str, case_facts: str
    ) -> List[Deadline]:
        """Extract and infer all relevant deadlines.

        Args:
        ----
            structured_summaries: Document summaries with key dates
            case_type: Practice area (e.g., "Construction Law")
            case_facts: Brief summary of case facts

        Returns:
        -------
            List of deadlines sorted by date
        """
        logger.info("Extracting deadlines from documents and Florida statutes")
        deadlines = []

        # 1. Extract from documents
        deadlines.extend(self._extract_from_documents(structured_summaries))

        # 2. Get deadline-relevant statutes from corpus
        keywords = self._extract_keywords(case_facts, case_type)
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
        logger.info(f"Identified {len(deadlines)} total deadlines")

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
                        "shall",
                        "respond by",
                        "payment due",
                        "completion",
                        "expire",
                        "final",
                        "last day",
                    ]
                )

                if is_deadline:
                    try:
                        deadline_date = datetime.strptime(key_date.date, "%Y-%m-%d")
                        deadlines.append(
                            Deadline(
                                date=deadline_date,
                                description=key_date.description,
                                source=summary.document_name,
                                urgency="normal",
                                deadline_type="contractual",
                            )
                        )
                    except ValueError:
                        logger.warning(f"Invalid date format: {key_date.date}")

        return deadlines

    def _infer_from_corpus_statutes(
        self, deadline_statutes: List, summaries: List[DocumentSummaryStructured], case_type: str
    ) -> List[Deadline]:
        """Infer deadlines from Florida statute text in corpus."""
        deadlines = []

        for statute_rec in deadline_statutes:
            statute_key = f"statute:{statute_rec.chapter}.{statute_rec.section}"

            if statute_key in self.validator.statutes:
                statute = self.validator.statutes[statute_key]
                statute_text = statute.get("text", "")

                # Extract deadline language from statute text
                deadline_info = self._parse_deadline_from_statute_text(statute_text, statute_rec.citation)

                if deadline_info:
                    # Find trigger date from documents
                    trigger_date = self._find_trigger_date(deadline_info["trigger_event"], summaries)

                    if trigger_date:
                        calculated_date = self._calculate_deadline_date(trigger_date, deadline_info["period"])

                        deadlines.append(
                            Deadline(
                                date=calculated_date,
                                description=deadline_info["description"],
                                source=statute_rec.citation,
                                urgency="normal",
                                deadline_type="statutory",
                                statute_text=statute_text[:200],  # First 200 chars
                            )
                        )

        return deadlines

    def _parse_deadline_from_statute_text(self, text: str, citation: str) -> Optional[Dict]:
        """Parse deadline language from statute text.

        Looks for patterns like:
        - "within 60 days"
        - "not later than 90 days after"
        - "before expiration of 5 years"
        """
        text_lower = text.lower()

        # Pattern: "within X days/months/years"
        within_match = re.search(r"within\s+(\d+)\s+(day|month|year)s?", text_lower)
        if within_match:
            amount = int(within_match.group(1))
            unit = within_match.group(2)

            return {
                "period": {"amount": amount, "unit": unit},
                "trigger_event": "relevant_date",  # Will need to identify from context
                "description": f"Deadline per {citation} ({amount} {unit}s from trigger)",
            }

        # Pattern: "not later than X days after [event]"
        not_later_match = re.search(r"not\s+later\s+than\s+(\d+)\s+(day|month|year)s?\s+after", text_lower)
        if not_later_match:
            amount = int(not_later_match.group(1))
            unit = not_later_match.group(2)

            return {
                "period": {"amount": amount, "unit": unit},
                "trigger_event": "after_event",
                "description": f"Deadline per {citation} ({amount} {unit}s)",
            }

        return None

    def _find_trigger_date(
        self, trigger_event: str, summaries: List[DocumentSummaryStructured]
    ) -> Optional[datetime]:
        """Find the trigger date for a deadline from documents."""
        # Look for relevant dates in summaries
        trigger_keywords = {
            "breach": ["breach", "stopped", "ceased", "terminated"],
            "notice": ["notice", "notified", "sent", "mailed"],
            "last_work": ["last work", "final", "completed", "finished"],
            "relevant_date": ["date", "when", "occurred"],
        }

        for summary in summaries:
            for key_date in summary.key_dates:
                desc_lower = key_date.description.lower()

                # Check if this date matches trigger event
                for trigger_type, keywords in trigger_keywords.items():
                    if any(kw in desc_lower for kw in keywords):
                        try:
                            return datetime.strptime(key_date.date, "%Y-%m-%d")
                        except ValueError:
                            continue

        return None

    def _calculate_deadline_date(self, trigger_date: datetime, period: Dict) -> datetime:
        """Calculate deadline date from trigger date and period."""
        amount = period["amount"]
        unit = period["unit"]

        if unit == "day":
            return trigger_date + timedelta(days=amount)
        elif unit == "month":
            return trigger_date + timedelta(days=amount * 30)  # Approximate
        elif unit == "year":
            return trigger_date + timedelta(days=amount * 365)  # Approximate

        return trigger_date

    def _extract_keywords(self, case_facts: str, case_type: str) -> List[str]:
        """Extract keywords from case facts and type."""
        keywords = []

        # Add case type keywords
        if case_type:
            keywords.extend(case_type.lower().split())

        # Extract common legal keywords
        case_lower = case_facts.lower()
        legal_terms = [
            "contract",
            "breach",
            "notice",
            "lien",
            "foreclosure",
            "tenant",
            "landlord",
            "construction",
            "defect",
            "repair",
        ]

        keywords.extend([term for term in legal_terms if term in case_lower])

        return list(set(keywords))

    def format_deadlines_for_prompt(self, deadlines: List[Deadline]) -> str:
        """Format deadlines for inclusion in letter generation prompt."""
        if not deadlines:
            return ""

        context = "**IDENTIFIED DEADLINES (Critical for Risks Section):**\n\n"

        # Group by urgency
        critical = [d for d in deadlines if d.urgency == "critical"]
        important = [d for d in deadlines if d.urgency == "important"]
        normal = [d for d in deadlines if d.urgency == "normal"]

        if critical:
            context += "🔴 **URGENT - Action Required Within 30 Days:**\n"
            for d in critical:
                context += f"• **{d.date.strftime('%B %d, %Y')}** - {d.description} [{d.source}]\n"
            context += "\n"

        if important:
            context += "⚠️ **Important - Next 30-90 Days:**\n"
            for d in important:
                context += f"• **{d.date.strftime('%B %d, %Y')}** - {d.description} [{d.source}]\n"
            context += "\n"

        if normal:
            context += "📅 **Long-term Deadlines:**\n"
            for d in normal[:3]:  # Limit to 3
                context += f"• **{d.date.strftime('%B %d, %Y')}** - {d.description} [{d.source}]\n"
            context += "\n"

        context += "**INSTRUCTION:** Include these deadlines in Section 2B (Risks and Deadlines) with [Source] citations.\n"

        return context
