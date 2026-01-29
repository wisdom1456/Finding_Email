# Attorney Workflow

## How Attorneys Actually Use Harvey AI

This document describes the operational workflow for using the Legal Document Analysis Portal. These instructions mirror the in-app help documentation and represent the standard operating procedure for case intake and document analysis.

## Five-Step Workflow

### Step 1: Create a New Case

Attorneys begin by creating a case record for each client matter.

**Action:**
- Navigate to the Dashboard or Cases page
- Click the "New Case" button
- Enter the client's full name
- Optionally add a reference number (e.g., Clio matter ID, internal case number)
- Click "Create" to initialize the case

**Purpose:**
Each case represents one client matter. The reference number enables linking to existing practice management systems for workflow continuity.

**Best Practice:**
Use consistent naming conventions for client names to enable search and filtering across cases.

### Step 2: Upload Documents

After creating a case, attorneys upload all relevant case documents.

**Action:**
- Navigate to the case detail page
- Use drag-and-drop or click "Upload Documents"
- Select multiple files for batch upload
- Wait for upload confirmation (progress indicators show upload status)

**Supported Document Formats:**
- PDF (standard digital and scanned)
- DOCX and DOC (Microsoft Word)
- TXT (plain text)
- CSV (spreadsheet data)
- JPG and PNG (images with automatic OCR)
- EML (email files)
- HTML (web pages)

**File Size Limits:**
Maximum 50MB per file. Batch uploads support multiple files simultaneously.

**Best Practice:**
Upload core documents first for better analysis context:
- Client intake form
- Police reports or incident documentation
- Contracts or agreements
- Key correspondence
- Supporting evidence

**Document Quality Considerations:**
The system provides document quality indicators after upload. Documents that fail extraction or have quality issues can be managed through the Verification Hub before analysis.

### Step 3: Start Analysis

Once documents are uploaded, attorneys initiate AI analysis.

**Action:**
- Click "Start Analysis" button on the case page
- The system automatically identifies the most likely legal issue based on intake form content
- Verify or change the AI-selected legal issue before proceeding
- Confirm analysis start

**What Happens During Analysis:**
The system processes documents through multiple stages:

1. **Document Extraction:** Text is extracted from all uploaded files. Scanned documents and images undergo OCR using GPT-4o Vision.

2. **Fact Identification:** AI identifies key facts, dates, parties, and events from extracted text.

3. **Timeline Construction:** Events are organized chronologically to establish case timeline.

4. **Legal Issue Analysis:** AI analyzes extracted facts against the selected legal issue category, identifies relevant statutes, and constructs legal arguments.

5. **Findings Email Generation:** AI produces a professional findings email with all facts cited to source documents.

**Progress Monitoring:**
Real-time progress updates appear during analysis via Server-Sent Events (SSE). Attorneys see which stage is currently processing and estimated time remaining.

**Analysis Time:**
- Small cases (1-5 documents): 1-2 minutes
- Medium cases (5-15 documents): 2-4 minutes
- Large cases (15+ documents): 4-8 minutes

OCR processing adds 30-60 seconds per scanned document.

**Pre-Analysis Document Validation:**
If documents are missing extracted text when analysis begins, the system displays a warning modal with three options:
- Run OCR on All (recommended for scanned documents)
- Skip These Documents (proceed without them)
- Cancel (return to document management)

### Step 4: Review Results

When analysis completes, attorneys review the generated outputs.

**What to Review:**

**Findings Email**
- Professional attorney-style formatting
- Structured sections: introduction, findings, legal analysis, conclusion
- Every fact cited to source document using clean filename references
- Citations appear as `[Client_Intake_Form.pdf]` or `[Contract_Agreement.docx]`

**Document Summaries**
- Extracted key facts from each uploaded document
- Summary of relevant content per document
- Document-by-document breakdown for verification

**Case Analysis**
- Structured timeline of events
- Identified legal issues with supporting facts
- Recommended statute citations validated against legal corpus
- Analysis of strengths and potential challenges

**Citation Verification**
Click any citation in the findings email to view the source document and verify the extracted fact matches the original context.

**Best Practice:**
Review findings email paragraph by paragraph. Verify that:
- Facts are accurately extracted
- Citations link to correct source documents
- Legal analysis matches case specifics
- Tone and language are appropriate for client delivery

### Step 5: Generate and Export Letter

After reviewing and editing the findings email, attorneys finalize the output.

**Action:**
- Edit letter content directly in the interface as needed
- Adjust language, tone, or structure
- Add or remove sections based on attorney judgment
- Export as HTML for further editing in Microsoft Word or other applications

**Critical Requirement:**
Always review the generated letter before sending to clients. The output is a draft designed for attorney review and revision, not autonomous final work product.

**Export Options:**
HTML format enables further formatting in Word, Google Docs, or other word processing software while preserving structure and formatting.

