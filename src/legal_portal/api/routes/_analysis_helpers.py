"""Shared helpers, Pydantic models, and constants used across analysis route modules.

This module contains functions and classes extracted from the monolithic analysis.py
during Phase 4 refactoring. It is imported by gap_routes, letter_routes, chat_routes,
document_status_routes, and analysis_core.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, validator

from legal_portal.api.middleware.retry import retry_sync
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import LetterType
from legal_portal.services.progress_manager import ProgressManager
from legal_portal.utils.type_safety import safe_str, safe_str_required, sanitize_nested_dict

logger = logging.getLogger(__name__)

# Explicit __all__ so that `from _analysis_helpers import *` re-exports
# underscore-prefixed symbols (Python's default * behavior skips them).
__all__ = [
    # Constants
    "_db_columns_cache",
    "_GAP_ANALYSIS_INPUT_SCHEMA_VERSION",
    "_SIGNATURE_TEXT_FALLBACK_PATTERNS",
    "_TEXT_SIGNING_DATE_PATTERNS",
    "_SIGNER_NAME_PATTERNS",
    "_SIGNATURE_INSTRUMENT_HINT_PATTERNS",
    "_SIGNATURE_VERIFICATION_STATUS_ALIASES",
    # Retry wrappers
    "_upsert_with_retry",
    "_update_case_with_retry",
    # Metrics / SSE / quality
    "_new_generation_metrics",
    "_emit_generation_metrics",
    "_to_sse",
    "_quality_report_placeholder",
    # Cancellation
    "AnalysisCancelledError",
    "_analysis_is_cancelled",
    "_cancel_analysis",
    "_update_analysis_progress",
    # User preferences
    "_get_user_ai_preferences",
    # Identity resolution
    "_first_non_empty_text",
    "_resolve_letter_identity_context",
    "_resolve_client_name_for_letter",
    # Signature helpers
    "_normalize_signature_verification_status",
    "_extract_signature_verification",
    "_apply_signature_verification_override",
    "_normalize_text_signing_date",
    "_infer_signature_detection_from_text",
    "_is_pdf_like_document",
    "_is_signature_inference_candidate",
    "_sample_text_for_state_hash",
    "_extract_signature_instrument_hints",
    # Case access helpers
    "_ensure_case_access",
    "_fetch_latest_analysis_result",
    # Pydantic models
    "AnalysisRequest",
    "AnalysisResponse",
    "LetterGenerationRequest",
    "LetterGenerationResponse",
    "StreamingAnalysisSaveRequest",
    "RecommendationLetterRequest",
    "RecommendationLetterResponse",
    "CalculateDemandAmountRequest",
    "CalculateDemandAmountResponse",
    "GapAnalysisRequest",
    "GapResolutionItemRequest",
    "GapResolutionRefreshRequest",
    "RetryDocumentsRequest",
    "SkipDocumentsRequest",
    "DocumentStatusResponse",
    "RecoveryActionResponse",
]

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class DBColumnsCache:
    """Encapsulates DB column existence checks to avoid repeated probing."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get(self, key: str, default=None):
        return self._cache.get(key, default)

    def __setitem__(self, key: str, value: Any):
        self._cache[key] = value

    def __getitem__(self, key: str):
        return self._cache[key]


_db_columns_cache = DBColumnsCache()
_GAP_ANALYSIS_INPUT_SCHEMA_VERSION = "2026-03-10-map-reduce-v1"

# ---------------------------------------------------------------------------
# Signature detection constants
# ---------------------------------------------------------------------------

