"""Document triage: classify documents into processing tiers before summarization.

Triage uses already-available metadata (filename, type label, text length, file type)
to route documents through tiered processing depth. No LLM calls are made during triage.

Tiers:
    T1_FULL: Full batch summarization (contracts, filings, intake, investment docs)
    T2_LIGHT: Light summarization with shorter output (correspondence, notes, financials)
    T3_METADATA: Register entry from metadata only — no LLM call (photos, staff notes)
    T4_SKIP: Excluded entirely (boilerplate instructions, zero-text non-images)
"""

from __future__ import annotations

import re
from enum import IntEnum
from typing import Any, Dict, List

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

__all__ = [
    "TriageTier",
    "TriageResult",
    "triage_documents",
    "triage_document",
]


# ---------------------------------------------------------------------------
# Tier definition (IntEnum for easy comparison: lower = deeper processing)
# ---------------------------------------------------------------------------


class TriageTier(IntEnum):
    """Processing depth tier assigned to each document during triage."""

    T1_FULL = 1       # Full batch summarization
    T2_LIGHT = 2      # Light summarization (200-token output)
    T3_METADATA = 3   # Metadata-only register entry (no LLM)
    T4_SKIP = 4       # Excluded entirely


class TriageResult:
    """Result of triaging a single document."""

    __slots__ = ("document", "tier", "reason")

    def __init__(self, document: Any, tier: TriageTier, reason: str):
        self.document = document
        self.tier = tier
        self.reason = reason

    def __repr__(self) -> str:
        name = getattr(self.document, "file_name", "?")
        return f"TriageResult({name!r}, {self.tier.name}, {self.reason!r})"


# ---------------------------------------------------------------------------
# Constants — tunable, derived from production data analysis
# ---------------------------------------------------------------------------

# Filenames (lowercased) that are boilerplate templates with zero legal value.
# These appear identically across 40+ cases in production.
BOILERPLATE_NAMES = frozenset({
    "documents needed to proceed",
    "attaching a document instructions",
})

# Partial filename matches for boilerplate (checked via substring)
BOILERPLATE_SUBSTRINGS = (
    "documents needed to proceed",
    "attaching a document instructions",
)

# Document type labels (from document_type_label DB column) that indicate high value.
HIGH_VALUE_TYPE_LABELS = frozenset({
    # Contracts and agreements
    "contract", "agreement", "lease", "deed", "operating agreement",
    "subscription agreement", "promissory note", "convertible note",
    "loan agreement", "financing agreement", "purchase agreement",
    # Legal filings
    "complaint", "summons", "motion", "order", "answer",
    "civil cover sheet", "return of service", "legal filing",
    "affidavit", "declaration", "judgment", "settlement",
    # Case foundation
    "intake form", "intake", "evidence packet",
    # Demand/notice
    "demand letter", "notice of intent", "letter of representation",
    "cease and desist",
    # Reports and assessments
    "inspection report", "appraisal", "expert report",
})

# Filename patterns that indicate high-value documents regardless of type_label.
_HIGH_VALUE_FILENAME_PATTERNS = re.compile(
    r"(?i)(?:"
    r"intake\s*form|"
    r"(?:subscription|operating|purchase|loan|financing)\s*agreement|"
    r"promissory\s*note|convertible\s*note|"
    r"complaint|summons|motion|order\b|answer\b|"
    r"demand\s*letter|notice\s*of\s*intent|"
    r"letter\s*of\s*representation|"
    r"evidence\s*packet|"
    r"inspection\s*report|appraisal|"
    r"attorney\s*(?:representation|fee)\s*agreement"
    r")"
)

# Clio Note patterns for staff initials — low value, short notes.
# Matches "Clio Note - EM NOTE", "Clio Note - MT NOTE", "Clio Note - DW assignment", etc.
_STAFF_INITIAL_NOTE_PATTERN = re.compile(
    r"(?i)^clio\s+note\s*-\s*(?:[a-z]{2,4}\s+(?:note|assignment|review))",
)

# Clio Note patterns that are HIGH value and should NOT be triaged down.
_HIGH_VALUE_CLIO_NOTE_PATTERN = re.compile(
    r"(?i)clio\s+note\s*-\s*(?:"
    r"(?:initial\s+)?case\s+(?:summary|review)|"
    r"intake|"
    r"attorney\s+initial|"
    r"pre-?suit\s+review|"
    r"closing\s+(?:summary|letter)|"
    r"client\s+(?:detailed|notes\s+re)"
    r")",
)

# File types that are images.
IMAGE_MIME_TYPES = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/bmp", "image/tiff",
    "image/generic",
})

