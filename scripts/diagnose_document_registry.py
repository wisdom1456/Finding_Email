#!/usr/bin/env python3
"""Diagnose document registry health across all documents.

Reports:
  1. Documents missing metadata.registry entirely
  2. Documents where denormalized columns don't match registry
  3. Documents with attorney override but mismatched effective label
  4. Documents with suggested_relationships but zero matching docs in case
  5. Documents with empty document_type_label but enough text to classify

Uses DocumentRegistryService.validate_registry_integrity() for column checks.

Usage:
  python scripts/diagnose_document_registry.py                  # All cases
  python scripts/diagnose_document_registry.py --case-id <id>   # Single case
  python scripts/diagnose_document_registry.py --fix --write     # Auto-fix column mismatches
"""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase import create_client

from legal_portal.services.document_registry_service import DocumentRegistryService


def main():
    parser = argparse.ArgumentParser(description="Diagnose document registry health")
    parser.add_argument("--case-id", type=str, help="Diagnose only documents in this case")
    parser.add_argument("--limit", type=int, default=1000, help="Max documents to scan (default 1000)")
    parser.add_argument("--fix", action="store_true", help="Auto-fix column mismatches via persist_to_document")
    parser.add_argument("--write", action="store_true", help="Required with --fix to actually persist fixes")
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    registry_service = DocumentRegistryService()

    # Fetch documents
    query = (
        supabase.table("documents")
        .select("id, case_id, file_name, extracted_text, metadata, "
                "document_type_label, document_type_confidence, signed_status, "
                "signature_expected, system_summary, enrichment_stage")
    )
    if args.case_id:
        query = query.eq("case_id", args.case_id)
    query = query.limit(args.limit)

    result = query.execute()
    docs = result.data or []

    # Counters
    total = len(docs)
    missing_registry = []
    column_mismatches = []
    override_mismatches = []
    orphan_relationships = []
    classifiable_but_empty = []

    # Build case -> doc_id lookup for relationship checks
    case_doc_ids: dict[str, set[str]] = defaultdict(set)
    doc_names_by_case: dict[str, dict[str, str]] = defaultdict(dict)
    for doc in docs:
        cid = doc.get("case_id", "")
        did = doc.get("id", "")
        fname = doc.get("file_name", "")
        case_doc_ids[cid].add(did)
        if fname:
            doc_names_by_case[cid][fname.lower()] = did

    for doc in docs:
        doc_id = doc["id"]
        file_name = doc.get("file_name", "")
        case_id = doc.get("case_id", "")
        metadata = doc.get("metadata") or {}
        registry = metadata.get("registry")
        attorney = metadata.get("attorney_enrichment") or {}

        # 1. Missing registry
        if registry is None:
            missing_registry.append((doc_id, file_name))
            # Still check #5 for classifiable-but-empty
            text = doc.get("extracted_text") or ""
            label = doc.get("document_type_label") or ""
            if not label and len(text.strip()) >= 100:
                classifiable_but_empty.append((doc_id, file_name, len(text)))
            continue

        # 2. Column mismatches (reuses validate_registry_integrity)
        issues = registry_service.validate_registry_integrity(doc)
        col_issues = [i for i in issues if "column" in i and "mismatch" in i]
        if col_issues:
            column_mismatches.append((doc_id, file_name, col_issues))

        # 3. Attorney override vs effective label mismatch
        override = attorney.get("document_type_override")
        label = doc.get("document_type_label") or ""
        if override and override != label:
            override_mismatches.append((doc_id, file_name, override, label))

        # 4. Suggested relationships with no matching docs
        suggested = registry.get("suggested_relationships") or []
        if suggested:
            other_ids = case_doc_ids.get(case_id, set()) - {doc_id}
            other_names = doc_names_by_case.get(case_id, {})
            has_match = False
            for rel in suggested:
                rel_name = (rel.get("related_doc_name") or "").lower()
                rel_id = rel.get("related_doc_id") or ""
                if rel_id in other_ids:
                    has_match = True
                    break
                if rel_name in other_names:
                    has_match = True
                    break
            if not has_match:
                orphan_relationships.append((doc_id, file_name, len(suggested)))

        # 5. Empty type label but enough text
        label = doc.get("document_type_label") or ""
        text = doc.get("extracted_text") or ""
        if not label and len(text.strip()) >= 100:
            classifiable_but_empty.append((doc_id, file_name, len(text)))

    # --- Report ---
    print(f"\n=== Document Registry Health Report ===")
    print(f"Total documents scanned: {total}\n")

    print(f"1. Missing metadata.registry: {len(missing_registry)}")
    for doc_id, fname in missing_registry[:10]:
        print(f"   {fname or doc_id}")
    if len(missing_registry) > 10:
        print(f"   ... and {len(missing_registry) - 10} more")

    print(f"\n2. Column mismatches (denormalized != registry): {len(column_mismatches)}")
    for doc_id, fname, issues in column_mismatches[:10]:
        print(f"   {fname or doc_id}: {'; '.join(issues)}")
    if len(column_mismatches) > 10:
        print(f"   ... and {len(column_mismatches) - 10} more")

    print(f"\n3. Attorney override vs label mismatch: {len(override_mismatches)}")
    for doc_id, fname, override, label in override_mismatches[:10]:
        print(f"   {fname or doc_id}: override={override!r}, label={label!r}")
    if len(override_mismatches) > 10:
        print(f"   ... and {len(override_mismatches) - 10} more")

    print(f"\n4. Orphan suggested relationships (no matching docs in case): {len(orphan_relationships)}")
    for doc_id, fname, count in orphan_relationships[:10]:
        print(f"   {fname or doc_id}: {count} suggestion(s)")
    if len(orphan_relationships) > 10:
        print(f"   ... and {len(orphan_relationships) - 10} more")

    print(f"\n5. Empty type label with classifiable text (>=100 chars): {len(classifiable_but_empty)}")
    for doc_id, fname, text_len in classifiable_but_empty[:10]:
        print(f"   {fname or doc_id}: {text_len} chars of text")
    if len(classifiable_but_empty) > 10:
        print(f"   ... and {len(classifiable_but_empty) - 10} more")

    # Health score
    issue_count = (len(missing_registry) + len(column_mismatches)
                   + len(override_mismatches) + len(classifiable_but_empty))
    if total > 0:
        healthy_pct = ((total - issue_count) / total) * 100
        print(f"\nHealth score: {healthy_pct:.1f}% ({total - issue_count}/{total} documents healthy)")
    else:
        print("\nNo documents found.")

    # Auto-fix column mismatches
    if args.fix and column_mismatches:
        if not args.write:
            print(f"\n--fix specified but --write not set. Would fix {len(column_mismatches)} column mismatches (dry run).")
        else:
            fixed = 0
            for doc_id, fname, _ in column_mismatches:
                doc_row = next((d for d in docs if d["id"] == doc_id), None)
                if not doc_row:
                    continue
                reg = (doc_row.get("metadata") or {}).get("registry")
                if not reg:
                    continue
                try:
                    registry_service.persist_to_document(doc_id, reg, supabase)
                    fixed += 1
                except Exception as e:
                    print(f"  FAIL fixing {fname}: {e}")
            print(f"\nFixed {fixed}/{len(column_mismatches)} column mismatches.")


if __name__ == "__main__":
    main()