_SIGNATURE_TEXT_FALLBACK_PATTERNS = [
    (
        "Counterpart signature page",
        re.compile(r"\bcounterpart\s+signature\s+page\b", re.IGNORECASE),
        True,
    ),
    (
        "Signed by marker",
        re.compile(r"\bsigned\s+by\b", re.IGNORECASE),
        True,
    ),
    (
        "Electronic signature marker",
        re.compile(r"\belectronically\s+signed\b", re.IGNORECASE),
        True,
    ),
    (
        "DocuSign envelope marker",
        re.compile(r"\bdocusign\s+envelope\s+id\b", re.IGNORECASE),
        True,
    ),
    (
        "Signature date marker",
        re.compile(r"\b(?:date\s+signed|signed\s+on|signature\s+date|executed\s+on)\b", re.IGNORECASE),
        True,
    ),
    (
        "Signature label",
        re.compile(r"\bsignature\s*[:_]", re.IGNORECASE),
        False,
    ),
]

_TEXT_SIGNING_DATE_PATTERNS = [
    re.compile(
        r"(?im)\b(?:date\s+signed|signed\s+on|signature\s+date|executed\s+on|completed)\s*[:\-]?\s*"
        r"(?P<date>[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|"
        r"\d{1,2}/\d{1,2}/\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)?|"
        r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?)"
    ),
]

_SIGNER_NAME_PATTERNS = [
    re.compile(r"(?im)^\s*signed\s+by\s*[:\-]\s*([A-Z][A-Za-z ,.'-]{2,80})\s*$"),
    re.compile(r"(?im)^\s*signature\s*[:\-]\s*([A-Z][A-Za-z ,.'-]{2,80})\s*$"),
    re.compile(r"(?im)^\s*/s/\s*([A-Z][A-Za-z ,.'-]{2,80})\s*$"),
]

_SIGNATURE_INSTRUMENT_HINT_PATTERNS = [
    ("subscription agreement", re.compile(r"\bsubscription\s+agreement\b", re.IGNORECASE)),
    ("investment agreement", re.compile(r"\binvestment\s+agreement\b", re.IGNORECASE)),
    ("purchase agreement", re.compile(r"\b(?:unit\s+)?purchase\s+agreement\b", re.IGNORECASE)),
    ("operating agreement", re.compile(r"\boperating\s+agreement\b", re.IGNORECASE)),
    ("promissory note", re.compile(r"\bpromissory\s+note\b", re.IGNORECASE)),
    ("convertible note", re.compile(r"\bconvertible\s+note\b", re.IGNORECASE)),
    ("loan agreement", re.compile(r"\bloan\s+agreement\b", re.IGNORECASE)),
    ("financing agreement", re.compile(r"\bfinancing\s+agreement\b", re.IGNORECASE)),
    ("membership units", re.compile(r"\bclass\s+[a-z0-9]+\s+units?\b", re.IGNORECASE)),
]

_SIGNATURE_VERIFICATION_STATUS_ALIASES = {
    "signed": "signed",
    "not_signed": "not_signed",
    "unsigned": "not_signed",
    "not signed": "not_signed",
    "not_detected": "not_signed",
    "not detected": "not_signed",
    "unknown": "unknown",
    "unclear": "unknown",
}

# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------


def _upsert_with_retry(supabase_client, table: str, data: dict, context_id: str, max_attempts: int = 3):
    """Upsert a row with retry on transient Supabase errors."""
    return retry_sync(
        lambda: supabase_client.table(table).upsert(data).execute(),
        max_attempts=max_attempts,
        context_label=f"{table} upsert for {context_id}",
    )


def _update_case_with_retry(supabase_client, case_id: str, update_data: dict, max_attempts: int = 3):
    """Update a case row with retry on transient Supabase errors."""
    return retry_sync(
        lambda: supabase_client.table("cases").update(update_data).eq("id", case_id).execute(),
        max_attempts=max_attempts,
        context_label=f"cases update for {case_id}",
    )


# ---------------------------------------------------------------------------
# Letter generation helpers
# ---------------------------------------------------------------------------


