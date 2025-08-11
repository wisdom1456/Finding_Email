from __future__ import annotations

import mimetypes
import os

from backend.utils.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from backend_logic.utils.logging_config import get_module_logger


logger = get_module_logger(__name__)


async def process_txt(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """
    Processes a TXT file by reading its content from a given path.
    """
    logger.debug(f"Processing TXT: {original_filename}")

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    logger.info(
        f"✅ Fixed: Created FileMetadata for {original_filename}, size: {file_size}"
    )

    return ProcessedDocument(
        file_name=original_filename,
        content=content,
        document_type=document_type,
        file_type=FileType.TXT,
        metadata=file_metadata,
    )
