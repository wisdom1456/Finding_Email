"""Metrics for evaluating document grouping quality.

Logs structured metrics for monitoring true positives, false positives,
false negatives, and impact on summarization and context building.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from legal_portal.core.data_models import DocumentGroup

logger = logging.getLogger(__name__)


@dataclass
class GroupingMetrics:
    """Metrics snapshot for a single case's grouping results."""

    case_id: str
    total_documents: int
    groups_detected: int
    grouped_documents: int
    ungrouped_documents: int
    groups_by_type: Dict[str, int] = field(default_factory=dict)
    # Set after summarization (Phase B)
    individual_summaries_generated: Optional[int] = None
    group_summaries_generated: Optional[int] = None
    ai_calls_saved: Optional[int] = None
    # Set after context building (Phase C)
    context_entries_before: Optional[int] = None
    context_entries_after: Optional[int] = None
    tokens_before: Optional[int] = None
    tokens_after: Optional[int] = None

    def log(self):
        """Emit structured log for monitoring dashboards."""
        logger.info(
            f"[GROUPING:METRICS] case={self.case_id} "
            f"docs={self.total_documents} groups={self.groups_detected} "
            f"grouped={self.grouped_documents} ungrouped={self.ungrouped_documents} "
            f"by_type={self.groups_by_type} "
            f"ai_calls_saved={self.ai_calls_saved} "
            f"token_reduction={self._token_reduction_pct()}"
        )

    def _token_reduction_pct(self) -> Optional[str]:
        if self.tokens_before and self.tokens_after:
            reduction = (1 - self.tokens_after / self.tokens_before) * 100
            return f"{reduction:.1f}%"
        return None


def build_grouping_metrics(
    case_id: str,
    total_documents: int,
    groups: List[DocumentGroup],
) -> GroupingMetrics:
    """Build initial metrics from detection results."""
    by_type: Dict[str, int] = {}
    for g in groups:
        by_type[g.group_type.value] = by_type.get(g.group_type.value, 0) + 1

    grouped = sum(g.member_count for g in groups)
    return GroupingMetrics(
        case_id=case_id,
        total_documents=total_documents,
        groups_detected=len(groups),
        grouped_documents=grouped,
        ungrouped_documents=total_documents - grouped,
        groups_by_type=by_type,
    )
