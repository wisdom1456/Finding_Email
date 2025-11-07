from __future__ import annotations

import base64
import mimetypes
import os

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


async def process_jpg(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """Processes a JPG file by extracting text using GPT-4o Vision API.

    NOTE: This is the single-image processing mode (legacy).
    For batch processing of multiple images (more efficient), use:
    batch_vision_processor.process_images_batch()
    """
    logger.debug(f"Processing JPG with GPT-4o Vision: {original_filename}")

    text_content = ""

    try:
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        openai_client = OpenAIClient()
        client = openai_client.client

        logger.info(f"Sending {original_filename} to GPT-4o Vision API for analysis...")
        logger.debug(
            f"GPT-4o Vision request structure: model=gpt-4o, image_url=data:image/jpeg;base64,[{len(base64_image)} chars]"
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Describe what you see in this image in detail. If it shows property damage, maintenance issues, "
                                "water intrusion, mold, structural problems, or other relevant visual information, describe the "
                                "condition, severity, and any visible details. Also extract any visible text, labels, dates, or annotations."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ],
                }
            ],
            max_tokens=1000,
            temperature=0.1,
        )

        logger.debug(f"GPT-4o Vision response (JPG): {response.model_dump_json(indent=2)}")

        # Extract text from response
        text_content = response.choices[0].message.content if response.choices else ""
        text_content = text_content.strip()

        if text_content:
            logger.info(f"Successfully extracted {len(text_content)} characters from JPG {original_filename}")
        else:
            logger.warning(f"GPT-4o did not return any text for JPG {original_filename}")
            text_content = "[GPT-4o Vision returned no text for this image.]"

    except Exception as e:
        logger.error(f"Error processing JPG {original_filename} with GPT-4o: {e}", exc_info=True)
        text_content = f"[Text extraction failed for {original_filename}. Error: {str(e)}]"

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    logger.info(f"✅ Created FileMetadata for JPG {original_filename}, size: {file_size}")

    # Assess extraction quality
    extraction_quality = "high"  # Default for successful extraction
    if "[Text extraction failed" in text_content or "[GPT-4o Vision returned no text" in text_content:
        extraction_quality = "low"
    elif len(text_content) < 100:
        extraction_quality = "medium"

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.JPG,
        metadata=file_metadata,
        extraction_method="GPT-4o Vision API",
        extraction_quality=extraction_quality,
    )
