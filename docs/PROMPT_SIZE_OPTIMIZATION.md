# Prompt Size Optimization for Letter Generation

**Date**: October 2, 2025  
**Issue**: Final prompt for letter generation was too large, growing linearly with document count

---

## Problem Analysis

### Before Optimization

For a case with **5-6 documents**, the `final_prompt.txt` was **3,160 lines**:
- Instructions & template: ~1,600 lines
- Complete document analyses: ~1,500 lines
  - Each document included ALL extracted fields:
    - `detailed_findings`: 500-800 words per document
    - `summary`: 250-400 words per document
    - `key_facts`: 10-20 per document
    - `evidence_points`: Full list per document
    - `parties_mentioned`: Full party data per document
    - `amounts_and_dates`: All financial/temporal data per document
    - Plus: `key_points`, `citations`, `metadata`, etc.

### Scalability Issue

**Projected for 40 documents:**
```
40 documents × ~250 lines/doc = ~10,000 lines (document data alone)
Plus instructions              = ~11,500 lines total
Estimated tokens               = 80,000-120,000 tokens
```

This would **exceed model context limits** and cause failures.

---

## Solution Implemented

### Location
`src/legal_portal/services/json_processing_service.py` (lines 154-167)

### Change
Added aggressive field exclusion for letter generation phase:

```python
analysis_data = analysis.model_dump(
    exclude={
        "analyzed_documents": {
            "__all__": {
                "original_content",  # Full document text
                "detailed_findings",  # 500-800 words (redundant)
                "evidence_points",   # Detailed list (in key_facts)
                "key_points",        # Often empty/redundant
                "citations",         # Often empty/redundant
                "metadata",          # Technical data not needed
            }
        }
    }
)
```

### What's Still Included (Per Document)
These fields provide sufficient context for letter generation:
- ✅ `file_name` - Document identifier
- ✅ `document_type` - Type classification
- ✅ `inferred_title` - Human-readable title
- ✅ `summary` - 250-400 word overview
- ✅ `key_facts` - 10-20 key factual statements
- ✅ `parties_mentioned` - Parties involved
- ✅ `amounts_and_dates` - Financial/temporal data
- ✅ `legal_issues_identified` - Legal issues
- ✅ `key_information` - One-line summary
- ✅ `relevance_to_case` - Why document matters
- ✅ `timeline_events` - Chronological events

---

## Expected Impact

### Token Reduction
**Before**: ~250 lines per document  
**After**: ~100 lines per document (60% reduction)

**For 40 documents:**
```
Before: ~11,500 lines → ~80,000-120,000 tokens (likely failure)
After:  ~5,600 lines  → ~40,000-50,000 tokens (within limits)
```

### Benefits
1. ✅ **Scalability**: Can handle 40+ document cases
2. ✅ **Performance**: Faster API responses (less data to process)
3. ✅ **Cost**: Lower token costs per letter generation
4. ✅ **Quality**: Still provides comprehensive context
5. ✅ **Reliability**: Stays within model token limits

---

## Testing Recommendations

### Test Cases
1. **Small case** (5-6 docs): Verify letter quality maintained
2. **Medium case** (15-20 docs): Check prompt size and generation success
3. **Large case** (40+ docs): Confirm no token overflow errors

### Verification Steps
```bash
# 1. Generate a letter for a case
./scripts/start_local_dev.sh

# 2. Check the final prompt size
wc -l validation_output/final_prompt.txt

# 3. Verify token count (approximate)
# Expected: <50,000 tokens for 40 documents
```

### Success Criteria
- [ ] Letter generation succeeds for 40+ document cases
- [ ] Letter quality is equivalent to pre-optimization
- [ ] Prompt size stays under 60,000 tokens for large cases
- [ ] All key facts and dates are properly cited in letters

---

## Notes

### Full Document Access Still Available
The excluded fields are still available via:
```python
analysis_proxy.analyzed_documents_with_content
```

This property returns full `AnalyzedDocument` objects with ALL fields, including:
- `original_content` (full document text)
- `detailed_findings` (verbose analysis)
- `evidence_points` (detailed evidence)

**Use case**: If a future feature needs deeper document analysis during letter generation, the data is accessible without re-analysis.

### Why These Fields Were Excluded

1. **`detailed_findings`** (500-800 words): Highly verbose, mostly duplicates information in `summary` and `key_facts`
2. **`evidence_points`**: Detailed evidence list that's already captured in `key_facts`
3. **`key_points`**: Often empty or redundant with other fields
4. **`citations`**: Often empty, not used in current letter template
5. **`metadata`**: Technical file metadata not relevant to letter content

### Architecture Alignment
This optimization aligns with the "Enhanced Document Analysis Extraction" strategy documented in `memory-bank/activeContext.md`:
- Extract comprehensive detail **once** during document analysis
- Use **concise structured data** in downstream prompts
- Avoid token overflow while maintaining quality

---

## Related Documentation
- `memory-bank/activeContext.md` - Enhanced Document Analysis strategy
- `docs/FULL_DOCUMENT_CONTENT_ARCHITECTURE.md` - Document content handling
- `DATA_PROPAGATION_ANALYSIS.md` - Data flow through system phases
