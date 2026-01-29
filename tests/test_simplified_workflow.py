#!/usr/bin/env python3
"""Test script for the simplified 2-call workflow.

Uses the Velasco test data to validate:
1. Intake form extraction
2. Document summarization (AI Call #1)
3. Findings letter generation (AI Call #2)
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from legal_portal.core.document_processor import DocumentProcessor
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.utils.openai_client import OpenAIClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class MockFile:
    """Mock Streamlit UploadedFile for testing."""

    def __init__(self, file_path: Path):
        self.path = file_path
        self.name = file_path.name
        self.type = self._get_mime_type(file_path)
        self.size = file_path.stat().st_size
        self._content = file_path.read_bytes()
        self._position = 0

    def _get_mime_type(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".txt": "text/plain",
        }
        return mime_types.get(ext, "application/octet-stream")

    def read(self):
        """Read file content."""
        content = self._content[self._position :]
        self._position = len(self._content)
        return content

    def seek(self, position):
        """Seek to position."""
        self._position = position

    def getvalue(self):
        """Get file content as bytes."""
        return self._content


async def _generate_document_summaries(openai_client, intake_content: str, case_documents: list) -> str:
    """AI Call #1: Generate contextual summaries of case documents."""
    prompt = f"""You are a legal document analyst. Given the client intake information below, summarize the following case documents. Focus on key facts, dates, parties, amounts, obligations, issues, and evidence relevant to the case.

INTAKE INFORMATION:
{intake_content[:3000]}

---
CASE DOCUMENTS TO SUMMARIZE:

"""

    for i, doc in enumerate(case_documents, 1):
        prompt += f"\n--- Document {i}: {doc.file_name} ---\n"
        content_preview = doc.content[:8000] if len(doc.content) > 8000 else doc.content
        prompt += f"{content_preview}\n"

    prompt += """
---
OUTPUT FORMAT:
For each document, provide:
1. Document Name
2. Document Type (contract, correspondence, disclosure, evidence, etc.)
3. Key Facts (parties, dates, amounts, obligations)
4. Issues/Problems Identified
5. Relevance to Case

Keep summaries concise but thorough. Focus on legally significant information.
"""

    response = openai_client.chat.completions.create(
        model="gpt-5-mini",  # Use gpt-5-mini for fast, cost-effective summarization
        messages=[
            {"role": "system", "content": "You are a precise legal document analyst."},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=4000,  # GPT-5 models use max_completion_tokens
    )

    return response.choices[0].message.content


async def run_test():
    """Run the test workflow."""
    print("=" * 80)
    print("SIMPLIFIED 2-CALL WORKFLOW TEST")
    print("=" * 80)
    print()

    # Load environment variables
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not found in .env file")
        return False

    print("✅ OpenAI API key loaded from .env")
    print()

    # Find test data
    test_folder = Path(
        "test_data/Velasco, Miguel [MetLife]/Shared Folder with Client/Shared with Bernhardt Riley"
    )
    if not test_folder.exists():
        print(f"❌ ERROR: Test folder not found: {test_folder}")
        return False

    print(f"📁 Test folder: {test_folder}")
    print()

    # Load files
    files = list(test_folder.glob("*"))
    files = [f for f in files if f.is_file() and not f.name.startswith(".")]

    if not files:
        print("❌ ERROR: No files found in test folder")
        return False

    print(f"📄 Found {len(files)} files:")
    for f in files:
        print(f"   - {f.name} ({f.stat().st_size:,} bytes)")
    print()

    # Identify intake form
    intake_file = None
    case_files = []

    for f in files:
        if "intake" in f.name.lower():
            intake_file = f
        else:
            case_files.append(f)

    if not intake_file:
        print("❌ ERROR: No intake form found (looking for 'intake' in filename)")
        return False

    print(f"📋 Intake form: {intake_file.name}")
    print(f"📑 Case documents: {len(case_files)}")
    for f in case_files:
        print(f"   - {f.name}")
    print()

    # Initialize services
    print("🔧 Initializing services...")
    openai_client_wrapper = OpenAIClient()
    openai_client = openai_client_wrapper.client
    doc_processor = DocumentProcessor()
    json_processing_service = JsonProcessingService(client=openai_client, config={})
    print("✅ Services initialized")
    print()

    # Create mock file objects
    mock_intake = MockFile(intake_file)
    mock_case_docs = [MockFile(f) for f in case_files]

    # STEP 1: Process intake form
    print("=" * 80)
    print("STEP 1: Processing Intake Form")
    print("=" * 80)
    start_time = datetime.now()

    processed_intake = await doc_processor.process_documents_from_streamlit(
        [mock_intake], intake_filenames=[mock_intake.name]
    )

    if not processed_intake:
        print("❌ ERROR: Failed to process intake form")
        return False

    intake_content = processed_intake[0].content
    duration = (datetime.now() - start_time).total_seconds()

    print(f"✅ Intake form processed in {duration:.2f}s")
    print(f"   Characters extracted: {len(intake_content):,}")
    print(f"   Preview: {intake_content[:200]}...")
    print()

    # STEP 2: Process case documents
    print("=" * 80)
    print("STEP 2: Processing Case Documents")
    print("=" * 80)
    start_time = datetime.now()

    processed_case_docs = await doc_processor.process_documents_from_streamlit(
        mock_case_docs, intake_filenames=[]
    )

    if not processed_case_docs:
        print("❌ ERROR: Failed to process case documents")
        return False

    duration = (datetime.now() - start_time).total_seconds()

    print(f"✅ {len(processed_case_docs)} case documents processed in {duration:.2f}s")
    for doc in processed_case_docs:
        print(f"   - {doc.file_name}: {len(doc.content):,} chars")
    print()

    # STEP 3: AI Call #1 - Generate document summaries
    print("=" * 80)
    print("STEP 3: AI Call #1 - Generating Document Summaries")
    print("=" * 80)
    start_time = datetime.now()

    document_summaries = await _generate_document_summaries(
        openai_client, intake_content, processed_case_docs
    )

    duration = (datetime.now() - start_time).total_seconds()

    print(f"✅ Document summaries generated in {duration:.2f}s")
    print(f"   Summary length: {len(document_summaries):,} characters")
    print("   Preview:")
    print("   " + "─" * 76)
    preview_lines = document_summaries[:500].split("\n")
    for line in preview_lines:
        print(f"   {line}")
    print("   " + "─" * 76)
    print()

    # STEP 4: AI Call #2 - Generate findings email
    print("=" * 80)
    print("STEP 4: AI Call #2 - Generating Findings Email")
    print("=" * 80)
    start_time = datetime.now()

    findings_letter_html = json_processing_service.generate_html_letter(
        intake_data=intake_content,
        document_summaries=document_summaries,
    )

    duration = (datetime.now() - start_time).total_seconds()

    print(f"✅ Findings letter generated in {duration:.2f}s")
    print(f"   Letter length: {len(findings_letter_html):,} characters")
    print()

    # STEP 5: Save outputs
    print("=" * 80)
    print("STEP 5: Saving Outputs")
    print("=" * 80)

    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)

    # Save document summaries
    summaries_file = output_dir / "document_summaries.txt"
    summaries_file.write_text(document_summaries, encoding="utf-8")
    print(f"✅ Document summaries saved: {summaries_file}")

    # Save findings email
    letter_file = output_dir / "findings_letter.html"
    letter_file.write_text(findings_letter_html, encoding="utf-8")
    print(f"✅ Findings letter saved: {letter_file}")

    print()
    print("=" * 80)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print()
    print(f"📂 Output files saved to: {output_dir.absolute()}")
    print(f"   - {summaries_file.name}")
    print(f"   - {letter_file.name}")
    print()
    print("💡 Open the HTML file in your browser to view the findings email")

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(run_test())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
