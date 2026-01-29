# How-To Guide

## Complete Workflow Overview

**End-to-End Process for Case Analysis & Findings Email:**

```
1. REGISTER → 2. CONNECT CLIO → 3. CREATE CASE → 4. RUN OCR → 5. ANALYZE → 6. GENERATE FINDINGS EMAIL
   ↓              ↓                ↓                ↓             ↓            ↓
Sign Up &    Connect Clio    Import Clio      Extract Text   Run Case    Generate Findings
Request      Integration     Matter with      from All       Analysis    Email & Download
Approval     (One-time)      Documents        Documents      (2-5 min)   HTML (30-90s)
```

**Quick Navigation:**
- [User Registration](#1-user-registration--approval)
- [Clio Integration](#clio-integration)
- [Creating Cases from Clio](#creating-a-case-from-clio)
- [OCR Text Extraction](#using-ocr-to-extract-text-from-documents)
- [Generating Findings Email](#generating-the-findings-email)
- [Case Chat](#case-chat)
- [Troubleshooting](#common-issues--solutions)

---

## Getting Started

### 1. User Registration & Approval

**New users must be approved before accessing the application.**

#### Step-by-Step:

1. **Go to the registration page**
   - Navigate to the sign-up form
   - Enter your email, password, and full name
   - Click the **"Sign Up"** button

2. **You will see the "Account Pending Approval" page**
   - Message: "Your account has been created successfully, but it requires administrator approval"
   - Note: "You will receive an email notification once your account has been approved"

3. **Request approval**
   - Email **Franklin@BRFlorida.com** with:
     - Your name
     - Email address used for registration
     - Brief reason for access
   
4. **Wait for approval** (typically 1-2 business days)
   - You will receive an email notification when approved
   - Log in again to access the full application

---

## Clio Integration

### Connecting Your Clio Account (First Time Setup)

**You must connect Clio before you can create cases from Clio matters.**

#### Step-by-Step:

1. **Navigate to the Cases page**
   - Click **"Cases"** in the main navigation menu
   - OR go directly to any case detail page

2. **Find the "Clio Integration" card**
   - Scroll down to locate the card titled **"Clio Integration"**
   - It will show: "Connect your Clio account to import matters, communications, and documents"

3. **Click the "Connect to Clio" button**
   - Large blue button with a lightning bolt icon
   - Button text: **"Connect to Clio"**

4. **Authorize on Clio's website**
   - You will be redirected to Clio's authorization page
   - Log in with your Clio username and password
   - Click **"Allow"** or **"Authorize"** to grant access

5. **Return to the application**
   - You will automatically be redirected back
   - The "Clio Integration" card now shows: **"Connected to Clio"** with a green checkmark
   - You'll see your Clio User ID displayed

**You only need to connect once. Your connection will remain active.**

---

## Creating a Case from Clio

### Step-by-Step Walkthrough

**IMPORTANT:** This is the preferred method for creating cases. It automatically imports all matter data and documents.

#### 1. Navigate to "Create New Case"

- Click **"Cases"** in the top navigation bar
- Click the **"New Case"** button (green button, top right)
- OR click the **"+ New Case"** button on the dashboard

#### 2. Verify Clio is Connected

- At the top of the page, the subtitle should read:
  - "Search for a Clio matter to automatically populate case details and documents"
- If you see "Enter case details manually" instead, click back to Cases and connect Clio first (see section above)

#### 3. Search for the Clio Matter

**In the "Find Your Clio Matter" section:**

- **Label:** "Client Name or Matter Number"
- **Enter at least 3 characters** in the search box:
  - Client name (e.g., "John Smith"), OR
  - Matter number (e.g., "2024-001")
- Click the **"Search"** button (gray button with magnifying glass icon)

#### 4. Review Search Results

You'll see a list of matching matters showing:
- **Matter number** (in blue, top left)
- **Client name** (bold, below matter number)
- **Description** (gray italicized text)
- **Practice area** (small icon + text)
- **Status** and **Open date** (small gray text at bottom)

#### 5. Create the Case

- Find the correct matter in the search results
- Click the **"Create Case"** button (green button on the right side of the matter card)

#### 6. Confirm Import

- A confirmation dialog appears:
  - "Create a new case from [Matter Number] - [Client Name]?"
  - "All documents will be imported automatically."
- Click **"OK"** to proceed

#### 7. Monitor Import Progress

**An import progress modal will appear showing:**
- "Creating case..." → "Importing documents..." → "Analyzing documents..."
- Progress bar with percentage
- Current document being processed
- Statistics: Documents imported, total size, intake forms found

**Do not close your browser during this process.**

#### 8. Import Complete

- When finished, you'll see: "Import Complete!" with a checkmark
- Statistics summary showing:
  - Total documents imported
  - Intake forms identified
  - Document types processed
- Click **"View Case"** button to go to the case detail page

**You are now ready to review documents and run analysis.**

---

## Using OCR to Extract Text from Documents

### When Do I Need OCR?

You need to run OCR when documents show:
- **Red warning badge:** "Extraction Failed"
- **Yellow badge:** "Needs Review"
- **No extracted text** in the document preview
- **Scanned PDFs** or **images** with text

### Three Ways to Run OCR

#### Method 1: Bulk OCR (Recommended for Multiple Documents)

**From the Case Detail Page:**

1. **Navigate to your case**
   - Click **"Cases"** → Select your case from the list

2. **Scroll to the Documents section**
   - Look for documents with warning badges or "needs review" status

3. **Click "Run OCR on X Docs" button**
   - Gray button appears above the document list
   - Shows count of documents needing extraction (e.g., "Run OCR on 5 Docs")
   - Icon: Spinning arrow icon

4. **Wait for processing**
   - Each document processes in sequence
   - You'll see: "Processing X Doc(s)..." with a spinning icon
   - Progress updates as each completes

5. **Verify results**
   - When complete, badges change from red/yellow to green "Ready"
   - Documents now have extracted text

**From the Verification Hub:**

1. **Go to the case detail page**
2. **Click the "Review & Verify" tab** OR **"Verification Hub"** button
3. **Look for "Pending Review" section** (yellow lightning bolt icon)
4. **Click "Run OCR on X Doc(s)"** button (gray button with spinning arrow)
5. **Wait for extraction** to complete (progress bar shows updates)

#### Method 2: Individual Document OCR

**For a single problematic document:**

1. **Find the document** in the document list
2. **Look for the red "Extraction Failed" badge**
3. **Click "Try Vision OCR" button** (blue button with spinning arrow icon)
4. **Wait 30-60 seconds** for processing
5. **Document updates** to show "Ready" status with green checkmark

#### Method 3: From Document Review Modal

1. **Click "View/Edit" button** on a document (eye icon)
2. **In the document preview modal:**
   - If extraction failed, you'll see a warning at the top
   - Click **"Run OCR Extraction"** or **"Try Vision OCR"** button
3. **Wait for extraction** to complete
4. **Review the extracted text** in the text area
5. **Click "Save"** if you make any edits

### After Running OCR

#### Verify Extracted Text:

1. **Click "View/Edit"** on the document (eye icon button)
2. **Review the "Extracted Text" field**
3. **Check for accuracy:**
   - Are all words captured correctly?
   - Is the formatting readable?
   - Are there any garbled characters?

4. **Edit if needed:**
   - Click in the text area to make corrections
   - Click **"Save Changes"** button (blue button at bottom)

5. **Mark as verified:**
   - Click **"Mark Verified"** button (green button with checkmark)
   - This confirms the document is ready for analysis

---

## Quick Reference - Button Guide

| Action | Where to Find | Button Name | Icon |
|--------|---------------|-------------|------|
| Sign Up | Registration Page | "Sign Up" | None |
| Connect Clio | Any Case Page → Clio Integration Card | "Connect to Clio" | ⚡ Lightning |
| Disconnect Clio | Any Case Page → Clio Integration Card | "Disconnect Clio" | None |
| Create New Case | Cases Page | "New Case" OR "+ New Case" | None |
| Search Matters | Create Case Page → Find Your Clio Matter | "Search" | 🔍 Magnifying glass |
| Create from Matter | Search Results → Matter Card | "Create Case" | None |
| Run Bulk OCR | Case Page → Documents Section | "Run OCR on X Docs" | 🔄 Spinning arrow |
| Single Document OCR | Document Card | "Try Vision OCR" | 🔄 Spinning arrow |
| View Document | Document Card | "View/Edit" | 👁️ Eye |
| Mark Verified | Document Card | "Mark Verified" | ✓ Checkmark |
| View Case | Import Complete Modal | "View Case" | None |
| Start Analysis | Case Page → Analysis Section | "Start Analysis" | None |
| View Results | Case Page → After Analysis | "View Results" | None |
| Switch to Findings & Demand | Results Page → Top Tabs | "Findings & Demand" tab | None |
| Generate Findings Email | Results → Letters Tab | "Generate Email" | None |
| Download Findings Email | Results → After Generation | "Download HTML" | None |
| Generate Demand | Results → Letters Tab → Demand Section | "Generate Demand Letter" | None |
| Calculate Amount | Results → Demand Letter Form | "Calculate" | None |
| Open Case Chat | Results Page → Top Tabs | "Case Chat" tab | None |
| Send Chat Message | Case Chat → Input at bottom | "Send" (or press Enter) | None |

---

## Using OCR to Extract Text from Documents

### When to Use OCR

Use OCR (Optical Character Recognition) when:
- Documents appear to have no extracted text
- Documents show "extraction failed" status
- You need to extract text from scanned PDFs or images
- Documents are marked as "needs review"

### How to Run OCR

#### Option 1: Individual Document Extraction

1. Navigate to the case detail page
2. Find the document in the document list
3. Click **"Try Vision OCR"** or **"Run OCR"** button on the document card
4. Wait for extraction to complete (may take 30-60 seconds per document)

#### Option 2: Bulk OCR Extraction

1. Navigate to the case detail page
2. Look for documents that need text extraction (marked with warning indicators)
3. Click **"Run OCR on X Docs"** button (appears when documents need extraction)
4. The system will process all documents that need OCR
5. Monitor progress as each document is processed

#### Option 3: From Verification Hub

1. Navigate to the case detail page
2. Go to the **"Verification Hub"** or document review section
3. Documents needing OCR will be grouped under **"Pending Review"**
4. Click **"Run OCR on X Doc(s)"** button
5. Wait for all documents to be processed

### After OCR Extraction

- Review extracted text by clicking **"View/Edit"** or **"Review Text"** on the document
- Verify the text is accurate and complete
- Mark documents as **"Verified"** once text extraction is confirmed
- Documents with extracted text are ready for case analysis

---

## Generating the Findings Email

### Overview

After creating a case and importing documents from Clio, you can analyze the case and generate a professional findings email to send to your client. This is a multi-step process.

### Complete Workflow (Step-by-Step)

#### Step 1: Verify All Documents Have Text

**Before running analysis, ensure all documents have extracted text.**

1. **Navigate to your case**
   - Click **"Cases"** → Select your case

2. **Check document status**
   - Look at document cards in the document list
   - Documents should show green **"Ready"** badges
   - If you see red **"Extraction Failed"** or yellow **"Needs Review"** badges:
     - Click **"Run OCR on X Docs"** button (see OCR section above)
     - Wait for all extractions to complete

3. **Optional: Use Verification Hub**
   - Click the **"Review & Verify"** tab or **"Verification Hub"** button
   - This shows documents organized by status
   - Click **"Mark Verified"** on each document after reviewing text

**Tip:** Analysis works best when all documents have clean, verified text.

---

#### Step 2: Start Case Analysis

1. **On the case detail page, scroll to the Analysis section**
   - Look for the **"Analysis"** section (blue header)
   - Or look for a blue **"Start Analysis"** button near the top

2. **Click "Start Analysis" button**
   - Large blue button with white text
   - May say **"Start Analysis"** (first time) or **"Run New Analysis"** (subsequent times)

3. **Wait for analysis to complete**
   - You'll see a progress modal showing:
     - "Initializing analysis..."
     - "Processing documents..."
     - "Analyzing case..."
     - Progress percentage
   - **Do not close your browser**
   - Analysis typically takes 2-5 minutes depending on case complexity

4. **Analysis completion**
   - Progress modal shows: "Analysis Complete!" with checkmark
   - You'll see analysis results on the page
   - A **"View Results"** button appears

---

#### Step 3: Navigate to Results

1. **Click "View Results" button**
   - Blue button that appears after analysis completes
   - OR click the **"Results"** tab at the top of the case page

2. **You'll see the Results page with several tabs:**
   - **Analysis** (default view)
   - **Documents**
   - **Letters** ← Generate findings email and demand letter
   - **Case Chat** ← Ask questions about your case with AI (see [Case Chat](#case-chat))
   - **Quality Report**

---

#### Step 4: Generate Findings Email

1. **Click the "Findings & Demand" tab**
   - Located in the tab bar at the top of the results page
   - Tab shows: **"Findings & Demand"**

2. **Find "Findings Email" section**
   - First card on the page
   - Header: **"Findings Email"**
   - Subtitle: "Generate a client-ready findings email on demand."

3. **Click "Generate Email" button**
   - Large blue button on the right side
   - Button text: **"Generate Email"**

4. **Wait for generation**
   - Button changes to show: **"Generating..."** with spinning icon
   - Findings email generates in real-time (you'll see text appearing)
   - Typically takes 30-90 seconds
   - **Do not close or navigate away**

5. **Review the generated findings email**
   - Email appears in a preview frame below
   - Scroll through to review content
   - The findings email includes:
     - Professional formatting
     - Case summary
     - Document analysis
     - Legal assessment
     - Recommendations

---

#### Step 5: Download the Findings Email

1. **Click "Download HTML" button**
   - Gray button appears above the email preview
   - Located on the right side
   - Button text: **"Download HTML"**

2. **Save the file**
   - File downloads as: `findings-email-[case-id].html` (or similar)
   - Save to your desired location

3. **Open and use the findings email**
   - Open the HTML file in any web browser
   - Print to PDF if needed
   - Copy content into your email client to send to your client
   - Edit in HTML editor if customization needed

---

### Optional: Generate Demand Letter

**After generating the findings email, you can also create a demand letter.**

1. **Stay on the "Findings & Demand" tab**
   - Scroll down to **"Demand Letter"** section

2. **Fill in demand letter details:**
   - **Opposing Party:** Select from dropdown (e.g., "John Doe (Defendant)")
   - **Demand Amount ($):** Enter amount or click **"Calculate"** button for AI suggestion
   - **Payment Deadline:** Select timeframe (default: "10 business days")
   - **Specific Demands:** Enter any additional demands (optional)

3. **Click "Generate Demand Letter" button**
   - Blue button on the right
   - Wait for generation (30-90 seconds)

4. **Download demand letter**
   - Click **"Download HTML"** button above demand letter preview
   - File saves as: `demand-letter-[party-name]-[case-id].html`

---

### Case Chat

**The Case Chat lets you ask questions about your case and get answers grounded in your analysis, documents, and jurisdiction.**

#### Where to Find It

1. **Go to the Results page** (after analysis has completed).
2. **Click the "Case Chat" tab** in the top tab bar (same row as Analysis, Documents, Letters, Quality Report).
3. You’ll see the **"Case Chat Assistant"** panel with the subtitle: *"Ask questions about this case—responses include specific facts and citations."*

#### What It Does

- **Uses your case context:** The assistant has access to your case analysis, including:
  - Case summary and practice area  
  - Parties and their roles  
  - Timeline highlights (with source documents)  
  - Financial summary (amounts, payment types)  
  - Primary legal issues  
  - Relevant statutes for your jurisdiction (e.g., Florida, New Mexico)  

- **Cites sources:** Answers reference specific documents and statutes (e.g., *"According to the Contract dated…"*, *"Fla. Stat. § 83.51"*).

- **Respects limits:** If the case data doesn’t support an answer, it says so. It focuses on your jurisdiction’s state civil law.

- **Keeps context:** The last several messages in the conversation are used so you can ask follow-up questions.

#### How to Use It

1. **Click the "Case Chat" tab** on the Results page.
2. **Type your question** in the text box at the bottom. Placeholder: *"Ask a question about case facts, documents, or legal strategy..."*
3. **Send the message** by clicking the blue **"Send"** button or pressing **Enter**.
4. **Watch the response:** The assistant’s reply streams in as it’s generated.
5. **Ask follow-ups:** Type another question; the chat uses recent messages as context.

#### Example Questions You Can Ask

- *"What are the main legal issues in this case?"*  
- *"Summarize the timeline of key events."*  
- *"Which documents support the claim for [amount/topic]?"*  
- *"What Florida statutes apply to this situation?"*  
- *"What is the opposing party’s role and what have they done?"*  
- *"What are the strongest facts in our favor?"*  
- *"What deadlines or important dates should I be aware of?"*

#### When Chat Is Available

- **Requires completed analysis:** Case Chat uses the latest analysis. If you haven’t run analysis, or it failed, you must run (or re-run) analysis first.
- **Same Results page:** Chat is on the same Results view as the Analysis, Documents, Letters, and Quality Report tabs—no separate page.

---

### Tips for Better Findings Emails

#### Before Analysis:
✅ Verify all documents have extracted text (no red/yellow badges)  
✅ Mark key documents as verified in Verification Hub  
✅ Ensure intake form or client communications are included  

#### After Generation:
✅ Review the findings email thoroughly before sending to client  
✅ Check that all facts and dates are accurate  
✅ Verify legal citations are appropriate  
✅ Customize tone or add personal notes if needed  

---

### What's Included in the Findings Email?

The AI-generated findings email typically includes:

- **Case Summary:** Overview of client situation and legal issues
- **Document Analysis:** Key findings from uploaded documents
- **Timeline of Events:** Chronological summary of important dates
- **Legal Assessment:** Analysis of case strength and applicable laws
- **Financial Summary:** Damages, amounts owed, payments made
- **Party Analysis:** Roles and relationships of all parties
- **Communication Summary:** Key correspondence and interactions
- **Recommendations:** Next steps and legal strategy
- **Professional Formatting:** Email-ready HTML suitable for sending to clients

---

### Time Estimates for Each Step

**From Case Creation to Finished Findings Email:**

| Step | Estimated Time | Notes |
|------|----------------|-------|
| **Account Approval** | 1-2 business days | One-time only, email Franklin@BRFlorida.com |
| **Connect Clio** | 1-2 minutes | One-time setup |
| **Search & Create Case** | 30 seconds | Depends on search results |
| **Import Documents** | 1-5 minutes | Depends on number/size of documents |
| **OCR Extraction (Bulk)** | 30-60 sec per document | Only needed for scanned PDFs/images |
| **Document Verification** | 2-10 minutes | Optional but recommended |
| **Run Analysis** | 2-5 minutes | Longer for complex cases (10+ docs) |
| **Generate Findings Email** | 30-90 seconds | Real-time generation |
| **Generate Demand Letter** | 30-90 seconds | Optional |
| **Download & Review** | 1-2 minutes | Final review before sending |

**Total Time (Typical Case):** 15-30 minutes from case creation to finished findings email  
**Total Time (First Case):** Add 1-2 days for account approval + Clio connection

---

## Common Issues & Solutions

### "Account Pending Approval" Message

**Problem:** After signing up, I can't access the application.

**Solution:**
1. This is expected behavior for new accounts
2. Check your inbox for approval notification (may take 1-2 business days)
3. Email **Franklin@BRFlorida.com** to expedite approval
4. Once approved, log out and log back in

---

### "Clio Integration" Card Says "Not Connected"

**Problem:** I can't search for Clio matters.

**Solution:**
1. Find the **"Clio Integration"** card on any case page
2. Click the blue **"Connect to Clio"** button
3. Log in to Clio and click **"Authorize"**
4. Wait to be redirected back (this happens automatically)
5. Verify you see **"Connected to Clio"** with a green checkmark

---

### "No Matters Found" When Searching

**Problem:** Search returns zero results.

**Solution:**
1. Check that you entered **at least 3 characters**
2. Try searching by:
   - Client's full name or part of it (e.g., "Smith" instead of "John Smith")
   - Matter number without dashes (e.g., "2024001" instead of "2024-001")
3. Verify your Clio account has access to this matter
4. Try **disconnecting** and **reconnecting** Clio (see button in Clio Integration card)

---

### Documents Show "Extraction Failed" (Red Badge)

**Problem:** Documents imported but have no text.

**Solution:**
1. These are typically scanned PDFs or images
2. **Option A - Bulk:** Click **"Run OCR on X Docs"** button above document list
3. **Option B - Single:** Click **"Try Vision OCR"** button on the document card
4. Wait 30-60 seconds per document for processing
5. Click **"View/Edit"** to verify text was extracted correctly

---

### Import Progress Stuck or Frozen

**Problem:** Import modal shows no progress for several minutes.

**Solution:**
1. **Do not close the browser** - large imports can take time
2. Check your internet connection
3. For very large matters (50+ documents), expect 5-10 minutes
4. If truly stuck after 15 minutes:
   - Refresh the page
   - Go to **Cases** page
   - Your case may have been created - check the list
   - If created but incomplete, you can manually upload missing documents

---

### Can't Find "Run OCR" Button

**Problem:** I need to extract text but don't see the button.

**Solution:**
1. Check if documents already have text:
   - Click **"View/Edit"** on a document
   - Look for text in "Extracted Text" field
   - If text exists, OCR is not needed
2. If text is missing:
   - Scroll to top of document list
   - Look for gray button with spinning arrow icon
   - Button appears only when documents need extraction

---

### Error: "Failed to Create Case"

**Problem:** Getting an error after clicking "Create Case" button.

**Solution:**
1. Check that Clio connection is still active (green checkmark in Clio Integration card)
2. Verify you have permission to access this matter in Clio
3. Try searching for and selecting the matter again
4. If error persists:
   - Use **"Create case manually without Clio"** link at bottom of page
   - Upload documents manually after case creation
   - Contact **Franklin@BRFlorida.com** for assistance

---

### "Start Analysis" Button is Disabled or Missing

**Problem:** Can't find or click the Start Analysis button.

**Solution:**
1. **Check document status:**
   - You need at least 1 document with extracted text
   - Red "Extraction Failed" badges must be resolved with OCR
   - Upload or import documents first if list is empty

2. **Look for warning messages:**
   - "Upload documents to start analysis" → Need to add documents
   - "Documents need text extraction" → Run OCR first
   
3. **Verify you're on the case detail page:**
   - URL should be: `/app/cases/[case-id]`
   - Not the "New Case" or "Cases List" page

---

### Analysis Fails or Gets Stuck

**Problem:** Analysis starts but shows error or never completes.

**Solution:**
1. **Wait longer:** Complex cases can take 5-10 minutes
2. **Check progress modal:** Look for specific error messages
3. **Refresh the page:** Sometimes analysis completes but UI doesn't update
4. **Verify all documents have text:**
   - Go back to document list
   - Run OCR on any failed documents
   - Try analysis again
5. **Contact support** if issue persists with case ID

---

### "Generate Email" Button Does Nothing

**Problem:** Clicking button but findings email doesn't generate.

**Solution:**
1. **Check browser console for errors:**
   - Press F12 → Console tab
   - Look for red error messages
2. **Verify analysis completed successfully:**
   - Go back to case page
   - Check that analysis status shows "Completed"
   - Re-run analysis if status is "Failed" or "Partial"
3. **Check internet connection:** Generation requires active connection
4. **Try refreshing the page** and clicking again
5. **Clear browser cache:**
   - Press F12 → Right-click refresh → "Empty Cache and Hard Reload"

---

### Case Chat Says "Requires Latest Analysis" or Won't Send

**Problem:** Case Chat tab shows an error or messages don't send.

**Solution:**
1. **Case Chat uses your latest case analysis.** You must run analysis first (see [Start Case Analysis](#step-2-start-case-analysis)).
2. **If you see "Case chat requires the latest analysis":**
   - Go back to the case detail page (not Results).
   - Click **"Start Analysis"** or **"Run New Analysis"**.
   - Wait for analysis to complete, then open Results → **Case Chat** again.
3. **If "Send" is disabled:** Type at least one character in the question box; the button enables when there is text.
4. **If responses fail or time out:** Check your internet connection and try a shorter question.

---

### Generated Findings Email is Incomplete or Poor Quality

**Problem:** Findings email generated but missing information or seems inaccurate.

**Solution:**
1. **Review source documents:**
   - Go to Results → Documents tab
   - Check that all key documents have accurate extracted text
   - Click "View/Edit" to verify text quality

2. **Check document verification:**
   - Return to case page → Verification Hub
   - Ensure important documents are marked "Verified"
   - Unverified docs may be given less weight

3. **Re-run analysis with corrections:**
   - Fix any document text issues (edit extracted text)
   - Mark all documents as verified
   - Run analysis again
   - Generate new findings email with improved analysis

4. **Check for missing documents:**
   - Compare Clio matter to imported documents
   - Manually upload any missing critical documents
   - Re-run analysis

---

### Can't Download HTML Findings Email

**Problem:** "Download HTML" button doesn't work or file is corrupted.

**Solution:**
1. **Check browser download settings:**
   - Ensure downloads are not blocked
   - Check download folder permissions
2. **Try alternative method:**
   - Right-click in the findings email preview
   - Select "Save As" or "Print to PDF"
3. **Copy content directly:**
   - Click in the findings email preview
   - Ctrl+A (Select All) → Ctrl+C (Copy)
   - Paste into Word or email client
4. **Generate again:** Sometimes re-generation fixes corruption issues

---

## Navigation Reference

### Where to Find Key Features

| Feature | How to Get There |
|---------|------------------|
| **Register** | Click "Sign Up" from login page |
| **Connect Clio** | Cases → Any case → Scroll to "Clio Integration" card → "Connect to Clio" |
| **Create Case from Clio** | Cases → "New Case" button → Enter search term → "Search" → "Create Case" |
| **Verify Documents** | Case Detail → "Review & Verify" tab OR "Verification Hub" button |
| **Run OCR (Bulk)** | Case Detail → Scroll to documents → "Run OCR on X Docs" |
| **Run OCR (Single)** | Case Detail → Document card → "Try Vision OCR" |
| **View Document Text** | Case Detail → Document card → "View/Edit" button |
| **Start Analysis** | Case Detail → Scroll to "Analysis" section → "Start Analysis" button |
| **View Results** | Case Detail → After analysis → "View Results" button OR "Results" tab |
| **Generate Findings Email** | Results page → "Letters" tab → "Generate Email" button |
| **Download Findings Email** | Results → Letters tab → After generation → "Download HTML" button |
| **Generate Demand Letter** | Results → Letters tab → Fill form → "Generate Demand Letter" button |
| **Case Chat** | Results page → "Case Chat" tab → Type question → "Send" button |
| **Request Approval** | Email **Franklin@BRFlorida.com** |

---

## Tips for Best Results

### Before Creating a Case from Clio:

✅ Connect Clio first (one-time setup)  
✅ Verify the matter has documents attached in Clio  
✅ Ensure you have good internet connection (imports can be large)  
✅ Don't close your browser during import  

### After Case Import:

✅ Run OCR on any documents showing "Extraction Failed" or "Needs Review"  
✅ Click "View/Edit" to verify extracted text is accurate  
✅ Mark documents as "Verified" after reviewing text  
✅ Only then proceed to case analysis  

### For Scanned Documents:

✅ Use Vision OCR (automatically selected)  
✅ Allow 30-60 seconds per page for processing  
✅ Review extracted text carefully for accuracy  
✅ Edit any errors in the text area before saving  

---

## Support & Contact

**For questions, issues, or account approval:**

📧 Email: **Franklin@BRFlorida.com**

Include in your message:
- Your name and email address
- Specific issue or question
- Screenshots (if applicable)
- Case ID or matter number (if relevant)
