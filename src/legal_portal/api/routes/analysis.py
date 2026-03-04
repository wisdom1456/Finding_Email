"""Document analysis endpoints."""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import traceback
import uuid
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, List, Literal, Optional

import html2text
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.rate_limiter import limiter
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import (
    ChatMessageRequest,
    ChatMessageResponse,
    ClioMatterContext,
    DocumentStatus,
    DocumentType,
    LetterType,
    ProcessedDocument,
    ProcessingResult,
    SkippedDocument,
)
from legal_portal.services.case_chat_service import CaseChatService
from legal_portal.services.demand_letter_service import DemandLetterService
from legal_portal.services.document_formatter import DocumentFormatterService
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.letter_validation_service import LetterValidationService
from legal_portal.services.main_processor import process_case_documents
from legal_portal.services.progress_manager import ProgressManager
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.security import sanitize_text_for_db
from legal_portal.utils.throttled_db_writer import ThrottledDBWriter
from legal_portal.utils.type_safety import safe_str, safe_str_required, sanitize_nested_dict

router = APIRouter()
logger = logging.getLogger(__name__)

# Cache for database column existence checks
_DB_COLUMNS_CACHE = {}
_GAP_ANALYSIS_INPUT_SCHEMA_VERSION = "2026-02-18-reconciliation-v3"


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
    global _DB_COLUMNS_CACHE

    if _DB_COLUMNS_CACHE.get("has_progress_column") is False:
        return

    try:
        supabase.table("analysis_results").update({"progress": payload}).eq("id", analysis_id).execute()
        _DB_COLUMNS_CACHE["has_progress_column"] = True
    except Exception as e:
        if "column analysis_results.progress does not exist" in str(e):
            logger.warning("DB column analysis_results.progress missing. Disabling DB updates.")
            _DB_COLUMNS_CACHE["has_progress_column"] = False
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

    status = verification.get("status")
    base: Dict[str, Any] = dict(signature_detection or {})

    if status == "signed":
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
    elif status == "not_signed":
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
    indicator = f"Attorney verified signature status: {status}"
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


# Optional WeasyPrint import for PDF generation
try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    WEASYPRINT_AVAILABLE = False
    HTML = None
    logger.warning(f"WeasyPrint not available: {e}. PDF generation will be disabled.")

ARTIFACT_BUCKET = os.getenv("SUPABASE_ARTIFACT_BUCKET", "documents")
ARTIFACT_PREFIX = os.getenv("ANALYSIS_ARTIFACT_PREFIX", "analysis_artifacts")
SIGNED_URL_TTL = int(os.getenv("ANALYSIS_ARTIFACT_URL_TTL", "3600"))

_HTML2TEXT_CONVERTER = html2text.HTML2Text()
_HTML2TEXT_CONVERTER.ignore_links = False
_HTML2TEXT_CONVERTER.body_width = 0


def _html_to_pdf_bytes(html: Optional[str]) -> Optional[bytes]:
    """Render HTML content to PDF bytes using WeasyPrint."""
    if not html:
        return None
    if not WEASYPRINT_AVAILABLE:
        logger.warning("WeasyPrint not available, PDF generation skipped")
        return None
    try:
        return HTML(string=html, base_url=os.getcwd()).write_pdf()
    except Exception as exc:
        logger.warning(f"Failed to render PDF artifact: {exc}")
        return None


def _html_to_plain_text(html: Optional[str]) -> str:
    """Convert HTML to plain text for email bodies."""
    if not html:
        return ""
    try:
        return _HTML2TEXT_CONVERTER.handle(html)
    except Exception as exc:
        logger.warning(f"Failed to convert HTML to plain text: {exc}")
        return ""


def _generate_eml_bytes(html: Optional[str], subject: str) -> Optional[bytes]:
    """Generate an EML file from HTML content."""
    if not html:
        return None
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["To"] = "client@example.com"
        msg["From"] = "noreply@legal-portal.local"
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        plain_text = _html_to_plain_text(html)
        msg.set_content(plain_text or "Please see the attached findings email.")
        msg.add_alternative(html, subtype="html")
        return msg.as_bytes()
    except Exception as exc:
        logger.warning(f"Failed to generate EML artifact: {exc}")
        return None


def _store_artifact(storage, path: str, data: bytes, content_type: str) -> Optional[Dict[str, Any]]:
    """Upload artifact bytes to Supabase storage and return metadata."""
    if not data:
        return None
    try:
        # Remove existing artifact if present
        try:
            storage.remove([path])
        except Exception:
            pass
        storage.upload(path, data, {"content-type": content_type})
        return {
            "bucket": ARTIFACT_BUCKET,
            "path": path,
            "content_type": content_type,
            "filename": os.path.basename(path),
        }
    except Exception as exc:
        logger.warning(f"Failed to upload artifact {path}: {exc}")
        return None


def _generate_and_store_artifacts(
    result: ProcessingResult,
    case_id: str,
    analysis_id: str,
    supabase_client,
) -> Dict[str, Dict[str, Any]]:
    """Create PDF/EML/appendix/citation map artifacts and store them in Supabase."""
    artifacts: Dict[str, Dict[str, Any]] = {}
    prefix = f"{ARTIFACT_PREFIX}/{case_id}/{analysis_id}"
    storage = supabase_client.storage.from_(ARTIFACT_BUCKET)

    pdf_bytes = _html_to_pdf_bytes(result.main_letter)
    if pdf_bytes:
        metadata = _store_artifact(storage, f"{prefix}/findings-email.pdf", pdf_bytes, "application/pdf")
        if metadata:
            artifacts["letter_pdf"] = metadata

    eml_bytes = _generate_eml_bytes(result.main_letter, f"Findings Email - Case {case_id}")
    if eml_bytes:
        metadata = _store_artifact(storage, f"{prefix}/findings-email.eml", eml_bytes, "message/rfc822")
        if metadata:
            artifacts["letter_eml"] = metadata

    if result.main_letter_with_citations:
        html_bytes = result.main_letter_with_citations.encode("utf-8")
        metadata = _store_artifact(
            storage,
            f"{prefix}/findings-email-cited.html",
            html_bytes,
            "text/html",
        )
        if metadata:
            artifacts["letter_cited_html"] = metadata

    if result.citation_appendix:
        appendix_bytes = result.citation_appendix.encode("utf-8")
        metadata = _store_artifact(storage, f"{prefix}/citation-appendix.html", appendix_bytes, "text/html")
        if metadata:
            artifacts["citation_appendix_html"] = metadata

    if result.citation_map:
        map_bytes = json.dumps(result.citation_map, indent=2).encode("utf-8")
        metadata = _store_artifact(storage, f"{prefix}/citation-map.json", map_bytes, "application/json")
        if metadata:
            artifacts["citation_map"] = metadata

    return {key: value for key, value in artifacts.items() if value}


