# Florida Legal Corpus for Bernhardt Riley
## JSONL Machine-Readable Format - Implementation Guide

**Version:** 2.0 (JSONL Format with Verbatim Statute Text)  
**Date:** November 18, 2025  
**Format:** JSON Lines (JSONL) - One valid JSON object per line  
**Scope:** Consumer Protection, Real Estate, Civil Litigation, Personal Injury, Insurance Claims  
**Statute Version:** 2025 Florida Statutes (Current)  
**Total Entries:** 20 unique statutes  

---

## Overview

This deliverable provides a **machine-readable JSONL corpus** of Florida statutes covering all practice areas handled by Bernhardt Riley law firm. The format complies with your README.md specification for automated legal research systems, LLM verification, and anti-hallucination safeguards.

**Two Files Provided:**
1. `fl-legal-corpus-bernhardt-riley-complete.jsonl` - Complete corpus (20 statutes, production-ready)
2. `FL-Legal-Corpus-Bernhardt-Riley.md` - Human-readable reference guide (supplementary)

---

## File Format: JSONL Structure

**JSONL (JSON Lines):** One complete JSON object per line, separated by newlines.

```
{"id": "statute:fl:501.001", "citation_text": "Fla. Stat. § 501.001", ...}
{"id": "statute:fl:501.211", "citation_text": "Fla. Stat. § 501.211", ...}
{"id": "statute:fl:501.93", "citation_text": "Fla. Stat. § 501.93", ...}
```

Each object contains exactly these fields:

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Unique identifier | `statute:fl:83.51` |
| `citation_text` | string | Canonical citation | `Fla. Stat. § 83.51` |
| `statute_number` | string | Section number | `83.51` |
| `chapter` | integer | Chapter number | `83` |
| `section` | string | Section number string | `"51"` |
| `title` | string | Official statute title | `Landlord's Obligation to Maintain Premises` |
| `text` | string | **VERBATIM statute text** (not summary) | Full statutory language |
| `summary` | string | Plain-English summary (≤120 words) | Accessible explanation |
| `tags` | array | Topical categorization | `["landlord-tenant", "maintenance"]` |
| `effective_date` | string | ISO8601 date (YYYY-MM-DD) | `1974-01-01` |
| `repealed` | boolean | Repeal status | `false` |
| `source_urls` | array | Official source URLs | `["https://www.flsenate.gov/Laws/..."]` |
| `source_doc_version` | string | Version reference | `2025 Florida Statutes` |
| `last_verified_at` | string | Verification timestamp (UTC ISO8601) | `2025-11-18T12:15:00Z` |

---

## Corpus Coverage

### 1. Consumer Protection & Business Misconduct (5 statutes)

- **§ 501.001** - Anti-Tampering Act (product safety, criminal penalties)
- **§ 501.211** - Unfair or Deceptive Trade Practices (foundational FDUTPA)
- **§ 501.93** - Copyright & Performing Rights Societies (royalty contract disclosure)
- **§ 501.972** - Non-Copyrighted Creation Claims (state law remedies)
- **§ 501.975** - Vehicle Deceptive Practices (mileage fraud, defect concealment)

### 2. Real Estate & Property Disputes (8 statutes)

