# Florida Legal Corpus - Phase 1
## Verifiable Citation-Normalized Statute and Rules Reference Database

**Version:** 1.1  
**Date:** November 13, 2025  
**Statute Version:** 2025 Florida Statutes (current)  
**Rules Version:** Florida Rules of Civil Procedure (effective June 19, 2025)

---

## Overview

This corpus provides a **verifiable, citation-normalized database** of Florida statutes and legal references with exact verbatim source text, comprehensive metadata, and anti-hallucination safeguards for automated legal research and verification systems.

**Primary Coverage:** Landlord-Tenant (Chapter 83), Construction Defects (Chapter 558), Mechanic's Liens (Chapter 713), and Florida Rules of Civil Procedure.

---

## File Schemas

### statutes.jsonl Schema

```json
{
  "id": "string (required) - Unique identifier: statute:fl:{chapter.section}",
  "citation_text": "string (required) - Canonical citation: Fla. Stat. § {chapter.section}",
  "statute_number": "string (required) - Section number: {chapter.section}",
  "title": "string (required) - Official section title from statute",
  "chapter": "string (required) - Chapter number",
  "section": "string (required) - Section number within chapter",
  "text": "string (required) - VERBATIM statute text from official source",
  "summary": "string (required) - Plain-English 2-5 sentences, neutral, ≤120 words",
  "tags": "array of strings (required) - Relevant topical tags",
  "effective_date": "string (optional) - YYYY-MM-DD format",
  "repealed": "boolean (required) - Always false (repealed statutes excluded)",
  "source_urls": "array of strings (required) - At least one resolvable official URL",
  "source_doc_version": "string (required) - E.g., '2025 Florida Statutes'",
  "last_verified_at": "string (required) - ISO8601 UTC timestamp"
}
```

---

## Usage Guidelines

**Citation Normalization:**
- Canonical Statute Format: `Fla. Stat. § [chapter].[section]`
- Canonical Rule Format: `Fla. R. Civ. P. [number]`

**Anti-Hallucination:**
- Compare LLM-generated citations against `citation_text` field.
- Verify exact text matches between query and `text` field.
- Flag any citations not present in corpus as potentially invalid.

---
*Last Updated: November 13, 2025*  
*Corpus Version: 1.1*
