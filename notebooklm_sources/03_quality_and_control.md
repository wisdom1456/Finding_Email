# Quality and Control

## Why Attorneys Can Trust Harvey AI

This document addresses quality assurance, accuracy mechanisms, and attorney control features built into the Legal Document Analysis Portal. These features exist to neutralize skepticism and provide attorneys with confidence in the system's outputs.

## Attorney Responsibility and Control

### Fundamental Principle

**The attorney remains responsible for all final work product.** This is not negotiable or qualified. Every finding, every citation, every legal conclusion must be reviewed and approved by the attorney before client delivery.

### What This Means in Practice

The system does not:
- Send communications directly to clients
- Make final decisions about case strategy
- Provide legal advice autonomously
- Replace attorney judgment

The system does:
- Provide a first draft of document analysis
- Generate professionally formatted findings emails
- Cite all facts to source documents for verification
- Accelerate the initial document review process

### The Junior Associate Analogy

Think of this system as a junior associate who:
- Never gets tired
- Never misses a document
- Always cites sources
- Works at high speed

But like any junior associate, the work product requires senior attorney review, fact verification, and editorial judgment before client delivery.

## Citation System

### How Citations Work

Every fact stated in the findings email is linked to its source document.

**Citation Format:**
Facts appear with inline citations using clean filename references:
- `[Client_Intake_Form.pdf]`
- `[Police_Report_2024-01-15.pdf]`
- `[Contract_Agreement.docx]`

**Citation Verification:**
Attorneys can click any citation to open the source document and verify the fact against the original context. This enables rapid fact-checking without manually searching through documents.

**Why This Matters:**
Traditional document review requires attorneys to manually track which facts came from which documents. Missing citations or incorrect attributions damage client trust and create liability risk. Automated citation linking makes verification straightforward and reduces errors.

### Citation Accuracy

The system extracts facts from document text and maintains the link between fact and source. However, attorneys must verify:
- The extracted fact accurately represents the source document content
- The fact is not taken out of context
- The source document is reliable and admissible
- The citation reference is clear and traceable

**Best Practice:**
Review every citation for high-stakes facts (dates, amounts, legal conclusions) by clicking through to the source document.

## Statute Citation Validation

### The Hallucination Problem

Large language models sometimes generate false legal citations. An AI system might reference "Florida Statute 123.456" when no such statute exists. This creates serious professional liability for attorneys who rely on invented citations.

### The Solution: Verified Legal Corpus

Harvey AI validates all statute citations against a verified legal corpus:

**Florida Legal Corpus**
- 51 verified statutes covering primary practice areas
- Complete coverage in consumer protection, landlord-tenant, foreclosure, construction, and personal injury
- Each statute manually verified against official Florida Statutes

**New Mexico Legal Corpus**
- 42 verified statutes covering primary practice areas
- 8 verified procedural rules (NMRA)
- Complete coverage in consumer protection (UPA), landlord-tenant (UORRA), construction, liens, foreclosure, insurance, and torts
- Each statute manually verified against official New Mexico Statutes Annotated

### How Validation Works

When generating findings emails and legal analysis, the AI system:
1. Identifies potentially relevant statutes based on case facts
2. Validates each statute citation against the legal corpus
3. Rejects citations to statutes not in the verified corpus
4. Provides only verified statute references in output

**What This Prevents:**
- Invented statute citations
- Incorrect statute numbers
- References to repealed or non-existent laws
- Cross-jurisdiction citation errors

**What This Requires:**
Attorneys must verify that cited statutes are applicable to the specific case facts and procedural posture. The system validates that citations are real, not that they are strategically appropriate.

### Jurisdiction Limitations

The verified legal corpus covers only Florida and New Mexico civil litigation. Attorneys attempting to use the system for:
- Federal claims
- Out-of-state matters (other than FL or NM)
- Criminal law
- Immigration, bankruptcy, or patent/trademark matters

...will receive unreliable or incomplete statute citations because the legal corpus does not cover these areas.

**Explicit Warning:**
The system displays jurisdiction warnings when creating cases to prevent misuse outside supported practice areas.

## Multi-Stage Quality Checks

### Document Processing Stage

**Quality Indicators:**
After document upload and text extraction, each document receives a quality status:
- **Ready:** Text successfully extracted, good quality
- **Needs Review:** Text extracted but quality is questionable
- **Extraction Failed:** No text extracted (requires OCR)
- **Corrupted:** File is damaged and cannot be processed
- **Download Failed:** Upload did not complete successfully

**Verification Hub:**
Attorneys use the Verification Hub to triage document quality issues before analysis. This prevents analysis failures and improves output quality by identifying problematic documents early.

**OCR Quality:**
GPT-4o Vision is used for OCR on scanned documents and images. OCR quality depends on:
- Scan resolution (300+ DPI recommended)
- Image clarity and contrast
- Text size and font legibility
- Absence of handwriting or annotations

Attorneys can retry OCR on failed documents or re-upload higher-quality scans.

### Analysis Stage

**Multi-Model Architecture:**
Different AI models handle different tasks based on their strengths:
- **GPT-4o Vision:** OCR and image text extraction (optimized for visual processing)
- **GPT-4o-mini:** Legal issue identification (fast, cost-effective)
- **GPT-4.1:** Comprehensive document analysis (balanced speed and quality)
- **GPT-5.2:** Findings letter generation (advanced reasoning, professional tone)

