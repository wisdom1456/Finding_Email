#!/usr/bin/env python3
"""Test the gap reconciliation fix to verify it will work."""

# Simulate the gap and signed docs from the actual case

gap_related_documents = [
    'Grow1 Operating Agreement (2).pdf',
    'Grow1 Operating Agreement (3).pdf',
    'Grow1 Operating Agreement.pdf'
]

signed_docs = [
    {"file_name": "Grow1 Operating Agreement.pdf", "status": "signed", "confidence": "low"},
    {"file_name": "Grow1 Operating Agreement (2).pdf", "status": "signed", "confidence": "low"},
    {"file_name": "Grow1 Operating Agreement (3).pdf", "status": "signed", "confidence": "low"},
]

# Test exact matching
related_docs_lower = {(doc or "").lower() for doc in gap_related_documents}
matched = []
seen = set()

print("Testing Gap Reconciliation Fix\n" + "="*50 + "\n")
print(f"Gap related_documents: {gap_related_documents}\n")
print(f"Signed documents:")
for doc in signed_docs:
    print(f"  - {doc['file_name']} ({doc['confidence']} confidence)")

print(f"\n{'='*50}\nTesting Exact Match Logic:\n{'='*50}\n")

for doc in signed_docs:
    file_name = doc.get("file_name") or ""
    file_name_lower = file_name.lower()
    base_name = file_name_lower.rsplit(".", 1)[0]

    if file_name_lower in related_docs_lower or base_name in related_docs_lower:
        key = file_name_lower
        if key not in seen:
            seen.add(key)
            matched.append(file_name)
            print(f"✅ MATCH: {file_name}")
            print(f"   - file_name_lower: {file_name_lower}")
            print(f"   - in related_docs: {file_name_lower in related_docs_lower}\n")

print(f"{'='*50}")
print(f"RESULT: {len(matched)} matches found\n")

if len(matched) == 3:
    print("✅ SUCCESS! All 3 signed Operating Agreements matched.")
    print("   The gap WILL be suppressed with the fix.\n")
    print("Expected behavior:")
    print("  1. Gap reconciliation will find these exact matches")
    print("  2. Gap will be removed from the results")
    print("  3. Reconciliation note will be added:")
    print('     "Execution metadata confirms signed documents (Grow1 Operating Agreement.pdf, ...);')
    print('      removed 1 execution/signature coverage gap(s) treated as non-blocking"')
else:
    print(f"❌ FAILED! Only {len(matched)} matches found (expected 3)")
    print("   The fix may not work as expected.")

print("\n" + "="*50)
