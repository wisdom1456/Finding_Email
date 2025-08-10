from __future__ import annotations

import mimetypes

import fitz  # PyMuPDF

from utils.data_models import DocumentType, FileType, ProcessedDocument
from utils.logging_config import setup_logging


logger = setup_logging("pdf_processor")


async def process_pdf(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """
    Processes a PDF file by extracting its text content using PyMuPDF from a given path.
    """
    logger.debug(f"Processing PDF: {original_filename}")

    text_content = ""

    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                text_content += page.get_text()
    except Exception as e:
        logger.error(f"Error processing PDF {original_filename}: {e}")
        text_content = f"Error extracting text from {original_filename}."

    content_type, _ = mimetypes.guess_type(file_path)

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.PDF,
        metadata={"content_type": content_type},
    )