**Why This Matters:**
Using specialized models for specific tasks improves accuracy and reduces errors. Fast models handle simple tasks; advanced reasoning models handle complex synthesis.

### Output Stage

**Professional Formatting Validation:**
Generated findings emails follow attorney-style formatting standards:
- Clear section structure
- Professional tone and language
- Proper citation formatting
- Client-appropriate complexity level

**Consistency:**
All findings emails follow the same structural template, ensuring consistent quality across cases and attorneys.

## Accuracy Positioning

### What the System Does Well

**Fact Extraction:**
The system is highly accurate at extracting facts from clear, well-formatted documents. Text-based PDFs and Word documents produce the most reliable results.

**Timeline Construction:**
Date extraction and event sequencing are generally accurate when dates are explicitly stated in documents.

**Citation Linking:**
Automatic citation of facts to source documents is reliable and saves significant attorney time.

**Professional Formatting:**
Generated letters consistently meet professional formatting standards.

### What Requires Attorney Verification

**Legal Issue Identification:**
The AI auto-selects the most likely legal issue based on intake form content. Attorneys must verify this selection is correct before running analysis.

**Statute Applicability:**
While statute citations are validated against the legal corpus (preventing hallucination), attorneys must verify that cited statutes apply to the specific case facts and procedural posture.

**Fact Context:**
Extracted facts may be accurate but taken out of context. Attorneys must verify that facts are presented with appropriate context in the findings email.

**Legal Conclusions:**
The AI generates legal analysis and conclusions based on extracted facts. Attorneys must verify that conclusions are legally sound and strategically appropriate.

**Tone and Language:**
The AI generates professional language, but attorneys may need to adjust tone based on client sophistication, case sensitivity, or firm style preferences.

### Accuracy Limitations

The system cannot:
- Understand implied or unstated facts
- Assess witness credibility
- Evaluate evidence admissibility
- Make strategic judgments about case strengths or weaknesses
- Replace attorney professional judgment

The system excels at:
- Processing large document volumes quickly
- Extracting explicitly stated facts
- Organizing information into structured formats
- Generating professional first drafts

## Verification Best Practices

### For Every Case

1. **Verify Legal Issue Selection:** Confirm the AI-selected legal issue is correct before running analysis.

2. **Review Document Quality:** Use Verification Hub to ensure all documents have successful text extraction before analysis.

3. **Check Key Facts:** Verify high-stakes facts (dates, amounts, parties, legal conclusions) by clicking citations to review source documents.

4. **Validate Statute Citations:** Confirm cited statutes are applicable to case facts and procedural posture.

5. **Edit for Tone:** Adjust language and tone to match client sophistication and case sensitivity.

6. **Proofread Output:** Review the complete findings email for grammatical errors, formatting issues, and logical flow.

### For High-Stakes Cases

For cases involving significant damages, complex legal issues, or high client visibility:

1. **Manual Citation Audit:** Verify every citation by reviewing the source document, not just high-stakes facts.

2. **Independent Legal Research:** Confirm statute recommendations through independent research, not just corpus validation.

3. **Peer Review:** Have another attorney review the AI-generated output before finalization.

4. **Client Communication:** Explain to clients that AI was used in document review, and that all outputs were attorney-reviewed and approved.

### Red Flags Requiring Extra Scrutiny

Stop and conduct additional verification if you notice:
- Facts that seem inconsistent with case narrative
- Statute citations that seem tangentially related to case facts
- Missing facts you expected to see from uploaded documents
- Unusual or unexpected legal conclusions
- Tone or language that seems inappropriate

In these cases, conduct manual document review to verify AI-generated outputs before relying on them.

## Data Security and Confidentiality

### Authentication and Access Control

- Supabase authentication with JWT tokens
- Row-level security enforces user access restrictions
- Each attorney sees only their own cases
- Practice administrators can access all cases for their organization

### Data Storage

- All case data stored in Supabase PostgreSQL database
- Documents stored securely with access controls
- API keys and credentials managed via environment variables
- No case data shared with third parties

### AI Provider Security

- OpenAI API is used for AI processing
- Documents and text are sent to OpenAI for analysis
- OpenAI's data use policies apply (attorneys should review OpenAI's terms)
- No long-term data retention by OpenAI for API usage

**Attorney Consideration:**
Attorneys should verify that uploading client documents to an AI-powered system is consistent with client confidentiality obligations and firm policies.

## Support and Issue Reporting

### When to Report Issues

Report technical issues if:
- Analysis fails repeatedly on the same case
- Document extraction fails on clearly readable documents
- Generated output contains obvious errors or nonsensical content
- System is unresponsive or displays error messages

### What to Include in Reports

- Case ID or client name
- Description of the issue
- Screenshots of errors (if applicable)
- Document types involved
- Steps to reproduce the issue

### Feedback Loop

The system is actively maintained and improved based on attorney feedback. Feature requests, usability improvements, and bug reports are reviewed and prioritized by the development team.

Attorneys are encouraged to provide feedback on:
- Output quality and accuracy
- Workflow efficiency
- Feature requests
- User interface improvements

## Final Reminder

**This system accelerates legal work. It does not replace legal judgment.**

Attorneys remain responsible for verifying facts, checking citations, validating legal conclusions, and approving all client communications. The system is a tool designed to remove low-value work so attorneys can focus on high-value strategic thinking and client service.

Trust the system to handle initial document processing. Verify the outputs before relying on them. Use attorney judgment for all final decisions.
