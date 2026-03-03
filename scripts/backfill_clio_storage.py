#!/usr/bin/env python3
"""One-time backfill: upload extracted_text to Supabase Storage for Clio import-only documents.

These are records created by the Clio import flow that set a storage_path like
'clio/{case_id}/comm_{id}.txt' or 'clio/{case_id}/note_{id}.txt' but never actually
uploaded a file to storage. The extract endpoint now uploads on import, but existing
records need to be backfilled.

This script is safe to run multiple times — if a file already exists in storage
(e.g., from the sync flow), the upload attempt is caught and skipped.

Usage:
    python scripts/backfill_clio_storage.py [--dry-run]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client


def backfill(dry_run: bool = False) -> None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment.")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    # Fetch all Clio-sourced documents that have extracted_text.
    # We page through in batches to avoid loading everything into memory at once.
    BATCH_SIZE = 500
    offset = 0
    total_uploaded = 0
    total_skipped = 0
    total_errors = 0

    print(f"{'DRY RUN — ' if dry_run else ''}Fetching Clio documents with extracted_text...")

    while True:
        response = (
            supabase.table("documents")
            .select("id, storage_path, extracted_text, file_name")
            .like("storage_path", "clio/%")
            .not_.is_("extracted_text", "null")
            .neq("extracted_text", "")
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )

        batch = response.data or []
        if not batch:
            break

        print(f"Processing batch of {len(batch)} documents (offset {offset})...")

        for doc in batch:
            storage_path = doc["storage_path"]
            extracted_text = doc["extracted_text"]
            file_name = doc.get("file_name", storage_path)

            if dry_run:
                print(f"  [DRY RUN] Would upload: {storage_path} ({len(extracted_text)} chars)")
                total_uploaded += 1
                continue

            try:
                supabase.storage.from_("documents").upload(
                    storage_path,
                    extracted_text.encode("utf-8"),
                    {"content-type": "text/plain"},
                )
                print(f"  Uploaded: {file_name} ({len(extracted_text)} chars)")
                total_uploaded += 1
            except Exception as e:
                err_str = str(e)
                if "already exists" in err_str.lower() or "duplicate" in err_str.lower() or "409" in err_str:
                    print(f"  Skipped (already exists): {file_name}")
                    total_skipped += 1
                else:
                    print(f"  ERROR uploading {file_name}: {e}")
                    total_errors += 1

        offset += BATCH_SIZE
        if len(batch) < BATCH_SIZE:
            break

    print()
    print("--- Backfill complete ---")
    print(f"  Uploaded: {total_uploaded}")
    print(f"  Skipped (already existed): {total_skipped}")
    print(f"  Errors: {total_errors}")
    if total_errors:
        print("  Check output above for details on errors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Clio documents into Supabase Storage.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded without actually uploading.",
    )
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
