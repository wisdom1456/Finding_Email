"""Content-hash deduplication for case documents.

Downloads document bytes from storage, computes SHA-256 content hashes,
and flags duplicates (keeping the earliest uploaded version).
Extracted from clio_import_service.py.
"""

import hashlib
import logging
from collections import defaultdict
from typing import Any, Dict

logger = logging.getLogger(__name__)


def run_content_hash_dedup(case_id: str, supabase) -> Dict[str, Any]:
    """Run content-hash dedup on all documents in a case.

    Downloads each document's bytes from storage, computes SHA-256,
    and flags duplicates (keeping the earliest uploaded version).
    """
    docs_resp = (
        supabase.table("documents")
        .select("id, file_name, file_size, storage_path, metadata, status, created_at")
        .eq("case_id", case_id)
        .neq("status", "duplicate")
        .neq("status", "skipped")
        .order("created_at")
        .execute()
    )
    docs = docs_resp.data or []

    if not docs:
        return {"duplicates_found": 0, "documents_checked": 0}

    hash_groups: Dict[str, list] = defaultdict(list)
    docs_checked = 0
    docs_hashed = 0

    for doc in docs:
        doc_id = doc["id"]
        metadata = doc.get("metadata") or {}
        content_hash = metadata.get("content_hash")

        if not content_hash:
            storage_path = doc.get("storage_path")
            if not storage_path:
                continue
            try:
                file_bytes = supabase.storage.from_("documents").download(storage_path)
                content_hash = hashlib.sha256(file_bytes).hexdigest()
                metadata["content_hash"] = content_hash
                supabase.table("documents").update(
                    {"metadata": metadata}
                ).eq("id", doc_id).execute()
                docs_hashed += 1
            except Exception as e:
                logger.warning(
                    f"Failed to download doc for hash: {doc['file_name']}",
                    extra={"doc_id": doc_id, "error": str(e)},
                )
                continue

        hash_groups[content_hash].append(doc)
        docs_checked += 1

    duplicates_found = 0
    flagged_ids = []

    for content_hash, group in hash_groups.items():
        if len(group) <= 1:
            continue

        canonical = group[0]
        for dup in group[1:]:
            dup_id = dup["id"]
            dup_metadata = dup.get("metadata") or {}
            dup_metadata["is_duplicate"] = True
            dup_metadata["duplicate_reason"] = "content_hash_match"
            dup_metadata["duplicate_of"] = canonical["id"]
            dup_metadata["excluded"] = True

            supabase.table("documents").update({
                "status": "duplicate",
                "metadata": dup_metadata,
            }).eq("id", dup_id).execute()

            duplicates_found += 1
            flagged_ids.append(dup_id)
            logger.info(
                f"Content-hash duplicate: {dup['file_name']} -> {canonical['file_name']}",
                extra={"dup_id": dup_id, "canonical_id": canonical["id"], "hash": content_hash[:12]},
            )

    return {
        "duplicates_found": duplicates_found,
        "documents_checked": docs_checked,
        "documents_hashed": docs_hashed,
        "flagged_ids": flagged_ids,
    }