def _attach_signed_artifact_urls(service_supabase, artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Attach signed URLs to stored artifact metadata."""
    enriched: Dict[str, Any] = {}
    for key, info in artifacts.items():
        # Skip if info is not a dictionary (e.g. it's a context string)
        if not isinstance(info, dict):
            enriched[key] = info
            continue

        path = info.get("path")
        bucket = info.get("bucket", ARTIFACT_BUCKET)
        if not path:
            enriched[key] = info
            continue
        try:
            signed = service_supabase.storage.from_(bucket).create_signed_url(path, SIGNED_URL_TTL)
            signed_url = signed.get("signedURL")
            enriched[key] = {**info, "signed_url": signed_url}
        except Exception as exc:
            logger.warning(f"Failed to create signed URL for {path}: {exc}")
            enriched[key] = info
    return enriched or artifacts


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
    letter_type: LetterType
    target_party_name: Optional[str] = None
    quality_report: Optional[Dict[str, Any]] = None
    generation_metrics: Optional[Dict[str, Any]] = None


def _download_and_extract_documents(
    case_id: str, documents: List[Dict[str, Any]], supabase, temp_dir: str
) -> tuple[Optional[str], List[str], Dict[str, str], List[SkippedDocument]]:
    """Download and extract documents synchronously."""
    file_paths = []
    intake_form_path = None
    path_to_id_map = {}
    skipped_documents = []

    for doc in documents:
        # Check status first - skip critical failures
        status = doc.get("status")
        if status in [DocumentStatus.DOWNLOAD_FAILED, DocumentStatus.CORRUPTED, DocumentStatus.SKIPPED]:
            logger.info(f"Auto-skipping document with status {status}: {doc['file_name']}")
            skipped_documents.append(
                SkippedDocument(
                    document_id=doc["id"],
                    file_name=doc["file_name"],
                    reason=f"Status is {status}",
                    error_type=status or "UNKNOWN",
                    recommendation="Re-upload or fix the document in the verification dashboard.",
                )
            )
            continue

        # Skip documents flagged as junk
        if doc.get("is_flagged_as_junk"):
            logger.info(f"Skipping junk-flagged document: {doc['file_name']}")
            continue

        storage_path = doc.get("storage_path")

        # Check if we have neither text nor a file
        text_content = doc.get("manual_text") or doc.get("extracted_text")
        if not text_content and not storage_path:
            logger.warning(f"Skipping document with no content and no storage path: {doc['file_name']}")
            skipped_documents.append(
                SkippedDocument(
                    document_id=doc["id"],
                    file_name=doc["file_name"],
                    reason="No extracted text and no storage file found.",
                    error_type="MISSING_CONTENT",
                    recommendation="Please re-upload this document.",
                )
            )
            continue
        # Robust sanitization to avoid filesystem issues with special characters (spaces, parentheses, etc)
        safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", doc["file_name"])
        # Ensure we don't have too many underscores and keep the extension
        safe_filename = re.sub(r"_+", "_", safe_filename)
        temp_path = os.path.join(temp_dir, safe_filename)

        # Skip video and audio files
        file_type = doc.get("file_type", "").lower()
        file_name_lower = doc["file_name"].lower()

        video_audio_types = [
            "video/",
            "audio/",  # Any video or audio MIME type
            "application/x-mpegurl",
            "application/vnd.apple.mpegurl",  # Streaming
        ]
        video_audio_extensions = [
            ".mov",
            ".mp4",
            ".avi",
            ".mkv",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",  # Video
            ".mp3",
            ".wav",
            ".aac",
            ".flac",
            ".m4a",
            ".ogg",
            ".wma",
            ".aiff",  # Audio
        ]

        is_video_audio = any(file_type.startswith(vtype) for vtype in video_audio_types) or any(
            file_name_lower.endswith(ext) for ext in video_audio_extensions
        )

        if is_video_audio:
            logger.info(f"Skipping video/audio file: {doc['file_name']}")
            continue

        # Check if document has manual_text (user-corrected) or extracted_text
        # Priority: manual_text > extracted_text > download and process
        text_content = doc.get("manual_text") or doc.get("extracted_text")
        if text_content:
            text_source = "manual_text" if doc.get("manual_text") else "extracted_text"
            logger.debug(f"Using {text_source} for: {doc['file_name']}")
            # Save text to temporary file
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(text_content)
            path_to_id_map[temp_path] = doc["id"]
        else:
            # Download file from Supabase Storage with validation and retry
            max_retries = 3
            expected_size = doc.get("file_size", 0)
            download_success = False

            # Check file size limits before downloading
            # More restrictive for zips since they could contain videos
            MAX_SIZE_ZIP_MB = 50
            MAX_SIZE_OTHER_MB = 100
            
            is_zip = doc["file_name"].lower().endswith(".zip")
            size_limit_mb = MAX_SIZE_ZIP_MB if is_zip else MAX_SIZE_OTHER_MB
            size_limit_bytes = size_limit_mb * 1024 * 1024
            
            if expected_size > size_limit_bytes:
                file_size_mb = expected_size / (1024 * 1024)
                logger.warning(
                    f"Skipping large file {doc['file_name']}: "
                    f"{file_size_mb:.1f}MB exceeds {size_limit_mb}MB limit"
                )
                skipped_documents.append(
                    SkippedDocument(
                        document_id=doc["id"],
                        file_name=doc["file_name"],
                        reason=f"File too large ({file_size_mb:.1f}MB). Maximum size is {size_limit_mb}MB for {'zip files' if is_zip else 'this file type'}.",
                        error_type="FILE_TOO_LARGE",
                        recommendation="Large files are skipped to prevent timeouts. Consider extracting key content manually or splitting into smaller files.",
                    )
                )
                continue

            for attempt in range(max_retries):
                try:
                    file_data = supabase.storage.from_("documents").download(storage_path)
                    actual_size = len(file_data)

                    # Validate download content is not just whitespace (corrupted upload indicator)
                    if actual_size > 0 and actual_size < 100 and not file_data.strip():
                        logger.warning(
                            f"Download for {doc['file_name']} appears to be only whitespace "
                            f"({actual_size} bytes). Potential corrupted upload."
                        )
                        # We don't retry whitespace errors as they are likely permanent in storage
                        break

                    # Validate download size if we know expected size
                    if expected_size > 0 and actual_size < expected_size * 0.9:
                        logger.warning(
                            f"Download may be truncated for {doc['file_name']}: "
                            f"got {actual_size} bytes, expected {expected_size} bytes "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                            continue

                    # Write file and ensure it's flushed to disk
                    with open(temp_path, "wb") as f:
                        f.write(file_data)
                        f.flush()
                        os.fsync(f.fileno())  # Force write to disk

                    # Verify file was written correctly
                    written_size = os.path.getsize(temp_path)
                    if written_size != actual_size:
                        logger.error(
                            f"File write mismatch for {doc['file_name']}: "
                            f"wrote {written_size}, expected {actual_size}"
                        )
                        if attempt < max_retries - 1:
                            continue

                    download_success = True
                    logger.debug(f"Successfully downloaded {doc['file_name']} ({actual_size} bytes)")
                    # Store mapping of path to document ID
                    path_to_id_map[temp_path] = doc["id"]
                    break

                except Exception as e:
                    logger.warning(
                        f"Download attempt {attempt + 1}/{max_retries} failed for {doc['file_name']}: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))
                    continue

            if not download_success:
                logger.error(f"Failed to download {doc['file_name']} after {max_retries} attempts")
                skipped_documents.append(
                    SkippedDocument(
                        document_id=doc["id"],
                        file_name=doc["file_name"],
                        reason=f"Failed to download after {max_retries} attempts.",
                        error_type="DOWNLOAD_FAILED",
                        recommendation="Please try re-uploading this document.",
                    )
                )
                continue  # Skip this document if all download attempts fail

        # Check if this is a zip file - extract it
        if doc["file_name"].lower().endswith(".zip"):
            import zipfile

            logger.info(f"Extracting zip file: {doc['file_name']}")

            try:
                # Create subdirectory for this zip's contents
                zip_extract_dir = os.path.join(temp_dir, f"{doc['id']}_extracted")
                os.makedirs(zip_extract_dir, exist_ok=True)

                # Extract zip file
                with zipfile.ZipFile(temp_path, "r") as zip_ref:
                    zip_ref.extractall(zip_extract_dir)

                # Force filesystem sync to prevent race conditions
                # Increased delay to 500ms for more reliable extraction
                time.sleep(0.5)
                logger.debug(f"Filesystem sync delay (500ms) after extracting {doc['file_name']}")

                # Add extracted files to processing list (filtering out video/audio)
                extracted_count = 0
                for root, _dirs, files in os.walk(zip_extract_dir):
                    for extracted_file in files:
                        # Skip hidden files and system files
                        if extracted_file.startswith(".") or extracted_file.startswith("__MACOSX"):
                            continue

                        # Skip video/audio files
                        if any(extracted_file.lower().endswith(ext) for ext in video_audio_extensions):
                            logger.info(f"Skipping video/audio in zip: {extracted_file}")
                            continue

                        extracted_path = os.path.join(root, extracted_file)

                        # Verify file exists before adding to processing list
                        if os.path.isfile(extracted_path):
                            file_paths.append(extracted_path)
                            extracted_count += 1
                        else:
                            logger.warning(
                                f"Extracted file not found (filesystem sync issue?): {extracted_path}"
                            )

                logger.info(f"Extracted {extracted_count} files from {doc['file_name']}")

                # Remove the original zip file
                os.remove(temp_path)
                continue  # Skip adding the zip file itself to file_paths

            except zipfile.BadZipFile:
                logger.warning(f"Invalid zip file: {doc['file_name']}")
            except Exception as e:
                logger.warning(f"Failed to extract zip file {doc['file_name']}: {e}")

        # Check if this is an intake form
        # Prioritize: 1) metadata flag, 2) PDF/DOCX files with "intake" in name, 3) other files with "intake"
        is_intake = doc.get("metadata", {}).get("is_intake_form", False)
        is_document_file = doc.get("file_type", "").lower() in [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]

        if not is_intake and "intake" in doc["file_name"].lower():
            # Prefer actual document files (PDF/DOCX) over communications/notes
            if is_document_file:
                is_intake = True

        if is_intake:
            # If we already have an intake form, only replace it with a better one
            # (e.g., PDF/DOCX over communication)
            if intake_form_path:
                # Check if new candidate is a document file and current isn't, or if new is explicitly marked
                current_is_doc = any(
                    doc_check.get("id") == doc.get("id")
                    and doc_check.get("file_type", "").lower()
                    in [
                        "application/pdf",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ]
                    for doc_check in documents
                )
                if is_document_file or (doc.get("metadata", {}).get("is_intake_form") and not current_is_doc):
                    # Add old intake to regular files
                    file_paths.append(intake_form_path)
                    intake_form_path = temp_path
                    logger.info(f"Replaced intake form with better match: {doc['file_name']}")
                else:
                    file_paths.append(temp_path)
            else:
                intake_form_path = temp_path
                logger.info(f"Identified intake form: {doc['file_name']}")
        else:
            file_paths.append(temp_path)

    # If no intake form found, prefer first PDF/DOCX, then any document
    if not intake_form_path and file_paths:
        # Try to find a PDF or DOCX first
        pdf_docx_files = [
            f
            for f in file_paths
            if any(
                doc.get("storage_path") in f
                for doc in documents
                if doc.get("file_type", "").lower()
                in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ]
            )
        ]
        if pdf_docx_files:
            intake_form_path = pdf_docx_files[0]
            file_paths.remove(intake_form_path)
        else:
            intake_form_path = file_paths.pop(0)

    return intake_form_path, file_paths, path_to_id_map, skipped_documents


async def process_case_background(case_id: str, analysis_id: str, supabase, provider: str = "openai"):
    """Background task to process case documents.

    Args:
    ----
        case_id: Case ID
        analysis_id: Analysis record ID
        supabase: Supabase client
        provider: AI provider to use

    """
    # #region agent log
    _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if __import__('os').getenv("VERCEL") else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
    def _dbg_log(hyp: str, msg: str, data: dict = None):
        try:
            import json as _j; import time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "analysis.py:process_case_background", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
        except: pass
    _dbg_log("H2", "BACKGROUND TASK STARTED", {"case_id": case_id, "analysis_id": analysis_id, "provider": provider})
    # #endregion agent log

    bg_start_time = time.time()

    logger.info(
        f"[BACKGROUND:START] [CASE:{case_id}] [ANALYSIS:{analysis_id}] "
        f"Background task started | provider={provider}"
    )

    # Initialize progress manager
    progress_manager = ProgressManager.get_instance()
    await progress_manager.create_channel(analysis_id)

    # #region agent log
    _dbg_log("H2,H4", "Channel created, publishing first progress", {"analysis_id": analysis_id})
    # #endregion agent log

    # Create temp directory before try block so it's available in finally
    temp_dir = tempfile.mkdtemp(prefix=f"case_{case_id}_")

    try:
        # If user cancelled before we start, bail out quickly.
        if _analysis_is_cancelled(supabase, analysis_id):
            raise AnalysisCancelledError("Analysis cancelled before processing began.")

        # Update status to processing
        supabase.table("analysis_results").update({"status": "processing"}).eq("id", analysis_id).execute()

        # Publish initial progress
        initial_payload = {
            "message": "Starting document analysis...",
            "phase": "initialization",
            "percent": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await progress_manager.publish_progress(channel_id=analysis_id, **initial_payload)
        await _update_analysis_progress(supabase, analysis_id, initial_payload)

        # Get case details
        elapsed = time.time() - bg_start_time
        logger.info(f"[BACKGROUND:FETCH] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] Fetching case and documents")

        case_response = supabase.table("cases").select("*").eq("id", case_id).execute()
        if not case_response.data:
            raise ValueError("Case not found")

        case = case_response.data[0]
        jurisdiction = case.get("jurisdiction", "Florida")  # Get jurisdiction from case

        # Get all documents for the case — explicit column list prevents pulling extracted_text
        # for columns not needed here; text is capped per-doc below in the processing loop.
        _fetch_start = time.time()
        docs_response = (
            supabase.table("documents")
            .select(
                "id, file_name, file_type, storage_path, file_size, metadata, "
                "extracted_text, manual_text, status, extraction_quality, "
                "extraction_method, extracted_at, page_count, ocr_provider, "
                "is_flagged_as_junk"
            )
            .eq("case_id", case_id)
            .execute()
        )
        documents = docs_response.data
        _fetch_elapsed = time.time() - _fetch_start
        logger.info(
            f"[BACKGROUND:FETCH] [CASE:{case_id}] docs_fetch rows={len(documents or [])} "
            f"elapsed={_fetch_elapsed:.2f}s"
        )

        if not documents:
            raise ValueError("No documents found for case")

        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:PREP] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Preparing documents | total_docs={len(documents)} jurisdiction={jurisdiction}"
        )

        # Step 1: Prepare ProcessedDocument objects directly from DB (no re-extraction)
        from legal_portal.core.data_models import FileMetadata, FileType

        processed_intake = []
        processed_case_docs = []
        skipped_documents = []

        await progress_manager.publish_progress(
            channel_id=analysis_id,
            message="Checking document signatures...",
            phase="preparing",
            percent=5,
            timestamp=datetime.utcnow().isoformat(),
        )

        for doc in documents:
            doc_name = doc.get("file_name", "unknown")
            doc_status = doc.get("status")
            has_extracted = bool(doc.get("extracted_text"))
            extracted_len = len(doc.get("extracted_text") or "")
            has_manual = bool(doc.get("manual_text"))
            manual_len = len(doc.get("manual_text") or "")

            logger.info(
                f"Document '{doc_name}': status={doc_status}, "
                f"has_extracted_text={has_extracted} (len={extracted_len}), "
                f"has_manual_text={has_manual} (len={manual_len}), "
                f"is_junk={doc.get('is_flagged_as_junk')}"
            )

            # Skip docs with critical issues, skipped status, or duplicates
            status = doc.get("status")
            if status in [
                DocumentStatus.DOWNLOAD_FAILED,
                DocumentStatus.CORRUPTED,
                DocumentStatus.SKIPPED,
                DocumentStatus.DUPLICATE,
                "duplicate",  # Also check string value for backwards compatibility
            ]:
                logger.info(f"SKIPPING '{doc_name}': status={status} (excluded from analysis)")
                # Don't add duplicates to skipped list - they're expected and not errors
                if status not in [DocumentStatus.DUPLICATE, "duplicate"]:
                    skipped_documents.append(
                        SkippedDocument(
                            document_id=doc["id"],
                            file_name=doc["file_name"],
                            reason=f"Status is {status}",
                            error_type=str(status) if status else "UNKNOWN",
                            recommendation="Fix in verification hub.",
                        )
                    )
                continue

            if doc.get("is_flagged_as_junk"):
                logger.warning(f"SKIPPING '{doc_name}': flagged as junk")
                continue

            # Get text from manual_text (priority) or extracted_text, capped at 200K chars
            _MAX_DOC_CHARS = 200_000
            text = doc.get("manual_text") or doc.get("extracted_text")
            if text:
                text = text[:_MAX_DOC_CHARS]
            if not text:
                logger.warning(f"SKIPPING '{doc_name}': no text found (manual={has_manual}, extracted={has_extracted})")
                skipped_documents.append(
                    SkippedDocument(
                        document_id=doc["id"],
                        file_name=doc["file_name"],
                        reason="No extracted text found",
                        error_type="MISSING_TEXT",
                        recommendation="Run OCR in verification hub.",
                    )
                )
                continue

            logger.info(f"PROCESSING '{doc_name}': has {len(text)} chars of text")

            # Construct ProcessedDocument
            metadata = FileMetadata(
                file_name=doc["file_name"],
                file_type=FileType.PDF,  # Fallback
                file_size=doc.get("file_size", 0),
            )

            doc_metadata = doc.get("metadata", {}) or {}
            signature_detection = doc_metadata.get("signature_detection")
            if not signature_detection and _is_signature_inference_candidate(
                doc.get("file_name"), doc.get("file_type")
            ):
                signature_detection = _infer_signature_detection_from_text(text)
                if signature_detection:
                    logger.info(
                        "Inferred signature markers from extracted text for %s (doc_id=%s, confidence=%s)",
                        doc_name,
                        doc.get("id"),
                        signature_detection.get("confidence"),
                    )
            signature_detection = _apply_signature_verification_override(
                signature_detection if isinstance(signature_detection, dict) else None,
                doc_metadata,
                file_name=doc.get("file_name"),
            )

            pdoc = ProcessedDocument(
                file_name=doc["file_name"],
                content=text,
                document_type=(
                    DocumentType.INTAKE_FORM
                    if doc_metadata.get("is_intake_form")
                    else DocumentType.CASE_DOCUMENT
                ),
                file_type=FileType.PDF,
                metadata=metadata,
                extraction_quality=doc.get("extraction_quality", "high"),
                extraction_method=doc.get("extraction_method", "db"),
                page_count=doc.get("page_count"),
                ocr_provider=doc.get("ocr_provider"),
                document_id=doc["id"],
                signature_detection=signature_detection,
                attorney_enrichment=doc_metadata.get("attorney_enrichment") or None,
            )

            if pdoc.document_type == DocumentType.INTAKE_FORM:
                processed_intake.append(pdoc)
            else:
                processed_case_docs.append(pdoc)

        # Ensure we have at least an intake form
        if not processed_intake:
            # Fallback: if no doc marked as intake, use the first document
            if processed_case_docs:
                processed_intake = [processed_case_docs.pop(0)]
                processed_intake[0].document_type = DocumentType.INTAKE_FORM
            else:
                raise ValueError("No documents with text found for analysis. Please run OCR first.")

        # Cooperative cancellation checkpoint after preparing documents.
        if _analysis_is_cancelled(supabase, analysis_id):
            raise AnalysisCancelledError("Analysis cancelled after preparing documents.")

        case_metadata = case.get("metadata") or {}
        if not isinstance(case_metadata, dict):
            case_metadata = {}

        clio_matter_data = case.get("clio_matter_data") or {}
        if not isinstance(clio_matter_data, dict):
            clio_matter_data = {}

        profile_data: Dict[str, Any] = {}
        try:
            user_id = case.get("user_id")
            if user_id:
                profile_resp = (
                    supabase.table("profiles")
                    .select("full_name,phone,firm_name,email")
                    .eq("id", user_id)
                    .limit(1)
                    .execute()
                )
                if profile_resp.data:
                    profile_data = profile_resp.data[0] or {}
        except Exception as profile_err:
            logger.warning("Failed to load profile context for case %s: %s", case_id, profile_err)

        def _first_non_empty(*values: Any) -> Optional[str]:
            for value in values:
                text = safe_str(value)
                if text:
                    return text
            return None

        def _to_string_list(value: Any) -> List[str]:
            if not isinstance(value, list):
                return []
            return [str(item).strip() for item in value if str(item).strip()]

        practice_areas = _to_string_list(case_metadata.get("practice_areas"))
        legal_issues = _to_string_list(case_metadata.get("legal_issues"))
        if not legal_issues and practice_areas:
            legal_issues = practice_areas[:5]

        clio_practice_area = _first_non_empty(clio_matter_data.get("practice_area"))
        if not legal_issues and clio_practice_area:
            legal_issues = [clio_practice_area]

        key_documents = _to_string_list(case_metadata.get("key_documents"))
        if not key_documents:
            key_documents = [doc.file_name for doc in processed_case_docs[:8] if doc.file_name]

        confirmed_qa_pairs = case_metadata.get("qa_pairs")
        if not isinstance(confirmed_qa_pairs, list):
            confirmed_qa_pairs = []

        clio_context = None
        clio_context_raw = case_metadata.get("clio_matter_context") or case.get("clio_matter_context")
        if isinstance(clio_context_raw, ClioMatterContext):
            clio_context = clio_context_raw
        elif isinstance(clio_context_raw, dict):
            try:
                clio_context = ClioMatterContext(**clio_context_raw)
            except Exception:
                logger.warning("Ignoring invalid clio_matter_context payload for case %s", case_id)

        attorney_name = _first_non_empty(
            case.get("attorney_name"),
            case.get("attorneyName"),
            case_metadata.get("attorney_name"),
            case_metadata.get("attorneyName"),
            profile_data.get("full_name"),
        )
        firm_name = _first_non_empty(
            case.get("firm_name"),
            case.get("firmName"),
            case_metadata.get("firm_name"),
            case_metadata.get("firmName"),
            profile_data.get("firm_name"),
        )
        contact_phone = _first_non_empty(
            case.get("contact_phone"),
            case.get("contactPhone"),
            case_metadata.get("contact_phone"),
            case_metadata.get("contactPhone"),
            profile_data.get("phone"),
        )
        contact_email = _first_non_empty(
            case.get("contact_email"),
            case.get("contactEmail"),
            case_metadata.get("contact_email"),
            case_metadata.get("contactEmail"),
            profile_data.get("email"),
        )
        case_type = _first_non_empty(
            case.get("case_type"),
            case.get("caseType"),
            case_metadata.get("case_type"),
            case_metadata.get("caseType"),
            clio_practice_area,
            practice_areas[0] if practice_areas else None,
        )

        legal_issue = _first_non_empty(
            case_metadata.get("legal_issue"),
            case.get("description"),
            clio_matter_data.get("description"),
            "General legal document analysis",
        )

        # Prepare case_info with extended attorney/firm/contact context.
        case_info = {
            "client_name": case["client_name"],
            "clientName": case["client_name"],
            "reference_number": case.get("reference_number", ""),
            "description": case.get("description", ""),
            "case_id": case_id,
            "jurisdiction": jurisdiction,
            "caseType": case_type,
            "case_type": case_type,
            "attorneyName": attorney_name,
            "attorney_name": attorney_name,
            "firmName": firm_name,
            "firm_name": firm_name,
            "contactPhone": contact_phone,
            "contact_phone": contact_phone,
            "contactEmail": contact_email,
            "contact_email": contact_email,
        }

        # Prepare review_data with richer intake and prioritization context.
        review_data = {
            "legal_issue": legal_issue,
            "legal_issues": legal_issues,
            "key_documents": key_documents,
            "confirmed_qa_pairs": confirmed_qa_pairs,
        }
        if clio_context:
            review_data["clio_matter_context"] = clio_context

        # Track timing and stats for the AI Command Center
        analysis_start_time = time.time()
        total_tokens_used = 0
        try:
            progress_model = OpenAIClient().get_preferred_model("document_analysis", "gpt-5.2")
        except Exception:
            progress_model = "gpt-5.2"

        # Throttle DB progress writes to reduce disk I/O (SSE remains real-time)
        _progress_db_writer = ThrottledDBWriter(
            write_fn=lambda payload: _update_analysis_progress(supabase, analysis_id, payload),
            min_interval_seconds=5.0,
        )

        # Create progress callback that publishes to SSE and stores in DB
        async def progress_callback(
            message: str,
            docs_processed=None,
            phase="",
            percent=0,
            sub_step=None,
            # New parameters for enhanced progress
            stage: Optional[dict] = None,
            document: Optional[dict] = None,
            tokens_used: int = 0,
        ):
            """Publish progress updates to SSE stream and persistent storage."""
            nonlocal total_tokens_used
            total_tokens_used += tokens_used

            payload = {
                "message": message,
                "phase": phase,
                "percent": percent,
                "docs_processed": docs_processed or [],
                "sub_step": sub_step or message,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Add structured data if provided
            if stage:
                payload["stage"] = stage
            if document:
                payload["document"] = document

            # Add stats periodically
            elapsed = time.time() - analysis_start_time
            payload["stats"] = {
                "elapsedSeconds": elapsed,
                "tokens_used": total_tokens_used,
                "model": progress_model,
            }

            # Cooperative cancellation
            if _analysis_is_cancelled(supabase, analysis_id):
                raise AnalysisCancelledError("Analysis cancelled by user.")

            # Publish SSE (always real-time) and throttled DB write
            await progress_manager.publish_progress(channel_id=analysis_id, **payload)
            await _progress_db_writer.maybe_write(payload)

        # NEW: Initial emission of all documents in pending state so they appear in UI
        for doc in processed_intake + processed_case_docs:
            await progress_callback(
                message=f"Queueing {doc.file_name}...",
                phase="initialization",
                document={"id": doc.document_id or doc.file_name, "name": doc.file_name, "status": "pending"}
            )

        # Call the actual processor (AI passes)
        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:PROCESSOR] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Calling main processor | intake_docs={len(processed_intake)} case_docs={len(processed_case_docs)}"
        )

        processor_start = time.time()
        result: ProcessingResult = await process_case_documents(
            processed_intake=processed_intake,
            processed_case_docs=processed_case_docs,
            case_info=case_info,
            review_data=review_data,
            progress_callback=progress_callback,
            jurisdiction=jurisdiction,  # Pass jurisdiction to main processor
            skipped_documents=skipped_documents,
            analysis_id=analysis_id,
            supabase_client=supabase,
        )
        processor_duration = time.time() - processor_start
        elapsed = time.time() - bg_start_time

        logger.info(
            f"[BACKGROUND:PROCESSOR] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Processor complete | duration={processor_duration:.1f}s status={result.status}"
        )

        # Persist document extraction results to the database
        if result.processed_documents:
            logger.info(
                f"[BACKGROUND:PERSIST] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
                f"Persisting extraction results | docs={len(result.processed_documents)}"
            )
            for _doc_idx, doc in enumerate(result.processed_documents):
                if doc.document_id:
                    try:
                        # Sanitize content to remove NULL characters that PostgreSQL can't store
                        sanitized_content = sanitize_text_for_db(doc.content)

                        # Prepare update data mapping model fields to database columns
                        update_data = {
                            "extracted_text": sanitized_content,
                            "extraction_method": doc.extraction_method,
                            "extraction_quality": doc.extraction_quality,
                            "extracted_at": doc.extracted_at.isoformat(),
                            "page_count": doc.page_count,
                            "ocr_provider": doc.ocr_provider,
                            "extraction_error": doc.extraction_error,
                            "status": (
                                DocumentStatus.READY
                                if sanitized_content and sanitized_content.strip()
                                else DocumentStatus.EXTRACTION_FAILED
                            ),
                        }
                        supabase.table("documents").update(update_data).eq("id", doc.document_id).execute()

                        # Pace writes: yield every 5 docs to avoid I/O spikes
                        if _doc_idx % 5 == 4:
                            await asyncio.sleep(0.1)
                    except Exception as db_err:
                        logger.warning(
                            f"Failed to persist extraction results for document {doc.document_id}: {db_err}"
                        )

        # Store skipped documents info in analysis_results artifacts
        if result.skipped_documents:
            logger.info(f"Adding {len(result.skipped_documents)} skipped documents to analysis artifacts")
            current_artifacts = result.artifacts or {}
            current_artifacts["skipped_documents"] = [s.model_dump() for s in result.skipped_documents]
            result.artifacts = current_artifacts

        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:ARTIFACTS] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Generating artifacts | status={result.status}"
        )

        artifacts_meta = _generate_and_store_artifacts(result, case_id, analysis_id, supabase)
        if artifacts_meta:
            result.artifacts = artifacts_meta

        # Strip document content before JSONB save — already persisted to documents table above.
        # Reduces analysis_results.result from ~40MB to <1MB for large cases.
        # Downstream consumers (chat, letters, gap analysis) re-fetch text from documents table.
        # Gate: set STRIP_PROCESSED_DOC_CONTENT=false in env to disable.
        if os.getenv("STRIP_PROCESSED_DOC_CONTENT", "true").lower() != "false":
            for _pdoc in result.processed_documents:
                _pdoc.content = ""

        # Convert result to dict for storage (with mode='json' to serialize datetime)
        result_dict = result.model_dump(mode="json")

        # Size instrumentation — confirms JSONB payload is bounded
        _result_size = len(__import__("json").dumps(result_dict))
        logger.info(
            f"[BACKGROUND:PERSIST] [CASE:{case_id}] result_dict size={_result_size:,} bytes "
            f"| processed_docs={len(result.processed_documents)}"
        )

        # Update analysis record with results
        supabase.table("analysis_results").update(
            {"status": "completed", "result": result_dict, "completed_at": datetime.utcnow().isoformat()}
        ).eq("id", analysis_id).execute()

        # Update case status
        supabase.table("cases").update({"status": "completed"}).eq("id", case_id).execute()

        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:COMPLETE] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Analysis complete | total_duration={elapsed:.1f}s"
        )

        # Flush any throttled progress before completion
        await _progress_db_writer.flush()

        # Publish completion event
        completion_payload = {
            "message": "Analysis completed successfully!",
            "phase": "completed",
            "percent": 100,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
        }
        await progress_manager.publish_progress(channel_id=analysis_id, **completion_payload)
        await _update_analysis_progress(supabase, analysis_id, completion_payload)

    except AnalysisCancelledError:
        await _cancel_analysis(
            supabase=supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=progress_manager,
        )
        return
    except Exception as e:
        # Log error and update status
        error_message = str(e)
        error_traceback = traceback.format_exc()
        elapsed = time.time() - bg_start_time

        # #region agent log
        _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if __import__('os').getenv("VERCEL") else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
        def _dbg_log(hyp: str, msg: str, data: dict = None):
            try:
                import json as _j; import time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "analysis.py:process_case_background:except", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
            except: pass
        _dbg_log("H3", "BACKGROUND TASK EXCEPTION", {"case_id": case_id, "analysis_id": analysis_id, "error": error_message, "error_type": type(e).__name__, "elapsed": elapsed})
        # #endregion agent log

        logger.error(
            f"[BACKGROUND:ERROR] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Analysis FAILED | error_type={type(e).__name__} error={error_message}"
        )
        logger.error(f"[BACKGROUND:ERROR] [CASE:{case_id}] Traceback:\n{error_traceback}")

        error_payload = {
            "message": f"Analysis failed: {error_message}",
            "phase": "error",
            "percent": 0,
            "status": "error",
            "error": error_message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await progress_manager.publish_progress(channel_id=analysis_id, **error_payload)

        # Flush any throttled progress before writing error state
        await _progress_db_writer.flush()

        try:
            supabase.table("analysis_results").update(
                {
                    "status": "error",
                    "error": f"{error_message}\n\n{error_traceback}",
                }
            ).eq("id", analysis_id).execute()
            await _update_analysis_progress(supabase, analysis_id, error_payload)
        except Exception as db_err:
            logger.warning(f"Failed to persist error status to DB: {db_err}")

        supabase.table("cases").update({"status": "error"}).eq("id", case_id).execute()

        # Publish error event
        await progress_manager.publish_progress(
            channel_id=analysis_id,
            message=f"Analysis failed: {error_message}",
            phase="error",
            percent=0,
            status="error",
            error=error_message,
        )

    finally:
        # Cleanup temporary files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp dir: {cleanup_error}")


@router.get("/{analysis_id}/letter/stream")
async def stream_findings_letter(
    analysis_id: str,
    force_generation: bool = Query(default=False, description="Override completeness gate for weak cases"),
    schema_version: int = Query(default=2, ge=1, le=2),
    mode: Literal["default", "strict_quality"] = Query(default="default"),
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream findings letter generation with v2 SSE events and legacy compatibility."""
    try:
        settings = get_settings()
        effective_schema_version = 2 if (schema_version == 2 and settings.letter_stream_schema_v2) else 1

        response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Analysis not found")

        analysis_data = response.data[0]
        await _ensure_fresh_gap_analysis_for_letter_generation(
            supabase=supabase,
            analysis_record=analysis_data,
            user_id=user["id"],
        )

        result_payload = analysis_data.get("result")
        if not result_payload:
            raise HTTPException(status_code=400, detail="Analysis result not yet available")

        processing_result = ProcessingResult(**result_payload)
        if not processing_result.multi_stage_result:
            raise HTTPException(status_code=400, detail="Multi-stage analysis results missing")

        msr = processing_result.multi_stage_result
        gap_analysis_data = msr.get("gap_analysis")
        if gap_analysis_data:
            from legal_portal.core.data_models import GapAnalysisResult

            gap_analysis = GapAnalysisResult(**gap_analysis_data)
            if gap_analysis.overall_completeness_score < 40:
                if not force_generation:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": "documentation_insufficient",
                            "message": (
                                "Case documentation is insufficient for letter generation. Please "
                                "provide the missing documents identified in Gap Analysis before "
                                "generating a letter."
                            ),
                            "completeness_score": gap_analysis.overall_completeness_score,
                            "critical_gaps": gap_analysis.critical_count,
                            "recommendation": (
                                "Review the Gap Analysis tab to identify which documents are needed."
                            ),
                            "allow_override": True,
                        },
                    )
                logger.warning(
                    "OVERRIDE: force_generation used for streaming letter with low completeness score "
                    "(%s%%) - analysis_id=%s, critical_gaps=%s",
                    gap_analysis.overall_completeness_score,
                    analysis_id,
                    gap_analysis.critical_count,
                )
            elif gap_analysis.overall_completeness_score < 60:
                logger.warning(
                    "Streaming letter with moderate completeness score: %s%% "
                    "(critical_gaps=%s, high_gaps=%s) - analysis_id=%s",
                    gap_analysis.overall_completeness_score,
                    gap_analysis.critical_count,
                    gap_analysis.high_count,
                    analysis_id,
                )

        artifacts = processing_result.artifacts or {}
        resolved_identity = _resolve_letter_identity_context(
            supabase=supabase,
            case_id=analysis_data.get("case_id"),
            artifacts=artifacts,
        )
        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)

        def _event_payload(event_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
            """Build schema-v1 or schema-v2 payload for the current stream request."""
            if effective_schema_version == 1:
                if event_name == "token":
                    return {"token": kwargs.get("token", "")}
                if event_name == "done":
                    return {"done": True}
                if event_name == "error":
                    return {"error": kwargs.get("error", "Stream failed")}
                return None

            payload: Dict[str, Any] = {
                "schema_version": 2,
                "event": event_name,
                "type": event_name,
            }
            payload.update(kwargs)
            if event_name == "done":
                payload["done"] = True
            return payload

        async def generate():
            request_started = time.monotonic()
            metrics = _new_generation_metrics(
                analysis_id=analysis_id,
                letter_type="findings",
                streaming=True,
            )
            quality_report = _quality_report_placeholder(mode=mode, letter_type="findings")
            recoverable_timeout = False
            draft_markdown = ""

            def _remaining_seconds(internal_deadline: float) -> float:
                return internal_deadline - time.monotonic()

            def _emit(event_name: str, **kwargs: Any) -> Optional[str]:
                payload = _event_payload(event_name, **kwargs)
                if payload is None:
                    return None
                return _to_sse(payload)

            try:
                internal_budget = max(30, int(settings.letter_internal_budget_seconds))
                context_budget = max(1, int(settings.letter_context_budget_seconds))
                draft_budget = max(5, int(settings.letter_draft_budget_seconds))
                lint_budget = max(1, int(settings.letter_lint_budget_seconds))
                repair_budget = max(1, int(settings.letter_repair_budget_seconds))
                finalize_budget = max(1, int(settings.letter_finalize_budget_seconds))
                strategy_budget = max(1, int(settings.letter_strategy_budget_seconds))
                critic_budget = max(1, int(settings.letter_critic_budget_seconds))
                heartbeat_interval = max(1, int(settings.letter_stream_heartbeat_seconds))
                internal_deadline = request_started + internal_budget

                phase_msg = _emit("phase", phase="strategy", message="Preparing letter strategy...", percent=3)
                if phase_msg:
                    yield phase_msg
                phase_msg = _emit("phase", phase="context_build", message="Building context", percent=8)
                if phase_msg:
                    yield phase_msg

                context_started = time.monotonic()
                from legal_portal.core.data_models import (
                    DeepAnalysis,
                    FactMatrix,
                    GapAnalysisResult,
                    LetterStructure,
                )

                jurisdiction = artifacts.get("jurisdiction", "Florida")
                fact_matrix = FactMatrix(**msr["fact_matrix"])
                deep_analysis = DeepAnalysis(**msr["deep_analysis"])
                letter_structure = LetterStructure(**msr["letter_structure"])
                stream_gap_analysis = (
                    GapAnalysisResult(**msr["gap_analysis"]) if msr.get("gap_analysis") else None
                )
                client_name = _resolve_client_name_for_letter(
                    resolved_identity=resolved_identity,
                    artifacts=artifacts,
                    fact_matrix=fact_matrix,
                )

                document_summaries_for_context: List[Dict[str, Any]] = []
                if processing_result.document_summaries:
                    try:
                        parsed_summaries = json.loads(processing_result.document_summaries)
                        if isinstance(parsed_summaries, list):
                            document_summaries_for_context = [
                                item for item in parsed_summaries if isinstance(item, dict)
                            ]
                    except Exception as parse_err:
                        logger.warning(
                            "[LETTER] Failed to parse document_summaries for stream context: %s",
                            parse_err,
                        )

                if (time.monotonic() - context_started) > context_budget:
                    metrics["timeout"] = True
                    metrics["error_code"] = "context_budget_exceeded"
                    raise TimeoutError("Context-build phase exceeded budget.")

                openai_client = OpenAIClient(user_preferences=ai_preferences)
                json_service = JsonProcessingService(client=openai_client, config={})
                normalize_markdown = getattr(json_service, "normalize_client_letter_markdown", None)

                def _normalize_markdown(text: str, letter_kind: str) -> str:
                    if callable(normalize_markdown):
                        return normalize_markdown(
                            text,
                            letter_type=letter_kind,
                            attorney_name=resolved_identity.get("attorney_name"),
                            firm_name=resolved_identity.get("firm_name"),
                        )
                    return text

                strategy_object: Optional[Dict[str, Any]] = None
                if settings.letter_strategy_enabled:
                    remaining_for_strategy = _remaining_seconds(internal_deadline)
                    reserve_for_downstream = draft_budget + lint_budget + finalize_budget
                    if remaining_for_strategy > reserve_for_downstream:
                        strategy_timeout = int(
                            min(strategy_budget, max(1, remaining_for_strategy - reserve_for_downstream))
                        )
                        strategy_started = time.monotonic()
                        try:
                            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                            strategy_object = await json_service.build_findings_strategy(
                                fact_matrix=fact_matrix,
                                deep_analysis=deep_analysis,
                                gap_analysis=stream_gap_analysis,
                                timeout_seconds=strategy_timeout,
                                allow_model=True,
                                model="gpt-5-mini",
                            )
                            metrics["strategy_used"] = bool(strategy_object)
                        except Exception as strategy_err:
                            logger.warning("[LETTER] Strategy step failed for stream: %s", strategy_err)
                        finally:
                            metrics["strategy_latency_ms"] = int(
                                (time.monotonic() - strategy_started) * 1000
                            )

                phase_msg = _emit("phase", phase="draft_generation", message="Generating draft")
                if phase_msg:
                    yield phase_msg

                metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1

                stream_generator = json_service.stream_findings_letter_adaptive(
                    intake_content=processing_result.intake_content or "",
                    fact_matrix=fact_matrix,
                    legal_analysis=deep_analysis,
                    structure_guidance=letter_structure,
                    verified_statutes=msr.get("verified_statutes", []),
                    attorney_name=resolved_identity.get("attorney_name"),
                    firm_name=resolved_identity.get("firm_name"),
                    confirmed_qa_pairs=artifacts.get("confirmed_qa_pairs", []),
                    contact_phone=resolved_identity.get("contact_phone"),
                    contact_email=resolved_identity.get("contact_email"),
                    quality_context=artifacts.get("quality_context", ""),
                    clio_matter_context=artifacts.get("clio_matter_context", ""),
                    jurisdiction=jurisdiction,
                    original_documents=msr.get("original_documents"),
                    document_summaries_for_context=document_summaries_for_context,
                    document_registry=msr.get("document_registry"),
                    strategy_object=strategy_object,
                    gap_analysis=stream_gap_analysis,
                )

                token_queue: asyncio.Queue = asyncio.Queue()

                async def _collect_tokens() -> None:
                    try:
                        async for token in stream_generator:
                            await token_queue.put(("token", token))
                    except Exception as stream_err:
                        await token_queue.put(("error", stream_err))
                    finally:
                        await token_queue.put(("done", None))

                collector_task = asyncio.create_task(_collect_tokens())
                draft_started = time.monotonic()
                reserved_for_after_draft = lint_budget + finalize_budget
                draft_deadline = min(
                    draft_started + draft_budget,
                    internal_deadline - reserved_for_after_draft,
                )
                _draft_token_count = 0
                _last_wc_emit_token = 0

                try:
                    while True:
                        if time.monotonic() > draft_deadline:
                            metrics["timeout"] = True
                            metrics["error_code"] = "draft_budget_exceeded"
                            break

                        try:
                            msg_type, msg_data = await asyncio.wait_for(
                                token_queue.get(),
                                timeout=heartbeat_interval,
                            )
                        except asyncio.TimeoutError:
                            heartbeat_msg = _emit(
                                "heartbeat",
                                phase="draft_generation",
                                elapsed_ms=int((time.monotonic() - request_started) * 1000),
                            )
                            if heartbeat_msg:
                                yield heartbeat_msg
                            continue

                        if msg_type == "token":
                            token = str(msg_data or "")
                            if not token:
                                continue
                            draft_markdown += token
                            _draft_token_count += 1
                            if metrics["ttft_ms"] is None:
                                metrics["ttft_ms"] = int((time.monotonic() - request_started) * 1000)
                            token_msg = _emit("token", token=token)
                            if token_msg:
                                yield token_msg
                            if _draft_token_count - _last_wc_emit_token >= 200:
                                _last_wc_emit_token = _draft_token_count
                                _wc = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
                                _pct = min(88, 10 + _wc * 78 // 1000)
                                wc_msg = _emit("phase", phase="draft_generation", message=f"Drafting letter... ({_wc:,} words)", percent=_pct)
                                if wc_msg:
                                    yield wc_msg
                            continue

                        if msg_type == "error":
                            if isinstance(msg_data, Exception):
                                raise msg_data
                            raise RuntimeError(str(msg_data))

                        if msg_type == "done":
                            break
                finally:
                    if not collector_task.done():
                        collector_task.cancel()
                        try:
                            await collector_task
                        except asyncio.CancelledError:
                            pass

                draft_word_count = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
                if metrics["timeout"] and draft_word_count >= 80:
                    recoverable_timeout = True
                    timeout_msg = _emit(
                        "error",
                        error=(
                            "Draft generation exceeded time budget; finalized the best available draft."
                        ),
                        code=metrics.get("error_code"),
                        recoverable=True,
                    )
                    if timeout_msg:
                        yield timeout_msg

                if not draft_markdown.strip():
                    raise TimeoutError("Draft generation ended before any content was produced.")

                draft_markdown = _normalize_markdown(draft_markdown, "findings")

                phase_msg = _emit("phase", phase="lint_validation", message="Validating quality")
                if phase_msg:
                    yield phase_msg

                validator = LetterValidationService()
                if settings.letter_quality_lint_enabled and _remaining_seconds(internal_deadline) > finalize_budget:
                    lint_started = time.monotonic()
                    quality_report = validator.lint_client_letter(
                        draft_markdown,
                        mode=mode,
                        letter_type="findings",
                    )
                    if (time.monotonic() - lint_started) > lint_budget:
                        logger.warning("[LETTER] Lint phase exceeded budget but completed.")

                final_markdown = draft_markdown
                critic_feedback: Dict[str, Any] = {"failed_sections": []}
                if (
                    settings.letter_quality_critic_enabled
                    and not quality_report.get("lint_passed", True)
                    and settings.letter_quality_lint_enabled
                ):
                    remaining_before_critic = _remaining_seconds(internal_deadline)
                    if remaining_before_critic >= (critic_budget + finalize_budget):
                        metrics["critic_attempted"] = True
                        critic_started = time.monotonic()
                        try:
                            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                            critic_feedback = await json_service.run_quality_critic(
                                draft_markdown=draft_markdown,
                                letter_type="findings",
                                lint_violations=quality_report.get("violations", []),
                                quality_report_v2=quality_report.get("quality_report_v2"),
                                model="gpt-5-mini",
                                timeout_seconds=critic_budget,
                            )
                        except Exception as critic_err:
                            logger.warning("[LETTER] Critic step failed: %s", critic_err)
                            metrics["critic_skipped_reason"] = f"critic_error:{type(critic_err).__name__}"
                            critic_feedback = {"failed_sections": []}
                        finally:
                            metrics["critic_latency_ms"] = int((time.monotonic() - critic_started) * 1000)
                    else:
                        metrics["critic_skipped_reason"] = "insufficient_budget"

                if (
                    settings.letter_conditional_repair_enabled
                    and not quality_report.get("lint_passed", True)
                    and settings.letter_quality_lint_enabled
                ):
                    remaining_after_lint = _remaining_seconds(internal_deadline)
                    if remaining_after_lint >= (repair_budget + finalize_budget):
                        phase_msg = _emit("phase", phase="repair", message="Repairing quality issues")
                        if phase_msg:
                            yield phase_msg
                        metrics["repair_attempted"] = True
                        metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                        repaired = await json_service.repair_letter_constraints(
                            draft_markdown,
                            quality_report.get("violations", []),
                            mode=mode,
                            model="gpt-5-mini",
                            critic_feedback=critic_feedback,
                        )
                        repaired = _normalize_markdown(repaired, "findings")
                        post_repair_report = validator.lint_client_letter(
                            repaired,
                            mode=mode,
                            letter_type="findings",
                        )
                        quality_report = {
                            **post_repair_report,
                            "pre_repair": quality_report,
                            "post_repair": post_repair_report,
                            "critic_feedback": critic_feedback,
                        }
                        if repaired.strip() and repaired.strip() != draft_markdown.strip():
                            final_markdown = repaired
                            metrics["repair_applied"] = True
                            if critic_feedback.get("failed_sections"):
                                metrics["critic_applied"] = True
                    else:
                        quality_report = {
                            **quality_report,
                            "repair_skipped": "insufficient_budget",
                            "critic_feedback": critic_feedback,
                        }

                # Polish pass: second AI call for prose formatting consistency
                if getattr(settings, "letter_polish_enabled", True):
                    polish_msg = _emit("phase", phase="polishing", message="Polishing letter...")
                    if polish_msg:
                        yield polish_msg
                    try:
                        from legal_portal.utils.letter_polish import polish_letter_async

                        pre_polish_markdown = final_markdown
                        _polish_timeout = getattr(settings, "letter_polish_timeout_seconds", 55)
                        polish_result = await polish_letter_async(
                            openai_client,
                            pre_polish_markdown,
                            timeout_seconds=float(_polish_timeout),
                        )
                        if polish_result.get("success") and polish_result.get("polished_letter"):
                            polished_candidate = polish_result["polished_letter"]
                            integrity_report = {"passed": True, "reason": "unsupported"}
                            if hasattr(validator, "check_polish_fact_integrity"):
                                integrity_report = validator.check_polish_fact_integrity(
                                    pre_polish_markdown,
                                    polished_candidate,
                                    tracked_entities=[
                                        client_name,
                                        resolved_identity.get("attorney_name") or "",
                                        resolved_identity.get("firm_name") or "",
                                    ],
                                )
                            metrics["polish_integrity_passed"] = bool(integrity_report.get("passed", True))

                            if integrity_report.get("passed", True):
                                final_markdown = polished_candidate
                                metrics["polish_applied"] = True
                            else:
                                metrics["polish_applied"] = False
                                metrics["polish_reverted"] = True
                                metrics["polish_revert_reason"] = (
                                    f"fact_integrity:{integrity_report.get('reason', 'unknown')}"
                                )
                                logger.warning(
                                    "[LETTER] Polish reverted due to fact integrity drift: %s",
                                    integrity_report,
                                )
                    except Exception as polish_err:
                        logger.warning("[LETTER] Polish pass failed, using raw draft: %s", polish_err)
                        metrics["polish_applied"] = False
                else:
                    logger.info("[LETTER] Polish pass disabled by configuration")

                phase_msg = _emit("phase", phase="finalizing", message="Finalizing letter")
                if phase_msg:
                    yield phase_msg

                final_markdown = _normalize_markdown(final_markdown, "findings")
                final_html = json_service._convert_markdown_to_html(final_markdown)
                final_html = DocumentFormatterService.format_findings_letter(
                    letter_html=final_html,
                    client_name=client_name,
                )
                metrics["lint_passed"] = quality_report.get("lint_passed")
                metrics["lint_score"] = quality_report.get("score")
                metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)

                try:
                    persisted_result = analysis_data.get("result") or {}
                    generated_letters = persisted_result.setdefault("generated_letters", {})
                    generated_letters["findings"] = final_html
                    generated_letters["findings_meta"] = {
                        "quality_report": quality_report,
                        "quality_report_v2": quality_report.get("quality_report_v2"),
                        "generation_metrics": metrics,
                        "strategy_object": strategy_object,
                    }
                    supabase.table("analysis_results").update({"result": persisted_result}).eq(
                        "id", analysis_id
                    ).execute()
                except Exception as persist_err:
                    logger.warning("[LETTER] Persisting streamed findings failed: %s", persist_err)

                quality_msg = _emit(
                    "quality",
                    quality_report=quality_report,
                    generation_metrics=metrics,
                )
                if quality_msg:
                    yield quality_msg

                final_msg = _emit(
                    "final",
                    content={
                        "format": "html",
                        "html": final_html,
                        "markdown": final_markdown,
                    },
                    quality_report=quality_report,
                    generation_metrics=metrics,
                )
                if final_msg:
                    yield final_msg

                done_msg = _emit("done")
                if done_msg:
                    yield done_msg
                _emit_generation_metrics(metrics)

            except Exception as stream_err:
                if isinstance(stream_err, TimeoutError):
                    metrics["timeout"] = True
                    if not metrics.get("error_code"):
                        metrics["error_code"] = "timeout"
                elif not metrics.get("error_code"):
                    metrics["error_code"] = type(stream_err).__name__

                metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)
                _emit_generation_metrics(metrics)

                error_msg = _emit(
                    "error",
                    error=str(stream_err),
                    code=metrics.get("error_code"),
                    recoverable=recoverable_timeout,
                )
                if error_msg:
                    yield error_msg

                done_msg = _emit("done")
                if done_msg:
                    yield done_msg

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in stream_findings_letter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{analysis_id}/chat/stream")
async def stream_chat_response(
    analysis_id: str,
    request: ChatMessageRequest,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream chat response token by token."""
    try:
        # 1. Get analysis context
        response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Analysis result not found")

        analysis_data = response.data[0]
        result_payload = analysis_data["result"]
        processing_result = ProcessingResult(**result_payload)

        # 2. Get conversation history (use case_id from the analysis record, not ProcessingResult)
        case_id = analysis_data["case_id"]
        history_response = (
            supabase.table("case_chat_messages")
            .select("user_message, ai_response")
            .eq("case_id", case_id)
            .order("created_at", desc=False)
            .limit(10)
            .execute()
        )
        conversation_history = []
        if history_response.data:
            for row in history_response.data:
                conversation_history.append({"role": "user", "content": row["user_message"]})
                conversation_history.append({"role": "assistant", "content": row["ai_response"]})

        async def generate():
            openai_client = OpenAIClient()
            artifacts = processing_result.artifacts or {}
            jurisdiction = artifacts.get("jurisdiction", "Florida")
            chat_service = CaseChatService(openai_client, jurisdiction=jurisdiction)

            full_response = ""
            async for token in chat_service.stream_message(
                user_message=request.message,
                analysis_result=processing_result,
                conversation_history=conversation_history,
            ):
                full_response += token
                yield f"data: {json.dumps({'token': token})}\n\n"

            # 3. Save to database after streaming completes
            try:
                supabase.table("case_chat_messages").insert(
                    {
                        "case_id": case_id,
                        "user_message": request.message,
                        "ai_response": full_response,
                        "context_used": processing_result.multi_stage_result or {},
                    }
                ).execute()
            except Exception as db_err:
                logger.error(f"Failed to save chat message to DB: {db_err}")

            yield f"data: {json.dumps({'done': True})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    except Exception as e:
        logger.error(f"Error in stream_chat_response: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")  # Rate limit AI analysis to prevent abuse
async def start_analysis(
    analysis_request: AnalysisRequest,
    request: Request,  # Required for rate limiter (must be named 'request')
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Start analysis for a case.
    
    On Vercel serverless, BackgroundTasks don't work reliably because the function
    instance is terminated after the response is sent. On Vercel, this endpoint
    returns an SSE stream that runs the analysis inline and streams progress.

    Args:
    ----
        analysis_request: Analysis request data
        request: FastAPI request object
        background_tasks: FastAPI background tasks handler (used for local dev only)
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        On local: JSON with analysis record (202)
        On Vercel: SSE stream with progress events

    """
    import os
    is_vercel = os.getenv("VERCEL") is not None

    # #region agent log
    _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if is_vercel else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
    def _dbg_log(hyp: str, msg: str, data: dict = None):
        try:
            import json as _j; import time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "analysis.py:start_analysis", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
        except: pass
    # #endregion agent log

    try:
        # Verify case ownership using user client (respects RLS)
        case_response = (
            user_supabase.table("cases")
            .select("id, status")
            .eq("id", analysis_request.case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        case = case_response.data[0]

        # Check if case already has pending/processing analysis
        if case["status"] in ["processing"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Case is already being processed"
            )

        # Clear needs_reanalysis flag when starting new analysis
        user_supabase.table("cases").update({
            "needs_reanalysis": False
        }).eq("id", analysis_request.case_id).execute()

        # Create analysis record using user client
        analysis_response = (
            user_supabase.table("analysis_results")
            .insert({"case_id": analysis_request.case_id, "status": "pending"})
            .execute()
        )

        if not analysis_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create analysis record"
            )

        analysis = analysis_response.data[0]

        # Update case status
        user_supabase.table("cases").update({"status": "processing"}).eq(
            "id", analysis_request.case_id
        ).execute()

        _dbg_log("H6", "start_analysis called", {"case_id": analysis_request.case_id, "analysis_id": analysis["id"], "is_vercel": is_vercel})

        if is_vercel:
            # On Vercel: Return SSE stream that runs analysis inline
            # This keeps the connection alive and prevents function termination
            logger.info(f"[VERCEL] Starting SSE stream for analysis {analysis['id']}")
            _dbg_log("H6", "Starting SSE stream analysis on Vercel", {"analysis_id": analysis["id"]})

            async def analysis_stream():
                """Generator that runs analysis and yields progress events with heartbeats."""
                import asyncio

                analysis_id = analysis["id"]

                # First, yield the analysis record so frontend knows the ID immediately
                yield f"data: {json.dumps({'type': 'started', 'analysis': analysis})}\n\n"

                # Create a task for the analysis so we can yield heartbeats while it runs
                analysis_task = asyncio.create_task(
                    process_case_background(
                        analysis_request.case_id,
                        analysis_id,
                        service_supabase,
                        analysis_request.provider,
                    )
                )

                last_progress = None
                heartbeat_count = 0

                try:
                    while not analysis_task.done():
                        # Check for progress updates in database
                        try:
                            result = service_supabase.table("analysis_results").select("status, progress").eq("id", analysis_id).single().execute()

                            if result.data:
                                current_status = result.data.get("status")
                                current_progress = result.data.get("progress")

                                # Yield progress if it changed
                                if current_progress and current_progress != last_progress:
                                    yield f"data: {json.dumps(current_progress)}\n\n"
                                    last_progress = current_progress
                                    heartbeat_count = 0  # Reset heartbeat counter on real progress

                                # Check if analysis completed or failed
                                if current_status in ["completed", "failed", "cancelled"]:
                                    break
                        except Exception as db_err:
                            logger.warning(f"Error checking progress: {db_err}")

                        # Send heartbeat every 10 seconds if no real progress
                        heartbeat_count += 1
                        if heartbeat_count >= 5:  # Every 5 * 2s = 10 seconds
                            yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                            heartbeat_count = 0

                        # Wait 2 seconds before checking again
                        await asyncio.sleep(2)

                    # Wait for the task to complete and get any exception
                    await analysis_task

                    # Fetch final status
                    final = service_supabase.table("analysis_results").select("status, progress").eq("id", analysis_id).single().execute()
                    final_status = final.data.get("status", "unknown") if final.data else "unknown"
                    final_progress = final.data.get("progress") if final.data else None

                    # Yield final progress if different
                    if final_progress and final_progress != last_progress:
                        yield f"data: {json.dumps(final_progress)}\n\n"

                    yield f"data: {json.dumps({'type': 'completed', 'status': final_status})}\n\n"
                    logger.info(f"[VERCEL] Analysis stream completed for {analysis_id} with status: {final_status}")

                except asyncio.CancelledError:
                    logger.warning(f"Analysis stream cancelled for {analysis_id}")
                    analysis_task.cancel()
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                except Exception as e:
                    logger.error(f"Analysis stream error for {analysis_id}: {e}", exc_info=True)
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            return StreamingResponse(
                analysis_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            # Local development: Use BackgroundTasks as before (returns JSON)
            logger.info(f"[LOCAL] Using BackgroundTasks for {analysis['id']}")
            background_tasks.add_task(
                process_case_background,
                analysis_request.case_id,
                analysis["id"],
                service_supabase,
                analysis_request.provider,
            )
            return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in start_analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error starting analysis: {str(e)}"
        ) from e


@router.post("/cancel/{analysis_id}", status_code=status.HTTP_200_OK)
async def cancel_analysis(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Cancel an in-progress analysis and un-stick the case.

    This is a cooperative cancel: we mark the analysis as cancelled and set the case back to pending.
    The background worker checks this status and stops as soon as it hits a checkpoint.
    """
    try:
        # Verify analysis belongs to the user (RLS via user_supabase)
        resp = (
            user_supabase.table("analysis_results")
            .select("id, case_id, status")
            .eq("id", analysis_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found",
            )

        analysis = resp.data[0]
        case_id = analysis["case_id"]

        progress_manager = ProgressManager.get_instance()
        await _cancel_analysis(
            supabase=user_supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=progress_manager,
        )

        return {"status": "cancelled", "analysis_id": analysis_id, "case_id": case_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel analysis: {str(e)}",
        ) from e


@router.post("/cancel-case/{case_id}", status_code=status.HTTP_200_OK)
async def cancel_case_analysis(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    r"""Cancel the most recent in-progress analysis for a case.

    This enables "Cancel" from the cases list UI without needing an analysis_id.
    """
    try:
        # Verify ownership of the case (RLS via user_supabase)
        case_resp = (
            user_supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )
        if not case_resp.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Find the newest analysis for this case that is still pending/processing
        analysis_resp = (
            user_supabase.table("analysis_results")
            .select("id, status")
            .eq("case_id", case_id)
            .in_("status", ["pending", "processing"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not analysis_resp.data:
            return {"status": "no_active_analysis", "case_id": case_id}

        analysis_id = analysis_resp.data[0]["id"]

        progress_manager = ProgressManager.get_instance()
        await _cancel_analysis(
            supabase=user_supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=progress_manager,
        )

        return {"status": "cancelled", "analysis_id": analysis_id, "case_id": case_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel case analysis: {str(e)}",
        ) from e


@router.get("/status/{case_id}", response_model=AnalysisResponse)
async def get_analysis_status(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get the latest analysis status for a case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Latest analysis result

    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get latest analysis for case
        response = (
            supabase.table("analysis_results")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this case"
            )

        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching analysis status: {str(e)}",
        ) from e


@router.get("/results/{case_id}")
async def get_analysis_results(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Get the full analysis results for a completed case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        Analysis results (ProcessingResult)

    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get most recent analysis (regardless of status)
        response = (
            supabase.table("analysis_results")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this case"
            )

        analysis = response.data[0]
        # Include status in the response so frontend can handle it
        result_payload = analysis.get("result") or {}
        result_payload["status"] = analysis.get("status")
        result_payload["analysis_id"] = analysis.get("id")
        result_payload["created_at"] = analysis.get("created_at")
        result_payload["error"] = analysis.get("error")
        artifacts = result_payload.get("artifacts")
        if artifacts:
            result_payload["artifacts"] = _attach_signed_artifact_urls(service_supabase, artifacts)

        return result_payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching analysis results: {str(e)}",
        ) from e


class StreamingAnalysisSaveRequest(BaseModel):
    """Request to save streaming analysis result."""

    content: str = Field(..., description="The markdown content from streaming analysis")


@router.post("/stream/{case_id}/save")
async def save_streaming_analysis(
    case_id: str,
    request: StreamingAnalysisSaveRequest,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Save the result of a streaming analysis.
    
    Parses the markdown content and embedded JSON, then stores as an analysis result.
    The embedded JSON (in ```json block) contains structured data for letter generation.
    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases")
            .select("id, client_name, jurisdiction")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case_data = case_response.data[0]

        # Parse embedded JSON from the markdown content
        structured_data = _extract_embedded_json(request.content)

        # Build case analysis from extracted data
        # Use clean issue names from structured JSON, not raw markdown
        key_issues_list = []
        if structured_data.get("primary_issues"):
            for issue in structured_data["primary_issues"]:
                issue_name = issue.get("name", "")
                if issue_name:
                    # Include strength and statutes for context
                    strength = issue.get("strength", "")
                    statutes = issue.get("statutes", [])
                    if statutes:
                        key_issues_list.append(f"{issue_name} ({strength}) - {', '.join(statutes)}")
                    else:
                        key_issues_list.append(f"{issue_name} ({strength})")

        # Fallback to markdown extraction if no structured data
        if not key_issues_list:
            key_issues_list = _extract_list_items(request.content, "Legal Issues Identified")

        case_analysis = {
            "case_summary": _extract_section(request.content, "Case Overview"),
            "key_issues": key_issues_list,
            "practice_area": structured_data.get("practice_area", "General Legal Matter"),
            "relevant_statutes": [],  # Extracted from structured_data below
        }

        # Add statutes from primary issues
        if structured_data.get("primary_issues"):
            for issue in structured_data["primary_issues"]:
                if issue.get("statutes"):
                    for statute in issue["statutes"]:
                        case_analysis["relevant_statutes"].append({
                            "statute": statute,
                            "relevance": issue.get("name", ""),
                        })

        # Build multi-stage compatible result for letter generation
        multi_stage_result = None
        if structured_data:
            # Build timeline with correct field names for FactMatrix model
            timeline_events = []
            for d in structured_data.get("key_dates", []):
                timeline_events.append({
                    "date": d.get("date", ""),
                    "description": d.get("event", ""),  # FactMatrix uses 'description' not 'event'
                    "source_document": "Streaming Analysis",  # Required field
                    "significance": None,
                    "supporting_evidence": [],
                })

            # Build properly structured parties list for FactMatrix/Party model compatibility
            structured_parties = []
            for p in structured_data.get("parties", []):
                party_role = (p.get("role") or "").lower()
                is_opposing = party_role not in ["client", "plaintiff", "claimant", "attorney", "counsel"]
                structured_parties.append({
                    "name": p.get("name", ""),
                    "role": p.get("role", ""),
                    "contact_info": None,
                    "first_mentioned_in": "Streaming Analysis",
                    "is_opposing_party": is_opposing,
                    "entity_type": p.get("entity_type", "unknown"),
                })

            multi_stage_result = {
                "fact_matrix": {
                    "parties": structured_parties,
                    "timeline": timeline_events,
                    "financial_data": [],  # Required field for FactMatrix
                    "key_documents": [],   # Required field for FactMatrix
                    "preliminary_issues": [i.get("name", "") for i in structured_data.get("primary_issues", [])],  # Required
                    "financial_items": [],  # Keep for backward compatibility
                },
                "issue_map": {
                    "primary_issues": [
                        {
                            "issue_name": i.get("name", ""),  # Frontend expects issue_name for demand letters
                            "category": i.get("category", ""),
                            "applicable_statutes": i.get("statutes", []),
                            "strength": i.get("strength", "Moderate"),
                        }
                        for i in structured_data.get("primary_issues", [])
                    ],
                },
                "letter_structure": {
                    "style": structured_data.get("recommended_letter_type", "numbered_findings"),
                    "intro": "Key Findings",
                    "issue_format": "numbered_sections_with_headers",
                    "reasoning": "Default structure for comprehensive legal analysis",
                },
                # Deep analysis structure needed for letter generation
                "deep_analysis": {
                    "issue_analyses": [
                        {
                            "issue_name": i.get("name", ""),
                            "legal_standard": f"Legal standard for {i.get('name', '')} - see full analysis for details",
                            "fact_application": f"Fact application for {i.get('name', '')} - see full analysis for details",
                            "statute_analysis": ", ".join(i.get("statutes", [])) if i.get("statutes") else None,
                            "case_law_support": None,
                            "remedies_available": ["See full analysis for detailed remedies"],
                            "procedural_requirements": None,
                            "confidence_level": i.get("strength", "moderate").lower(),
                            "supporting_evidence": [],
                        }
                        for i in structured_data.get("primary_issues", [])
                    ],
                    "risk_assessment": {
                        "major_risks": [],
                        "risk_mitigation_steps": [],
                        "statute_of_limitations_concerns": None,
                        "evidence_gaps": [],
                    },
                    "deadline_tracking": [],
                    "evidence_strength": {
                        "strong_evidence": [],
                        "weak_evidence": [],
                        "missing_evidence": [],
                        "overall_strength": "moderate",
                    },
                    "overall_case_strength": structured_data.get("case_strength", "Moderate"),
                    "key_strengths": [],
                    "key_challenges": [],
                    "is_viable": True,
                    "viability_reasoning": "Based on streaming analysis",
                    "recommend_demand_letter": structured_data.get("recommended_letter_type") in ["demand", "demand_with_findings"],
                },
            }

            # Add financial data if present (parse currency strings to floats)
            if structured_data.get("financial_summary"):
                fin = structured_data["financial_summary"]
                total_claimed = _parse_currency(fin.get("total_claimed"))
                documented_damages = _parse_currency(fin.get("documented_damages"))

                if total_claimed > 0:
                    # Add to financial_items (legacy field for backward compatibility)
                    multi_stage_result["fact_matrix"]["financial_items"].append({
                        "description": "Total Claimed",
                        "amount": total_claimed,
                    })
                    # Add to financial_data (correct field for FactMatrix model)
                    multi_stage_result["fact_matrix"]["financial_data"].append({
                        "amount": total_claimed,
                        "description": "Total Claimed",
                        "source_document": "Streaming Analysis",
                        "payment_type": "claimed",
                        "category": "damages_claimed",
                        "date": None,
                    })

                if documented_damages > 0:
                    multi_stage_result["fact_matrix"]["financial_items"].append({
                        "description": "Documented Damages",
                        "amount": documented_damages,
                    })
                    multi_stage_result["fact_matrix"]["financial_data"].append({
                        "amount": documented_damages,
                        "description": "Documented Damages",
                        "source_document": "Streaming Analysis",
                        "payment_type": "claimed",
                        "category": "damages_claimed",
                        "date": None,
                    })

            # Verify statutes against legal corpus for letter generation
            # Defensive check: ensure multi_stage_result exists before modifying it
            if multi_stage_result is None:
                logger.warning("[STREAM] multi_stage_result is None, skipping verified_statutes conversion")
                multi_stage_result = {}

            try:
                from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
                jurisdiction = case_data.get("jurisdiction", "Florida")
                statute_service = StatuteRecommendationService(jurisdiction=jurisdiction)

                # Get legal issues from structured data
                legal_issues = [i.get("name", "") for i in structured_data.get("primary_issues", [])]

                # Get verified statutes from corpus (jurisdiction already set in constructor)
                verified_statutes = statute_service.recommend_statutes(
                    case_facts=request.content[:2000],  # First 2000 chars of analysis
                    legal_issues=legal_issues,
                )

                # Validate verified_statutes is a list
                if not isinstance(verified_statutes, list):
                    logger.warning(f"[STREAM] verified_statutes is not a list (type: {type(verified_statutes)}), converting to empty list")
                    verified_statutes = []

                # Convert StatuteRecommendation dataclass objects to dicts for JSON serialization
                from dataclasses import asdict
                converted_statutes = []
                conversion_errors = []

                for idx, statute in enumerate(verified_statutes):
                    try:
                        # Check if it's a StatuteRecommendation instance
                        from legal_portal.services.statute_recommendation_service import StatuteRecommendation
                        if isinstance(statute, StatuteRecommendation):
                            converted = asdict(statute)
                            # Validate conversion produced a dict
                            if not isinstance(converted, dict):
                                raise TypeError(f"asdict() returned {type(converted)}, expected dict")
                            converted_statutes.append(converted)
                        else:
                            # If it's already a dict, validate and use it
                            if isinstance(statute, dict):
                                converted_statutes.append(statute)
                            else:
                                logger.warning(f"[STREAM] Item {idx} in verified_statutes is unexpected type: {type(statute)}")
                                conversion_errors.append(f"Item {idx}: {type(statute)}")
                    except (TypeError, AttributeError) as conv_err:
                        logger.error(f"[STREAM] Failed to convert StatuteRecommendation at index {idx}: {conv_err}")
                        conversion_errors.append(f"Item {idx}: {str(conv_err)}")
                    except Exception as conv_err:
                        logger.error(f"[STREAM] Unexpected error converting item {idx}: {conv_err}")
                        conversion_errors.append(f"Item {idx}: {str(conv_err)}")

                multi_stage_result["verified_statutes"] = converted_statutes

                if conversion_errors:
                    logger.warning(f"[STREAM] Had {len(conversion_errors)} conversion errors: {conversion_errors}")

                logger.info(f"[STREAM] Converted {len(converted_statutes)} StatuteRecommendation objects to dicts for {jurisdiction}")

            except (ImportError, ModuleNotFoundError) as import_err:
                logger.info(f"[STREAM] StatuteRecommendationService not available: {import_err}")
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []
            except (TypeError, AttributeError) as conv_err:
                logger.warning(f"[STREAM] Conversion error getting verified statutes: {conv_err}", exc_info=True)
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []
            except Exception as e:
                logger.warning(f"[STREAM] Failed to get verified statutes from corpus: {e}", exc_info=True)
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []

        # Fetch documents for this case (they're in a separate table, not embedded in case_data)
        docs_response = (
            service_supabase.table("documents")
            .select("*")
            .eq("case_id", case_id)
            .execute()
        )
        documents = docs_response.data if docs_response.data else []
        logger.info(f"[STREAM] Building summaries for {len(documents)} documents")

        # Filter out duplicate/excluded documents from summaries and quality report
        # These documents should not appear in Document Review or Quality Report tabs
        filtered_documents = []
        excluded_count = 0
        for doc in documents:
            doc_status = doc.get("status") or ""
            metadata = doc.get("metadata") or {}
            is_excluded = metadata.get("excluded", False)
            is_duplicate = doc_status == "duplicate" or metadata.get("is_duplicate", False)

            if is_excluded or is_duplicate:
                excluded_count += 1
                continue
            filtered_documents.append(doc)

        if excluded_count > 0:
            logger.info(f"[STREAM] Filtered out {excluded_count} duplicate/excluded documents")

        # Build document summaries from filtered documents as JSON array (frontend expects this format)
        doc_summaries_array = []
        quality_report = []

        for doc in filtered_documents:
            # Handle None values explicitly - dict.get() only uses default if key is missing, not if value is None
            extracted_text = doc.get("extracted_text") or ""
            doc_quality = doc.get("quality_score") or 0
            file_type = doc.get("file_type") or ""
            file_name = doc.get("file_name") or "Document"

            # Determine extraction quality based on text length and quality score
            if doc_quality >= 8 or len(extracted_text) > 500:
                extraction_quality = "high"
            elif doc_quality >= 5 or len(extracted_text) > 100:
                extraction_quality = "medium"
            else:
                extraction_quality = "low"

            # Determine document type
            doc_type = doc.get("document_type")
            if not doc_type and file_type:
                doc_type = file_type.split("/")[-1].upper()
            doc_type = doc_type or "Unknown"

            # Build document summary for Document Review tab
            doc_summary = {
                "document_name": file_name,
                "document_type": doc_type,
                "extraction_quality": extraction_quality,
                "relevance_to_case": bool(extracted_text),
                "executive_summary": (extracted_text[:300] + "...") if len(extracted_text) > 300 else (extracted_text or "No summary available"),
                "key_content": extracted_text[:1000] if extracted_text else "No text extracted",
                "key_amounts": [],
            }
            doc_summaries_array.append(doc_summary)

            # Build quality report entry for Quality Report tab
            quality_issues = []
            if not extracted_text:
                quality_issues.append("No text could be extracted from this document")
            elif len(extracted_text) < 100:
                quality_issues.append("Very little text extracted - document may be an image or scan")
            if file_type.startswith("image/"):
                quality_issues.append("Image file - text extraction may be limited")

            quality_report.append({
                "document": file_name,
                "document_id": doc.get("id") or "",
                "score": doc_quality if doc_quality > 0 else (8 if extraction_quality == "high" else 6 if extraction_quality == "medium" else 3),
                "confidence_level": extraction_quality,
                "issues": quality_issues,
            })

        # Extract opposing parties from structured data for demand letter dropdown
        opposing_parties = []
        if structured_data and structured_data.get("parties"):
            for party_data in structured_data["parties"]:
                role = (party_data.get("role") or "").lower()
                name = party_data.get("name") or ""

                # Identify opposing parties (not client or attorney)
                # Common opposing party roles include: landlord, contractor, seller, defendant, respondent
                is_opposing = (
                    "opposing" in role or
                    "defendant" in role or
                    "respondent" in role or
                    "landlord" in role or
                    "contractor" in role or
                    "seller" in role or
                    "hoa" in role or
                    "association" in role or
                    "company" in role or
                    "employer" in role or
                    (role and "client" not in role and "plaintiff" not in role and
                     "claimant" not in role and "attorney" not in role and "counsel" not in role)
                )

                if is_opposing and name:
                    opposing_parties.append({
                        "name": name,
                        "role": party_data.get("role", "Party"),
                        "entity_type": party_data.get("entity_type", "unknown"),
                        "is_opposing_party": True,
                    })

        logger.info(f"[STREAM] Identified {len(opposing_parties)} opposing parties for demand letter dropdown")

        # Build the complete result - must match ProcessingResult structure
        streaming_result = {
            # Required fields for ProcessingResult compatibility
            "main_letter": "",  # Letters are generated separately via letter generation endpoint
            "document_summaries": json.dumps(doc_summaries_array),  # Frontend expects JSON array
            "case_analysis": json.dumps(case_analysis),
            "quality_report": quality_report,  # For Quality Report tab

            # Streaming-specific fields
            "streaming_analysis": request.content,
            "multi_stage_result": multi_stage_result,
            "opposing_parties": opposing_parties,  # For demand letter party dropdown
            "artifacts": {
                "analysis_type": "streaming",
                "jurisdiction": case_data.get("jurisdiction", "Florida"),
                "structured_data": structured_data,
            },
            "status": "completed",
        }

        # Apply recursive conversion to catch any nested StatuteRecommendation objects
        logger.debug("[STREAM] Applying recursive conversion to streaming_result")
        streaming_result = _convert_statute_recommendations_recursive(streaming_result)

        # Explicit JSON serialization test before database save
        # This catches any serialization errors early with detailed error messages
        try:
            test_json = json.dumps(streaming_result)
            logger.debug(f"[STREAM] JSON serialization test passed ({len(test_json)} bytes)")
        except TypeError as json_err:
            # Find the problematic field
            error_msg = str(json_err)
            logger.error(f"[STREAM] JSON serialization test FAILED: {error_msg}")

            # Try to identify the problematic field by testing each top-level key
            problematic_fields = []
            for key, value in streaming_result.items():
                try:
                    json.dumps(value)
                except TypeError as field_err:
                    problematic_fields.append(f"{key}: {field_err}")
                    logger.error(f"[STREAM] Field '{key}' is not JSON serializable: {field_err}")

            # Apply recursive conversion one more time as a last resort
            logger.warning("[STREAM] Applying recursive conversion again to fix serialization issues")
            streaming_result = _convert_statute_recommendations_recursive(streaming_result)

            # Test again
            try:
                test_json = json.dumps(streaming_result)
                logger.info("[STREAM] JSON serialization test passed after recursive conversion")
            except TypeError as retry_err:
                # Log structure keys for debugging (not full content)
                result_keys = list(streaming_result.keys())
                logger.error(
                    f"[STREAM] JSON serialization still failing after recursive conversion. "
                    f"Error: {retry_err}. Result keys: {result_keys}. "
                    f"Problematic fields: {problematic_fields}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to serialize analysis result: {retry_err}. Problematic fields: {problematic_fields}"
                )

        # Create or update analysis result
        # Note: Gap analysis is now handled on-demand via POST /analyze-gaps endpoint
        analysis_id = str(uuid.uuid4())  # Generate proper UUID for database

        try:
            # Check if case exists before saving (prevents race condition in Clio import)
            # Retry up to 3 times with 2 second delays to allow case creation to complete
            import time
            case_exists = False
            for retry in range(3):
                case_check = service_supabase.table("cases").select("id").eq("id", case_id).limit(1).execute()
                if case_check.data:
                    case_exists = True
                    break

                if retry < 2:  # Don't wait on last attempt
                    logger.warning(f"[STREAM] Case {case_id} not found, retry {retry + 1}/3 in 2s...")
                    time.sleep(2)

            if not case_exists:
                logger.error(f"[STREAM] Case {case_id} still not found after 3 retries")
                raise HTTPException(
                    status_code=404,
                    detail=f"Case {case_id} not found in database. Please ensure the case was created before starting analysis."
                )

            logger.info(f"[STREAM] Case {case_id} confirmed, saving analysis results...")
            service_supabase.table("analysis_results").upsert({
                "id": analysis_id,
                "case_id": case_id,
                "status": "completed",
                "result": streaming_result,
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
        except HTTPException:
            raise
        except Exception as db_err:
            # If database save fails, log detailed error
            error_detail = str(db_err)
            logger.error(
                f"[STREAM] Database save failed for case {case_id}: {error_detail}. "
                f"Result keys: {list(streaming_result.keys())}"
            )
            # Check if it's a serialization error
            if "not JSON serializable" in error_detail or "TypeError" in error_detail:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save analysis result due to serialization error: {error_detail}"
                )
            raise

        # Update case status - must use valid status from constraint: pending, processing, completed, error, cancelled
        supabase.table("cases").update({
            "status": "completed",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", case_id).execute()

        logger.info(f"[STREAM] Saved streaming analysis for case {case_id} | structured_data={'yes' if structured_data else 'no'}")

        return {"success": True, "analysis_id": analysis_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving streaming analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _convert_statute_recommendations_recursive(obj: Any) -> Any:
    """Recursively convert any StatuteRecommendation dataclass objects to dicts.
    
    This function walks through the entire data structure (dicts, lists, nested structures)
    and converts any StatuteRecommendation instances to dictionaries for JSON serialization.
    
    Args:
        obj: The object to scan and convert (can be dict, list, or any other type)
    
    Returns:
        The same structure with all StatuteRecommendation objects converted to dicts

    """
    from dataclasses import asdict

    from legal_portal.services.statute_recommendation_service import StatuteRecommendation

    # If it's a StatuteRecommendation instance, convert it
    if isinstance(obj, StatuteRecommendation):
        return asdict(obj)

    # If it's a dict, recursively process values
    if isinstance(obj, dict):
        return {key: _convert_statute_recommendations_recursive(value) for key, value in obj.items()}

    # If it's a list, recursively process items
    if isinstance(obj, list):
        return [_convert_statute_recommendations_recursive(item) for item in obj]

    # If it's a tuple, convert to list, process, and convert back (or keep as list)
    if isinstance(obj, tuple):
        return tuple(_convert_statute_recommendations_recursive(item) for item in obj)

    # For any other type, return as-is
    return obj


def _parse_currency(value) -> float:
    """Parse currency string like '$1,234.56' to float.
    
    Handles various formats:
    - "$1,234.56" -> 1234.56
    - "1234.56" -> 1234.56
    - 1234.56 -> 1234.56
    - None -> 0.0
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove $, commas, and whitespace
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return 0.0


def _extract_embedded_json(content: str) -> dict:
    """Extract the structured JSON block from streaming analysis markdown.
    
    The JSON is embedded in a ```json code fence at the end of the markdown.
    """
    import re

    # Look for JSON code block
    json_pattern = r"```json\s*\n(.*?)\n```"
    match = re.search(json_pattern, content, re.DOTALL)

    if not match:
        logger.warning("[STREAM] No embedded JSON found in streaming analysis")
        return {}

    try:
        json_str = match.group(1).strip()
        structured_data = json.loads(json_str)
        logger.info(f"[STREAM] Extracted structured data: {list(structured_data.keys())}")
        return structured_data
    except json.JSONDecodeError as e:
        logger.error(f"[STREAM] Failed to parse embedded JSON: {e}")
        return {}


def _extract_section(content: str, section_name: str) -> str:
    """Extract a section from markdown content."""
    import re
    pattern = rf"## {section_name}\n(.*?)(?=\n## |$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_list_items(content: str, section_name: str) -> List[str]:
    """Extract list items from a section."""
    import re
    section = _extract_section(content, section_name)
    if not section:
        return []
    # Find bullet points or numbered items
    items = re.findall(r"[-*•]\s*(.+?)(?=\n[-*•]|\n\n|$)", section, re.MULTILINE)
    return [item.strip() for item in items if item.strip()]


@router.get("/stream/{case_id}")
async def stream_case_analysis(
    case_id: str,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream comprehensive case analysis in real-time.
    
    Uses GPT-4.1 to generate a complete analysis in a single streaming call.
    Output is markdown format that renders progressively in the frontend.
    
    This replaces the multi-stage analysis for faster, more reliable results.
    """
    from legal_portal.core.data_models import DocumentSummaryStructured
    from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer

    # Maximum characters of extracted_text to load per document.  Email
    # archives imported from Clio can contain 30+ MB of thread history — loading
    # them all in a single Supabase response causes an httpx ReadTimeout.  Only
    # the first MAX_DOC_CHARS are useful for LLM analysis anyway.
    MAX_DOC_CHARS = 200_000

    try:
        # 1. Verify case ownership — fetch case metadata and document stubs only.
        # extracted_text is intentionally excluded from the nested relation to
        # avoid a single HTTP response that could exceed 100+ MB for cases with
        # many large email documents.
        case_response = (
            supabase.table("cases")
            .select("*, documents(id,file_name,file_type,status,metadata)")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case_data = case_response.data[0]
        doc_stubs = case_data.get("documents", [])

        if not doc_stubs:
            raise HTTPException(status_code=400, detail="No documents found for this case")

        # 1b. Fetch extracted_text for all documents in a single batch query.
        # Using .in_() avoids N+1 round trips (one per document) which was the
        # primary cause of connection count and CPU exhaustion on Supabase.
        doc_ids = [stub["id"] for stub in doc_stubs]
        text_by_id: dict = {}
        try:
            text_resp = (
                supabase.table("documents")
                .select("id, extracted_text")
                .in_("id", doc_ids)
                .execute()
            )
            for row in text_resp.data or []:
                raw = row.get("extracted_text") or ""
                text_by_id[row["id"]] = raw[:MAX_DOC_CHARS]
        except Exception as text_err:
            logger.warning(f"[STREAM] Could not batch-fetch extracted_text: {text_err}")

        documents = []
        for stub in doc_stubs:
            doc = dict(stub)
            doc["extracted_text"] = text_by_id.get(stub["id"], "")
            documents.append(doc)

        # 2. Build document summaries from extracted text
        doc_summaries = []
        intake_content = ""

        for doc in documents:
            extracted_text = doc.get("extracted_text", "") or ""
            file_name = doc.get("file_name", "unknown")
            
            # Derive doc_type from metadata or file_type since it's not a DB column
            metadata = doc.get("metadata") or {}
            doc_type = (
                metadata.get("classification")
                or metadata.get("attorney_enrichment", {}).get("document_type_override")
                or doc.get("file_type", "document")
            )

            if extracted_text:
                # Find intake form
                if "intake" in file_name.lower():
                    intake_content = extracted_text

                doc_summaries.append(DocumentSummaryStructured(
                    document_name=file_name,
                    document_type=doc_type,
                    executive_summary=extracted_text[:500],
                    key_content=extracted_text[:3000],
                ))

        if not intake_content and doc_summaries:
            # Use first document if no intake found
            intake_content = doc_summaries[0].key_content or ""

        # 3. Determine jurisdiction
        jurisdiction = case_data.get("jurisdiction", "Florida")

        # Compute scope counts before the stream so they're available in the done event.
        # _build_condensed_context caps at max_docs=20 for token budget reasons.
        _STREAM_MAX_DOCS = 20
        _docs_in_scope = min(len(doc_summaries), _STREAM_MAX_DOCS)
        _docs_omitted = max(0, len(doc_summaries) - _STREAM_MAX_DOCS)

        logger.info(
            f"[STREAM] Starting streaming analysis for case {case_id} | "
            f"docs={len(doc_summaries)} in_scope={_docs_in_scope} omitted={_docs_omitted} "
            f"jurisdiction={jurisdiction}"
        )

        # 4. Stream the analysis with thinking heartbeats
        async def generate():
            try:
                openai_client = OpenAIClient()
                analyzer = MultiStageAnalyzer(openai_client=openai_client)

                full_content = ""
                first_token_received = False
                start_time = time.time()
                last_heartbeat = start_time

                # Signal that we're starting (thinking phase begins)
                yield f"data: {json.dumps({'phase': 'thinking', 'elapsed': 0})}\n\n"

                # Create the token generator
                token_generator = analyzer.analyze_streaming(
                    intake_content=intake_content,
                    document_summaries=doc_summaries,
                    jurisdiction=jurisdiction,
                )

                # Use asyncio.Queue to handle tokens with heartbeat timeout
                token_queue: asyncio.Queue = asyncio.Queue()
                done_event = asyncio.Event()

                async def collect_tokens():
                    """Collect tokens and put them in queue."""
                    try:
                        async for token in token_generator:
                            await token_queue.put(('token', token))
                        await token_queue.put(('done', None))
                    except Exception as e:
                        await token_queue.put(('error', str(e)))

                # Start token collection in background
                collector_task = asyncio.create_task(collect_tokens())

                try:
                    while True:
                        try:
                            # Wait for token with 5-second timeout for heartbeat
                            msg_type, msg_data = await asyncio.wait_for(
                                token_queue.get(),
                                timeout=5.0
                            )

                            if msg_type == 'token':
                                if not first_token_received:
                                    first_token_received = True
                                    elapsed = int(time.time() - start_time)
                                    logger.info(f"[STREAM] First token received after {elapsed}s thinking")
                                    # Signal transition from thinking to streaming
                                    yield f"data: {json.dumps({'phase': 'streaming', 'thinking_time': elapsed})}\n\n"

                                full_content += msg_data
                                yield f"data: {json.dumps({'token': msg_data})}\n\n"

                            elif msg_type == 'done':
                                # Signal completion — include scope counts for UI warning
                                yield f"data: {json.dumps({'done': True, 'content': full_content, 'docs_in_scope': _docs_in_scope, 'docs_omitted': _docs_omitted})}\n\n"
                                logger.info(
                                    f"[STREAM] Completed streaming for case {case_id} | "
                                    f"docs_in_scope={_docs_in_scope} docs_omitted={_docs_omitted}"
                                )
                                break

                            elif msg_type == 'error':
                                yield f"data: {json.dumps({'error': msg_data})}\n\n"
                                break

                        except asyncio.TimeoutError:
                            # No token received in 5 seconds - send heartbeat
                            elapsed = int(time.time() - start_time)

                            if not first_token_received:
                                # Still in thinking phase - send thinking heartbeat
                                yield f"data: {json.dumps({'phase': 'thinking', 'elapsed': elapsed})}\n\n"
                                logger.debug(f"[STREAM] Thinking heartbeat: {elapsed}s")
                            else:
                                # In streaming phase but slow - send streaming heartbeat
                                yield f"data: {json.dumps({'heartbeat': elapsed})}\n\n"

                finally:
                    # Ensure collector task is cleaned up
                    if not collector_task.done():
                        collector_task.cancel()
                        try:
                            await collector_task
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                logger.error(f"[STREAM] Error during streaming: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable Vercel/nginx buffering
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in stream_case_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-letter", response_model=LetterGenerationResponse)
@limiter.limit("10/minute")  # Rate limit letter generation
async def generate_letter(
    letter_request: LetterGenerationRequest,
    request: Request,  # Required for rate limiter (must be named 'request')
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Generate findings or demand letters on-demand."""
    settings = get_settings()
    started_at = time.monotonic()

    _ensure_case_access(supabase, letter_request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, letter_request.case_id)
    metrics = _new_generation_metrics(
        analysis_id=analysis_record["id"],
        letter_type=letter_request.letter_type.value,
        streaming=False,
    )
    internal_deadline = started_at + max(30, int(settings.letter_internal_budget_seconds))
    strategy_budget = max(1, int(settings.letter_strategy_budget_seconds))
    critic_budget = max(1, int(settings.letter_critic_budget_seconds))
    repair_budget = max(1, int(settings.letter_repair_budget_seconds))
    finalize_budget = max(1, int(settings.letter_finalize_budget_seconds))

    def _remaining_seconds() -> float:
        return internal_deadline - time.monotonic()

    try:
        await _ensure_fresh_gap_analysis_for_letter_generation(
            supabase=supabase,
            analysis_record=analysis_record,
            user_id=user["id"],
        )

        result_payload = analysis_record["result"]
        processing_result = ProcessingResult(**result_payload)

        if not processing_result.multi_stage_result:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="On-demand letters require the latest analysis. Please re-run the case analysis.",
            )

        artifacts = processing_result.artifacts or {}
        resolved_identity = _resolve_letter_identity_context(
            supabase=supabase,
            case_id=letter_request.case_id,
            artifacts=artifacts,
            overrides={
                "attorney_name": letter_request.attorney_name,
                "firm_name": letter_request.firm_name,
                "contact_phone": letter_request.contact_phone,
                "contact_email": letter_request.contact_email,
                "client_name": letter_request.client_name,
            },
        )
        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        attorney_info = {
            "name": resolved_identity.get("attorney_name"),
            "firm": resolved_identity.get("firm_name"),
            "phone": resolved_identity.get("contact_phone"),
            "email": resolved_identity.get("contact_email"),
        }

        msr = processing_result.multi_stage_result
        letter_html: str
        target_party_name: Optional[str] = None
        client_name = _resolve_client_name_for_letter(
            resolved_identity=resolved_identity,
            artifacts=artifacts,
            fact_matrix=msr.get("fact_matrix"),
        )
        strategy_object: Optional[Dict[str, Any]] = None
        draft_markdown_for_repair: Optional[str] = None
        quality_report = _quality_report_placeholder(
            mode="default",
            letter_type=letter_request.letter_type.value,
        )

        jurisdiction = artifacts.get("jurisdiction", "Florida")
        logger.info(f"Generating {letter_request.letter_type} letter for {jurisdiction}")

        diag_logger = None
        if DiagnosticLogger.get_enabled():
            diag_logger = DiagnosticLogger(session_id=letter_request.case_id)

        gap_analysis = None
        fact_matrix = None
        verified_statutes: List[Dict[str, Any]] = []
        json_service = JsonProcessingService(client=openai_client, config={})
        normalize_markdown = getattr(json_service, "normalize_client_letter_markdown", None)

        def _normalize_markdown(text: str, letter_kind: str) -> str:
            if callable(normalize_markdown):
                return normalize_markdown(
                    text,
                    letter_type=letter_kind,
                    attorney_name=attorney_info.get("name"),
                    firm_name=attorney_info.get("firm"),
                )
            return text

        if letter_request.letter_type == LetterType.FINDINGS:
            from legal_portal.core.data_models import (
                DeepAnalysis,
                FactMatrix,
                GapAnalysisResult,
                LetterStructure,
            )

            fact_matrix = FactMatrix(**msr["fact_matrix"])
            deep_analysis = DeepAnalysis(**msr["deep_analysis"])
            letter_structure = LetterStructure(**msr["letter_structure"])
            verified_statutes = msr.get("verified_statutes", [])
            client_name = _resolve_client_name_for_letter(
                resolved_identity=resolved_identity,
                artifacts=artifacts,
                fact_matrix=fact_matrix,
            )

            gap_analysis_data = msr.get("gap_analysis")
            if gap_analysis_data:
                try:
                    gap_analysis = GapAnalysisResult(**gap_analysis_data)
                    logger.info(
                        "Gap analysis loaded: completeness=%s, critical_gaps=%s",
                        gap_analysis.overall_completeness_score,
                        gap_analysis.critical_count,
                    )
                except Exception as gap_err:
                    logger.warning(f"Could not load gap analysis for guardrails: {gap_err}")

            document_summaries_for_context: List[Dict[str, Any]] = []
            if processing_result.document_summaries:
                try:
                    parsed_summaries = json.loads(processing_result.document_summaries)
                    if isinstance(parsed_summaries, list):
                        document_summaries_for_context = [
                            item for item in parsed_summaries if isinstance(item, dict)
                        ]
                except Exception as parse_err:
                    logger.warning(
                        "[LETTER] Failed to parse document_summaries for findings context: %s",
                        parse_err,
                    )

            if gap_analysis:
                if gap_analysis.overall_completeness_score < 40:
                    if not letter_request.force_generation:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail={
                                "error": "documentation_insufficient",
                                "message": (
                                    "Case documentation is insufficient for letter generation. "
                                    "Please provide the missing documents identified in Gap Analysis "
                                    "before generating a letter."
                                ),
                                "completeness_score": gap_analysis.overall_completeness_score,
                                "critical_gaps": gap_analysis.critical_count,
                                "recommendation": (
                                    "Review the Gap Analysis tab to identify which documents are needed."
                                ),
                                "allow_override": True,
                            },
                        )
                    logger.warning(
                        "OVERRIDE: force_generation used for case %s with low completeness score "
                        "(%s%%) - critical_gaps=%s",
                        letter_request.case_id,
                        gap_analysis.overall_completeness_score,
                        gap_analysis.critical_count,
                    )
                elif gap_analysis.overall_completeness_score < 60:
                    logger.warning(
                        "Generating letter with low completeness score: %s%% "
                        "(critical_gaps=%s, high_gaps=%s)",
                        gap_analysis.overall_completeness_score,
                        gap_analysis.critical_count,
                        gap_analysis.high_count,
                    )

            if settings.letter_strategy_enabled and _remaining_seconds() >= (strategy_budget + finalize_budget):
                strategy_started = time.monotonic()
                try:
                    metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                    strategy_object = await json_service.build_findings_strategy(
                        fact_matrix=fact_matrix,
                        deep_analysis=deep_analysis,
                        gap_analysis=gap_analysis,
                        timeout_seconds=strategy_budget,
                        allow_model=True,
                        model="gpt-5-mini",
                    )
                    metrics["strategy_used"] = bool(strategy_object)
                except Exception as strategy_err:
                    logger.warning("[LETTER] Findings strategy build failed: %s", strategy_err)
                finally:
                    metrics["strategy_latency_ms"] = int((time.monotonic() - strategy_started) * 1000)

            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
            raw_findings_html = await json_service.generate_findings_letter_adaptive(
                intake_content=processing_result.intake_content or "",
                fact_matrix=fact_matrix,
                legal_analysis=deep_analysis,
                structure_guidance=letter_structure,
                verified_statutes=verified_statutes,
                attorney_name=attorney_info["name"],
                firm_name=attorney_info["firm"],
                confirmed_qa_pairs=artifacts.get("confirmed_qa_pairs", []),
                contact_phone=attorney_info["phone"],
                contact_email=attorney_info["email"],
                quality_context=artifacts.get("quality_context", ""),
                clio_matter_context=artifacts.get("clio_matter_context", ""),
                jurisdiction=jurisdiction,
                diag_logger=diag_logger,
                original_documents=msr.get("original_documents"),
                document_summaries_for_context=document_summaries_for_context,
                document_registry=msr.get("document_registry"),
                strategy_object=strategy_object,
                gap_analysis=gap_analysis,
            )
            draft_markdown_for_repair = html2text.html2text(raw_findings_html)
            letter_html = DocumentFormatterService.format_findings_letter(
                letter_html=raw_findings_html,
                client_name=client_name,
            )
            letter_key = "findings"
        else:
            if not letter_request.target_party_name:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="target_party_name is required for demand letters",
                )
            client_name = _resolve_client_name_for_letter(
                resolved_identity=resolved_identity,
                artifacts=artifacts,
                fact_matrix=msr.get("fact_matrix"),
            )

            document_summaries = []
            if processing_result.document_summaries:
                try:
                    document_summaries = json.loads(processing_result.document_summaries)
                except Exception as parse_err:
                    logger.warning(f"Failed to parse document_summaries: {parse_err}")

            demand_service = DemandLetterService(openai_client)
            from legal_portal.core.data_models import DeepAnalysis, FactMatrix, GapAnalysisResult

            demand_fact_matrix = FactMatrix(**msr["fact_matrix"])
            demand_deep_analysis = DeepAnalysis(**msr["deep_analysis"])
            if not gap_analysis and msr.get("gap_analysis"):
                try:
                    gap_analysis = GapAnalysisResult(**msr["gap_analysis"])
                except Exception:
                    gap_analysis = None

            if settings.letter_strategy_enabled and _remaining_seconds() >= (strategy_budget + finalize_budget):
                strategy_started = time.monotonic()
                try:
                    metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                    strategy_object = await demand_service.build_demand_strategy(
                        fact_matrix=demand_fact_matrix,
                        deep_analysis=demand_deep_analysis,
                        target_party_name=letter_request.target_party_name,
                        demand_amount=letter_request.demand_amount,
                        demand_deadline=letter_request.demand_deadline,
                        specific_demands=letter_request.specific_demands,
                        client_name=client_name,
                        gap_analysis=gap_analysis,
                        timeout_seconds=strategy_budget,
                        allow_model=True,
                        model="gpt-5-mini",
                    )
                    metrics["strategy_used"] = bool(strategy_object)
                except Exception as strategy_err:
                    logger.warning("[LETTER] Demand strategy build failed: %s", strategy_err)
                finally:
                    metrics["strategy_latency_ms"] = int((time.monotonic() - strategy_started) * 1000)

            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
            letter_html, draft_markdown_for_repair = await demand_service.generate_demand_letter_with_markdown(
                fact_matrix_dict=msr["fact_matrix"],
                deep_analysis_dict=msr["deep_analysis"],
                target_party_name=letter_request.target_party_name,
                demand_amount=letter_request.demand_amount,
                demand_deadline=letter_request.demand_deadline,
                specific_demands=letter_request.specific_demands,
                attorney_info=attorney_info,
                client_name=client_name,
                document_summaries=document_summaries,
                jurisdiction=jurisdiction,
                strategy_object=strategy_object,
            )
            target_party_name = letter_request.target_party_name
            # Polish pass: second AI call for prose formatting consistency
            if getattr(settings, "letter_polish_enabled", True):
                try:
                    from legal_portal.utils.letter_polish import polish_letter_async

                    pre_polish_markdown = draft_markdown_for_repair
                    _polish_timeout = getattr(settings, "letter_polish_timeout_seconds", 55)
                    polish_result = await polish_letter_async(
                        openai_client,
                        pre_polish_markdown,
                        timeout_seconds=float(_polish_timeout),
                    )
                    if polish_result.get("success") and polish_result.get("polished_letter"):
                        polished_candidate = polish_result["polished_letter"]
                        integrity_report = {"passed": True, "reason": "unsupported"}
                        if hasattr(LetterValidationService, "check_polish_fact_integrity"):
                            integrity_report = LetterValidationService().check_polish_fact_integrity(
                                pre_polish_markdown,
                                polished_candidate,
                                tracked_entities=[
                                    client_name,
                                    target_party_name,
                                    attorney_info.get("name") or "",
                                    attorney_info.get("firm") or "",
                                ],
                            )
                        metrics["polish_integrity_passed"] = bool(integrity_report.get("passed", True))

                        if integrity_report.get("passed", True):
                            draft_markdown_for_repair = polished_candidate
                            polished_html = json_service._convert_markdown_to_html(polished_candidate)
                            letter_html = DocumentFormatterService.format_demand_letter(
                                letter_html=polished_html,
                                recipient_name=target_party_name,
                            )
                            metrics["polish_applied"] = True
                        else:
                            metrics["polish_applied"] = False
                            metrics["polish_reverted"] = True
                            metrics["polish_revert_reason"] = (
                                f"fact_integrity:{integrity_report.get('reason', 'unknown')}"
                            )
                            logger.warning(
                                "[DEMAND] Polish reverted due to fact integrity drift: %s",
                                integrity_report,
                            )
                except Exception as polish_err:
                    logger.warning("[DEMAND] Polish pass failed, using raw draft: %s", polish_err)
            else:
                logger.info("[DEMAND] Polish pass disabled by configuration")
            letter_key = f"demand_{letter_request.target_party_name.replace(' ', '_')}".lower()

        validator = LetterValidationService()

        if gap_analysis and letter_request.letter_type == LetterType.FINDINGS and fact_matrix is not None:
            try:
                validation_result = validator.validate_letter(
                    letter_html=letter_html,
                    fact_matrix=fact_matrix,
                    gap_analysis=gap_analysis,
                    verified_statutes=verified_statutes,
                )
                if validation_result.warnings:
                    warning_summary = "; ".join([w.message for w in validation_result.warnings[:5]])
                    logger.warning(
                        "Letter validation warnings (%s total): %s",
                        len(validation_result.warnings),
                        warning_summary,
                    )
                else:
                    logger.info("Letter passed source-of-truth validation with no warnings")
            except Exception as validation_err:
                logger.warning(f"Letter validation skipped due to error: {validation_err}")

        if draft_markdown_for_repair:
            normalized_draft = _normalize_markdown(
                draft_markdown_for_repair,
                letter_request.letter_type.value,
            )
            if normalized_draft.strip() and normalized_draft.strip() != draft_markdown_for_repair.strip():
                draft_markdown_for_repair = normalized_draft
                if letter_request.letter_type == LetterType.DEMAND and target_party_name:
                    normalized_html = json_service._convert_markdown_to_html(draft_markdown_for_repair)
                    letter_html = DocumentFormatterService.format_demand_letter(
                        letter_html=normalized_html,
                        recipient_name=target_party_name,
                    )
                elif letter_request.letter_type == LetterType.FINDINGS:
                    normalized_html = json_service._convert_markdown_to_html(draft_markdown_for_repair)
                    letter_html = DocumentFormatterService.format_findings_letter(
                        letter_html=normalized_html,
                        client_name=client_name,
                    )
                else:
                    letter_html = json_service._convert_markdown_to_html(draft_markdown_for_repair)

        lint_input = draft_markdown_for_repair or letter_html
        if settings.letter_quality_lint_enabled:
            try:
                quality_report = validator.lint_client_letter(
                    lint_input,
                    mode="default",
                    letter_type=letter_request.letter_type.value,
                )
            except Exception as lint_err:
                logger.warning(f"Letter lint failed, using placeholder report: {lint_err}")

        critic_feedback: Dict[str, Any] = {"failed_sections": []}
        if (
            settings.letter_quality_critic_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
            and _remaining_seconds() >= (critic_budget + finalize_budget)
        ):
            metrics["critic_attempted"] = True
            critic_started = time.monotonic()
            try:
                metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                critic_feedback = await json_service.run_quality_critic(
                    draft_markdown=lint_input,
                    letter_type=letter_request.letter_type.value,
                    lint_violations=quality_report.get("violations", []),
                    quality_report_v2=quality_report.get("quality_report_v2"),
                    model="gpt-5-mini",
                    timeout_seconds=critic_budget,
                )
            except Exception as critic_err:
                logger.warning("[LETTER] Critic step failed: %s", critic_err)
                metrics["critic_skipped_reason"] = f"critic_error:{type(critic_err).__name__}"
            finally:
                metrics["critic_latency_ms"] = int((time.monotonic() - critic_started) * 1000)
        elif (
            settings.letter_quality_critic_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
            and _remaining_seconds() < (critic_budget + finalize_budget)
        ):
            metrics["critic_skipped_reason"] = "insufficient_budget"

        if (
            settings.letter_conditional_repair_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
            and _remaining_seconds() >= (repair_budget + finalize_budget)
        ):
            metrics["repair_attempted"] = True
            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
            repaired_markdown = await json_service.repair_letter_constraints(
                lint_input,
                quality_report.get("violations", []),
                mode="default",
                model="gpt-5-mini",
                critic_feedback=critic_feedback,
            )
            repaired_markdown = _normalize_markdown(
                repaired_markdown,
                letter_request.letter_type.value,
            )
            post_repair_report = validator.lint_client_letter(
                repaired_markdown,
                mode="default",
                letter_type=letter_request.letter_type.value,
            )
            quality_report = {
                **post_repair_report,
                "pre_repair": quality_report,
                "post_repair": post_repair_report,
                "critic_feedback": critic_feedback,
            }
            if repaired_markdown.strip() and repaired_markdown.strip() != lint_input.strip():
                if letter_request.letter_type == LetterType.DEMAND and target_party_name:
                    repaired_html = json_service._convert_markdown_to_html(repaired_markdown)
                    letter_html = DocumentFormatterService.format_demand_letter(
                        letter_html=repaired_html,
                        recipient_name=target_party_name,
                    )
                elif letter_request.letter_type == LetterType.FINDINGS:
                    repaired_html = json_service._convert_markdown_to_html(repaired_markdown)
                    letter_html = DocumentFormatterService.format_findings_letter(
                        letter_html=repaired_html,
                        client_name=client_name,
                    )
                else:
                    letter_html = json_service._convert_markdown_to_html(repaired_markdown)
                draft_markdown_for_repair = repaired_markdown
                metrics["repair_applied"] = True
                if critic_feedback.get("failed_sections"):
                    metrics["critic_applied"] = True
        elif (
            settings.letter_conditional_repair_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
        ):
            quality_report = {
                **quality_report,
                "repair_skipped": "insufficient_budget",
                "critic_feedback": critic_feedback,
            }

        metrics["lint_passed"] = quality_report.get("lint_passed")
        metrics["lint_score"] = quality_report.get("score")
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)

        generated_letters = result_payload.setdefault("generated_letters", {})
        generated_letters[letter_key] = letter_html
        if letter_request.letter_type == LetterType.FINDINGS:
            generated_letters["findings_meta"] = {
                "quality_report": quality_report,
                "quality_report_v2": quality_report.get("quality_report_v2"),
                "generation_metrics": metrics,
                "strategy_object": strategy_object,
            }
        else:
            generated_letters[f"{letter_key}_meta"] = {
                "quality_report": quality_report,
                "quality_report_v2": quality_report.get("quality_report_v2"),
                "generation_metrics": metrics,
                "strategy_object": strategy_object,
            }

        supabase.table("analysis_results").update({"result": result_payload}).eq(
            "id", analysis_record["id"]
        ).execute()

        _emit_generation_metrics(metrics)

        return LetterGenerationResponse(
            letter_html=letter_html,
            letter_type=letter_request.letter_type,
            target_party_name=target_party_name,
            quality_report=quality_report,
            generation_metrics=metrics,
        )
    except HTTPException as exc:
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)
        if isinstance(exc.detail, dict):
            metrics["error_code"] = exc.detail.get("error") or str(exc.status_code)
        else:
            metrics["error_code"] = str(exc.status_code)
        _emit_generation_metrics(metrics)
        raise
    except Exception as exc:
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)
        metrics["error_code"] = type(exc).__name__
        _emit_generation_metrics(metrics)
        raise


