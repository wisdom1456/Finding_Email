from __future__ import annotations

import mimetypes
import os
from io import BytesIO

import pytesseract
from PIL import Image

from backend.utils.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)


async def process_image(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """
    Processes an image file by extracting text using OCR from a given path.
    """
    print(f"Processing Image: {original_filename}")

    text_content = ""

    try:
        with open(file_path, "rb") as f:
            image = Image.open(BytesIO(f.read()))
            # Convert image to grayscale for better OCR results
            image = image.convert("L")
            text_content = pytesseract.image_to_string(image)
            print(f"Successfully extracted text from {original_filename}")
    except Exception as e:
        print(f"Error processing image {original_filename}: {e}")
        text_content = f"Error extracting text from {original_filename}."

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    print(f"✅ Fixed: Created FileMetadata for {original_filename}, size: {file_size}")

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.IMAGE,
        metadata=file_metadata,
    )
