# Harvey AI Screenshot Plan

## Purpose

This document specifies the exact screenshots required for the attorney adoption presentation. Each screenshot must represent the actual production UI—no mockups, no fabrications.

---

## Screenshot Requirements

### General Guidelines

- **Resolution:** 1920x1080 minimum for clarity
- **Browser:** Chrome or Firefox (production environment)
- **Crop:** Remove browser chrome (address bar, bookmarks) unless context is needed
- **Annotations:** No annotations in raw screenshots; add callouts in PowerPoint if needed
- **File Format:** PNG for lossless quality
- **Naming Convention:** `harvey_ai_[location]_[description].png`

---

## Required Screenshots

### Screenshot 1: Dashboard / New Case

**Slide:** Interface overview (if added as separate slide)

**Purpose:** Show attorneys where they start—the main dashboard and "New Case" button.

**UI Location:**
- Route: `/app` (Dashboard)
- Element: Main dashboard view showing case list (if any) and prominent "New Case" button

**What to Capture:**
- Full dashboard layout
- "New Case" button clearly visible
- Navigation bar at top (showing "Dashboard", "Cases", "Help", "Clio" options)
- Empty state message if no cases exist, or sample case list if cases exist

**Notes:**
- Use a test account with 0-2 cases so the UI is clean and uncluttered
- Ensure "New Case" button is prominently visible

**Filename:** `harvey_ai_dashboard_new_case.png`

---

### Screenshot 2: Document Upload

**Slide:** Interface overview (if added as separate slide)

**Purpose:** Demonstrate the drag-and-drop document upload interface.

**UI Location:**
- Route: `/app/cases/[case_id]` (Case detail page)
- Element: Document upload section showing drag-and-drop area

**What to Capture:**
- Document upload interface (drag-and-drop zone)
- "Upload Documents" button or area
- Visual indicators for supported file types (if visible)
- Optional: Show 2-3 uploaded documents below the upload area to demonstrate batch capability

**Notes:**
- Capture during an active case with the upload area visible
- If possible, show the drag-and-drop visual state (hovering over drop zone) or the standard state
- Include a few uploaded documents to show successful uploads

**Filename:** `harvey_ai_document_upload.png`

---

### Screenshot 3: Analysis Results

**Slide:** Interface overview (if added as separate slide)

**Purpose:** Show the analysis results page with structured output.

**UI Location:**
- Route: `/app/cases/[case_id]` (Case detail page after analysis completion)
- Element: Analysis results section showing findings email preview, document summaries, or case analysis tabs

**What to Capture:**
- Analysis results view
- Findings email preview (first few paragraphs visible)
- Navigation tabs or sections (e.g., "Findings Email", "Document Summaries", "Case Analysis")
- Status indicator showing "Completed" or similar success state

**Notes:**
- Use a completed analysis (status: "completed")
- Ensure findings email content is visible but redact any sensitive client information
- Show enough content to demonstrate structure and citations

**Filename:** `harvey_ai_analysis_results.png`

---

### Screenshot 4: Findings Email with Citations

**Slide:** Interface overview (if added as separate slide)

**Purpose:** Demonstrate professional letter formatting and document-linked citations.

**UI Location:**
- Route: `/app/cases/[case_id]` (Case detail page — findings email tab/section)
- Element: Full findings email view with citations visible

**What to Capture:**
- Complete findings email section
- Professional formatting (headers, paragraphs, structure)
- **Critical:** Visible citation references (e.g., "[Client_Intake_Form.pdf]", "[Police_Report.pdf]")
- Letter structure: introduction, findings, legal analysis, conclusion sections

**Notes:**
- Zoom in enough to show citation formatting clearly
- Redact sensitive client data (names, addresses, case details) using black bars or anonymized test data
- Emphasize citation clarity—this is a trust-builder for attorneys

**Filename:** `harvey_ai_findings_letter_citations.png`

---

## Optional Screenshots (Additional Slides)

### Optional 5: Clio Integration Modal

**Purpose:** Show Clio connection interface for practice management integration.

**UI Location:**
- Route: Click "Clio" button in navigation → Clio modal appears
- Element: Clio connection modal showing "Connect to Clio" button or connected status

**What to Capture:**
- Clio modal with connection button
- If connected: green indicator showing successful connection
- Matter search interface (if available)

**Filename:** `harvey_ai_clio_integration.png`

---

### Optional 6: Verification Hub

**Purpose:** Demonstrate document quality management and bulk OCR capability.

**UI Location:**
- Route: `/app/cases/[case_id]` → Click "Verification Hub" button
- Element: Verification Hub interface showing document status triage (Critical, Needs Attention, Ready)

**What to Capture:**
- Verification Hub triage view
- Documents grouped by status (Critical, Needs Attention, Ready, Duplicates, Excluded)
- Bulk action buttons (e.g., "Run OCR on All")
- Document quality indicators

**Filename:** `harvey_ai_verification_hub.png`

---

### Optional 7: Analysis Progress (SSE Streaming)

**Purpose:** Show real-time progress updates during analysis.

**UI Location:**
- Route: `/app/cases/[case_id]` during active analysis
- Element: Progress bar or status messages showing analysis stages

**What to Capture:**
- Progress bar or spinner
- Real-time status messages (e.g., "Extracting text from documents...", "Analyzing legal issues...")
- Stage indicators (if visible)

**Filename:** `harvey_ai_analysis_progress.png`

---

## Screenshot Checklist

Before using screenshots in the presentation, verify:

- [ ] All screenshots are from the production environment (not local dev)
- [ ] No sensitive client data is visible
- [ ] UI elements match the in-app help documentation language
- [ ] Resolution is high enough for projection (1920x1080 minimum)
- [ ] File format is PNG (lossless quality)
- [ ] Filenames follow naming convention
- [ ] Screenshots accurately represent current UI (no outdated interfaces)

---

## Notes on Test Data

When capturing screenshots, use anonymized test data:

- **Client Name:** "Jane Doe" or "John Smith"
- **Case Reference:** "TEST-001" or similar
- **Document Names:** Generic but realistic (e.g., "Client_Intake_Form.pdf", "Contract_Agreement.docx")
- **Dates:** Recent but non-specific (e.g., "January 2026")
- **Content:** Redact or use placeholder legal text that demonstrates structure without exposing real case details

---

## Integration into Presentation

Screenshots will be manually inserted into Slide 8 placeholder areas or added as additional slides if needed. Each screenshot should:

1. Be inserted at actual size (no stretching or distortion)
2. Maintain aspect ratio when resizing
3. Include a thin border (2pt, accent color) for visual clarity
4. Have a caption below identifying the UI section shown

---

**Document Version:** 2.0  
**Last Updated:** January 23, 2026  
**Prepared for:** Harvey AI Attorney Adoption Presentation
