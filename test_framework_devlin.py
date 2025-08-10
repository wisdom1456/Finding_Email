#!/usr/bin/env python3
"""
Quick test of the updated AUTHENTIC_ATTORNEY_ADVISOR framework with Devlin case documents.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


# Add the project root to the Python path
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

from openai import OpenAI

from backend_logic.ai import AIAnalyzer
from backend_logic.email_generator import EmailGenerator


async def test_devlin_case():
    """Test the updated framework with Devlin case documents."""

    logger.info("🔍 Testing AUTHENTIC_ATTORNEY_ADVISOR Framework with Devlin Case")
    logger.info("=" * 60)

    # Initialize components
    try:
        openai_client = OpenAI()  # Uses OPENAI_API_KEY from environment
        ai_analyzer = AIAnalyzer(openai_client)
        email_generator = EmailGenerator(openai_client)
        logger.info("✅ OpenAI client and components initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenAI: {e}")
        return

    # Define the document folder
    docs_folder = "apr_samples/Devlin, Erik [MetLife]/Shared Folder with Client/Shared with Bernhardt Riley"

    if not os.path.exists(docs_folder):
        logger.info(f"❌ Document folder not found: {docs_folder}")
        return

    logger.debug(f"📁 Processing documents from: {docs_folder}")

    # Get all PDF files from the folder
    pdf_files = []
    for file in os.listdir(docs_folder):
        if file.endswith(".pdf"):
            full_path = os.path.join(docs_folder, file)
            pdf_files.append(full_path)
            logger.info(f"   📄 Found: {file}")

    if not pdf_files:
        logger.info("❌ No PDF files found in the specified folder")
        return

    logger.debug(f"\n🔄 Processing {len(pdf_files)} documents...")

    try:
        # Process the documents using the analyzer
        analysis_result = await ai_analyzer.analyze_case_documents(
            file_paths=pdf_files,
            client_name="Amber Bell & Erik Devlin",
            case_type="Contractor Dispute",
        )

        logger.info("✅ Document analysis completed")

        # Generate the email using the updated AUTHENTIC_ATTORNEY_ADVISOR framework
        logger.info(
            "\n📝 Generating findings letter with AUTHENTIC_ATTORNEY_ADVISOR framework..."
        )

        email_response = email_generator.generate_email_and_analysis_docs(
            analysis_result
        )

        logger.info("✅ Email generation completed")

        # Display the generated letter
        main_letter = email_response.get("main_letter", "")

        logger.info("\n" + "=" * 60)
        logger.info("📧 GENERATED FINDINGS LETTER (First 2000 characters)")
        logger.info("=" * 60)
        logger.info(main_letter[:2000])
        if len(main_letter) > 2000:
            logger.info(
                f"\n... [truncated, full length: {len(main_letter)} characters]"
            )

        # Save the full output for review
        output_file = "devlin_test_output.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(main_letter)

        logger.info(f"\n💾 Full output saved to: {output_file}")

        # Check for key improvements
        logger.info("\n🔍 FRAMEWORK IMPROVEMENT ANALYSIS:")
        logger.info("-" * 40)

        improvements = []
        if "1. FACTUAL SUMMARY" in main_letter or "1. " in main_letter:
            improvements.append("✅ Numbered sections with headers")
        else:
            improvements.append("❌ Missing numbered section format")

        if main_letter.count("We look forward to working") <= 1:
            improvements.append("✅ Reduced repetitive closings")
        else:
            improvements.append("❌ Still has repetitive closings")

        if (
            "strong case" not in main_letter.lower()
            and "compelling evidence" not in main_letter.lower()
        ):
            improvements.append("✅ Reduced overly optimistic language")
        else:
            improvements.append("❌ Still contains overly optimistic language")

        if "Good afternoon" in main_letter or "Dear" in main_letter:
            improvements.append("✅ Professional greeting")
        else:
            improvements.append("❌ Missing professional greeting")

        for improvement in improvements:
            logger.info(f"   {improvement}")

        logger.info(f"\n📊 Letter length: {len(main_letter)} characters")
        logger.info("🎯 Test completed successfully!")

    except Exception as e:
        logger.error(f"❌ Error during processing: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_devlin_case())
