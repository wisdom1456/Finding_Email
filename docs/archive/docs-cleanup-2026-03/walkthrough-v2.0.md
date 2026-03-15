# Case Analysis Portal — Walkthrough (v2.0.0)

A step-by-step guide to using the Case Analysis Portal, from connecting to Clio through generating findings emails and demand letters.

---

## Step 1: Connect to Clio (~2 minutes, one-time setup)

1. Click **"Connect to Clio"** in the navigation bar.
2. A modal will open — click **"Authorize"** to sign in with your Clio credentials.
3. Once connected, the portal can access your Clio matters and documents.

[Screenshot: Clio connection modal in the navigation bar]

> **Tip:** You only need to connect once. The portal remembers your Clio authorization across sessions.

---

## Step 2: Create a Case (~30 seconds)

1. From the **Cases** page, click **"New Case"**.
2. Select a Clio matter to import documents from.
3. The portal imports documents from Clio automatically. Small images under 50KB (email signature logos, social media icons) are filtered out to reduce noise.

[Screenshot: New case creation with Clio matter selection]

> **What's happening:** The portal pulls all documents from the selected Clio matter, identifies their types, and prepares them for analysis. HEIC photos (iPhone format) are automatically converted to JPEG.

---

## Step 3: Document Verification & OCR (~5-15 minutes)

Once documents are imported, use the **Verification Hub** to review and prepare them for analysis.

### 3a. Open the Verification Hub

Click the **"Verification Hub"** button on the case page. Your documents are organized into triage groups:

- **Critical** — Documents that need immediate attention (missing text, failed extraction)
- **Needs Attention** — Documents that may need OCR or manual review
- **Ready** — Documents with extracted text, ready for analysis
- **Duplicates** — Exact-duplicate documents identified by content hash
- **Excluded** — Documents filtered out or blacklisted

[Screenshot: Verification Hub showing triage groups with document counts]

### 3b. Run OCR

For documents that need text extraction (scanned PDFs, images, photos):

1. Click **"Run OCR on All"** to process all documents that need extraction, or
2. Select individual documents and click **"Run OCR"** for targeted extraction.

OCR uses GPT-5.2 Vision and typically takes 30-60 seconds per document.

[Screenshot: OCR in progress with status indicators]

### 3c. Signature Review

The Verification Hub identifies documents where signatures are expected and shows whether signed versions have been found. This helps you spot missing executed agreements.

[Screenshot: Signature reconciliation showing signed vs. unsigned status]

> **Tip:** The portal uses document content (not just filenames) to match signed and unsigned versions, which helps when documents have opaque or auto-generated filenames.

---

## Step 4: Run Analysis (~2-8 minutes)

1. From the case page, click **"Run Analysis"**.
2. Choose your analysis type:
   - **Standard Analysis** — for most cases
   - **Multi-Stage Analysis** — comprehensive pipeline using GPT-5.4, recommended for complex cases
3. Watch real-time progress updates as the analysis runs.

[Screenshot: Analysis in progress with streaming progress indicators]

> **What's happening:** The portal processes each document, identifies legal issues, assesses risks, and compiles a comprehensive case analysis. For large cases (50+ documents), a map-reduce pipeline is used to handle the volume more reliably.

**Time estimates:**
| Case Size | Approximate Time |
|---|---|
| Small (1-5 documents) | 1-2 minutes |
| Medium (5-15 documents) | 2-4 minutes |
| Large (15+ documents) | 4-8 minutes |
| Very large (50+ documents) | 10-15 minutes |

---

## Step 5: Review Results

Results are available in the **results workspace**, which stays open as you navigate within the case. The workspace has these tabs:

- **Case Analysis** — Summary of legal issues, risks, and key findings
- **Gaps** — Missing information, evidence gaps, and areas needing attention. Includes per-gap resolution notes.
- **Full Analysis** — Detailed, magazine-style analysis of all documents
- **Document Review** — Per-document analysis details
- **Findings & Demand** — Generated findings emails and demand letters
- **Case Chat** — AI assistant for asking follow-up questions about the case
- **Quality Report** — Analysis quality metrics and confidence scores

[Screenshot: Results workspace showing the Case Analysis tab]

> **Tip:** The results workspace persists when you switch between case tabs, so you don't lose your place.

---

## Step 6: Generate Letters (~1-2 minutes each)

### Findings Email

1. Go to the **Findings & Demand** tab in the results workspace.
2. Click **"Generate Findings Email"**.
3. The portal generates a findings email using a multi-step process:
   - **Draft** — Initial generation with combined law + application format
   - **Critic review** — Automated review for structure and substance
   - **Polish** — Final readability pass
4. Review the output and copy or download.

[Screenshot: Generated findings email with section headers visible]

### Demand Letter

1. From the same tab, click **"Generate Demand Letter"**.
2. The portal generates a demand letter based on the case analysis and gap assessment.
3. Review and edit as needed.

[Screenshot: Demand letter generation interface]

### Recommendation Letters

Additional letter types are available:
- **Proceed** — Recommendation to proceed with the case
- **Declination** — Recommendation to decline the case
- **Settlement Advisory** — Settlement analysis and recommendations
- **Request for Documents** — Letter requesting additional documentation

---

## Settings

Access **Settings** from the navigation bar to customize:

### AI Model Preferences

Choose which AI model powers each task:

| Task | Default | Description |
|---|---|---|
| Document Analysis | GPT-5 Mini | Processes and extracts information from documents |
| Findings Email & Demand Letter | GPT-5.4 | Generates findings emails, demand letters, and recommendation letters |
| Case Chat | GPT-5 Mini | Powers the case chat assistant |
| Multi-Stage Analysis | GPT-5.4 | Runs the comprehensive case analysis pipeline |

Available models: **GPT-5.4** (most capable), **GPT-5 Mini** (fast and cost-effective), **GPT-5 Nano** (fastest, lighter tasks), **GPT-5.2** (previous generation).

Click **"Reset to Defaults"** to restore recommended settings.

[Screenshot: Settings page showing AI model preferences]

### Other Settings

- **Contact Information** — Used in letter headers (name, firm, address, phone, email)
- **Jurisdiction** — Default jurisdiction for legal analysis
- **Document Blacklist** — Automatically exclude specific document names during Clio import

---

## Tips & Troubleshooting

- **Analysis seems slow?** Large cases with many documents take longer. The progress bar shows real-time status. If the connection drops, the portal is designed to automatically attempt to recover and continue.
- **Documents missing text?** Use the Verification Hub to identify documents needing OCR and run extraction.
- **Findings email looks different?** The v2.0 format uses a combined law + application structure. This is the new default — let us know if you have feedback.
- **Want to change AI models?** Go to Settings → AI Model Preferences. The defaults are designed to balance quality and speed for most cases.

---

## Need Help?

- Click **Help** in the navigation bar for detailed documentation and the "What's New" section.
- Contact [support contact] for technical issues or questions.

---

*All `[Screenshot: ...]` placeholders must be replaced with actual screenshots from the validated preview deployment before distribution.*
