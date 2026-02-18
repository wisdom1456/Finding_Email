#!/usr/bin/env python3
"""
Debug script to show exactly what signature_evidence is being built for a case.
This helps diagnose why gap reconciliation isn't working.
"""

import sys
import os
from supabase import create_client


def debug_signature_evidence(case_id: str):
    """Show signature evidence that would be built for gap analysis."""

    # Initialize Supabase client
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        return

    supabase = create_client(supabase_url, supabase_key)

    print(f"\n🔍 Debugging signature evidence for case: {case_id}\n")

    # Get documents
    docs_resp = supabase.table("documents").select(
        "id, file_name, file_type, metadata, extracted_text, manual_text"
    ).eq("case_id", case_id).execute()

    docs = docs_resp.data or []
    print(f"Total documents: {len(docs)}\n")

    # Build signature evidence (mimicking _build_signature_evidence)
    signature_evidence = []

    for doc in docs:
        metadata = doc.get("metadata") or {}
        sig_det = metadata.get("signature_detection")

        if not sig_det:
            # Try fallback detection from text
            text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
            if text and "signed by" in text.lower():
                sig_det = {
                    "status": "signed",
                    "confidence": "low",
                    "has_digital_signature": False,
                    "indicators": ["Signed by marker (inferred)"]
                }

        if sig_det and isinstance(sig_det, dict):
            signature_evidence.append({
                "document_id": doc.get("id"),
                "file_name": doc.get("file_name"),
                "status": sig_det.get("status"),
                "confidence": sig_det.get("confidence"),
                "has_digital_signature": sig_det.get("has_digital_signature", False),
                "indicators": sig_det.get("indicators", [])
            })

    # Show signature evidence
    print("=" * 70)
    print("SIGNATURE EVIDENCE (what gap analysis receives)")
    print("=" * 70)

    signed_docs = [s for s in signature_evidence if s.get("status") == "signed"]

    print(f"\nTotal signature evidence entries: {len(signature_evidence)}")
    print(f"Signed documents: {len(signed_docs)}\n")

    if not signed_docs:
        print("❌ NO SIGNED DOCUMENTS FOUND!")
        print("   This explains why gap reconciliation can't suppress execution gaps.\n")
        print("Possible causes:")
        print("  1. signature_detection not in document metadata")
        print("  2. Documents have status != 'signed'")
        print("  3. No documents were processed with signature detection")
    else:
        print("✅ Found signed documents:\n")
        for sig in signed_docs:
            print(f"  • {sig['file_name']}")
            print(f"    Status: {sig['status']}")
            print(f"    Confidence: {sig['confidence']}")
            print(f"    Digital: {sig['has_digital_signature']}")
            print(f"    Indicators: {sig['indicators'][:2]}")
            print()

        # Check for Operating Agreements
        operating_agreements = [
            s for s in signed_docs
            if "operating" in s['file_name'].lower() and "agreement" in s['file_name'].lower()
        ]

        if operating_agreements:
            print(f"\n✅ Found {len(operating_agreements)} signed Operating Agreement(s)")
            print("   These SHOULD suppress execution gaps about Operating Agreements.")
            print("\n   If gaps are still showing, check:")
            print("   1. Gap title/description matches these file names")
            print("   2. Gap is classified as execution-related")
            print("   3. Matching logic is finding these docs")
        else:
            print("\n⚠️  No signed Operating Agreements found")
            print("   Gap analysis correctly reports them as missing/low-confidence")

    # Show all documents with/without signature detection
    print("\n" + "=" * 70)
    print("ALL DOCUMENTS (metadata.signature_detection status)")
    print("=" * 70 + "\n")

    for doc in docs:
        metadata = doc.get("metadata") or {}
        sig_det = metadata.get("signature_detection")
        file_name = doc.get("file_name")

        if "operating" in file_name.lower():
            marker = "📄"
        else:
            marker = "  "

        print(f"{marker} {file_name}")
        if sig_det:
            print(f"   ✓ Status: {sig_det.get('status')}, Confidence: {sig_det.get('confidence')}")
        else:
            print(f"   ❌ NO signature_detection in metadata")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 debug_signature_evidence.py <case_id>")
        print("\nExample: python3 debug_signature_evidence.py e7c99dfa-6092-4775-9007-64ed569d7bcd")
        sys.exit(1)

    debug_signature_evidence(sys.argv[1])