def _new_generation_metrics(
    *,
    analysis_id: str,
    letter_type: str,
    streaming: bool,
) -> Dict[str, Any]:
    """Create a standard metrics payload for letter generation."""
    return {
        "request_id": str(uuid.uuid4()),
        "analysis_id": analysis_id,
        "letter_type": letter_type,
        "streaming": streaming,
        "ttft_ms": None,
        "total_latency_ms": None,
        "model_calls": 0,
        "repair_attempted": False,
        "repair_applied": False,
        "strategy_used": False,
        "critic_attempted": False,
        "critic_applied": False,
        "critic_skipped_reason": None,
        "polish_applied": False,
        "polish_reverted": False,
        "polish_revert_reason": None,
        "polish_integrity_passed": None,
        "strategy_latency_ms": None,
        "critic_latency_ms": None,
        "timeout": False,
        "error_code": None,
        "lint_passed": None,
        "lint_score": None,
    }


def _emit_generation_metrics(metrics: Dict[str, Any]) -> None:
    """Emit request-level generation metrics in a single structured log line."""
    try:
        logger.info("[LETTER_METRICS] %s", json.dumps(metrics, default=str))
    except Exception:
        logger.info("[LETTER_METRICS] %s", metrics)


def _to_sse(payload: Dict[str, Any]) -> str:
    """Serialize an SSE data payload."""
    return f"data: {json.dumps(payload)}\n\n"


def _quality_report_placeholder(*, mode: str, letter_type: str) -> Dict[str, Any]:
    """Return a no-op quality report when lint is disabled/unavailable."""
    return {
        "mode": mode,
        "letter_type": letter_type,
        "lint_passed": True,
        "score": 100,
        "violations": [],
        "word_count": 0,
        "section_counts": {},
        "quality_report_v2": {
            "term_explainer_passed": True,
            "evidence_linkage_score": 1.0,
            "section_depth_score": 1.0,
            "unsupported_assertion_flags": [],
        },
    }


# ---------------------------------------------------------------------------
# Analysis state helpers
# ---------------------------------------------------------------------------


class AnalysisCancelledError(Exception):
    """Raised when an in-progress analysis is cancelled by the user."""


def _analysis_is_cancelled(supabase, analysis_id: str) -> bool:
    """Check whether an analysis has been cancelled.

    We treat either status='cancelled' or status='canceled' as cancelled.
    """
    try:
        resp = supabase.table("analysis_results").select("status").eq("id", analysis_id).limit(1).execute()
        if not resp.data:
            return False
        status_val = (resp.data[0].get("status") or "").lower()
        return status_val in {"cancelled", "canceled"}
    except Exception:
        # Never break processing due to a cancellation check failure
        return False


async def _cancel_analysis(
    *,
    supabase,
    case_id: str,
    analysis_id: str,
    progress_manager: Optional[ProgressManager] = None,
):
    """Cancel an analysis by updating DB state and emitting progress."""
    # Mark analysis as cancelled
    supabase.table("analysis_results").update({"status": "cancelled"}).eq("id", analysis_id).execute()

    # Un-stick the case so a new analysis can be started
    # (we keep the case and documents; user can retry later)
    supabase.table("cases").update({"status": "pending"}).eq("id", case_id).execute()

    # Best-effort progress update so UI can stop spinning
    payload = {
        "message": "Analysis cancelled by user.",
        "phase": "cancelled",
        "percent": 0,
        "status": "cancelled",
        "timestamp": datetime.utcnow().isoformat(),
    }
    if progress_manager is not None:
        try:
            await progress_manager.publish_progress(channel_id=analysis_id, **payload)
        except Exception:
            pass
    await _update_analysis_progress(supabase, analysis_id, payload)


async def _update_analysis_progress(supabase, analysis_id: str, payload: dict):
    """Update analysis progress in DB with safety check for column existence."""
    if _db_columns_cache.get("has_progress_column") is False:
        return

    try:
        supabase.table("analysis_results").update({"progress": payload}).eq("id", analysis_id).execute()
        _db_columns_cache["has_progress_column"] = True
    except Exception as e:
        if "column analysis_results.progress does not exist" in str(e):
            logger.warning("DB column analysis_results.progress missing. Disabling DB updates.")
            _db_columns_cache["has_progress_column"] = False
        else:
            logger.warning(f"Failed to persist progress to DB: {e}")