# Thresholds
_TEXT_LEN_METADATA_ONLY_IMAGE = 2000   # Images with <2K text → T3
_TEXT_LEN_METADATA_ONLY_NOTE = 800     # Staff notes with <800 chars → T3
_TEXT_LEN_LIGHT_THRESHOLD = 3000       # Docs with <3K text → T2 (unless high-value)
_TEXT_LEN_ZERO = 0                     # Zero text → T4 (unless image)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def triage_documents(
    documents: List[Any],
    *,
    enable_triage: bool = True,
) -> Dict[TriageTier, List[TriageResult]]:
    """Triage a list of documents into processing tiers.

    Args:
        documents: List of ProcessedDocument objects.
        enable_triage: If False, all docs get T1_FULL (feature flag bypass).

    Returns:
        Dict mapping each tier to its list of TriageResults.
    """
    results: Dict[TriageTier, List[TriageResult]] = {
        TriageTier.T1_FULL: [],
        TriageTier.T2_LIGHT: [],
        TriageTier.T3_METADATA: [],
        TriageTier.T4_SKIP: [],
    }

    for doc in documents:
        if enable_triage:
            tr = triage_document(doc)
        else:
            tr = TriageResult(doc, TriageTier.T1_FULL, "triage_disabled")
        results[tr.tier].append(tr)

    # Log triage summary
    counts = {tier.name: len(items) for tier, items in results.items()}
    total = sum(counts.values())
    logger.info(
        f"[TRIAGE] {total} docs triaged: "
        f"T1_FULL={counts['T1_FULL']} T2_LIGHT={counts['T2_LIGHT']} "
        f"T3_METADATA={counts['T3_METADATA']} T4_SKIP={counts['T4_SKIP']}"
    )

    # Log individual T4 skips for observability
    for tr in results[TriageTier.T4_SKIP]:
        name = getattr(tr.document, "file_name", "?")
        logger.info(f"[TRIAGE:SKIP] {name!r} — {tr.reason}")

    # Log T3 metadata-only docs
    if results[TriageTier.T3_METADATA]:
        t3_names = [getattr(tr.document, "file_name", "?") for tr in results[TriageTier.T3_METADATA]]
        logger.info(f"[TRIAGE:METADATA_ONLY] {len(t3_names)} docs: {', '.join(t3_names[:10])}")

    return results


def triage_document(doc: Any) -> TriageResult:
    """Classify a single document into a processing tier.

    Uses only already-available metadata: filename, file_type, extracted text length,
    document_type_label. No LLM calls.

    Args:
        doc: A ProcessedDocument-like object with file_name, content, file_type,
             and optionally registry dict with document_type_label.

    Returns:
        TriageResult with tier and reason.
    """
    filename = getattr(doc, "file_name", "") or ""
    filename_lower = filename.lower()
    content = getattr(doc, "content", "") or ""
    text_len = len(content)

    # Get file_type as string for comparison
    file_type_raw = getattr(doc, "file_type", None)
    file_type = file_type_raw.value if hasattr(file_type_raw, "value") else str(file_type_raw or "")

    # Get document_type_label from registry metadata if available
    registry = getattr(doc, "registry", None) or {}
    type_label = (registry.get("document_type") or registry.get("document_type_label") or "").lower().strip()

    # --- T4: Skip — boilerplate ---
    for bp in BOILERPLATE_SUBSTRINGS:
        if bp in filename_lower:
            return TriageResult(doc, TriageTier.T4_SKIP, f"boilerplate: {bp}")

    # --- T4: Skip — zero text, non-image ---
    if text_len == _TEXT_LEN_ZERO and file_type not in IMAGE_MIME_TYPES:
        return TriageResult(doc, TriageTier.T4_SKIP, "zero_text_non_image")

    # --- T1: Full — high-value by type label ---
    if type_label and _is_high_value_type_label(type_label):
        return TriageResult(doc, TriageTier.T1_FULL, f"high_value_type: {type_label}")

    # --- T1: Full — high-value by filename pattern ---
    if _HIGH_VALUE_FILENAME_PATTERNS.search(filename):
        return TriageResult(doc, TriageTier.T1_FULL, "high_value_filename")

    # --- T1: Full — high-value Clio notes (case summaries, intake, attorney review) ---
    if _HIGH_VALUE_CLIO_NOTE_PATTERN.search(filename):
        return TriageResult(doc, TriageTier.T1_FULL, "high_value_clio_note")

    # --- T3: Metadata-only — low-text images/photos ---
    if file_type in IMAGE_MIME_TYPES and text_len < _TEXT_LEN_METADATA_ONLY_IMAGE:
        return TriageResult(doc, TriageTier.T3_METADATA, f"low_text_image ({text_len} chars)")

    # --- T3: Metadata-only — brief staff initial notes ---
    if _STAFF_INITIAL_NOTE_PATTERN.search(filename) and text_len < _TEXT_LEN_METADATA_ONLY_NOTE:
        return TriageResult(doc, TriageTier.T3_METADATA, f"staff_note ({text_len} chars)")

    # --- T2: Light — Clio communications (moderate value) ---
    if "clio communication" in filename_lower:
        return TriageResult(doc, TriageTier.T2_LIGHT, "clio_communication")

    # --- T2: Light — remaining staff notes that weren't caught above ---
    if _STAFF_INITIAL_NOTE_PATTERN.search(filename):
        return TriageResult(doc, TriageTier.T2_LIGHT, "staff_note_with_content")

    # --- T2: Light — short documents (< 3K text) unless they were already classified ---
    if text_len < _TEXT_LEN_LIGHT_THRESHOLD and text_len > 0:
        return TriageResult(doc, TriageTier.T2_LIGHT, f"short_doc ({text_len} chars)")

    # --- Default: T1 Full ---
    return TriageResult(doc, TriageTier.T1_FULL, "default_full")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_high_value_type_label(label: str) -> bool:
    """Check if a document_type_label indicates high value.

    Checks both exact match and substring match against known high-value types.
    """
    if label in HIGH_VALUE_TYPE_LABELS:
        return True

    # Substring check for composite labels like "operating agreement (amended)"
    for hv in HIGH_VALUE_TYPE_LABELS:
        if hv in label:
            return True

    return False