## Advanced Features

### Verification Hub (Document Management)

The Verification Hub provides advanced document quality management before analysis.

**Access:**
Click "Verification Hub" button on the case page.

**Triage Mode:**
Documents are grouped by status:
- **Critical:** Failed downloads or corrupted files requiring re-upload
- **Needs Attention:** Extraction failed or quality is questionable
- **Ready:** Successfully processed with good quality text extraction
- **Duplicates:** Same file uploaded multiple times
- **Excluded:** Manually excluded from analysis

**Bulk Actions:**
- Select multiple documents with failed extractions
- Click "Run OCR on All" to process batch OCR using GPT-4o Vision
- Verify extraction quality after OCR completes

**Individual Document Actions:**
- Click "Retry" on any failed document to re-run OCR
- Preview document content to verify extraction quality
- Exclude documents from analysis if not relevant
- Mark duplicates for exclusion

**Best Practice:**
Use Verification Hub before running analysis to identify and fix document issues. This prevents analysis failures and improves output quality.

### Clio Integration

Attorneys can import matters directly from Clio practice management software.

**Setup:**
1. Click "Clio" button in the navigation bar
2. Click "Connect to Clio" in the modal
3. Authorize the connection on Clio's website (OAuth redirect)
4. Return to portal (green indicator shows successful connection)

**Importing Matters:**
1. Click "Clio" button while connected
2. Search for matters by client name or matter number
3. Select a matter to import
4. System automatically imports:
   - Matter details and metadata
   - Associated documents
   - Email communications
   - Notes and case information

**Workflow Benefit:**
Eliminates manual document downloads and uploads. All Clio matter content becomes available for analysis immediately after import.

### Re-Running Analysis

Attorneys can re-analyze cases at any time.

**Use Cases:**
- New documents added after initial analysis
- Different legal issue category selected for analysis
- Initial analysis failed or produced poor results

**Action:**
Click "Start Analysis" again on the case page. Previous analysis results are replaced with new analysis.

**Best Practice:**
If preserving previous analysis results is important, create a duplicate case before re-running analysis.

## Document Quality Best Practices

### For Scanned Documents

**Optimal Scanning Settings:**
- Resolution: 300 DPI or higher
- Color: Grayscale or full color (not black and white)
- Format: PDF or JPG
- Orientation: Correct orientation before upload

**OCR Success Factors:**
- Clear, high-contrast text
- Minimal handwriting or annotations
- Standard fonts (not decorative or script fonts)
- Clean scans without shadows or distortion

### For Digital Documents

**Preferred Formats:**
- Native PDF (text-based, not scanned)
- DOCX for Word documents
- Original digital files rather than printouts

**Avoid:**
- Screenshots of documents (use original files)
- Low-resolution images
- Heavily redacted documents where context is lost

### For Email Files

**Best Practice:**
- Export emails as .EML format from email client
- Include full email headers for date and party identification
- Preserve attachments by saving them as separate files

## Common Workflow Patterns

### Standard Intake Case

1. Create case immediately after client consultation
2. Upload intake form, contracts, and correspondence
3. Run analysis within 24 hours of intake
4. Review findings email and verify facts
5. Edit and send letter to client within 48 hours of intake

**Time Savings:**
Reduces intake processing from 3-4 hours to 30-60 minutes of attorney time.

### Clio-Integrated Workflow

1. Receive new matter in Clio
2. Open Harvey AI portal
3. Click Clio button and search for matter
4. Import matter directly (documents auto-upload)
5. Run analysis immediately
6. Review and finalize findings email

**Time Savings:**
Eliminates manual document download and upload. Reduces intake processing to 20-40 minutes of attorney time.

### Complex Multi-Document Cases

1. Create case and upload all available documents (15-30 files)
2. Open Verification Hub and review document quality
3. Run bulk OCR on any scanned documents
4. Verify all documents show "Ready" status
5. Run analysis
6. Review generated outputs carefully due to document volume
7. Use citation links to verify facts across multiple documents

**Time Savings:**
Reduces complex case review from 8-12 hours to 2-3 hours of attorney time.

## Attorney Responsibilities

### Before Analysis

- Verify uploaded documents are relevant to the case
- Ensure document quality is sufficient (use Verification Hub)
- Confirm correct legal issue category is selected
- Review that all key documents are included

### During Analysis

- Monitor progress for any errors or failures
- Wait for analysis to complete (do not navigate away if using SSE progress)

### After Analysis

- Review findings email completely before any client communication
- Verify all facts against source documents using citation links
- Check that statute citations are appropriate and accurate
- Edit language, tone, and structure as needed for client delivery
- Confirm professional formatting is maintained

### Always Remember

The attorney remains responsible for all final work product. This system accelerates document review and drafting but does not replace attorney judgment, verification, or approval.
