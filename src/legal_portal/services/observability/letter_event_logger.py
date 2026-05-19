"""Records letter-generation requests into ``letter_generation_events``.

Why a separate table (not just ``analysis_results.result.generated_letters``):
  - generated_letters is overwritten on every regeneration → no history
  - generated_letters never records *failed* attempts (user clicked,
    it errored, no row written anywhere today)
  - One row per request captures duration, QA roll-up, and error,
    queryable without walking JSONB trees

Critical invariant: this module MUST NEVER raise into letter generation
code paths. If the DB is unreachable, ``begin()`` returns ``None`` and
``complete()``/``fail()`` no-op. The letter still ships.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


def _now_iso() -> str:
    """ISO-8601 UTC timestamp for completed_at writes."""
    return datetime.now(timezone.utc).isoformat()


def summarize_qa(qa_summary: Optional[Dict[str, Any]]) -> Optional[bool]:
    """Roll up the multi-field quality_report_v2 dict into one bool.

    Returns:
      - ``True``  if all measurable checks passed
      - ``False`` if at least one measurable check failed
      - ``None``  if no checks ran (empty dict / None input)

    Failure conditions:
      - ``term_explainer_passed`` is explicitly ``False``
      - ``demand_specificity_passed`` is explicitly ``False`` (only set
        for demand letters; null for findings)
      - ``evidence_linkage_score`` < 0.5
      - ``unsupported_assertion_flags`` is non-empty
    """
    if not qa_summary:
        return None

    measured = False

    if "term_explainer_passed" in qa_summary:
        measured = True
        if qa_summary["term_explainer_passed"] is False:
            return False

    if qa_summary.get("demand_specificity_passed") is False:
        measured = True
        return False

    if "evidence_linkage_score" in qa_summary:
        measured = True
        score = qa_summary["evidence_linkage_score"]
        if isinstance(score, (int, float)) and score < 0.5:
            return False

    flags = qa_summary.get("unsupported_assertion_flags")
    if isinstance(flags, list) and flags:
        return False

    return True if measured else None


class LetterEventLogger:
    """Thin write-only wrapper around letter_generation_events.

    Construct with a supabase client (service_role). All methods are
    fail-safe — they log a warning and return on any exception.
    """

    TABLE = "letter_generation_events"

    def __init__(self, supabase: Any) -> None:
        self._sb = supabase

    def begin(
        self,
        *,
        user_id: Optional[str],
        case_id: str,
        analysis_id: Optional[str],
        letter_type: str,
        letter_key: Optional[str] = None,
    ) -> Optional[str]:
        """Insert a 'requested' row. Returns the event id or None on failure."""
        try:
            resp = (
                self._sb.table(self.TABLE)
                .insert({
                    "user_id": user_id,
                    "case_id": case_id,
                    "analysis_id": analysis_id,
                    "letter_type": letter_type,
                    "letter_key": letter_key,
                    "status": "requested",
                })
                .execute()
            )
            rows = getattr(resp, "data", None) or []
            if rows and rows[0].get("id"):
                return rows[0]["id"]
            return None
        except Exception as e:
            logger.warning(f"letter_event_logger.begin failed: {e}")
            return None

    def complete(
        self,
        event_id: Optional[str],
        *,
        qa_summary: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        if not event_id:
            return
        try:
            payload: Dict[str, Any] = {
                "status": "completed",
                "qa_summary": qa_summary,
                "qa_passed": summarize_qa(qa_summary),
                "completed_at": _now_iso(),
            }
            if duration_ms is not None:
                payload["duration_ms"] = int(duration_ms)
            (
                self._sb.table(self.TABLE)
                .update(payload)
                .eq("id", event_id)
                .execute()
            )
        except Exception as e:
            logger.warning(f"letter_event_logger.complete failed: {e}")

    def fail(
        self,
        event_id: Optional[str],
        *,
        error: str,
        duration_ms: Optional[int] = None,
    ) -> None:
        if not event_id:
            return
        try:
            payload: Dict[str, Any] = {
                "status": "failed",
                "error": (error or "")[:2000],  # cap stored error length
                "completed_at": _now_iso(),
            }
            if duration_ms is not None:
                payload["duration_ms"] = int(duration_ms)
            (
                self._sb.table(self.TABLE)
                .update(payload)
                .eq("id", event_id)
                .execute()
            )
        except Exception as e:
            logger.warning(f"letter_event_logger.fail failed: {e}")
