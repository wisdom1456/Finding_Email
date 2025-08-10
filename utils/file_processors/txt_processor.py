from __future__ import annotations

import mimetypes

from utils.data_models import DocumentType, FileType, ProcessedDocument
from utils.logging_config import setup_logging


logger = setup_logging("txt_processor")


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

    return ProcessedDocument(
        file_name=original_filename,
        content=content,
        document_type=document_type,
        file_type=FileType.TXT,
        metadata={"content_type": content_type},
    )
