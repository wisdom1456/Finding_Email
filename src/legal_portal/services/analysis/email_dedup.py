"""Email thread deduplication logic.

Deduplicates email threads by subject grouping, body hash, and
thread supersession detection. Extracted from analysis_orchestrator.py.
"""

import logging
import re

logger = logging.getLogger(__name__)


async def _dedup_email_threads(
    eml_docs: list,
    supabase,
) -> set:
    """Deduplicate email threads by subject grouping and body hash.

    Flags superseded emails (shorter versions of the same thread) and
    exact duplicates (same body_hash) as is_flagged_as_junk=True.

    Returns set of flagged document IDs.
    """
    if not eml_docs:
        return set()

    def _normalize_subject(subject: str) -> str:
        """Strip Re:/Fwd:/FW: prefixes and normalize."""
        cleaned = re.sub(
            r"^(re:\s*|fwd?:\s*|fw:\s*)+", "", subject, flags=re.IGNORECASE,
        )
        return cleaned.strip().lower()

    def _extract_subject(doc: dict) -> str:
        """Extract subject from extracted_text header."""
        text = doc.get("extracted_text", "")
        for line in text.split("\n"):
            if line.startswith("Subject: "):
                return line[9:].strip()
        return ""

    # Group by normalized subject
    thread_groups: dict[str, list[dict]] = {}
    for doc in eml_docs:
        subject = _extract_subject(doc)
        norm = _normalize_subject(subject)
        if norm:
            thread_groups.setdefault(norm, []).append(doc)

    flagged_ids = set()

    for norm_subject, group in thread_groups.items():
        if len(group) < 2:
            continue

        # Phase 1: Exact duplicate dedup (same body_hash)
        hash_groups: dict[str, list[dict]] = {}
        for doc in group:
            bh = (doc.get("metadata") or {}).get("body_hash", "")
            if bh:
                hash_groups.setdefault(bh, []).append(doc)

        # For exact duplicates, keep the first, flag the rest
        deduped_group = []
        seen_hashes = set()
        for doc in group:
            bh = (doc.get("metadata") or {}).get("body_hash", "")
            if bh and bh in seen_hashes:
                # Exact duplicate
                flagged_ids.add(doc["id"])
                try:
                    supabase.table("documents").update({
                        "is_flagged_as_junk": True,
                        "metadata": {
                            **(doc.get("metadata") or {}),
                            "junk_reason": "exact_duplicate",
                        },
                    }).eq("id", doc["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to flag duplicate {doc['id']}: {e}")
            else:
                if bh:
                    seen_hashes.add(bh)
                deduped_group.append(doc)

        # Phase 2: Thread supersession (longer body contains shorter)
        if len(deduped_group) < 2:
            continue

        # Sort by extracted_text length descending
        deduped_group.sort(
            key=lambda d: len(d.get("extracted_text", "")), reverse=True,
        )
        canonical = deduped_group[0]
        canonical_text = canonical.get("extracted_text", "")

        for doc in deduped_group[1:]:
            doc_body = doc.get("extracted_text", "")
            # Check if the shorter email's body is contained in the canonical
            # Strip headers for comparison (body starts after first blank line)
            canon_body = canonical_text.split("\n\n", 1)[-1] if "\n\n" in canonical_text else canonical_text
            short_body = doc_body.split("\n\n", 1)[-1] if "\n\n" in doc_body else doc_body

            if short_body.strip() and short_body.strip() in canon_body:
                flagged_ids.add(doc["id"])
                try:
                    supabase.table("documents").update({
                        "is_flagged_as_junk": True,
                        "metadata": {
                            **(doc.get("metadata") or {}),
                            "junk_reason": "superseded_by_later_reply",
                            "superseded_by": canonical["id"],
                        },
                    }).eq("id", doc["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to flag superseded {doc['id']}: {e}")

    logger.info(f"[DEDUP] Flagged {len(flagged_ids)} emails as junk")
    return flagged_ids
