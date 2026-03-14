from __future__ import annotations

from collections.abc import Awaitable
import logging
from typing import Callable, Optional

from legal_portal.core.data_models import (
    DocumentType,
    ProcessedDocument,
)

from .csv_processor import process_csv
from .doc_processor import process_doc
from .eml_processor import process_eml
from .pdf_processor import process_pdf
from .txt_processor import process_txt

logger = logging.getLogger(__name__)

try:
    from .docx_processor import process_docx
except ImportError as e:
    process_docx = None
    logger.warning(f"DOCX processor unavailable: {e}")

try:
    from .image_processor import process_image
except ImportError as e:
    process_image = None
    logger.warning(f"Image processor unavailable: {e}")

# Type alias for progress callback used by processors
# Signature: (message: str, sub_step: Optional[str]) -> Awaitable[None]
ProcessorProgressCallback = Callable[[str, Optional[str]], Awaitable[None]]

# Type alias for processor functions
# Now accepts an optional progress_callback for granular reporting
Processor = Callable[
    [str, DocumentType, str, Optional[ProcessorProgressCallback]],
    Awaitable[ProcessedDocument],
]

# Map FileType enum to processor functions
PROCESSOR_MAP: dict[str, Processor] = {
    "application/pdf": process_pdf,
    "application/msword": process_doc,
    "message/rfc822": process_eml,
    "text/plain": process_txt,
    "text/csv": process_csv,
    "application/csv": process_csv,
}

if process_docx:
    PROCESSOR_MAP["application/vnd.openxmlformats-officedocument.wordprocessingml.document"] = process_docx

if process_image:
    PROCESSOR_MAP["image/jpeg"] = process_image
    PROCESSOR_MAP["image/png"] = process_image
    PROCESSOR_MAP["image/gif"] = process_image
    PROCESSOR_MAP["image/bmp"] = process_image
    PROCESSOR_MAP["image/tiff"] = process_image


def get_processor(file_type: str) -> Processor | None:
    """Return the appropriate processor for a given file content type, or None if unsupported."""
    return PROCESSOR_MAP.get(file_type)