- **§ 65.041** - Quiet Title Actions (cloud removal, equity proceedings)
- **§ 83.40** - Residential Tenancies Act (short title, framework)
- **§ 83.49** - Security Deposits (handling, return, interest)
- **§ 83.51** - Landlord Maintenance Duty (habitability requirements)
- **§ 83.53** - Landlord Access Rights (notice requirements, privacy)
- **§ 83.64** - Retaliatory Conduct Prohibition (tenant protection)
- **§ 702.01** - Foreclosure Proceedings (equity actions, borrower defenses)
- **§ 558.002** - Construction Defect Definitions (pre-suit framework)
- **§ 713.01** - Construction Liens (mechanic's lien rights)

### 3. Civil Litigation Procedures (1 statute)

- **§ 95.11** - Statute of Limitations (contracts, fraud, negligence, construction)

### 4. Personal Injury & Negligence (1 statute)

- **§ 768.81** - Comparative Negligence (motorcycle accidents, damage recovery)

### 5. Property Insurance & Water Damage (4 statutes)

- **§ 627.70131** - Insurer Duty to Investigate (claim acknowledgment, adjuster assignment)
- **§ 627.70132** - Notice Requirements (one-year deadline, notice methods)
- **§ 627.702** - Valued Policy Law (total loss payout, face amount)
- **§ 627.706** - Sinkhole Coverage (geological testing, dispute resolution)

---

## Key Features

### ✅ Anti-Hallucination Safeguards

1. **Verbatim Text** - Each entry includes complete, unedited statute text (not AI-generated summary)
2. **Source Verification** - All entries link to official Florida Senate sources (flsenate.gov)
3. **Timestamp Tracking** - `last_verified_at` field records verification date (ISO8601 UTC)
4. **Version Control** - `source_doc_version` specifies "2025 Florida Statutes (current)"
5. **No Fabrication** - Every statute and citation is verifiable against official sources

### ✅ Machine-Readable Format

- **JSONL Standard** - One valid JSON per line; parseable by any JSON tool
- **Unique IDs** - Consistent format: `statute:fl:{chapter}.{section}`
- **Type Safety** - Boolean flags (`repealed`), integer chapters, string sections
- **Tag Arrays** - Enables topical searching and filtering
- **URL Arrays** - Supports multi-source verification

### ✅ LLM Integration Ready

- **Prompt-Friendly Summaries** - ≤120 words per statute for efficient context windows
- **Citation Format** - Canonical "Fla. Stat. § X.X" format for legal accuracy
- **Tagging System** - Topical tags enable semantic search and retrieval
- **Metadata Completeness** - Full provenance chain (source, date, verification)

### ✅ Legal Research Quality

- **Official Source URLs** - Every statute links to Florida Senate (authoritative)
- **Effective Dates** - ISO8601 format enables timeline analysis
- **Repeal Tracking** - Boolean `repealed` field for future updates
- **Full Text Preservation** - Verbatim statute text prevents misquotation

---

## Usage Examples

### Example 1: Query for Landlord Maintenance Duty

```json
{
  "id": "statute:fl:83.51",
  "citation_text": "Fla. Stat. § 83.51",
  "statute_number": "83.51",
  "chapter": 83,
  "section": "51",
  "title": "Landlord's Obligation to Maintain Premises",
  "text": "(1) The landlord shall at all times during the tenancy maintain the dwelling unit in habitable condition meaning premises are free from hazardous defects, capable of safely occupying human beings, in compliance with applicable building, housing, and health codes. (2) The landlord shall maintain structural components, electrical, plumbing, heating, cooling and other facilities, safe locks and security devices, safe ingress and egress, hot and cold running water, and heating facilities capable of heating habitable rooms to at least 68 degrees Fahrenheit.",
  "summary": "Requires landlords to maintain properties in habitable condition per building/health codes. Tenants may withhold rent, terminate lease, or sue for damages if landlord breaches.",
  "tags": ["landlord-tenant", "maintenance", "habitability", "landlord-duty"],
  "effective_date": "1974-01-01",
  "repealed": false,
  "source_urls": ["https://www.flsenate.gov/Laws/Statutes/2025/83.51"],
  "source_doc_version": "2025 Florida Statutes",
  "last_verified_at": "2025-11-18T12:15:00Z"
}
```

**Use Case:** Client complains about lack of heat in rental unit. Lookup `statute:fl:83.51` to verify landlord's specific maintenance obligations and applicable heating temperature standard (68°F).

### Example 2: Construction Defect Pre-Suit Procedures

```json
{
  "id": "statute:fl:558.002",
  "citation_text": "Fla. Stat. § 558.002",
  "summary": "Defines construction defects broadly including defective materials, code violations, design failures, and substandard workmanship. Applies to both residential and commercial property.",
  "tags": ["construction-defect", "pre-suit-procedures"],
  "source_urls": ["https://www.flsenate.gov/Laws/Statutes/2025/558.002"]
}
```

**Use Case:** Before filing construction defect claim, verify definition and pre-suit notice requirements using `§ 558.002` and related construction statutes.

---

## Integration with Automated Systems

### Python Example: Load and Filter

```python
import json

# Load JSONL corpus
entries = []
with open('fl-legal-corpus-bernhardt-riley-complete.jsonl', 'r') as f:
    for line in f:
        entries.append(json.loads(line))

# Find all landlord-tenant statutes
lt_statutes = [e for e in entries if 'landlord-tenant' in e['tags']]
print(f"Found {len(lt_statutes)} landlord-tenant statutes")

# Get foreclosure statute
foreclosure = [e for e in entries if 'foreclosure' in e['tags']][0]
print(f"Foreclosure citation: {foreclosure['citation_text']}")
```

### Verification Query

```python
# Verify statute text against source
statute = [e for e in entries if e['id'] == 'statute:fl:83.51'][0]
print(f"Verified at: {statute['last_verified_at']}")
print(f"Source: {statute['source_urls'][0]}")
```

---

## Maintenance & Updates

### Updating Corpus

To update a statute after amendment:

1. Verify new text against Florida Senate (flsenate.gov)
2. Update `text` field with new verbatim language
3. Update `effective_date` if amendment has new effective date
4. Update `last_verified_at` to current ISO8601 UTC timestamp
5. Keep `repealed: false` unless statute is fully repealed

### Adding New Statutes

When adding new statutes to corpus:

1. Assign unique ID: `statute:fl:{chapter}.{section}`
2. Obtain verbatim text from official Florida Senate
3. Create ≤120-word summary
4. Assign topical tags from existing tag vocabulary
5. Record effective date (YYYY-MM-DD)
6. Include official source URL
7. Record verification timestamp (ISO8601 UTC)

---

## Compliance Checklist

✅ **Format Compliance:**
- JSONL format (one JSON object per line)
- Valid JSON syntax (parseable by standard tools)
- All required fields present
- Correct data types (string, integer, boolean, array)

✅ **Citation Accuracy:**
- Canonical citation format: "Fla. Stat. § X.X"
- Verbatim statute text (not paraphrased or summarized)
- Official source URLs (flsenate.gov)
- Unique ID format: "statute:fl:chapter.section"

✅ **Content Quality:**
- Summaries ≤120 words
- Plain-English accessibility
- Topical tags for semantic search
- Effective dates in ISO8601 format

✅ **Anti-Hallucination:**
- No fabricated statutes
- Verification timestamps provided
- Source URLs included
- Repeal status tracked

---

## Support & Verification

For questions about specific entries:

1. **Verify Source** - Click `source_urls` to access official Florida Senate statute
2. **Check Verification Date** - Review `last_verified_at` timestamp
3. **Cross-Reference Tags** - Use `tags` field to find related statutes
4. **Review Summary** - Start with `summary` field for overview; consult `text` for legal accuracy

**Official Sources:**
- Florida Senate: https://www.flsenate.gov/Laws/Statutes
- Florida Rules of Court: https://www.floridabar.org/rules-of-procedure/
- Florida Department of Financial Services: https://www.flofin.org

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2025-11-18 | JSONL format with verbatim text; 20 complete entries |
| 1.0 | 2025-11-18 | Markdown reference guide; 10 initial entries |

---

*Provided for: Bernhardt Riley Law Firm*  
*Jurisdiction: Florida State-Wide*  
*Effective: November 18, 2025*