# =============================================================================
# RECOMMENDATION LETTER GENERATION ENDPOINT
# =============================================================================


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


@router.post("/generate-recommendation-letter", response_model=RecommendationLetterResponse)
async def generate_recommendation_letter(
    letter_request: RecommendationLetterRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Generate a recommendation-based letter (proceed, request_documents, settlement_advisory, declination).

    This endpoint generates letters based on the case recommendation category from gap analysis.
    Unlike findings/demand letters, these are advisory letters about case status.
    """
    settings = get_settings()
    started_at = time.monotonic()
    case_id = letter_request.case_id
    logger.info(f"[REC_LETTER_ENDPOINT] Generating {letter_request.letter_type} letter for case {case_id}")

    _ensure_case_access(supabase, case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, case_id)
    metrics = _new_generation_metrics(
        analysis_id=analysis_record["id"],
        letter_type=letter_request.letter_type,
        streaming=False,
    )

    try:
        result_payload = analysis_record["result"]
        processing_result = ProcessingResult(**result_payload)

        if not processing_result.multi_stage_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Recommendation letter requires a completed multi-stage analysis. "
                    "Please run case analysis first."
                ),
            )

        msr = processing_result.multi_stage_result

        from legal_portal.core.data_models import (
            DeepAnalysis,
            DocumentSummaryStructured,
            FactMatrix,
            GapAnalysisResult,
            RecommendedLetterType,
        )
        from legal_portal.services.recommendation_letter_service import RecommendationLetterService

        try:
            letter_type_enum = RecommendedLetterType(letter_request.letter_type)
        except ValueError:
            valid_types = [
                t.value for t in RecommendedLetterType if t.value not in ["findings", "demand"]
            ]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid letter_type '{letter_request.letter_type}'. Valid types: {valid_types}",
            )

        gap_analysis_data = msr.get("gap_analysis")
        if not gap_analysis_data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Recommendation letter requires gap analysis. Please run gap analysis first.",
            )

        gap_analysis = GapAnalysisResult(**gap_analysis_data)
        fact_matrix = FactMatrix(**msr.get("fact_matrix", {})) if msr.get("fact_matrix") else None
        deep_analysis = DeepAnalysis(**msr.get("deep_analysis", {})) if msr.get("deep_analysis") else None

        document_summaries = None
        if processing_result.document_summaries:
            try:
                doc_summaries_raw = json.loads(processing_result.document_summaries)
                document_summaries = [DocumentSummaryStructured(**ds) for ds in doc_summaries_raw]
            except Exception as parse_err:
                logger.warning(f"Failed to parse document_summaries: {parse_err}")

        artifacts = processing_result.artifacts or {}
        resolved_identity = _resolve_letter_identity_context(
            supabase=supabase,
            case_id=case_id,
            artifacts=artifacts,
            overrides={
                "attorney_name": letter_request.attorney_name,
                "firm_name": letter_request.firm_name,
                "contact_phone": letter_request.contact_phone,
                "contact_email": letter_request.contact_email,
                "client_name": letter_request.client_name,
            },
        )
        jurisdiction = artifacts.get("jurisdiction", "Florida")
        attorney_info = {
            "attorney_name": resolved_identity.get("attorney_name"),
            "firm_name": resolved_identity.get("firm_name"),
            "contact_phone": resolved_identity.get("contact_phone"),
            "contact_email": resolved_identity.get("contact_email"),
        }

        client_name = _resolve_client_name_for_letter(
            resolved_identity=resolved_identity,
            artifacts=artifacts,
            fact_matrix=fact_matrix,
        )

        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        rec_letter_service = RecommendationLetterService(openai_client)
        metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1

        try:
            letter_html = await rec_letter_service.generate_recommendation_letter(
                letter_type=letter_type_enum,
                gap_analysis=gap_analysis,
                deep_analysis=deep_analysis,
                fact_matrix=fact_matrix,
                document_summaries=document_summaries,
                attorney_info=attorney_info,
                client_name=client_name,
                jurisdiction=jurisdiction,
            )
        except Exception as gen_err:
            logger.error(f"[REC_LETTER_ENDPOINT] Error generating letter: {gen_err}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate recommendation letter: {str(gen_err)}",
            )

        quality_report = _quality_report_placeholder(mode="default", letter_type="recommendation")
        if settings.letter_quality_lint_enabled:
            try:
                validator = LetterValidationService()
                quality_report = validator.lint_client_letter(
                    letter_html,
                    mode="default",
                    letter_type="recommendation",
                )
            except Exception as lint_err:
                logger.warning(f"[REC_LETTER_ENDPOINT] Lint failed; using placeholder report: {lint_err}")

        metrics["lint_passed"] = quality_report.get("lint_passed")
        metrics["lint_score"] = quality_report.get("score")
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)

        letter_key = f"recommendation_{letter_request.letter_type}"
        generated_letters = result_payload.setdefault("generated_letters", {})
        generated_letters[letter_key] = letter_html
        generated_letters[f"{letter_key}_meta"] = {
            "quality_report": quality_report,
            "generation_metrics": metrics,
        }
        service_supabase.table("analysis_results").update({"result": result_payload}).eq(
            "id", analysis_record["id"]
        ).execute()

        logger.info(
            "[REC_LETTER_ENDPOINT] %s letter generated and saved for case %s",
            letter_request.letter_type,
            case_id,
        )
        _emit_generation_metrics(metrics)

        recommendation_category = None
        if gap_analysis.recommendation:
            recommendation_category = gap_analysis.recommendation.category.value

        return RecommendationLetterResponse(
            letter_html=letter_html,
            letter_type=letter_request.letter_type,
            recommendation_category=recommendation_category,
            quality_report=quality_report,
            generation_metrics=metrics,
        )
    except HTTPException as exc:
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)
        if isinstance(exc.detail, dict):
            metrics["error_code"] = exc.detail.get("error") or str(exc.status_code)
        else:
            metrics["error_code"] = str(exc.status_code)
        _emit_generation_metrics(metrics)
        raise
    except Exception as exc:
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)
        metrics["error_code"] = type(exc).__name__
        _emit_generation_metrics(metrics)
        raise


@router.get("/{analysis_id}/recommendation-letter/stream")
async def stream_recommendation_letter(
    analysis_id: str,
    letter_type: str = Query(...),
    schema_version: int = Query(default=2, ge=1, le=2),
    mode: Literal["default", "strict_quality"] = Query(default="default"),
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream recommendation letter generation with optional v2 SSE schema."""
    settings = get_settings()
    if not settings.recommendation_stream_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not enabled")

    from legal_portal.core.data_models import (
        DeepAnalysis,
        DocumentSummaryStructured,
        FactMatrix,
        GapAnalysisResult,
        RecommendedLetterType,
    )
    from legal_portal.services.recommendation_letter_service import RecommendationLetterService

    response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis_data = response.data[0]
    _ensure_case_access(supabase, analysis_data["case_id"], user["id"])
    result_payload = analysis_data.get("result")
    if not result_payload:
        raise HTTPException(status_code=400, detail="Analysis result not yet available")

    processing_result = ProcessingResult(**result_payload)
    if not processing_result.multi_stage_result:
        raise HTTPException(status_code=400, detail="Multi-stage analysis results missing")

    msr = processing_result.multi_stage_result
    gap_analysis_data = msr.get("gap_analysis")
    if not gap_analysis_data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recommendation letter requires gap analysis. Please run gap analysis first.",
        )

    try:
        letter_type_enum = RecommendedLetterType(letter_type)
    except ValueError:
        valid_types = [t.value for t in RecommendedLetterType if t.value not in ["findings", "demand"]]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid letter_type '{letter_type}'. Valid types: {valid_types}",
        )

    effective_schema_version = 2 if (schema_version == 2 and settings.letter_stream_schema_v2) else 1
    artifacts = processing_result.artifacts or {}
    resolved_identity = _resolve_letter_identity_context(
        supabase=supabase,
        case_id=analysis_data["case_id"],
        artifacts=artifacts,
    )
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)

    def _event_payload(event_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if effective_schema_version == 1:
            if event_name == "token":
                return {"token": kwargs.get("token", "")}
            if event_name == "done":
                return {"done": True}
            if event_name == "error":
                return {"error": kwargs.get("error", "Stream failed")}
            return None

        payload: Dict[str, Any] = {
            "schema_version": 2,
            "event": event_name,
            "type": event_name,
        }
        payload.update(kwargs)
        if event_name == "done":
            payload["done"] = True
        return payload

    async def generate():
        request_started = time.monotonic()
        metrics = _new_generation_metrics(
            analysis_id=analysis_id,
            letter_type=letter_type,
            streaming=True,
        )
        quality_report = _quality_report_placeholder(mode=mode, letter_type="recommendation")
        draft_markdown = ""
        recoverable_timeout = False
        internal_budget = max(30, int(settings.letter_internal_budget_seconds))
        lint_budget = max(1, int(settings.letter_lint_budget_seconds))
        repair_budget = max(1, int(settings.letter_repair_budget_seconds))
        finalize_budget = max(1, int(settings.letter_finalize_budget_seconds))
        heartbeat_interval = max(1, int(settings.letter_stream_heartbeat_seconds))
        internal_deadline = request_started + internal_budget

        def _emit(event_name: str, **kwargs: Any) -> Optional[str]:
            payload = _event_payload(event_name, **kwargs)
            if payload is None:
                return None
            return _to_sse(payload)

        try:
            phase_msg = _emit("phase", phase="context_build", message="Building context", percent=8)
            if phase_msg:
                yield phase_msg

            gap_analysis = GapAnalysisResult(**gap_analysis_data)
            fact_matrix = FactMatrix(**msr.get("fact_matrix", {})) if msr.get("fact_matrix") else None
            deep_analysis = DeepAnalysis(**msr.get("deep_analysis", {})) if msr.get("deep_analysis") else None

            document_summaries = None
            if processing_result.document_summaries:
                try:
                    doc_summaries_raw = json.loads(processing_result.document_summaries)
                    document_summaries = [DocumentSummaryStructured(**ds) for ds in doc_summaries_raw]
                except Exception as parse_err:
                    logger.warning("Failed to parse document_summaries: %s", parse_err)

            jurisdiction = artifacts.get("jurisdiction", "Florida")
            attorney_info = {
                "attorney_name": resolved_identity.get("attorney_name"),
                "firm_name": resolved_identity.get("firm_name"),
                "contact_phone": resolved_identity.get("contact_phone"),
                "contact_email": resolved_identity.get("contact_email"),
            }
            client_name = _resolve_client_name_for_letter(
                resolved_identity=resolved_identity,
                artifacts=artifacts,
                fact_matrix=fact_matrix,
            )

            phase_msg = _emit("phase", phase="draft_generation", message="Generating draft")
            if phase_msg:
                yield phase_msg

            openai_client = OpenAIClient(user_preferences=ai_preferences)
            rec_service = RecommendationLetterService(openai_client)
            json_service = JsonProcessingService(client=openai_client, config={})
            normalize_markdown = getattr(json_service, "normalize_client_letter_markdown", None)

            def _normalize_markdown(text: str, letter_kind: str) -> str:
                if callable(normalize_markdown):
                    return normalize_markdown(
                        text,
                        letter_type=letter_kind,
                        attorney_name=attorney_info.get("attorney_name"),
                        firm_name=attorney_info.get("firm_name"),
                    )
                return text

            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1

            token_queue: asyncio.Queue = asyncio.Queue()

            async def _collect_tokens() -> None:
                try:
                    async for token in rec_service.stream_recommendation_letter(
                        letter_type=letter_type_enum,
                        gap_analysis=gap_analysis,
                        deep_analysis=deep_analysis,
                        fact_matrix=fact_matrix,
                        document_summaries=document_summaries,
                        attorney_info=attorney_info,
                        client_name=client_name,
                        jurisdiction=jurisdiction,
                    ):
                        await token_queue.put(("token", token))
                except Exception as stream_err:
                    await token_queue.put(("error", stream_err))
                finally:
                    await token_queue.put(("done", None))

            collector_task = asyncio.create_task(_collect_tokens())
            draft_deadline = internal_deadline - (lint_budget + finalize_budget)
            _draft_token_count = 0
            _last_wc_emit_token = 0
            try:
                while True:
                    if time.monotonic() > draft_deadline:
                        metrics["timeout"] = True
                        metrics["error_code"] = "draft_budget_exceeded"
                        break
                    try:
                        msg_type, msg_data = await asyncio.wait_for(
                            token_queue.get(),
                            timeout=heartbeat_interval,
                        )
                    except asyncio.TimeoutError:
                        heartbeat_msg = _emit(
                            "heartbeat",
                            phase="draft_generation",
                            elapsed_ms=int((time.monotonic() - request_started) * 1000),
                        )
                        if heartbeat_msg:
                            yield heartbeat_msg
                        continue

                    if msg_type == "token":
                        token = str(msg_data or "")
                        if not token:
                            continue
                        draft_markdown += token
                        _draft_token_count += 1
                        if metrics["ttft_ms"] is None:
                            metrics["ttft_ms"] = int((time.monotonic() - request_started) * 1000)
                        token_msg = _emit("token", token=token)
                        if token_msg:
                            yield token_msg
                        if _draft_token_count - _last_wc_emit_token >= 200:
                            _last_wc_emit_token = _draft_token_count
                            _wc = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
                            _pct = min(88, 10 + _wc * 78 // 1000)
                            wc_msg = _emit("phase", phase="draft_generation", message=f"Drafting letter... ({_wc:,} words)", percent=_pct)
                            if wc_msg:
                                yield wc_msg
                    elif msg_type == "error":
                        if isinstance(msg_data, Exception):
                            raise msg_data
                        raise RuntimeError(str(msg_data))
                    elif msg_type == "done":
                        break
            finally:
                if not collector_task.done():
                    collector_task.cancel()
                    try:
                        await collector_task
                    except asyncio.CancelledError:
                        pass

            draft_word_count = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
            if metrics["timeout"] and draft_word_count >= 80:
                recoverable_timeout = True
                timeout_msg = _emit(
                    "error",
                    error="Draft generation exceeded time budget; finalizing best available content.",
                    code=metrics.get("error_code"),
                    recoverable=True,
                )
                if timeout_msg:
                    yield timeout_msg

            if not draft_markdown.strip():
                raise RuntimeError("Recommendation letter generation produced no content.")

            draft_markdown = _normalize_markdown(draft_markdown, "recommendation")

            phase_msg = _emit("phase", phase="lint_validation", message="Validating quality")
            if phase_msg:
                yield phase_msg

            validator = LetterValidationService()
            if settings.letter_quality_lint_enabled and (internal_deadline - time.monotonic()) > finalize_budget:
                quality_report = validator.lint_client_letter(
                    draft_markdown,
                    mode=mode,
                    letter_type="recommendation",
                )

            final_markdown = draft_markdown
            if (
                settings.letter_conditional_repair_enabled
                and settings.letter_quality_lint_enabled
                and not quality_report.get("lint_passed", True)
            ):
                remaining_seconds = internal_deadline - time.monotonic()
                if remaining_seconds >= (repair_budget + finalize_budget):
                    phase_msg = _emit("phase", phase="repair", message="Repairing quality issues")
                    if phase_msg:
                        yield phase_msg
                    metrics["repair_attempted"] = True
                    metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                    repaired = await rec_service.repair_recommendation_letter_constraints(
                        draft_markdown,
                        quality_report.get("violations", []),
                        mode=mode,
                        model="gpt-5-mini",
                    )
                    repaired = _normalize_markdown(repaired, "recommendation")
                    post_report = validator.lint_client_letter(
                        repaired,
                        mode=mode,
                        letter_type="recommendation",
                    )
                    quality_report = {
                        **post_report,
                        "pre_repair": quality_report,
                        "post_repair": post_report,
                    }
                    if repaired.strip() and repaired.strip() != draft_markdown.strip():
                        final_markdown = repaired
                        metrics["repair_applied"] = True
                else:
                    quality_report = {
                        **quality_report,
                        "repair_skipped": "insufficient_budget",
                    }

            phase_msg = _emit("phase", phase="finalizing", message="Finalizing letter")
            if phase_msg:
                yield phase_msg

            final_markdown = _normalize_markdown(final_markdown, "recommendation")
            final_html = rec_service.render_markdown_to_html(
                final_markdown,
                letter_type=letter_type_enum,
                client_name=client_name,
            )
            metrics["lint_passed"] = quality_report.get("lint_passed")
            metrics["lint_score"] = quality_report.get("score")
            metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)

            persisted_result = analysis_data.get("result") or {}
            generated_letters = persisted_result.setdefault("generated_letters", {})
            letter_key = f"recommendation_{letter_type}"
            generated_letters[letter_key] = final_html
            generated_letters[f"{letter_key}_meta"] = {
                "quality_report": quality_report,
                "generation_metrics": metrics,
            }
            supabase.table("analysis_results").update({"result": persisted_result}).eq(
                "id", analysis_id
            ).execute()

            quality_msg = _emit(
                "quality",
                quality_report=quality_report,
                generation_metrics=metrics,
            )
            if quality_msg:
                yield quality_msg

            final_msg = _emit(
                "final",
                content={
                    "format": "html",
                    "html": final_html,
                    "markdown": final_markdown,
                },
                quality_report=quality_report,
                generation_metrics=metrics,
            )
            if final_msg:
                yield final_msg

            done_msg = _emit("done")
            if done_msg:
                yield done_msg
            _emit_generation_metrics(metrics)

        except Exception as stream_err:
            if isinstance(stream_err, TimeoutError):
                metrics["timeout"] = True
                metrics["error_code"] = "timeout"
            else:
                metrics["error_code"] = type(stream_err).__name__
            metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)
            _emit_generation_metrics(metrics)

            error_msg = _emit(
                "error",
                error=str(stream_err),
                code=metrics.get("error_code"),
                recoverable=recoverable_timeout,
            )
            if error_msg:
                yield error_msg

            done_msg = _emit("done")
            if done_msg:
                yield done_msg

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class CalculateDemandAmountRequest(BaseModel):
    """Request to calculate demand amount."""

    case_id: str
    target_party_name: str


