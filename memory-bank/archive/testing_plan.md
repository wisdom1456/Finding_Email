# Manual Test Plan: Legal Document Analysis Portal

## 1. Test Environment Setup
- **Objective**: Ensure the application is running correctly.
- **Actions**:
    1. Verify that the Streamlit frontend is running (typically at `http://localhost:8501`).
    2. Confirm that the FastAPI backend is active (e.g., at `http://localhost:8000`).

## 2. Case Information Entry
- **Objective**: Test the case information form.
- **Actions**:
    1. Enter "Balaji Badam" for "Client Name."
    2. Enter "Test Attorney" for "Attorney Name."
    3. Enter "Badam v. Tenant" for "Case Name."

## 3. File Upload
- **Objective**: Test the file upload functionality with various formats.
- **Actions**:
    1. Upload the intake form: [`samples/Intake (General) - Balaji Badam.pdf`](samples/Intake%20(General)%20-%20Balaji%20Badam.pdf).
    2. Upload the client documents from [`samples/Badam, Balaji [MetLife]/Client Docs/`](samples/Badam,%20Balaji%20[MetLife]/Client%20Docs/) (select multiple files, including PDFs and images).

## 4. Document Processing and Analysis
- **Objective**: Execute the main processing workflow.
- **Actions**:
    1. Click the "Generate Findings" button.
    2. Monitor the progress indicators.

## 5. Results Download
- **Objective**: Verify that the results are generated and downloadable.
- **Actions**:
    1. Download the "Findings Letter" (`.eml` file).
    2. Download the "Case Analysis" (`.txt` file).
    3. Open both files to check their contents.

## 6. Multi-Format Document Test
- **Objective**: Test the system with a case involving varied document types (PDF, DOCX, EML, images).
- **Actions**:
    1. Refresh the page to start a new session.
    2. Use the "Clifton Price" documents from `samples/Price, Clifton [MetLife]/`.

Please follow these steps and report the outcome of each stage.
