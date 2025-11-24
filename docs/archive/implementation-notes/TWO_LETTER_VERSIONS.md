# Two Letter Versions - Client & Attorney

## Overview

The system generates **TWO versions** of the findings letter to serve different audiences:

### 1. 📧 Client Letter (Clean)
**Purpose:** Client-ready communication  
**Audience:** The client  
**Format:** Professional letter without source citations  
**Use:** Send directly to the client via email or mail

**Features:**
- Clean, readable format
- No inline citations or source references
- Professional legal tone suitable for clients
- Formatted for immediate client delivery

**Download formats:**
- PDF (for email or printing)
- HTML (for viewing/editing)
- EML (draft email with letter content)

---

### 2. 📚 Attorney Letter (With Citations)
**Purpose:** Attorney review and fact verification  
**Audience:** The attorney or legal team  
**Format:** Same letter content WITH inline source citations  
**Use:** Internal review to verify facts and sources

**Features:**
- Inline citations in format: `(Source: filename.pdf)`
- Every major fact is linked to its source document
- Enables quick fact-checking and evidence review
- Helps prepare for client discussions or follow-up questions

**Download formats:**
- HTML (for reviewing citations)
- Citation appendix (separate HTML file with all sources)
- Citation map JSON (machine-readable citation data)

---

## How It Works

### Generation Process

```
1. AI generates letter WITH inline citations
   Example: "On November 14, 2024, you entered into a contract (Source: Contract.pdf) 
             for $128,000 (Source: Contract.pdf)."

2. Post-processing creates two versions:
   ├─> Strip citations → Client Letter (Clean)
   │   "On November 14, 2024, you entered into a contract for $128,000."
   │
   └─> Keep citations → Attorney Letter (With Citations)
       "On November 14, 2024, you entered into a contract (Source: Contract.pdf) 
        for $128,000 (Source: Contract.pdf)."
```

### What Gets Cited

Every major fact includes a source citation:
- ✅ **Dates:** "on September 3, 2025 (Source: Demand Letter.pdf)"
- ✅ **Dollar amounts:** "$128,000 (Source: Contract.pdf)"
- ✅ **Party names:** "LLW Construction, Inc. (Source: Contract.pdf)"
- ✅ **Key events:** "contractor ceased work (Source: Client Notes.txt)"
- ✅ **Contractual terms:** "per the agreement (Source: Construction Agreement.pdf)"

---

## Using the Two Versions

### Recommended Workflow

1. **Generate Analysis**
   - Upload intake form and case documents
   - Review Q&A and confirm case details
   - Run full analysis

2. **Review Attorney Letter First**
   - Go to "📚 Attorney Letter (With Citations)" tab
   - Verify all facts have source citations
   - Check that citations reference the correct documents
   - Note any facts that need additional verification

3. **Review Client Letter**
   - Go to "📧 Client Letter (Clean)" tab
   - Ensure letter reads smoothly without citations
   - Check tone and messaging for client appropriateness
   - Verify no internal notes or placeholders remain

4. **Send to Client**
   - Download Client Letter (Clean) as PDF or EML
   - Customize any firm-specific details
   - Send to client

5. **Keep Attorney Letter for Files**
   - Download Attorney Letter (With Citations) for case file
   - Use as reference for client questions
   - Keep citation map for future fact verification

---

## Technical Details

### File Locations

**Backend (Streamlit):**
- `src/legal_portal/services/main_processor.py` - Lines 544-587
  - Generates both versions
  - Strips citations for clean version
  - Formats both versions

**Frontend (SvelteKit):**
- `frontend/src/routes/app/cases/[id]/results/+page.svelte` - Lines 195-264
  - Displays both versions with info banners
  - Provides download buttons

**UI Components:**
- `src/legal_portal/ui/components/ui_components.py` - Lines 588-671
  - Tab-based display of both versions
  - Color-coded info banners

### Data Models

**`ProcessingResult` (data_models.py):**
```python
main_letter: str                          # Clean version (no citations)
main_letter_with_citations: Optional[str] # Cited version (with citations)
citation_summary: Optional[Dict[str, Any]] # Stats about citations
citation_appendix: Optional[str]          # HTML appendix with all citations
citation_map: Optional[Dict[str, Any]]    # Full citation structure
```

### Services Used

1. **`CitationTrackingService`** - Manages citations
   - `create_citation_map()` - Maps facts to sources
   - `embed_citations()` - Adds inline citations
   - `remove_citations_from_letter()` - Strips citations
   - `clean_filename_hashes()` - Removes temp file hashes

2. **`DocumentFormatterService`** - Formats letters
   - `format_findings_letter()` - Applies professional styling
   - Maintains consistent formatting across versions

---

## Benefits

### For Attorneys
✅ **Fact Verification:** Quickly verify every statement has a source  
✅ **Client Prep:** Anticipate client questions by reviewing sources  
✅ **Risk Management:** Ensure no unsupported claims in letter  
✅ **Case File:** Keep cited version for reference and documentation  

### For Clients
✅ **Readability:** Clean letter without distracting citations  
✅ **Professional:** Polished communication suitable for direct delivery  
✅ **Focus:** Client focuses on legal advice, not source documentation  

### For Firm
✅ **Efficiency:** One analysis generates both versions automatically  
✅ **Quality Control:** Citations enable quick review and verification  
✅ **Compliance:** Documented sources for every factual statement  

---

## Troubleshooting

### "Cited letter not showing"
- Check that documents were processed successfully
- Verify `main_letter_with_citations` is not empty
- Check browser console for any errors

### "Citations missing in attorney letter"
- Verify prompt includes citation instructions
- Check `CitationTrackingService` is creating citation map
- Review logs for citation generation errors

### "Both versions look the same"
- Verify `remove_citations_from_letter()` is being called
- Check that citations were added before removal
- Look for `(Source: filename.pdf)` format in cited version

---

## Future Enhancements

Potential improvements:
- [ ] Side-by-side comparison view
- [ ] Clickable citations that open source document
- [ ] Citation coverage report (% of facts with sources)
- [ ] Custom citation formats (footnotes, endnotes, etc.)
- [ ] Batch download both versions as ZIP

---

## Questions?

Contact the development team or refer to:
- `CITATION_REMOVAL_IMPLEMENTATION.md` - Original implementation
- `OPTION_A_FINAL_IMPLEMENTATION.md` - Final solution details
- `CITED_LETTER_TAB_IMPLEMENTATION.md` - UI implementation notes

