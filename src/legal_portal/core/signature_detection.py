"""Signature detection constants and pure-logic helpers.

Extracted from api/routes/_analysis_helpers.py so that service-layer modules
can import these symbols without depending on the route layer.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

__all__ = [
    "_SIGNATURE_TEXT_FALLBACK_PATTERNS",
    "_TEXT_SIGNING_DATE_PATTERNS",
    "_SIGNER_NAME_PATTERNS",
    "_SIGNATURE_INSTRUMENT_HINT_PATTERNS",
    "_SIGNATURE_VERIFICATION_STATUS_ALIASES",
    "_normalize_signature_verification_status",
    "_extract_signature_verification",
    "_apply_signature_verification_override",
    "_normalize_text_signing_date",
    "_infer_signature_detection_from_text",
    "_is_pdf_like_document",
    "_is_signature_inference_candidate",
    "_sample_text_for_state_hash",
    "_extract_signature_instrument_hints",
]

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
