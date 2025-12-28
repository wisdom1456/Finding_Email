#!/usr/bin/env python3
"""Manual smoke test script for Google Cloud Vision OCR."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from legal_portal.core.data_models import DocumentType  # noqa: E402
from legal_portal.services.file_processors.pdf_processor import process_pdf  # noqa: E402
from legal_portal.utils.logging_config import setup_logging  # noqa: E402


async def verify_file(file_path: str, label: str):
    """Verify a single file using the PDF processor.

    Args:
    ----
        file_path: Path to the PDF file
        label: Label for the file (e.g. "Intake")

    """
    print(f"\n--- Verifying {label}: {file_path} ---")
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        return

    try:
        # process_pdf should detect if OCR is needed based on heuristics.
        result = await process_pdf(
            file_path=file_path,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename=os.path.basename(file_path),
        )

        print(f"Extraction Method: {result.extraction_method}")
        print(f"OCR Provider: {result.ocr_provider}")
        print(f"Page Count: {result.page_count}")
        print(f"Content Length: {len(result.content)} chars")
        print("-" * 40)
        print(f"Preview (first 300 chars):\n{result.content[:300]}...")
        print("-" * 40)

        if result.extraction_error:
            print(f"Extraction Error: {result.extraction_error}")

        if "Google" in (result.extraction_method or ""):
            print("✅ SUCCESS: Google Cloud Vision used correctly.")
        elif "GPT-4o" in (result.extraction_method or ""):
            print("⚠️ WARNING: Fell back to GPT-4o Vision.")
        else:
            print(f"ℹ️ INFO: Standard extraction used: {result.extraction_method}")

    except Exception as e:
        import traceback

        print(f"❌ FAILED: {e}")
        traceback.print_exc()


async def main():
    """Run verification on selected files."""
    setup_logging()

    # Files selected by user
    root = Path(__file__).parent.parent
    files = [
        ("Intake", str(root / "test_data_old/Intake - Miguel and Rachael.pdf")),
        ("Scanned", str(root / "test_data_old/Tyler, Austin/Claim of Lien/Claim of Lien.pdf")),
    ]

    for label, path in files:
        await verify_file(path, label)


if __name__ == "__main__":
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON") and not os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    ):
        print("ERROR: No Google Vision credentials found in environment.")
        print(
            "Please set GOOGLE_APPLICATION_CREDENTIALS_JSON (base64) "
            "or GOOGLE_APPLICATION_CREDENTIALS (path)."
        )
        sys.exit(1)

    asyncio.run(main())
