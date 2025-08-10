#!/usr/bin/env python3
"""
Diagnostic script to validate the current state of the media processing pipeline.
This script checks for the specific issues mentioned in the conversation summary.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


def check_await_keywords(file_path):
    """Check for missing await keywords in async function calls."""
    logger.debug(f"\n🔍 Checking await keywords in {file_path}")

    with open(file_path) as f:
        content = f.read()
        lines = content.splitlines()

    issues = []

    # Look for calls to async functions without await
    async_method_pattern = r"self\._build_final_assessment_prompt\("

    for i, line in enumerate(lines, 1):
        if re.search(async_method_pattern, line):
            if "await" not in line:
                issues.append(f"Line {i}: Missing 'await' - {line.strip()}")
            else:
                logger.info(f"✅ Line {i}: Correct 'await' usage - {line.strip()}")

    if issues:
        logger.info("❌ Found missing await keywords:")
        for issue in issues:
            logger.info(f"   {issue}")
    else:
        logger.info("✅ No missing await keywords found")

    return issues


def check_data_model_fields(file_path):
    """Check if CaseAnalysisResult has the required media fields."""
    logger.debug(f"\n🔍 Checking data model fields in {file_path}")

    with open(file_path) as f:
        content = f.read()

    # Look for CaseAnalysisResult class definition
    class_match = re.search(
        r"class CaseAnalysisResult\(BaseModel\):(.*?)(?=class|\Z)", content, re.DOTALL
    )

    if not class_match:
        logger.info("❌ CaseAnalysisResult class not found")
        return False

    class_content = class_match.group(1)

    required_fields = ["transcripted_media", "video_insights"]
    found_fields = []

    for field in required_fields:
        if field in class_content:
            found_fields.append(field)
            logger.info(f"✅ Found field: {field}")
        else:
            logger.info(f"❌ Missing field: {field}")

    return len(found_fields) == len(required_fields)


def check_ai_analyzer_references(file_path):
    """Check if ai_analyzer.py references the correct media fields."""
    logger.debug(f"\n🔍 Checking media field references in {file_path}")

    with open(file_path) as f:
        content = f.read()
        lines = content.splitlines()

    # Look for references to media fields
    media_field_patterns = [r"\.transcripted_media", r"\.video_insights"]

    references = []
    for i, line in enumerate(lines, 1):
        for pattern in media_field_patterns:
            if re.search(pattern, line):
                references.append(f"Line {i}: {line.strip()}")

    if references:
        logger.info("✅ Found media field references:")
        for ref in references:
            logger.info(f"   {ref}")
    else:
        logger.info("❌ No media field references found")

    return references


def check_vertex_ai_model(file_path):
    """Check the current Vertex AI model configuration."""
    logger.debug(f"\n🔍 Checking Vertex AI model configuration in {file_path}")

    try:
        with open(file_path) as f:
            content = f.read()

        # Look for model configuration
        model_patterns = [
            r"gemini-pro-vision",
            r"gemini-1\.5-pro-vision-001",
            r"gemini-2\.0-flash",
        ]

        for pattern in model_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                line_num = content[: match.start()].count("\n") + 1
                logger.info(f"✅ Found model: {match.group()} at line {line_num}")

    except FileNotFoundError:
        logger.info(f"❌ File not found: {file_path}")


def main():
    """Main diagnostic function."""
    logger.debug("🧪 DIAGNOSTIC ANALYSIS: Media Processing Pipeline Issues")
    logger.info("=" * 60)

    # Check files
    ai_analyzer_path = Path("backend_logic/ai_analyzer.py")
    data_models_path = Path("backend/utils/data_models.py")
    video_processor_path = Path("backend_logic/video_processor.py")

    # Issue 1: Check await keywords
    if ai_analyzer_path.exists():
        await_issues = check_await_keywords(ai_analyzer_path)
    else:
        logger.info(f"❌ File not found: {ai_analyzer_path}")
        await_issues = ["File not found"]

    # Issue 2: Check data model fields
    if data_models_path.exists():
        fields_correct = check_data_model_fields(data_models_path)
    else:
        logger.info(f"❌ File not found: {data_models_path}")
        fields_correct = False

    # Issue 3: Check media field references
    if ai_analyzer_path.exists():
        references = check_ai_analyzer_references(ai_analyzer_path)
    else:
        references = []

    # Issue 4: Check Vertex AI model
    if video_processor_path.exists():
        check_vertex_ai_model(video_processor_path)
    else:
        logger.info(f"❌ File not found: {video_processor_path}")

    # Summary
    logger.info("\n📊 DIAGNOSTIC SUMMARY")
    logger.info("=" * 30)
    logger.info(
        f"Await keyword issues: {len(await_issues) if isinstance(await_issues, list) else 'Unknown'}"
    )
    logger.info(f"Data model fields correct: {fields_correct}")
    logger.info(f"Media field references found: {len(references)}")

    if not await_issues and fields_correct and references:
        logger.info("\n🎉 CONCLUSION: No issues found with the reported problems!")
        logger.info("The code appears to be correctly implemented.")
        logger.info("The issues may have been resolved or the problem lies elsewhere.")
    else:
        logger.info("\n⚠️  CONCLUSION: Issues confirmed, fixes needed.")


if __name__ == "__main__":
    main()
