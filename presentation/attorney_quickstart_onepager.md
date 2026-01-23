# Harvey AI — Attorney Quick Start Guide

**Legal Document Analysis Portal**  
_Faster intake. Cleaner analysis. Verified citations._

---

## What This Is

Harvey AI is Bernhardt Riley's internal legal document analysis portal. It analyzes case documents using AI and generates professional findings letters with verified citations. You remain in control—this accelerates the first pass, not replaces your judgment.

---

## 5-Step Workflow

### 1. Create a New Case

- Go to **Dashboard** or **Cases** page
- Click **"New Case"** button
- Enter client name and optional reference number (e.g., Clio matter ID)
- Click **"Create"**

### 2. Upload Documents

- Drag-and-drop files onto the upload area, or click **"Upload Documents"**
- Supported formats: **PDF, DOCX, DOC, TXT, CSV, JPG, PNG, EML, HTML**
- Batch upload supported (up to 50MB per file)
- **Best practice:** Upload core documents first (intake form, police report, contracts)

### 3. Run Analysis

- Click **"Start Analysis"** button
- Analysis takes **1-8 minutes** for typical cases
- Watch real-time progress updates (document extraction → fact identification → legal analysis → letter generation)
- AI automatically identifies the most likely legal issue (you can verify or change before analysis)

### 4. Review Results

- Review **Findings Letter** (professional format, document-cited facts)
- Check **Document Summaries** (extracted key facts from each document)
- Verify **Case Analysis** (timeline, legal issues, statute recommendations)
- Click any citation to verify against source document

### 5. Generate & Export Letter

- Review and edit the findings letter as needed
- Export as **HTML** for further editing in Word or other tools
- **Critical:** Always review before sending to clients—this is a draft, not final output

---

## Supported Jurisdictions

Harvey AI is optimized for **Florida and New Mexico civil litigation**:

- **Florida:** 51 verified statutes (consumer protection, landlord-tenant, foreclosure, construction, personal injury)
- **New Mexico:** 42 verified statutes (UPA, UORRA, construction & liens, foreclosure, insurance & torts)

**Not supported:** Federal claims, criminal law, immigration, bankruptcy, patent/trademark

---

## Key Features

### ✓ Multi-Format Document Support
PDF (standard & scanned), Word, images (with OCR), emails, plain text, CSV

### ✓ Verified Statute Citations
Validated against Florida (51) and New Mexico (42) legal corpus to prevent AI hallucination

### ✓ Verification Hub
Manage document quality, run bulk OCR, exclude duplicates, verify extraction success

### ✓ Clio Integration
Import matters directly from Clio (click "Clio" in navigation to connect)

### ✓ Professional Formatting
Findings letters follow attorney-style structure with clean filename citations

### ✓ Real-Time Progress
Server-Sent Events (SSE) provide live updates during analysis

---

## Document Quality & OCR

**What if documents fail to process or have no text?**

- **Before Analysis:** If documents are missing text, you'll see a warning with options to:
  - **Run OCR on All** (recommended—uses GPT-4o Vision)
  - **Skip These Documents** (proceed without them)
  - **Cancel** (go back and fix manually)

- **Verification Hub:** Click "Verification Hub" button to manage document issues:
  - View documents by status: Critical, Needs Attention, Ready, Duplicates, Excluded
  - Run bulk OCR on failed extractions
  - Retry individual documents
  - Verify extraction quality

**Pro Tip:** OCR works best on clear, high-resolution scans (300+ DPI recommended)

---

## Best Practices

### Do:
✓ Upload intake forms for better context  
✓ Verify AI-selected legal issue before running analysis  
✓ Review generated letters before sending to clients  
✓ Check citations against source documents  
✓ Use Verification Hub to triage document issues  
✓ Run analysis on new intakes to save 2-4 hours per case  

### Don't:
✗ Send letters without attorney review  
✗ Upload sensitive documents outside Florida/New Mexico civil matters  
✗ Rely on AI output without verification  
✗ Skip document quality checks before analysis  

---

## FAQ

**How long does analysis take?**  
- Small cases (1-5 documents): 1-2 minutes  
- Medium cases (5-15 documents): 2-4 minutes  
- Large cases (15+ documents): 4-8 minutes  

**Can I edit the generated letter?**  
Yes! The letter is fully editable. Think of it as a first draft from a thorough junior associate.

**How accurate is the AI?**  
High-quality analysis, but attorney review is required. Every fact is cited to source documents for verification. Statute citations are validated against verified legal corpus to prevent hallucination.

**Can I re-run analysis?**  
Yes. Add new documents and re-analyze, or change the selected legal issue and run again.

**What if analysis fails?**  
Check document quality (corrupted files, poor scans). Use Verification Hub to identify problematic documents. Re-upload clear copies if needed.

**How do I connect to Clio?**  
Click **"Clio"** in the navigation bar → **"Connect to Clio"** → authorize on Clio's site → return to portal (green indicator shows connection).

---

## Support & Feedback

- **In-App Help:** Click **"Help"** in navigation for detailed documentation
- **Q&A Session:** Wednesday meeting (date TBD)
- **Feedback Loop:** Report bugs, request features, suggest improvements to [your system administrator]

---

## Key Reminder

**You remain responsible for final output.**  
Harvey AI accelerates document review and drafting—it does not replace attorney judgment. Always verify citations, check facts against source documents, and review letters before client delivery.

---

**Think of this as a junior associate that never gets tired, never misses a document, and always cites their sources.**

---

**Version:** 2.0  
**Last Updated:** January 23, 2026  
**Status:** Production Ready  
**System Name (Internal):** Legal Document Analysis Portal  
**System Name (Public):** Harvey AI
