# Florida Legal Corpus - Production Version

**Version:** 2.2  
**Date:** November 18, 2025  
**Statute Version:** 2025 Florida Statutes (current)  
**Rules Version:** Florida Rules of Civil Procedure (effective June 19, 2025)

---

## Overview

This corpus provides a **verifiable, citation-normalized database** of 51 Florida statutes and 3 Florida Rules with exact verbatim source text, comprehensive metadata, and anti-hallucination safeguards for automated legal research and verification systems.

**Primary Coverage:** 
- Consumer Protection & Business Misconduct (Ch. 501, 672)
- Landlord-Tenant Law (Ch. 83)
- Foreclosure Defense (Ch. 702)
- Construction Defects (Ch. 558)
- Mechanic's Liens (Ch. 713)
- Property Insurance Claims (Ch. 627)
- Statutes of Limitation (Ch. 95)
- Attorney Fees & Sanctions (Ch. 57)

**Scope:** Florida state law only. Federal statutes are not included.

---

## File Structure

### Active Corpus Files

| File | Lines | Description |
|------|-------|-------------|
| `statutes.jsonl` | 51 | Florida statutes with full text and metadata |
| `statute_aliases.jsonl` | 51 | Citation normalization aliases |
| `florida_refs.jsonl` | 3 | Florida Rules of Civil Procedure |

### Supporting Files

| File | Purpose |
|------|---------|
| `validate_corpus.py` | Validation utility script |
| `COVERAGE_TARGETS.md` | Expansion tracking and targets |
| `JSONL-Corpus-Guide.md` | Format documentation |

---

## Schema

### statutes.jsonl

```json
{
  "id": "statute:fl:{chapter}.{section}",
  "citation_text": "Fla. Stat. § {chapter}.{section}",
  "statute_number": "{chapter}.{section}",
  "title": "Official section title",
  "chapter": "Chapter number",
  "section": "Section number",
  "text": "VERBATIM statute text from official source",
  "summary": "Plain-English 2-3 sentences, ≤150 words",
  "tags": ["relevant", "topical", "tags"],
  "effective_date": "YYYY-MM-DD",
  "repealed": false,
  "source_urls": ["https://www.leg.state.fl.us/..."],
  "source_doc_version": "2025 Florida Statutes",
  "last_verified_at": "ISO8601 UTC timestamp"
}
```

### statute_aliases.jsonl

```json
{
  "statute_id": "statute:fl:{chapter}.{section}",
  "alias_text": "§ {chapter}.{section}",
  "normalized": "Fla. Stat. § {chapter}.{section}",
  "patterns": ["F.S. {chapter}.{section}", "Florida Statutes {chapter}.{section}"]
}
```

### florida_refs.jsonl

```json
{
  "id": "rule:fl:civ_proc:{rule_number}",
  "citation_key": "Fla. R. Civ. P. {rule_number}",
  "rule_number": "{rule_number}",
  "title": "Official rule title",
  "text": "Rule text",
  "summary": "Plain-English summary",
  "tags": ["relevant", "tags"],
  "effective_date": "YYYY-MM-DD",
  "source_urls": ["https://www.floridasupremecourt.org/..."],
  "source_doc_version": "Florida Rules of Civil Procedure (2025)",
  "last_verified_at": "ISO8601 UTC timestamp"
}
```

---

## Usage Guidelines

### Citation Normalization

**Canonical Formats:**
- Statutes: `Fla. Stat. § [chapter].[section]`
- Rules: `Fla. R. Civ. P. [rule_number]`

**Alias Patterns Recognized:**
- `F.S. 501.204`
- `Florida Statutes 501.204`
- `s. 501.204`
- `§ 501.204`
- `§501.204` (no space)

### Anti-Hallucination Features

1. **Citation Validation:** Compare AI-generated citations against `citation_text` field
2. **Text Verification:** Verify exact text matches between output and `text` field
3. **Status Classification:** Flag citations as `verified`, `unverified`, or `suspicious`
4. **Coverage Detection:** Warn when case type falls outside corpus coverage areas

---

## Validation

Run the validation script to verify corpus integrity:

