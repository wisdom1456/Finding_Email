#!/usr/bin/env python3
"""Backfill document registry for existing documents missing registry data.

Finds documents in the DB that lack metadata.registry, builds an initial
registry from their extracted text + metadata, and persists via the canonical
write path (DocumentRegistryService.persist_to_document).

Safety rules:
  - Never overwrites attorney_enrichment
  - Never overwrites healthy enriched documents (enrichment_stage != none/migration)
    unless --force is passed
  - All writes go through persist_to_document (canonical registry path)
  - Dry-run by default (use --write to actually persist)

Usage:
  python scripts/backfill_document_registry.py                    # Dry run
  python scripts/backfill_document_registry.py --write            # Persist changes
  python scripts/backfill_document_registry.py --write --force    # Overwrite existing registries
  python scripts/backfill_document_registry.py --case-id <id>     # Backfill single case
"""

import argparse
import os
import re
import sys

# Ensure the project root is on the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase import create_client

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.services.document_registry_service import DocumentRegistryService


_EXT_TO_FILETYPE = {
    ".pdf": FileType.PDF,
    ".docx": FileType.DOCX,
    ".doc": FileType.DOC,
    ".txt": FileType.TXT,
    ".csv": FileType.CSV,
    ".eml": FileType.EML,
    ".jpg": FileType.JPG,
    ".jpeg": FileType.JPG,
    ".png": FileType.PNG,
    ".gif": FileType.GIF,
    ".bmp": FileType.BMP,
    ".tiff": FileType.TIFF,
    ".tif": FileType.TIFF,
    ".heic": FileType.JPG,
}


def _guess_file_type(file_name: str) -> FileType:
    ext = os.path.splitext(file_name or "")[1].lower()
    return _EXT_TO_FILETYPE.get(ext, FileType.PDF)


def main():
    parser = argparse.ArgumentParser(description="Backfill document registry")
    parser.add_argument("--write", action="store_true", help="Actually persist changes (default is dry run)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing healthy registries")
    parser.add_argument("--case-id", type=str, help="Backfill only documents in this case")
    parser.add_argument("--limit", type=int, default=500, help="Max documents to process (default 500)")
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    registry_service = DocumentRegistryService()

    # Build query
    query = (
        supabase.table("documents")
        .select("id, file_name, file_type, file_size, extracted_text, metadata, "
                "extraction_quality, enrichment_stage, document_type_label")
    )
    if args.case_id:
        query = query.eq("case_id", args.case_id)
    query = query.limit(args.limit)

    result = query.execute()
    docs = result.data or []

    stats = {"scanned": 0, "updated": 0, "skipped_healthy": 0, "skipped_no_text": 0, "failed": 0}

    for doc in docs:
        stats["scanned"] += 1
        doc_id = doc["id"]
        file_name = doc.get("file_name", "")
        metadata = doc.get("metadata") or {}
        existing_registry = metadata.get("registry")
        enrichment_stage = doc.get("enrichment_stage") or (existing_registry or {}).get("enrichment_stage", "none")

        # Skip healthy documents unless forced
        if existing_registry and enrichment_stage not in ("none", "migration", None, ""):
            if not args.force:
                stats["skipped_healthy"] += 1
                continue

        # Skip documents without extracted text
        text = doc.get("extracted_text") or ""
        if not text.strip():
            stats["skipped_no_text"] += 1
            continue

        # Build ProcessedDocument
        file_type = _guess_file_type(file_name)
        sig_detection = metadata.get("signature_detection")
        attorney_enrichment = metadata.get("attorney_enrichment")

        pdoc = ProcessedDocument(
            file_name=file_name,
            content=text[:200_000],
            document_type=DocumentType.CASE_DOCUMENT,
            file_type=file_type,
            metadata=FileMetadata(
                file_name=file_name,
                file_type=file_type,
                file_size=doc.get("file_size", 0),
            ),
            document_id=doc_id,
            extraction_quality=doc.get("extraction_quality", "high"),
            signature_detection=sig_detection if isinstance(sig_detection, dict) else None,
            attorney_enrichment=attorney_enrichment if isinstance(attorney_enrichment, dict) else None,
        )

        try:
            registry = registry_service.build_initial_registry(pdoc)

            if args.write:
                registry_service.persist_to_document(doc_id, registry, supabase)

            stats["updated"] += 1
            print(f"  {'WRITE' if args.write else 'DRY'} {file_name} -> type={registry.get('document_type')}, "
                  f"sig_expected={registry.get('signature_expected')}, stage={registry.get('enrichment_stage')}")
        except Exception as e:
            stats["failed"] += 1
            print(f"  FAIL {file_name}: {e}")

    # Summary
    print("\n--- Backfill Summary ---")
    print(f"  Scanned:        {stats['scanned']}")
    print(f"  Updated:        {stats['updated']}" + (" (dry run)" if not args.write else ""))
    print(f"  Skipped healthy: {stats['skipped_healthy']}")
    print(f"  Skipped no text: {stats['skipped_no_text']}")
    print(f"  Failed:         {stats['failed']}")

    if not args.write and stats["updated"] > 0:
        print(f"\nRun with --write to persist {stats['updated']} changes.")


if __name__ == "__main__":
    main()
