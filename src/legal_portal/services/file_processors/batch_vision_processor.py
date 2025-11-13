"""Batch vision processor for optimized multi-image analysis."""

from __future__ import annotations

import base64
import mimetypes
import os
import re
from typing import List, Tuple

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


async def process_images_batch(image_files: List[Tuple[str, DocumentType, str]]) -> List[ProcessedDocument]:
    """Processes multiple images in a single Vision API call for efficiency.

    Args:
    ----
        image_files: List of tuples (file_path, document_type, original_filename)

    Returns:
    -------
        List of ProcessedDocument objects (one per image)

    This function reduces API calls by batching related images together while
    maintaining context awareness between images for better analysis quality.

    """
    if not image_files:
        return []

    if len(image_files) == 1:
        # Fall back to single image processing for efficiency
        return [await _process_single_image(image_files[0])]

    logger.info(f"Processing batch of {len(image_files)} images in single Vision API call")

    try:
        # Encode all images to base64
        encoded_images = []
        filenames = []

        for file_path, doc_type, original_filename in image_files:
            with open(file_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")

            # Determine image format
            mime_type, _ = mimetypes.guess_type(file_path)
            image_format = "jpeg" if "jpeg" in mime_type or "jpg" in mime_type else "png"

            encoded_images.append((base64_image, image_format))
            filenames.append(original_filename)

        # Construct batch vision API prompt
        openai_client = OpenAIClient()
        client = openai_client.client

        # Build prompt with structured format requirement
        prompt_text = f"""Analyze each of the {len(image_files)} images below. For EACH image, provide a separate, clearly labeled analysis.

Format your response EXACTLY as follows:

## IMAGE 1: {filenames[0]}
[Your detailed description here]

## IMAGE 2: {filenames[1]}
[Your detailed description here]

{f'## IMAGE 3: {filenames[2]}' if len(filenames) > 2 else ''}
{'[Your detailed description here]' if len(filenames) > 2 else ''}

{f'## IMAGE 4: {filenames[3]}' if len(filenames) > 3 else ''}
{'[Your detailed description here]' if len(filenames) > 3 else ''}

For EACH image, describe:
- What is shown (property damage, maintenance issues, water intrusion, mold, structural problems, documents, text, etc.)
- Condition and severity if applicable
- Any visible text, labels, dates, timestamps, or annotations
- Relationships to other images if apparent (e.g., "This appears to be the same location as Image 1 from a different angle")

IMPORTANT: You must analyze ALL {len(image_files)} images and provide a separate section for each one starting with "## IMAGE N: filename"."""

        # Build content array with prompt + all images
        content = [{"type": "text", "text": prompt_text}]

        for _idx, (base64_image, image_format) in enumerate(encoded_images, 1):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{image_format};base64,{base64_image}"},
                }
            )

        logger.info(f"Sending batch of {len(image_files)} images to GPT-4o Vision API...")

        # Make Vision API call
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}],
            max_tokens=1500 * len(image_files),  # Scale tokens with number of images
            temperature=0.1,
        )

        # Extract response text
        response_text = response.choices[0].message.content if response.choices else ""

        if not response_text:
            logger.error("GPT-4o Vision returned empty response for batch")
            raise ValueError("Empty response from Vision API")

        logger.debug(f"Batch vision response length: {len(response_text)} characters")

        # Parse response and split by image
        image_descriptions = _parse_batch_response(response_text, filenames)

        # Validate we got descriptions for all images
        if len(image_descriptions) != len(image_files):
            logger.warning(
                f"Response contained {len(image_descriptions)} image sections "
                f"but expected {len(image_files)}. Falling back to individual processing."
            )
            # Fall back to individual processing
            return await _fallback_individual_processing(image_files)

        # Create ProcessedDocument for each image
        processed_docs = []
        for (file_path, doc_type, original_filename), description in zip(image_files, image_descriptions):
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            file_metadata = FileMetadata(filename=original_filename, size=file_size)

            # Determine file type
            if original_filename.lower().endswith((".jpg", ".jpeg")):
                file_type = FileType.JPG
            elif original_filename.lower().endswith(".png"):
                file_type = FileType.PNG
            else:
                file_type = FileType.IMAGE

            processed_doc = ProcessedDocument(
                file_name=original_filename,
                content=description,
                document_type=doc_type,
                file_type=file_type,
                metadata=file_metadata,
            )
            processed_docs.append(processed_doc)
            logger.info(f"✅ Extracted {len(description)} characters from {original_filename} (batch)")

        logger.info(f"✅ Successfully processed batch of {len(image_files)} images")
        return processed_docs

    except Exception as e:
        logger.error(f"Error processing image batch: {e}", exc_info=True)
        logger.info("Falling back to individual image processing...")
        return await _fallback_individual_processing(image_files)


def _parse_batch_response(response_text: str, expected_filenames: List[str]) -> List[str]:
    """Parse batch vision response into individual image descriptions.

    Args:
    ----
        response_text: Full response from Vision API
        expected_filenames: List of filenames we expect to find

    Returns:
    -------
        List of descriptions (one per image, in order)

    """
    descriptions = []

    # Split by image markers
    # Pattern: ## IMAGE N: filename
    image_sections = re.split(r"##\s*IMAGE\s+\d+:", response_text, flags=re.IGNORECASE)

    # First element is text before first marker (discard)
    if len(image_sections) > 1:
        image_sections = image_sections[1:]

    for section in image_sections:
        # Clean up the description
        # Remove the filename line (first line)
        lines = section.strip().split("\n")
        if len(lines) > 1:
            # Skip first line (filename), join the rest
            description = "\n".join(lines[1:]).strip()
        else:
            description = section.strip()

        if description:
            descriptions.append(description)

    logger.debug(f"Parsed {len(descriptions)} image descriptions from batch response")
    return descriptions


async def _process_single_image(image_info: Tuple[str, DocumentType, str]) -> ProcessedDocument:
    """Process a single image using the original individual processing method.
    Used as fallback when batch processing fails.
    """
    file_path, doc_type, original_filename = image_info

    # Determine which processor to use based on file extension
    if original_filename.lower().endswith((".jpg", ".jpeg")):
        from legal_portal.services.file_processors.jpg_processor import process_jpg

        return await process_jpg(file_path, doc_type, original_filename)
    elif original_filename.lower().endswith(".png"):
        from legal_portal.services.file_processors.png_processor import process_png

        return await process_png(file_path, doc_type, original_filename)
    else:
        from legal_portal.services.file_processors.image_processor import process_image

        return await process_image(file_path, doc_type, original_filename)


async def _fallback_individual_processing(
    image_files: List[Tuple[str, DocumentType, str]],
) -> List[ProcessedDocument]:
    """Fall back to processing each image individually if batch processing fails."""
    logger.info(f"Processing {len(image_files)} images individually as fallback")

    processed_docs = []
    for image_info in image_files:
        try:
            doc = await _process_single_image(image_info)
            processed_docs.append(doc)
        except Exception as e:
            logger.error(f"Failed to process {image_info[2]} in fallback: {e}")
            # Create a minimal document with error message
            file_path, doc_type, original_filename = image_info
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            file_metadata = FileMetadata(filename=original_filename, size=file_size)

            error_doc = ProcessedDocument(
                file_name=original_filename,
                content=f"[Failed to process image: {str(e)}]",
                document_type=doc_type,
                file_type=FileType.IMAGE,
                metadata=file_metadata,
            )
            processed_docs.append(error_doc)

    return processed_docs
