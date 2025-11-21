#!/usr/bin/env python3
"""Test citation removal regex patterns."""

import re

# Test text with various citation formats
test_letter = """
Good afternoon Client,

You entered into a contract [Source: Contract.pdf] on November 14, 2024 [Source: Contract.pdf]
for $128,000 [Source: Contract.pdf]. You paid $100,000 [Source: Payment_Records.pdf] to date,
but the contractor ceased work (Source: Client_Notes.txt) in March 2025.

According to the Property Disclosure Form [Source: Property_Disclosure_Form.pdf], the seller
answered "I don't know" to flood history questions.
"""

print("ORIGINAL TEXT:")
print(test_letter)
print("\n" + "=" * 80 + "\n")

# Current regex from the code
citation_pattern = r"[\(\[]Source:[^\)\]]+[\)\]]"

cleaned = re.sub(citation_pattern, "", test_letter)

# Clean up multiple spaces
cleaned = re.sub(r"\s+", " ", cleaned)

# Clean up double periods
cleaned = re.sub(r"\.\.+", ".", cleaned)

# Clean up spaces before punctuation
cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)

print("CLEANED TEXT:")
print(cleaned.strip())
print("\n" + "=" * 80 + "\n")

# Test specific patterns
test_patterns = [
    "[Source: Contract.pdf]",
    "(Source: Contract.pdf)",
    " [Source: Contract.pdf]",
    " (Source: Contract.pdf)",
    "[Source: Payment_Records.pdf]",
]

print("PATTERN TESTS:")
for pattern_text in test_patterns:
    matches = re.findall(citation_pattern, pattern_text)
    print(f"  '{pattern_text}' -> Matches: {matches}")
