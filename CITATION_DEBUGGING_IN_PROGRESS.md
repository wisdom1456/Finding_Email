# Citation Debugging - In Progress

## Issue Reported
User reports seeing only ONE letter labeled "clean" but it contains citations.

## Expected Behavior
- **Tab 1:** "📧 Client Letter (Clean)" - NO citations
- **Tab 2:** "📚 Attorney Letter (With Citations)" - WITH citations `[Source: filename.pdf]`

## Investigation So Far

### ✅ Citation Removal Regex - WORKS CORRECTLY
Tested the regex pattern in `remove_citations_from_letter()`:
```python
citation_pattern = r"[\(\[]Source:[^\)\]]+[\)\]]"
```

**Test Results:**
- Successfully removes `[Source: Contract.pdf]`
- Successfully removes `(Source: Contract.pdf)`
- Cleans up spacing and punctuation correctly

### ✅ Backend Processing - APPEARS TO WORK
From `backend.log`:
```json
{"message": "Successfully created both versions: clean (4317 chars) and cited (4605 chars)"}
```

This shows:
- Clean version: 4,317 characters
- Cited version: 4,605 characters
- **Difference: 288 characters** (reasonable for inline citations)

### ❓ Possible Root Causes

**Theory 1: Exception Handler Triggered**
- If citation processing throws an exception (line 599-615 in `main_processor.py`)
- Fallback code sets BOTH letters to the same value:
  ```python
  letter_with_citations = improved_letter
  clean_letter = improved_letter  # BOTH THE SAME
  ```

**Theory 2: Session State Assignment Issue**
- Both `main_letter` and `main_letter_with_citations` getting set to same value
- Unlikely given backend logs show different sizes

**Theory 3: UI Display Bug**
- Both tabs accidentally showing same session state variable
- Checked code - they show different variables (unlikely)

## Debug Code Added

### Added to Tab 1 (Client Letter):
```python
has_source_citations = "[Source:" in main_letter_content or "(Source:" in main_letter_content
if has_source_citations:
    st.error(f"🐛 DEBUG: Clean letter contains {citation_count} citation(s)")
else:
    st.success(f"✅ Clean letter has no citations")
```

### Added to Tab 2 (Attorney Letter):
```python
has_source_citations_cited = "[Source:" in cited_letter_content or "(Source:" in cited_letter_content
if has_source_citations_cited:
    st.success(f"✅ Cited letter contains {citation_count_cited} citation(s)")
else:
    st.error("🐛 DEBUG: Cited letter has NO citations")
```

### Enhanced Exception Logging:
```python
except Exception as e:
    logger.error(f"CITATION PROCESSING FAILED: {e}", exc_info=True)
    logger.error(f"Exception type: {type(e).__name__}")
    logger.error("⚠️  FALLBACK MODE: Using same letter for both versions")
```

## Next Steps

1. **User runs new analysis**
2. **Check debug output** in both tabs
3. **Check backend logs** for any "CITATION PROCESSING FAILED" errors
4. **Compare letter lengths** shown in debug vs. log file

## Files Modified

- `src/legal_portal/services/main_processor.py` (lines 568-615)
  - Added has_citations debug logging
  - Enhanced exception logging
  
- `src/legal_portal/ui/components/ui_components.py` (lines 600-680)
  - Added citation detection debug output to both tabs

## Log Commands

```bash
# Check for citation processing errors
tail -200 backend.log | grep -E "(CITATION|citation|FALLBACK|Exception)"

# Check letter creation
tail -200 backend.log | grep "Successfully created both versions"

# Check session state assignment
tail -200 backend.log | grep "Stored.*results"
```

## Current Status

**⏳ WAITING FOR USER TO RUN NEW ANALYSIS**

Once debug output is visible, we'll know:
1. Whether clean letter has citations (should be NO)
2. Whether cited letter has citations (should be YES)
3. If an exception is being thrown during processing
4. Exact character counts in session state

---

## Quick Reference

**Citation Formats to Look For:**
- `[Source: filename.pdf]`
- `(Source: filename.pdf)`

**Backend Flow:**
```
1. AI generates letter WITH citations
2. clean_filename_hashes() → letter_with_clean_filenames
3. embed_citations() → letter_with_citations (adds <sup>[1]</sup>)
4. remove_citations_from_letter() → clean_letter (strips [Source: ...])
5. format_findings_letter() → both versions formatted
6. ProcessingResult(main_letter=clean_letter, main_letter_with_citations=letter_with_citations)
```

**Session State Variables:**
- `st.session_state.main_letter` → Should be clean (no citations)
- `st.session_state.main_letter_with_citations` → Should have citations

---

## Update After Debug Output

*To be filled in after user runs analysis and reports debug output*

**Debug Output Seen:**
- Tab 1: [TO BE FILLED]
- Tab 2: [TO BE FILLED]

**Log File Errors:**
- [TO BE FILLED]

**Root Cause:**
- [TO BE DETERMINED]

**Fix Applied:**
- [TO BE DOCUMENTED]

