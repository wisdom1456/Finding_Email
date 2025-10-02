from __future__ import annotations

from collections.abc import Awaitable
from typing import Callable

from legal_portal.core.data_models import (
    DocumentType,
    ProcessedDocument,
)

from .csv_processor import process_csv
from .doc_processor import process_doc
from .docx_processor import process_docx
from .eml_processor import process_eml
from .image_processor import process_image
from .jpg_processor import process_jpg
from .pdf_processor import process_pdf
from .png_processor import process_png
from .txt_processor import process_txt

# Type alias for processor functions
Processor = Callable[[str, DocumentType, str], Awaitable[ProcessedDocument]]

# Map FileType enum to processor functions
PROCESSOR_MAP: dict[str, Processor] = {
    "application/pdf": process_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": process_docx,
    "application/msword": process_doc,  # Updated to use dedicated legacy DOC processor
    "message/rfc822": process_eml,
    "text/plain": process_txt,
    "text/csv": process_csv,
    "application/csv": process_csv,
    "image/jpeg": process_jpg,  # Updated to use dedicated JPG processor
    "image/png": process_png,  # Updated to use dedicated PNG processor
    "image/gif": process_image,  # Keep generic processor for other image types
    "image/bmp": process_image,
    "image/tiff": process_image,
}


def get_processor(file_type: str) -> Processor | None:
    """Returns the appropriate processor for a given file content type, or None if unsupported."""
    return PROCESSOR_MAP.get(file_type)