async def _get_user_ai_preferences(user_id: str, supabase) -> Optional[Dict[str, str]]:
    """Fetch user's AI model preferences from profile."""
    try:
        response = supabase.table("profiles").select("ai_preferences").eq("id", user_id).single().execute()
        if response.data and response.data.get("ai_preferences"):
            return response.data["ai_preferences"]
    except Exception as e:
        logger.warning(f"Could not fetch user AI preferences: {e}")
    return None


# ---------------------------------------------------------------------------
# Identity resolution helpers
# ---------------------------------------------------------------------------


def _first_non_empty_text(*values: Any) -> Optional[str]:
    """Return the first non-empty string-like value, excluding booleans.

    Delegates to safe_str() for type-safe extraction from untyped data.
    """
    for value in values:
        result = safe_str(value)
        if result:
            return result
    return None


def _resolve_letter_identity_context(
    *,
    supabase,
    case_id: str,
    artifacts: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """Resolve attorney/firm/contact/client identity context with robust fallbacks."""
    artifacts_map = artifacts if isinstance(artifacts, dict) else {}
    overrides_map = overrides if isinstance(overrides, dict) else {}

    case_data: Dict[str, Any] = {}
    profile_data: Dict[str, Any] = {}

    try:
        case_resp = supabase.table("cases").select("*").eq("id", case_id).limit(1).execute()
        if case_resp.data:
            case_data = case_resp.data[0] or {}
    except Exception as case_err:
        logger.warning("[LETTER] Failed to load case identity context for %s: %s", case_id, case_err)

    case_metadata = case_data.get("metadata")
    if not isinstance(case_metadata, dict):
        case_metadata = {}
    else:
        case_metadata = sanitize_nested_dict(case_metadata)

    clio_matter_data = case_data.get("clio_matter_data")
    if not isinstance(clio_matter_data, dict):
        clio_matter_data = {}
    else:
        clio_matter_data = sanitize_nested_dict(clio_matter_data)

    user_id = case_data.get("user_id")
    if user_id:
        try:
            profile_resp = (
                supabase.table("profiles")
                .select("full_name,firm_name,phone,email")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if profile_resp.data:
                profile_data = profile_resp.data[0] or {}
        except Exception as profile_err:
            logger.warning(
                "[LETTER] Failed to load profile identity context for %s: %s",
                case_id,
                profile_err,
            )

    attorney_name = _first_non_empty_text(
        overrides_map.get("attorney_name"),
        overrides_map.get("attorneyName"),
        overrides_map.get("name"),
        artifacts_map.get("attorney_name"),
        artifacts_map.get("attorneyName"),
        case_data.get("attorney_name"),
        case_data.get("attorneyName"),
        case_metadata.get("attorney_name"),
        case_metadata.get("attorneyName"),
        clio_matter_data.get("responsible_attorney"),
        clio_matter_data.get("responsibleAttorney"),
        profile_data.get("full_name"),
    )
    firm_name = _first_non_empty_text(
        overrides_map.get("firm_name"),
        overrides_map.get("firmName"),
        overrides_map.get("firm"),
        artifacts_map.get("firm_name"),
        artifacts_map.get("firmName"),
        case_data.get("firm_name"),
        case_data.get("firmName"),
        case_metadata.get("firm_name"),
        case_metadata.get("firmName"),
        clio_matter_data.get("firm_name"),
        clio_matter_data.get("firmName"),
        clio_matter_data.get("law_firm_name"),
        clio_matter_data.get("lawFirmName"),
        profile_data.get("firm_name"),
    )
    contact_phone = _first_non_empty_text(
        overrides_map.get("contact_phone"),
        overrides_map.get("contactPhone"),
        overrides_map.get("phone"),
        artifacts_map.get("contact_phone"),
        artifacts_map.get("contactPhone"),
        case_data.get("contact_phone"),
        case_data.get("contactPhone"),
        case_metadata.get("contact_phone"),
        case_metadata.get("contactPhone"),
        clio_matter_data.get("contact_phone"),
        clio_matter_data.get("contactPhone"),
        profile_data.get("phone"),
    )
    contact_email = _first_non_empty_text(
        overrides_map.get("contact_email"),
        overrides_map.get("contactEmail"),
        overrides_map.get("email"),
        artifacts_map.get("contact_email"),
        artifacts_map.get("contactEmail"),
        case_data.get("contact_email"),
        case_data.get("contactEmail"),
        case_metadata.get("contact_email"),
        case_metadata.get("contactEmail"),
        clio_matter_data.get("contact_email"),
        clio_matter_data.get("contactEmail"),
        profile_data.get("email"),
    )
    client_name = _first_non_empty_text(
        overrides_map.get("client_name"),
        overrides_map.get("clientName"),
        artifacts_map.get("client_name"),
        artifacts_map.get("clientName"),
        case_data.get("client_name"),
        case_data.get("clientName"),
        case_metadata.get("client_name"),
        case_metadata.get("clientName"),
        clio_matter_data.get("client_name"),
        clio_matter_data.get("clientName"),
    )

    return {
        "attorney_name": attorney_name,
        "firm_name": firm_name,
        "contact_phone": contact_phone,
        "contact_email": contact_email,
        "client_name": client_name,
    }


def _resolve_client_name_for_letter(
    *,
    resolved_identity: Optional[Dict[str, Any]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    fact_matrix: Optional[Any] = None,
) -> str:
    """Resolve client name from identity context with fact-matrix fallback."""
    client_name = _first_non_empty_text(
        (resolved_identity or {}).get("client_name"),
        (artifacts or {}).get("client_name"),
        (artifacts or {}).get("clientName"),
    )

    if not client_name and fact_matrix is not None:
        parties: List[Any] = []
        if isinstance(fact_matrix, dict):
            parties = fact_matrix.get("parties", []) or []
        else:
            parties = getattr(fact_matrix, "parties", []) or []

        for party in parties:
            role = ""
            name = ""
            if isinstance(party, dict):
                role = safe_str(party.get("role")) or ""
                name = safe_str(party.get("name")) or ""
            else:
                role = safe_str(getattr(party, "role", None)) or ""
                name = safe_str(getattr(party, "name", None)) or ""

            if role.lower() in {"client", "plaintiff", "claimant"} and name.strip():
                client_name = name.strip()
                break

    return client_name or "Client"


# ---------------------------------------------------------------------------
# Signature detection helpers
# ---------------------------------------------------------------------------


def _normalize_signature_verification_status(raw_status: Any) -> Optional[str]:
    """Normalize metadata signature-verification status to canonical values."""
    text = str(raw_status or "").strip().lower()
    if not text:
        return None
    return _SIGNATURE_VERIFICATION_STATUS_ALIASES.get(text)


def _extract_signature_verification(doc_metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Extract normalized signature-verification metadata, if present."""
    metadata = doc_metadata if isinstance(doc_metadata, dict) else {}
    raw = metadata.get("signature_verification")
    if not isinstance(raw, dict):
        return None

    normalized_status = _normalize_signature_verification_status(raw.get("status"))
    if not normalized_status:
        return None

    signer_names = raw.get("signer_names")
    if not isinstance(signer_names, list):
        signer_names = []
    cleaned_signers = [str(name).strip() for name in signer_names if str(name).strip()][:10]

    notes = str(raw.get("notes") or "").strip() or None
    signing_date = str(raw.get("signing_date") or "").strip() or None

    return {
        "status": normalized_status,
        "notes": notes,
        "signing_date": signing_date,
        "signer_names": cleaned_signers,
        "verified_at": raw.get("verified_at"),
        "verified_by_user_id": raw.get("verified_by_user_id"),
    }


def _apply_signature_verification_override(
    signature_detection: Optional[Dict[str, Any]],
    doc_metadata: Optional[Dict[str, Any]],
    *,
    file_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Apply attorney signature verification override to signature-detection metadata."""
    verification = _extract_signature_verification(doc_metadata)
    if not verification:
        return signature_detection

    status_val = verification.get("status")
    base: Dict[str, Any] = dict(signature_detection or {})

    if status_val == "signed":
        base["status"] = "signed"
        base["confidence"] = "verified"
        base["detection_source"] = "attorney_verification"
        base["has_signature_markers"] = True
        marker_count = base.get("signature_marker_count")
        try:
            marker_count_int = int(marker_count)
        except (TypeError, ValueError):
            marker_count_int = 0
        base["signature_marker_count"] = max(1, marker_count_int)
    elif status_val == "not_signed":
        base["status"] = "not_detected"
        base["confidence"] = "verified"
        base["detection_source"] = "attorney_verification"
    else:
        # "unknown" status should not fabricate signature detection if no baseline exists.
        if not base:
            return None

    base["verified_by_attorney"] = True
    if verification.get("verified_at"):
        base["verified_at"] = verification.get("verified_at")
    if verification.get("verified_by_user_id"):
        base["verified_by_user_id"] = verification.get("verified_by_user_id")
    if verification.get("notes"):
        base["verification_notes"] = verification.get("notes")
    if verification.get("signing_date"):
        base["signing_date"] = _normalize_text_signing_date(verification.get("signing_date"))
    if verification.get("signer_names"):
        base["signer_names"] = verification.get("signer_names")

    indicators = base.get("indicators")
    if not isinstance(indicators, list):
        indicators = []
    indicator = f"Attorney verified signature status: {status_val}"
    if file_name:
        indicator += f" ({file_name})"
    if indicator not in indicators:
        indicators = indicators + [indicator]
    base["indicators"] = indicators[:10]

    return base


def _normalize_text_signing_date(raw_date: Optional[str]) -> Optional[str]:
    """Normalize common textual signing date formats to ISO-like strings."""
    if not raw_date:
        return None

    cleaned = raw_date.strip()
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            if " " in fmt:
                return parsed.strftime("%Y-%m-%dT%H:%M:%S")
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return cleaned


def _infer_signature_detection_from_text(extracted_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Infer likely signature presence for legacy PDFs lacking signature metadata."""
    text = (extracted_text or "").strip()
    if not text:
        return None

    indicators: List[str] = []
    strong_hits = 0
    weak_hits = 0

    for label, pattern, is_strong in _SIGNATURE_TEXT_FALLBACK_PATTERNS:
        if pattern.search(text):
            indicators.append(label)
            if is_strong:
                strong_hits += 1
            else:
                weak_hits += 1

    # Avoid false positives from a single blank "Signature:" label.
    if strong_hits == 0 and weak_hits < 2:
        return None

    raw_signing_date = None
    for pattern in _TEXT_SIGNING_DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            raw_signing_date = (match.group("date") or "").strip()
            break

    signer_names: List[str] = []
    seen_signer_keys = set()
    for pattern in _SIGNER_NAME_PATTERNS:
        for match in pattern.findall(text):
            candidate = re.sub(r"\s+", " ", match).strip()
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen_signer_keys:
                continue
            seen_signer_keys.add(key)
            signer_names.append(candidate)
            if len(signer_names) >= 5:
                break
        if len(signer_names) >= 5:
            break

    confidence = "high" if strong_hits >= 2 else "medium" if strong_hits == 1 else "low"

    return {
        "status": "signed",
        "confidence": confidence,
        "has_digital_signature": False,
        "has_signature_markers": True,
        "signature_marker_count": len(indicators),
        "signing_date": _normalize_text_signing_date(raw_signing_date),
        "signing_date_raw": raw_signing_date,
        "signer_names": signer_names,
        "indicators": indicators[:10],
        "detection_source": "analysis_text_fallback",
    }


def _is_pdf_like_document(file_name: Optional[str], file_type: Optional[str]) -> bool:
    """Return True when a document is likely a PDF."""
    ft = (file_type or "").lower()
    name = (file_name or "").lower()
    return ft in {"application/pdf", "pdf"} or name.endswith(".pdf")


def _is_signature_inference_candidate(file_name: Optional[str], file_type: Optional[str]) -> bool:
    """Return True when text-based signature inference should run for this document."""
    ft = (file_type or "").lower()
    name = (file_name or "").lower()

    blocked_mime_prefixes = ("image/", "video/", "audio/")
    if any(ft.startswith(prefix) for prefix in blocked_mime_prefixes):
        return False

    blocked_mime_types = {
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    }
    if ft in blocked_mime_types:
        return False

    blocked_extensions = (
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tiff",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".mp3",
        ".wav",
        ".aac",
        ".flac",
        ".m4a",
    )
    return not any(name.endswith(ext) for ext in blocked_extensions)


def _sample_text_for_state_hash(raw_text: Optional[str], limit: int = 16000) -> str:
    """Build a compact text sample for deterministic state hashing."""
    text = (raw_text or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2) :]
    return f"{head}\n... [omitted for hash] ...\n{tail}"


def _extract_signature_instrument_hints(
    file_name: Optional[str],
    extracted_text: Optional[str],
) -> List[str]:
    """Extract contract/instrument hints for signature reconciliation matching."""
    sampled_text = _sample_text_for_state_hash(extracted_text, limit=24000)
    corpus = f"{file_name or ''}\n{sampled_text}"

    hints: List[str] = []
    for label, pattern in _SIGNATURE_INSTRUMENT_HINT_PATTERNS:
        if pattern.search(corpus):
            hints.append(label)

    deduped: List[str] = []
    seen = set()
    for hint in hints:
        key = hint.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hint)
        if len(deduped) >= 6:
            break

    return deduped


# ---------------------------------------------------------------------------
# Case access helpers
# ---------------------------------------------------------------------------


def _ensure_case_access(supabase_client, case_id: str, user_id: str) -> None:
    """Ensure the authenticated user owns the requested case."""
    case_response = (
        supabase_client.table("cases").select("id").eq("id", case_id).eq("user_id", user_id).execute()
    )

    if not case_response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")


def _fetch_latest_analysis_result(supabase_client, case_id: str) -> Dict[str, Any]:
    """Fetch the latest completed analysis result for a case."""
    response = (
        supabase_client.table("analysis_results")
        .select("id, result")
        .eq("case_id", case_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No completed analysis found for this case",
        )

    record = response.data[0]
    if not record.get("result"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Analysis result payload is missing",
        )

    return record


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AnalysisRequest(BaseModel):
    """Request model for starting case analysis."""

    case_id: str
    provider: Optional[str] = Field(default="openai", pattern="^(openai|anthropic)$")


class AnalysisResponse(BaseModel):
    """Response model for analysis status."""

    id: str
    case_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LetterGenerationRequest(BaseModel):
    """Request payload for on-demand letter generation."""

    case_id: str
    letter_type: LetterType = LetterType.FINDINGS
    target_party_name: Optional[str] = None
    demand_amount: Optional[float] = None
    demand_deadline: str = "10 business days"
    specific_demands: List[str] = Field(default_factory=list)
    attorney_name: Optional[str] = None
    firm_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    client_name: Optional[str] = None
    force_generation: bool = Field(
        default=False, description="Override completeness gate for weak cases"
    )

    @validator("attorney_name", "firm_name", "contact_phone", "contact_email", "client_name", pre=True)
    def sanitize_string_fields(cls, v):
        """Convert boolean to None to prevent boolean-to-string conversion."""
        if isinstance(v, bool):
            return None
        return v


class LetterGenerationResponse(BaseModel):
    """Response payload for generated letters."""

    letter_html: str
    letter_type: LetterType = LetterType.FINDINGS
    target_party_name: Optional[str] = None
    quality_report: Optional[Dict[str, Any]] = None
    generation_metrics: Optional[Dict[str, Any]] = None


class StreamingAnalysisSaveRequest(BaseModel):
    """Request to save streaming analysis result."""

    content: str = Field(..., description="The markdown content from streaming analysis")


class RecommendationLetterRequest(BaseModel):
    """Request payload for generating recommendation-based letters."""

    case_id: str
    letter_type: str = Field(
        description="Type of recommendation letter: proceed, request_documents, settlement_advisory, declination"
    )
    attorney_name: Optional[str] = None
    firm_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    client_name: Optional[str] = None


class RecommendationLetterResponse(BaseModel):
    """Response payload for generated recommendation letters."""

    letter_html: str
    letter_type: str
    recommendation_category: Optional[str] = None
    quality_report: Optional[Dict[str, Any]] = None
    generation_metrics: Optional[Dict[str, Any]] = None


class CalculateDemandAmountRequest(BaseModel):
    """Request to calculate demand amount."""

    case_id: str
    target_party_name: str


class CalculateDemandAmountResponse(BaseModel):
    """Response with calculated demand amount."""

    amount: float
    reasoning: str
    breakdown: List[Dict[str, Any]]


class GapAnalysisRequest(BaseModel):
    """Request model for on-demand gap analysis."""

    case_id: str = Field(..., description="The case ID to analyze for gaps")
    force_refresh: bool = Field(
        default=False,
        description="If true, bypass cached gap analysis and re-run AI gap analysis",
    )


class GapResolutionItemRequest(BaseModel):
    """A user-provided resolution for a specific gap."""

    gap_id: str = Field(..., description="Gap ID from the existing gap analysis")
    resolution_text: str = Field(..., description="User explanation/evidence that addresses the gap")
    mark_resolved: bool = Field(
        default=True,
        description="Whether user believes this gap is resolved",
    )
    related_document_ids: List[str] = Field(
        default_factory=list,
        description="Optional document IDs supporting this resolution",
    )

    @validator("resolution_text", pre=True)
    def sanitize_resolution_text(cls, v):
        """Convert boolean to empty string to prevent .strip() errors."""
        if isinstance(v, bool):
            return ""
        return v


class GapResolutionRefreshRequest(BaseModel):
    """Request model for applying user resolutions and refreshing gap analysis."""

    case_id: str = Field(..., description="The case ID to update")
    resolutions: List[GapResolutionItemRequest] = Field(
        default_factory=list,
        description="Per-gap user resolutions",
    )
    global_resolution_notes: Optional[str] = Field(
        default=None,
        description="General notes or context to apply across all gaps",
    )
    attached_document_ids: List[str] = Field(
        default_factory=list,
        description="Optional supporting case document IDs to prioritize",
    )
    force_refresh: bool = Field(
        default=False,
        description="If true, re-run even when resolution payload is unchanged",
    )

    @validator("global_resolution_notes", pre=True)
    def sanitize_global_notes(cls, v):
        """Convert boolean to None to prevent .strip() errors."""
        if isinstance(v, bool):
            return None
        return v


class RetryDocumentsRequest(BaseModel):
    """Request to retry failed documents."""

    document_ids: List[str] = Field(
        default=[],
        description="List of document IDs to retry, or empty to retry all failed"
    )


class SkipDocumentsRequest(BaseModel):
    """Request to skip failed documents and continue."""

    document_ids: List[str] = Field(
        default=[],
        description="List of document IDs to skip, or empty to skip all failed"
    )


class DocumentStatusResponse(BaseModel):
    """Response with document processing status."""

    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    skipped: int
    documents: Dict[str, Any] = Field(default_factory=dict)
    can_proceed: bool = False


class RecoveryActionResponse(BaseModel):
    """Response after retry/skip action."""

    success: bool
    action: str
    affected_count: int
    message: str