```bash
python3 validate_corpus.py
```

**Expected Output:**
```
Statistics:
  Statutes: 51
  Aliases:  51
  Rules:    3
  Total:    105

✅ No errors found!
✅ No warnings!
✅ CORPUS VALIDATION PASSED
```

---

## Supported Practice Areas

This corpus is optimized for Florida civil litigation in the following areas:

✅ **Consumer Protection & Business Misconduct** (FDUTPA, contracts, UCC)  
✅ **Landlord-Tenant Disputes** (evictions, habitability, security deposits)  
✅ **Foreclosure Defense** (judicial foreclosure procedures)  
✅ **Construction Defects & Mechanic's Liens** (Ch. 558, 713)  
✅ **Property Insurance Claims** (homeowner claims, bad faith)  
✅ **Civil Litigation** (statutes of limitation, attorney fees)

❌ **NOT Supported:**
- Federal claims or federal court matters
- Criminal law
- Immigration law
- Bankruptcy (federal jurisdiction)
- Patent/Trademark law (federal jurisdiction)

---

## Maintenance

**Last Verified:** November 18, 2025  
**Source:** Florida Legislature ([leg.state.fl.us](https://www.leg.state.fl.us/statutes/))  
**Verification Method:** Manual review of statute text from official sources  
**Update Frequency:** Annual review recommended (July 1 effective dates)

---

## Version History

### Version 2.2 (November 18, 2025 - EVENING)
- **🏆 100% COVERAGE ACHIEVEMENT: 51 statutes (+8.5% growth)**
- **4 practice areas now at 100% coverage:**
  - Landlord-Tenant (12/12) ✅ Added § 83.62
  - Mechanic's Liens (7/7) ✅ Added § 713.20
  - Consumer Protection (6/6) ✅ Added § 501.2105
  - Construction Defects (6/6) ✅ Added § 558.006
- **Total growth from initial: +264% (14 → 51 statutes)**

### Version 2.1 (November 18, 2025 - PM)
- **Final expansion from 40 to 47 statutes (+17.5% growth)**
- **Added Ch. 768 (Personal Injury/Damages) - 3 statutes**
  - § 768.81 - Comparative Fault (critical for all PI cases)
  - § 768.73 - Punitive Damages
  - § 768.76 - Evidence of Profits
- **Completed Landlord-Tenant (Ch. 83) - now 11 statutes**
  - § 83.53 - Landlord's Access
  - § 83.64 - Retaliatory Conduct
- **Comprehensive Insurance (Ch. 627) - now 6 statutes**
  - § 627.702 - Valued Policy Law (Florida-unique)
  - § 627.428 - Attorney's Fees (insurance)
- **Total growth from initial: +236% (14 → 47 statutes)**

### Version 2.0 (November 18, 2025 - AM)
- Expanded from 14 to 40 statutes (+186% coverage)
- Added comprehensive practice area coverage
- Implemented citation validation and recommendation services
- Added corpus coverage detection
- Enhanced alias normalization (40 aliases)

### Version 1.1 (November 13, 2025)
- Initial corpus with 14 statutes
- Basic coverage of landlord-tenant, construction, and liens

---

## Integration

This corpus integrates with:
- `StatuteValidationService` - Citation extraction and validation
- `StatuteRecommendationService` - AI-powered statute suggestions
- `CorpusCoverageService` - Practice area detection
- `LetterReviewService` - Citation quality checks

For integration details, see:
- `CORPUS_INTEGRATION_SUMMARY.md`
- `CORPUS_EXPANSION_SUMMARY.md`
- `CORPUS_FEATURE_FLAGS_AND_WARNINGS_SUMMARY.md`

---

**Status:** 🏆 **4 AREAS AT 100% COVERAGE** - Production Ready  
**Coverage:** 51 statutes, 3 rules, 51 aliases = 105 total entries  
**Quality:** 100% validated, 0 errors, 0 warnings  
**Growth:** 264% increase from initial corpus (14 → 51 statutes)  
**Perfect Coverage:** Landlord-Tenant (12/12), Mechanic's Liens (7/7), Consumer Protection (6/6), Construction Defects (6/6)