class CalculateDemandAmountResponse(BaseModel):
    """Response with calculated demand amount."""

    amount: float
    reasoning: str
    breakdown: List[Dict[str, Any]]


@router.post("/calculate-demand-amount", response_model=CalculateDemandAmountResponse)
async def calculate_demand_amount(
    request: CalculateDemandAmountRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Calculate suggested demand amount based on case analysis and selected party."""
    _ensure_case_access(supabase, request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, request.case_id)

    result_payload = analysis_record["result"]
    processing_result = ProcessingResult(**result_payload)

    if not processing_result.multi_stage_result:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Demand calculation requires the latest analysis. Please re-run the case analysis.",
        )

    # Fetch user's AI preferences
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
    openai_client = OpenAIClient(user_preferences=ai_preferences)

    msr = processing_result.multi_stage_result
    fact_matrix = msr.get("fact_matrix", {})
    deep_analysis = msr.get("deep_analysis", {})

    # Build context for AI calculation
    financial_data = fact_matrix.get("financial_data", [])
    parties = fact_matrix.get("parties", [])
    legal_issues = deep_analysis.get("issue_analyses", [])

    # Filter financial items related to the target party
    party_financial_items = []
    # general_financial_items = []

    for item in financial_data:
        description = item.get("description", "").lower()
        if request.target_party_name.lower() in description:
            party_financial_items.append(item)
        # else:
        #     general_financial_items.append(item)

    # Build AI prompt
    target_party = request.target_party_name
    prompt = f"""Analyze this case data and calculate a reasonable demand amount for: {target_party}

Financial Data:
{json.dumps(financial_data, indent=2)}

Parties Involved:
{json.dumps(parties, indent=2)}

Legal Issues:
{json.dumps(legal_issues, indent=2)}

Instructions:
1. Identify all amounts owed, damages claimed, or contract breaches related to {target_party}
2. Consider the strength of legal claims and potential recovery likelihood
3. Include reasonable attorney fees and costs if applicable
4. Provide a total demand amount that is justified by the evidence

Return a JSON object with:
- amount: float (total demand amount)
- reasoning: string (2-3 sentence explanation)
- breakdown: array of objects with {{description: string, amount: float}}

Be realistic and evidence-based. Only include amounts supported by the case data."""

    try:
        model = openai_client.get_preferred_model("demand_calculation", "gpt-5-mini")
        response = await asyncio.to_thread(
            openai_client.create_response,
            model=model,
            input=prompt,
            instructions="You are a legal analyst calculating demand amounts. Return only valid JSON.",
            reasoning_effort="low",
            verbosity="medium",
            max_output_tokens=1000,
        )

        result = json.loads(response["content"])

        return CalculateDemandAmountResponse(
            amount=result.get("amount", 0.0),
            reasoning=result.get("reasoning", "Unable to calculate demand amount."),
            breakdown=result.get("breakdown", []),
        )
    except Exception as e:
        logger.error(f"Error calculating demand amount: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate demand amount: {str(e)}",
        ) from e


# =============================================================================
# ON-DEMAND GAP ANALYSIS ENDPOINT
# =============================================================================


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


def _build_gap_resolution_hash(request: GapResolutionRefreshRequest) -> str:
    """Build stable hash for resolution payload to avoid unnecessary re-runs."""
    canonical = {
        "resolutions": sorted(
            [
                {
                    "gap_id": r.gap_id,
                    "resolution_text": (r.resolution_text if isinstance(r.resolution_text, str) else "").strip(),
                    "mark_resolved": bool(r.mark_resolved),
                    "related_document_ids": sorted(r.related_document_ids or []),
                }
                for r in request.resolutions
            ],
            key=lambda x: x["gap_id"],
        ),
        "global_resolution_notes": (request.global_resolution_notes if isinstance(request.global_resolution_notes, str) else "").strip(),
        "attached_document_ids": sorted(request.attached_document_ids or []),
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_supporting_document_hash(
    document_rows: List[Dict[str, Any]],
    requested_document_ids: List[str],
) -> str:
    """Build stable hash for supporting document content/state."""
    canonical_docs = []
    for doc in document_rows or []:
        text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        sig = _derive_signature_detection_for_gap_doc(doc)
        sig_status = sig.get("status") if isinstance(sig, dict) else None
        canonical_docs.append(
            {
                "id": doc.get("id"),
                "updated_at": doc.get("updated_at"),
                "text_hash": text_hash,
                "signature_status": sig_status,
            }
        )

    canonical = {
        "requested_document_ids": sorted(set(requested_document_ids or [])),
        "documents": sorted(canonical_docs, key=lambda d: (d.get("id") or "")),
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _derive_signature_detection_for_gap_doc(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Derive signature detection for a document row, with text fallback for text-like docs."""
    doc_metadata = doc.get("metadata") or {}
    if not isinstance(doc_metadata, dict):
        doc_metadata = {}

    sig = doc_metadata.get("signature_detection")
    sig = _apply_signature_verification_override(
        sig if isinstance(sig, dict) else None,
        doc_metadata,
        file_name=doc.get("file_name"),
    )
    if sig:
        return sig

    if not _is_signature_inference_candidate(doc.get("file_name"), doc.get("file_type")):
        return None

    text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
    if not text:
        return _apply_signature_verification_override(
            None,
            doc_metadata,
            file_name=doc.get("file_name"),
        )

    inferred = _infer_signature_detection_from_text(text)
    return _apply_signature_verification_override(
        inferred,
        doc_metadata,
        file_name=doc.get("file_name"),
    )


_GAP_CONTEXT_MAX_DOCS = 50
_GAP_CONTEXT_MAX_CHARS = 200_000


def _fetch_case_documents_for_gap_context(
    supabase,
    case_id: str,
) -> List[Dict[str, Any]]:
    """Fetch case documents used to build signature evidence and cache invalidation hashes.

    Capped at _GAP_CONTEXT_MAX_DOCS rows ordered by most recently updated to prevent
    40MB+ network payloads for large cases. Per-doc text is also capped at
    _GAP_CONTEXT_MAX_CHARS characters as a secondary guard.
    """
    try:
        _fetch_start = __import__("time").time()
        docs_resp = (
            supabase.table("documents")
            .select(
                "id, file_name, file_type, status, updated_at, extracted_text, "
                "manual_text, metadata"
            )
            .eq("case_id", case_id)
            .order("updated_at", desc=True)
            .limit(_GAP_CONTEXT_MAX_DOCS)
            .execute()
        )
        rows = docs_resp.data or []
        _elapsed = __import__("time").time() - _fetch_start
        logger.info(
            f"[GAP:FETCH] case_id={case_id} rows={len(rows)} elapsed={_elapsed:.2f}s "
            f"(limit={_GAP_CONTEXT_MAX_DOCS})"
        )

        # Warn when the case has more documents than we fetched
        # (count is not available without a separate query, so warn whenever we hit the cap)
        if len(rows) == _GAP_CONTEXT_MAX_DOCS:
            logger.warning(
                f"[GAP:TRUNCATED] case_id={case_id} gap context capped at {_GAP_CONTEXT_MAX_DOCS} docs. "
                f"Documents beyond the cap are excluded from gap analysis, letters, and demand calc."
            )

        # Per-doc character cap as secondary guard against individual oversized documents
        for doc in rows:
            for field in ("extracted_text", "manual_text"):
                if doc.get(field) and len(doc[field]) > _GAP_CONTEXT_MAX_CHARS:
                    doc[field] = doc[field][:_GAP_CONTEXT_MAX_CHARS]

        return rows
    except Exception as doc_err:
        logger.warning(f"[GAP] Failed to load case documents for context: {doc_err}")
        return []


def _build_case_document_state_hash(document_rows: List[Dict[str, Any]]) -> str:
    """Build lightweight state hash for document set to avoid stale gap-analysis cache hits."""
    if not document_rows:
        return "no_case_documents"

    canonical_rows: List[Dict[str, Any]] = []
    for doc in document_rows:
        signature_detection = _derive_signature_detection_for_gap_doc(doc)
        signature_status = (
            signature_detection.get("status")
            if isinstance(signature_detection, dict)
            else None
        )
        sampled_text = _sample_text_for_state_hash(
            doc.get("manual_text") or doc.get("extracted_text")
        )
        text_fingerprint = hashlib.sha256(sampled_text.encode("utf-8")).hexdigest()
        canonical_rows.append(
            {
                "id": doc.get("id"),
                "updated_at": doc.get("updated_at"),
                "status": str(doc.get("status") or ""),
                "file_name": doc.get("file_name"),
                "text_fingerprint": text_fingerprint,
                "signature_status": signature_status,
            }
        )

    payload = json.dumps(
        sorted(canonical_rows, key=lambda row: (row.get("id") or "")),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_signature_evidence(
    document_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Create compact signature evidence list for gap-analysis prompt grounding."""
    evidence: List[Dict[str, Any]] = []

    for doc in document_rows:
        signature_detection = _derive_signature_detection_for_gap_doc(doc)
        if not isinstance(signature_detection, dict):
            continue

        combined_text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
        instrument_hints = _extract_signature_instrument_hints(
            file_name=doc.get("file_name"),
            extracted_text=combined_text,
        )
        signer_names = signature_detection.get("signer_names")
        indicators = signature_detection.get("indicators")

        evidence.append(
            {
                "document_id": doc.get("id"),
                "file_name": doc.get("file_name"),
                "status": signature_detection.get("status"),
                "confidence": signature_detection.get("confidence"),
                "has_digital_signature": bool(
                    signature_detection.get("has_digital_signature")
                ),
                "signing_date": signature_detection.get("signing_date"),
                "detection_source": signature_detection.get("detection_source"),
                "signer_names": signer_names if isinstance(signer_names, list) else [],
                "indicators": indicators if isinstance(indicators, list) else [],
                "instrument_hints": instrument_hints,
            }
        )

    return sorted(evidence, key=lambda row: (row.get("file_name") or "").lower())


def _build_document_registry_for_gap_context(
    document_rows: List[Dict[str, Any]],
    result_payload: Dict[str, Any],
    fact_matrix: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Build authoritative document registry rows from current DB document state."""
    try:
        from legal_portal.core.data_models import (
            DocumentType,
            FactMatrix,
            FileMetadata,
            FileType,
            ProcessedDocument,
        )
        from legal_portal.services.document_registry_service import DocumentRegistryService

        summaries = _parse_gap_document_summaries(result_payload)
        processed_docs: List[ProcessedDocument] = []

        def _coerce_file_type(raw: Any, file_name: str) -> FileType:
            text = str(raw or "").lower().strip()
            if text in {"application/pdf", "pdf"} or (file_name or "").lower().endswith(".pdf"):
                return FileType.PDF
            if "wordprocessingml.document" in text or (file_name or "").lower().endswith(".docx"):
                return FileType.DOCX
            if text == "application/msword" or (file_name or "").lower().endswith(".doc"):
                return FileType.DOC
            if text in {"text/plain", "txt"} or (file_name or "").lower().endswith(".txt"):
                return FileType.TXT
            if text in {"text/csv", "csv"} or (file_name or "").lower().endswith(".csv"):
                return FileType.CSV
            if text in {"message/rfc822", "eml"} or (file_name or "").lower().endswith(".eml"):
                return FileType.EML
            if text.startswith("image/"):
                if text == "image/png":
                    return FileType.PNG
                if text in {"image/jpeg", "image/jpg"}:
                    return FileType.JPG
                return FileType.IMAGE
            return FileType.PDF

        for doc in document_rows or []:
            file_name = str(doc.get("file_name") or "").strip()
            text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
            if not file_name or not text:
                continue

            doc_type = (
                DocumentType.INTAKE_FORM
                if bool((doc.get("metadata") or {}).get("is_intake_form"))
                else DocumentType.CASE_DOCUMENT
            )
            file_type = _coerce_file_type(doc.get("file_type"), file_name)
            metadata = FileMetadata(file_name=file_name, file_type=file_type, file_size=0)
            signature_detection = _derive_signature_detection_for_gap_doc(doc)

            processed_docs.append(
                ProcessedDocument(
                    file_name=file_name,
                    content=text,
                    document_type=doc_type,
                    file_type=file_type,
                    metadata=metadata,
                    document_id=doc.get("id"),
                    extraction_quality="high",
                    extraction_method="db",
                    signature_detection=signature_detection,
                )
            )

        fact_matrix_model = None
        if isinstance(fact_matrix, FactMatrix):
            fact_matrix_model = fact_matrix
        elif isinstance(fact_matrix, dict):
            fact_matrix_model = FactMatrix(**fact_matrix)

        registry_service = DocumentRegistryService()
        return registry_service.build_registry(
            processed_documents=processed_docs,
            document_summaries=summaries,
            fact_matrix=fact_matrix_model,
        )
    except Exception as registry_err:
        logger.warning("[GAP] Failed to build document registry context: %s", registry_err)
        return []


def _hash_jsonable(value: Any) -> str:
    """Compute deterministic hash for JSON-serializable payloads."""
    serialized = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_gap_analysis_input_hash(
    analysis_id: str,
    result_payload: Dict[str, Any],
    case_document_state_hash: str,
) -> str:
    """Build stable hash representing inputs that materially affect gap-analysis output."""
    document_summaries_raw = result_payload.get("document_summaries", [])
    if isinstance(document_summaries_raw, str):
        document_summaries_hash = hashlib.sha256(
            document_summaries_raw.encode("utf-8")
        ).hexdigest()
    else:
        document_summaries_hash = _hash_jsonable(document_summaries_raw)

    multi_stage = result_payload.get("multi_stage_result") or {}
    canonical = {
        "analysis_id": analysis_id,
        "analysis_logic_version": _GAP_ANALYSIS_INPUT_SCHEMA_VERSION,
        "fact_matrix_hash": _hash_jsonable(multi_stage.get("fact_matrix", {})),
        "issue_map_hash": _hash_jsonable(multi_stage.get("issue_map", {})),
        "deep_analysis_hash": _hash_jsonable(multi_stage.get("deep_analysis", {})),
        "document_summaries_hash": document_summaries_hash,
        "case_document_state_hash": case_document_state_hash,
    }
    return _hash_jsonable(canonical)


async def _ensure_fresh_gap_analysis_for_letter_generation(
    *,
    supabase,
    analysis_record: Dict[str, Any],
    user_id: str,
) -> None:
    """Refresh cached gap analysis when case documents changed since it was computed."""
    result_payload = analysis_record.get("result") or {}
    multi_stage_result = result_payload.get("multi_stage_result") or {}
    existing_gap_dict = multi_stage_result.get("gap_analysis")
    if not existing_gap_dict:
        return

    analysis_id = analysis_record.get("id")
    case_id = analysis_record.get("case_id")
    if not analysis_id or not case_id:
        return

    case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
    case_document_state_hash = _build_case_document_state_hash(case_document_rows)
    gap_input_hash = _build_gap_analysis_input_hash(
        analysis_id=analysis_id,
        result_payload=result_payload,
        case_document_state_hash=case_document_state_hash,
    )
    existing_gap_state = result_payload.get("gap_analysis_state") or {}
    if existing_gap_state.get("input_hash") == gap_input_hash:
        return

    logger.info(
        "[LETTER] Refreshing stale gap analysis before letter generation for case %s",
        case_id,
    )

    try:
        from legal_portal.core.data_models import DeepAnalysis, FactMatrix, LegalIssueMap
        from legal_portal.services.gap_analysis_service import GapAnalysisService

        fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
        issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
        deep_analysis_data = multi_stage_result.get("deep_analysis", {})
        deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None
        if not deep_analysis:
            logger.warning(
                "[LETTER] Cannot refresh stale gap analysis for case %s: deep analysis missing",
                case_id,
            )
            return

        doc_summaries_list = _parse_gap_document_summaries(result_payload)
        intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
        signature_evidence = _build_signature_evidence(case_document_rows)
        document_registry = _build_document_registry_for_gap_context(
            document_rows=case_document_rows,
            result_payload=result_payload,
            fact_matrix=fact_matrix,
        )

        ai_preferences = await _get_user_ai_preferences(user_id, supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        gap_service = GapAnalysisService(openai_client=openai_client)

        gap_result = await gap_service.analyze_gaps(
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            document_summaries=doc_summaries_list,
            intake_content=intake_content,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
        )

        gap_dict = gap_result.model_dump(mode="json")
        multi_stage_result["gap_analysis"] = gap_dict
        multi_stage_result["document_registry"] = document_registry
        result_payload["multi_stage_result"] = multi_stage_result
        result_payload["gap_analysis_state"] = {
            "input_hash": gap_input_hash,
            "case_document_state_hash": case_document_state_hash,
            "signature_record_count": len(signature_evidence),
            "signed_document_count": sum(
                1
                for row in signature_evidence
                if (row.get("status") or "").lower() == "signed"
            ),
            "updated_at": datetime.utcnow().isoformat(),
        }

        supabase.table("analysis_results").update({"result": result_payload}).eq(
            "id", analysis_id
        ).execute()
        analysis_record["result"] = result_payload
        logger.info(
            "[LETTER] Refreshed gap analysis for case %s (score=%.1f, total_gaps=%s)",
            case_id,
            gap_result.overall_completeness_score,
            gap_result.total_gaps,
        )
    except Exception as refresh_err:
        logger.warning(
            "[LETTER] Failed to refresh stale gap analysis for case %s: %s",
            case_id,
            refresh_err,
            exc_info=True,
        )


def _compute_resolution_document_state_hash(
    supabase,
    case_id: str,
    attached_document_ids: List[str],
) -> str:
    """Compute a state hash for supporting docs used in selective gap refresh caching."""
    doc_ids = sorted(set(attached_document_ids or []))
    if not doc_ids:
        return "no_supporting_documents"

    try:
        docs_resp = (
            supabase.table("documents")
            .select("id, updated_at, extracted_text, manual_text, metadata")
            .eq("case_id", case_id)
            .in_("id", doc_ids)
            .execute()
        )
        rows = docs_resp.data or []
        return _build_supporting_document_hash(rows, doc_ids)
    except Exception as doc_err:
        logger.warning(f"[GAP_RESOLVE] Failed to hash supporting docs: {doc_err}")
        # Fallback to requested IDs only so cache still behaves deterministically.
        fallback = json.dumps({"requested_document_ids": doc_ids}, sort_keys=True)
        return f"fallback:{hashlib.sha256(fallback.encode('utf-8')).hexdigest()}"


def _parse_gap_document_summaries(result_payload: Dict[str, Any]):
    """Parse and validate document summaries for gap analysis."""
    from legal_portal.core.data_models import DocumentSummaryStructured

    doc_summaries_raw = result_payload.get("document_summaries", [])
    doc_summaries_array = []

    if isinstance(doc_summaries_raw, str):
        try:
            doc_summaries_array = json.loads(doc_summaries_raw)
            logger.info(
                f"[GAP] Parsed {len(doc_summaries_array)} document summaries from JSON string"
            )
        except json.JSONDecodeError as json_err:
            logger.warning(f"[GAP] Could not parse document_summaries JSON: {json_err}")
    elif isinstance(doc_summaries_raw, list):
        doc_summaries_array = doc_summaries_raw

    doc_summaries_list = []
    for doc_sum in doc_summaries_array:
        try:
            if isinstance(doc_sum, dict):
                doc_summaries_list.append(DocumentSummaryStructured(**doc_sum))
            elif hasattr(doc_sum, "model_dump"):
                doc_summaries_list.append(doc_sum)
            else:
                logger.warning(f"[GAP] Unexpected doc summary type: {type(doc_sum)}")
        except Exception as doc_err:
            logger.warning(f"[GAP] Could not convert doc summary: {doc_err}")

    return doc_summaries_list


def _fetch_gap_intake_content(supabase, case_id: str, result_payload: Dict[str, Any]) -> Optional[str]:
    """Fetch intake content for gap analysis, with fallback to streaming summary."""
    try:
        intake_response = supabase.table("intakes").select("content").eq("case_id", case_id).limit(1).execute()
        return intake_response.data[0]["content"] if intake_response.data else None
    except Exception as intake_err:
        logger.warning(f"[GAP] Could not fetch intake content: {intake_err}")
        return result_payload.get("streaming_analysis", "")[:5000]


def _collect_resolution_documents(
    supabase,
    case_id: str,
    attached_document_ids: List[str],
) -> List[Dict[str, Any]]:
    """Fetch selected documents to enrich resolution context."""
    if not attached_document_ids:
        return []

    try:
        docs_resp = (
            supabase.table("documents")
            .select("id, file_name, file_type, extracted_text, manual_text, metadata")
            .eq("case_id", case_id)
            .in_("id", attached_document_ids)
            .execute()
        )
        docs = docs_resp.data or []
    except Exception as doc_err:
        logger.warning(f"[GAP_RESOLVE] Failed to load attached docs: {doc_err}")
        return []

    condensed_docs = []
    for doc in docs:
        text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
        if len(text) > 2200:
            text = text[:1200] + "\n... [excerpt omitted] ...\n" + text[-800:]

        sig = _derive_signature_detection_for_gap_doc(doc)
        condensed_docs.append(
            {
                "id": doc.get("id"),
                "file_name": doc.get("file_name"),
                "signature_detection": sig,
                "text_excerpt": text,
            }
        )

    return condensed_docs


def _build_resolution_context(
    existing_gap: Dict[str, Any],
    request: GapResolutionRefreshRequest,
    supporting_docs: List[Dict[str, Any]],
) -> str:
    """Create compact, structured context for selective gap re-analysis."""
    lines = []
    lines.append("USER GAP RESOLUTIONS")
    lines.append(f"Total user resolutions: {len(request.resolutions)}")
    if request.global_resolution_notes and isinstance(request.global_resolution_notes, str):
        lines.append("Global notes:")
        lines.append(request.global_resolution_notes.strip())

    gap_lookup = {}
    for gaps in (existing_gap or {}).get("gaps_by_category", {}).values():
        for gap in gaps:
            if isinstance(gap, dict) and gap.get("gap_id"):
                gap_lookup[gap["gap_id"]] = gap

    for idx, resolution in enumerate(request.resolutions, start=1):
        original_gap = gap_lookup.get(resolution.gap_id, {})
        lines.append("")
        lines.append(f"Resolution {idx}:")
        lines.append(f"- gap_id: {resolution.gap_id}")
        lines.append(f"- user_mark_resolved: {resolution.mark_resolved}")
        if original_gap:
            lines.append(f"- original_title: {original_gap.get('title', '')}")
            lines.append(f"- original_severity: {original_gap.get('severity', '')}")
            lines.append(f"- original_category: {original_gap.get('category', '')}")
        if resolution.related_document_ids:
            lines.append(f"- related_document_ids: {', '.join(resolution.related_document_ids)}")
        lines.append("- resolution_text:")
        res_text = resolution.resolution_text if isinstance(resolution.resolution_text, str) else ""
        lines.append(res_text.strip())

    if supporting_docs:
        lines.append("")
        lines.append("ATTACHED SUPPORTING DOCUMENT EXCERPTS")
        for doc in supporting_docs[:8]:
            lines.append(f"- {doc.get('file_name')} (id={doc.get('id')})")
            if doc.get("signature_detection"):
                lines.append(f"  signature_detection={doc.get('signature_detection')}")
            if doc.get("text_excerpt"):
                lines.append(f"  excerpt={doc.get('text_excerpt')}")

    return "\n".join(lines).strip()


@router.post("/analyze-gaps")
@limiter.limit("5/minute")  # Rate limit gap analysis
async def analyze_gaps_on_demand(
    gap_request: GapAnalysisRequest,
    request: Request,  # Required for rate limiter
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Run gap analysis on-demand for a completed case analysis.

    This endpoint analyzes the case for:
    - Missing documents
    - Factual contradictions
    - Timeline gaps
    - Unverifiable claims

    Returns GapAnalysisResult and saves to database for future retrieval.
    """
    case_id = gap_request.case_id
    logger.info(f"[GAP_ENDPOINT] Starting on-demand gap analysis for case {case_id}")

    # Verify access
    _ensure_case_access(supabase, case_id, user["id"])

    # Fetch existing analysis
    analysis_record = _fetch_latest_analysis_result(supabase, case_id)
    result_payload = analysis_record["result"]
    analysis_id = analysis_record["id"]

    # Check for multi_stage_result
    multi_stage_result = result_payload.get("multi_stage_result")
    if not multi_stage_result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Gap analysis requires a completed multi-stage analysis. Please run case analysis first.",
        )

    case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
    case_document_state_hash = _build_case_document_state_hash(case_document_rows)
    signature_evidence = _build_signature_evidence(case_document_rows)
    gap_input_hash = _build_gap_analysis_input_hash(
        analysis_id=analysis_id,
        result_payload=result_payload,
        case_document_state_hash=case_document_state_hash,
    )

    # Check if gap analysis already exists
    existing_gap = multi_stage_result.get("gap_analysis")
    existing_gap_state = result_payload.get("gap_analysis_state") or {}
    if existing_gap and not gap_request.force_refresh:
        if existing_gap_state.get("input_hash") == gap_input_hash:
            logger.info(f"[GAP_ENDPOINT] Returning cached gap analysis for case {case_id}")
            return existing_gap
        logger.info(
            "[GAP_ENDPOINT] Cached gap analysis invalidated for case %s (state mismatch)",
            case_id,
        )

    try:
        # Import gap analysis dependencies
        from legal_portal.core.data_models import (
            DeepAnalysis,
            FactMatrix,
            LegalIssueMap,
        )
        from legal_portal.services.gap_analysis_service import GapAnalysisService

        # Fetch user's AI preferences
        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        gap_service = GapAnalysisService(openai_client=openai_client)

        # Convert multi_stage_result dicts to Pydantic models
        fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
        issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
        deep_analysis_data = multi_stage_result.get("deep_analysis", {})
        deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None

        if not deep_analysis:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Gap analysis requires deep analysis data. Please re-run case analysis.",
            )

        # Convert document summaries (stored as JSON string)
        doc_summaries_list = _parse_gap_document_summaries(result_payload)

        # Fetch intake content
        intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
        document_registry = _build_document_registry_for_gap_context(
            document_rows=case_document_rows,
            result_payload=result_payload,
            fact_matrix=fact_matrix,
        )

        logger.info(f"[GAP_ENDPOINT] Running gap analysis with {len(doc_summaries_list)} documents")

        # Run gap analysis (no timeout - let it complete)
        gap_result = await gap_service.analyze_gaps(
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            document_summaries=doc_summaries_list,
            intake_content=intake_content,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
        )

        logger.info(f"[GAP_ENDPOINT] Gap analysis complete: {gap_result.total_gaps} gaps found")

        # Save gap analysis to database
        gap_dict = gap_result.model_dump(mode="json")
        multi_stage_result["gap_analysis"] = gap_dict
        multi_stage_result["document_registry"] = document_registry
        result_payload["multi_stage_result"] = multi_stage_result
        result_payload["gap_analysis_state"] = {
            "input_hash": gap_input_hash,
            "case_document_state_hash": case_document_state_hash,
            "signature_record_count": len(signature_evidence),
            "signed_document_count": sum(
                1
                for row in signature_evidence
                if (row.get("status") or "").lower() == "signed"
            ),
            "updated_at": datetime.utcnow().isoformat(),
        }

        service_supabase.table("analysis_results").update({
            "result": result_payload,
        }).eq("id", analysis_id).execute()

        logger.info(f"[GAP_ENDPOINT] Gap analysis saved for case {case_id}")

        return gap_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GAP_ENDPOINT] Gap analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gap analysis failed: {str(e)}",
        ) from e


@router.post("/analyze-gaps/resolve")
@limiter.limit("10/minute")
async def resolve_gaps_and_refresh(
    resolution_request: GapResolutionRefreshRequest,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Apply user-provided gap resolutions and refresh gap analysis selectively.

    This avoids full case re-analysis by only re-running the gap stage with:
    - Existing fact matrix / issue map / deep analysis
    - Existing gap list
    - User-entered resolutions and optional supporting docs
    """
    case_id = resolution_request.case_id
    logger.info(f"[GAP_RESOLVE] Starting selective gap refresh for case {case_id}")

    _ensure_case_access(supabase, case_id, user["id"])

    analysis_record = _fetch_latest_analysis_result(supabase, case_id)
    result_payload = analysis_record["result"]
    analysis_id = analysis_record["id"]

    multi_stage_result = result_payload.get("multi_stage_result")
    if not multi_stage_result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Gap resolution requires a completed multi-stage analysis. Please run case analysis first.",
        )

    existing_gap_dict = multi_stage_result.get("gap_analysis")
    if not existing_gap_dict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No existing gap analysis found. Run gap analysis first.",
        )

    resolution_hash = _build_gap_resolution_hash(resolution_request)
    prior_resolution_state = result_payload.get("gap_resolution_state") or {}

    all_doc_ids = set(resolution_request.attached_document_ids or [])
    for item in resolution_request.resolutions:
        all_doc_ids.update(item.related_document_ids or [])
    all_doc_ids_list = sorted(all_doc_ids)

    case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
    case_document_state_hash = _build_case_document_state_hash(case_document_rows)

    supporting_doc_hash = _compute_resolution_document_state_hash(
        supabase=supabase,
        case_id=case_id,
        attached_document_ids=all_doc_ids_list,
    )
    if (
        not resolution_request.force_refresh
        and prior_resolution_state.get("resolution_hash") == resolution_hash
        and prior_resolution_state.get("supporting_doc_hash") == supporting_doc_hash
        and prior_resolution_state.get("case_document_state_hash") == case_document_state_hash
        and existing_gap_dict
    ):
        logger.info(f"[GAP_RESOLVE] Returning cached selective refresh for case {case_id}")
        return {
            "gap_analysis": existing_gap_dict,
            "cache_hit": True,
            "resolution_state": prior_resolution_state,
        }

    try:
        from legal_portal.core.data_models import (
            DeepAnalysis,
            FactMatrix,
            GapAnalysisResult,
            LegalIssueMap,
        )
        from legal_portal.services.gap_analysis_service import GapAnalysisService

        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        gap_service = GapAnalysisService(openai_client=openai_client)

        signature_evidence = _build_signature_evidence(case_document_rows)

        fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
        issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
        deep_analysis_data = multi_stage_result.get("deep_analysis", {})
        deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None

        if not deep_analysis:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Gap resolution requires deep analysis data. Please re-run case analysis.",
            )

        doc_summaries_list = _parse_gap_document_summaries(result_payload)
        intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
        existing_gap_model = GapAnalysisResult(**existing_gap_dict)
        document_registry = _build_document_registry_for_gap_context(
            document_rows=case_document_rows,
            result_payload=result_payload,
            fact_matrix=fact_matrix,
        )

        supporting_docs = _collect_resolution_documents(
            supabase=supabase,
            case_id=case_id,
            attached_document_ids=all_doc_ids_list,
        )
        resolution_context = _build_resolution_context(
            existing_gap=existing_gap_dict,
            request=resolution_request,
            supporting_docs=supporting_docs,
        )

        logger.info(
            f"[GAP_RESOLVE] Re-running gap stage with "
            f"resolutions={len(resolution_request.resolutions)} "
            f"supporting_docs={len(supporting_docs)}"
        )

        gap_result = await gap_service.analyze_gaps(
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            document_summaries=doc_summaries_list,
            intake_content=intake_content,
            resolution_context=resolution_context,
            prior_gap_analysis=existing_gap_model,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
        )

        gap_dict = gap_result.model_dump(mode="json")
        multi_stage_result["gap_analysis"] = gap_dict
        multi_stage_result["document_registry"] = document_registry
        result_payload["multi_stage_result"] = multi_stage_result

        resolution_state = {
            "resolution_hash": resolution_hash,
            "updated_at": datetime.utcnow().isoformat(),
            "applied_resolution_count": len(resolution_request.resolutions),
            "applied_gap_ids": [r.gap_id for r in resolution_request.resolutions],
            "attached_document_ids": all_doc_ids_list,
            "supporting_doc_hash": supporting_doc_hash,
            "case_document_state_hash": case_document_state_hash,
            "signature_record_count": len(signature_evidence),
            "signed_document_count": sum(
                1
                for row in signature_evidence
                if (row.get("status") or "").lower() == "signed"
            ),
            "global_resolution_notes": (resolution_request.global_resolution_notes if isinstance(resolution_request.global_resolution_notes, str) else "").strip(),
        }
        result_payload["gap_resolution_state"] = resolution_state

        service_supabase.table("analysis_results").update({
            "result": result_payload,
        }).eq("id", analysis_id).execute()

        logger.info(
            f"[GAP_RESOLVE] Selective gap refresh complete for case {case_id} | "
            f"total_gaps={gap_result.total_gaps} score={gap_result.overall_completeness_score:.1f}"
        )

        return {
            "gap_analysis": gap_dict,
            "cache_hit": False,
            "resolution_state": resolution_state,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GAP_RESOLVE] Selective gap refresh failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Selective gap refresh failed: {str(e)}",
        ) from e


@router.post("/analyze-gaps/stream")
@limiter.limit("5/minute")
async def analyze_gaps_streaming(
    gap_request: GapAnalysisRequest,
    request: Request,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Run gap analysis on-demand with streaming progress updates.

    Returns a streaming response with progress events and final result.
    Event types:
    - phase: Progress update (preparing, analyzing, saving)
    - result: Final gap analysis result
    - error: Error occurred
    """
    case_id = gap_request.case_id
    logger.info(f"[GAP_STREAM] Starting streaming gap analysis for case {case_id}")

    # Verify access first (non-streaming to fail fast)
    _ensure_case_access(supabase, case_id, user["id"])

    async def generate():
        import time
        start_time = time.time()

        try:
            # Phase 1: Preparing
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'preparing', 'message': 'Loading case data...', 'elapsed': 0})}\n\n"

            # Fetch existing analysis
            analysis_record = _fetch_latest_analysis_result(supabase, case_id)
            result_payload = analysis_record["result"]
            analysis_id = analysis_record["id"]

            # Check for multi_stage_result
            multi_stage_result = result_payload.get("multi_stage_result")
            if not multi_stage_result:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Gap analysis requires a completed multi-stage analysis. Please run case analysis first.'})}\n\n"
                return

            case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
            case_document_state_hash = _build_case_document_state_hash(case_document_rows)
            signature_evidence = _build_signature_evidence(case_document_rows)
            gap_input_hash = _build_gap_analysis_input_hash(
                analysis_id=analysis_id,
                result_payload=result_payload,
                case_document_state_hash=case_document_state_hash,
            )

            # Check if gap analysis already exists
            existing_gap = multi_stage_result.get("gap_analysis")
            existing_gap_state = result_payload.get("gap_analysis_state") or {}
            if existing_gap and not gap_request.force_refresh:
                if existing_gap_state.get("input_hash") == gap_input_hash:
                    logger.info(f"[GAP_STREAM] Returning cached gap analysis for case {case_id}")
                    yield f"data: {json.dumps({'type': 'phase', 'phase': 'cached', 'message': 'Using cached analysis', 'elapsed': time.time() - start_time})}\n\n"
                    yield f"data: {json.dumps({'type': 'result', 'data': existing_gap})}\n\n"
                    return
                logger.info(
                    "[GAP_STREAM] Cached gap analysis invalidated for case %s (state mismatch)",
                    case_id,
                )

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'preparing', 'message': 'Converting documents...', 'elapsed': time.time() - start_time})}\n\n"

            # Import gap analysis dependencies
            from legal_portal.core.data_models import (
                DeepAnalysis,
                FactMatrix,
                LegalIssueMap,
            )
            from legal_portal.services.gap_analysis_service import GapAnalysisService

            # Fetch user's AI preferences
            ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
            openai_client = OpenAIClient(user_preferences=ai_preferences)
            gap_service = GapAnalysisService(openai_client=openai_client)

            # Convert multi_stage_result dicts to Pydantic models
            fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
            issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
            deep_analysis_data = multi_stage_result.get("deep_analysis", {})
            deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None

            if not deep_analysis:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Gap analysis requires deep analysis data. Please re-run case analysis.'})}\n\n"
                return

            # Convert document summaries (stored as JSON string)
            doc_summaries_list = _parse_gap_document_summaries(result_payload)

            # Fetch intake content
            intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
            document_registry = _build_document_registry_for_gap_context(
                document_rows=case_document_rows,
                result_payload=result_payload,
                fact_matrix=fact_matrix,
            )

            # Phase 2: Analyzing
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'analyzing', 'message': 'AI is analyzing case for gaps...', 'elapsed': time.time() - start_time, 'doc_count': len(doc_summaries_list)})}\n\n"

            logger.info(f"[GAP_STREAM] Running gap analysis with {len(doc_summaries_list)} documents")

            # Run gap analysis
            gap_result = await gap_service.analyze_gaps(
                fact_matrix=fact_matrix,
                issue_map=issue_map,
                deep_analysis=deep_analysis,
                document_summaries=doc_summaries_list,
                intake_content=intake_content,
                signature_evidence=signature_evidence,
                document_registry=document_registry,
            )

            logger.info(f"[GAP_STREAM] Gap analysis complete: {gap_result.total_gaps} gaps found")

            # Phase 3: Saving
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'saving', 'message': 'Saving results...', 'elapsed': time.time() - start_time, 'gaps_found': gap_result.total_gaps})}\n\n"

            # Save gap analysis to database
            gap_dict = gap_result.model_dump(mode="json")
            multi_stage_result["gap_analysis"] = gap_dict
            multi_stage_result["document_registry"] = document_registry
            result_payload["multi_stage_result"] = multi_stage_result
            result_payload["gap_analysis_state"] = {
                "input_hash": gap_input_hash,
                "case_document_state_hash": case_document_state_hash,
                "signature_record_count": len(signature_evidence),
                "signed_document_count": sum(
                    1
                    for row in signature_evidence
                    if (row.get("status") or "").lower() == "signed"
                ),
                "updated_at": datetime.utcnow().isoformat(),
            }

            service_supabase.table("analysis_results").update({
                "result": result_payload,
            }).eq("id", analysis_id).execute()

            logger.info(f"[GAP_STREAM] Gap analysis saved for case {case_id}")

            # Final result
            yield f"data: {json.dumps({'type': 'result', 'data': gap_dict, 'elapsed': time.time() - start_time})}\n\n"

        except Exception as e:
            logger.error(f"[GAP_STREAM] Gap analysis failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=ChatMessageResponse)
async def case_chat(
    request: ChatMessageRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Chat about a case with the AI assistant."""
    if not request.case_id:
        raise HTTPException(status_code=400, detail="case_id is required for this endpoint")
    _ensure_case_access(supabase, request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, request.case_id)

    result_payload = analysis_record["result"]
    processing_result = ProcessingResult(**result_payload)

    if not processing_result.multi_stage_result:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Case chat requires the latest analysis. Please re-run the case analysis.",
        )

    history_response = (
        supabase.table("case_chat_messages")
        .select("user_message, ai_response")
        .eq("case_id", request.case_id)
        .order("created_at", desc=False)
        .limit(10)
        .execute()
    )

    conversation_history: List[Dict[str, str]] = []
    if history_response.data:
        for row in history_response.data:
            conversation_history.append({"role": "user", "content": row["user_message"]})
            conversation_history.append({"role": "assistant", "content": row["ai_response"]})

    # Fetch user's AI preferences
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
    openai_client = OpenAIClient(user_preferences=ai_preferences)

    # Extract jurisdiction from artifacts
    artifacts = processing_result.artifacts or {}
    jurisdiction = artifacts.get("jurisdiction", "Florida")

    chat_service = CaseChatService(openai_client, jurisdiction=jurisdiction)
    ai_response = await chat_service.send_message(
        user_message=request.message,
        analysis_result=processing_result,
        conversation_history=conversation_history,
    )

    supabase.table("case_chat_messages").insert(
        {
            "case_id": request.case_id,
            "user_message": request.message,
            "ai_response": ai_response,
            "context_used": processing_result.multi_stage_result or {},
        }
    ).execute()

    return ChatMessageResponse(response=ai_response, context_used={})


# =============================================================================
# CHUNKED PROCESSING & RECOVERY ENDPOINTS
# =============================================================================


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


@router.get("/{analysis_id}/documents", response_model=DocumentStatusResponse)
async def get_document_status(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get detailed status of all documents in an analysis."""
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state = analysis.get("chunk_state") or {}
    documents = chunk_state.get("documents", {})

    # Calculate summary
    statuses = [info.get("status", "pending") for info in documents.values()]

    summary = {
        "total": len(documents),
        "pending": statuses.count("pending"),
        "processing": statuses.count("processing"),
        "completed": statuses.count("completed"),
        "failed": statuses.count("failed"),
        "skipped": statuses.count("skipped"),
    }

    can_proceed = summary["pending"] == 0 and summary["processing"] == 0 and summary["failed"] == 0

    return DocumentStatusResponse(
        **summary,
        documents=documents,
        can_proceed=can_proceed
    )


@router.post("/{analysis_id}/retry", response_model=RecoveryActionResponse)
async def retry_failed_documents(
    analysis_id: str,
    request: RetryDocumentsRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Retry processing of failed documents.
    
    If document_ids is empty, all failed documents will be retried.
    """
    from legal_portal.services.chunk_state_manager import ChunkStateManager

    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state_mgr = ChunkStateManager(supabase, analysis_id)

    # Get failed documents
    failed_docs = await chunk_state_mgr.get_failed_documents()

    if not failed_docs:
        return RecoveryActionResponse(
            success=True,
            action="retry",
            affected_count=0,
            message="No failed documents to retry"
        )

    # Determine which docs to retry
    if request.document_ids:
        doc_ids_to_retry = [d for d in request.document_ids if d in [f["id"] for f in failed_docs]]
    else:
        doc_ids_to_retry = [f["id"] for f in failed_docs]

    if not doc_ids_to_retry:
        return RecoveryActionResponse(
            success=False,
            action="retry",
            affected_count=0,
            message="No matching failed documents found"
        )

    # Reset documents to pending
    count = await chunk_state_mgr.reset_documents_for_retry(doc_ids_to_retry)

    # Update analysis status to allow re-processing
    supabase.table("analysis_results").update({
        "status": "pending"
    }).eq("id", analysis_id).execute()

    logger.info(f"[RETRY] Reset {count} documents for retry in analysis {analysis_id}")

    return RecoveryActionResponse(
        success=True,
        action="retry",
        affected_count=count,
        message=f"Reset {count} documents for retry. Re-run analysis to process them."
    )


@router.post("/{analysis_id}/skip", response_model=RecoveryActionResponse)
async def skip_failed_documents(
    analysis_id: str,
    request: SkipDocumentsRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Skip failed documents and continue with synthesis.
    
    If document_ids is empty, all failed documents will be skipped.
    """
    from legal_portal.services.chunk_state_manager import ChunkStateManager

    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state_mgr = ChunkStateManager(supabase, analysis_id)

    # Get failed documents
    failed_docs = await chunk_state_mgr.get_failed_documents()

    if not failed_docs:
        return RecoveryActionResponse(
            success=True,
            action="skip",
            affected_count=0,
            message="No failed documents to skip"
        )

    # Determine which docs to skip
    if request.document_ids:
        doc_ids_to_skip = [d for d in request.document_ids if d in [f["id"] for f in failed_docs]]
    else:
        doc_ids_to_skip = [f["id"] for f in failed_docs]

    if not doc_ids_to_skip:
        return RecoveryActionResponse(
            success=False,
            action="skip",
            affected_count=0,
            message="No matching failed documents found"
        )

    # Mark documents as skipped
    count = await chunk_state_mgr.mark_documents_skipped(doc_ids_to_skip)

    logger.info(f"[SKIP] Skipped {count} documents in analysis {analysis_id}")

    # Check if we can now proceed to synthesis
    can_proceed = await chunk_state_mgr.can_proceed_to_synthesis()

    message = f"Skipped {count} documents."
    if can_proceed:
        message += " Analysis can now proceed to synthesis."

    return RecoveryActionResponse(
        success=True,
        action="skip",
        affected_count=count,
        message=message
    )


@router.get("/{analysis_id}/state")
async def get_analysis_state(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get full analysis state for recovery/resume.
    
    Returns chunk_state with all document statuses, chunk plan, and summaries.
    """
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, status, chunk_state, created_at, updated_at"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state = analysis.get("chunk_state") or {}

    # Add computed fields
    documents = chunk_state.get("documents", {})
    statuses = [info.get("status", "pending") for info in documents.values()]

    return {
        "analysis_id": analysis_id,
        "status": analysis.get("status"),
        "phase": chunk_state.get("phase", "unknown"),
        "current_chunk": chunk_state.get("current_chunk", 0),
        "total_chunks": len(chunk_state.get("chunks", [])),
        "summary": {
            "total": len(documents),
            "pending": statuses.count("pending"),
            "processing": statuses.count("processing"),
            "completed": statuses.count("completed"),
            "failed": statuses.count("failed"),
            "skipped": statuses.count("skipped"),
        },
        "can_proceed": (
            statuses.count("pending") == 0 and
            statuses.count("processing") == 0 and
            statuses.count("failed") == 0
        ),
        "chunk_state": chunk_state,
        "created_at": analysis.get("created_at"),
        "updated_at": analysis.get("updated_at"),
    }


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
