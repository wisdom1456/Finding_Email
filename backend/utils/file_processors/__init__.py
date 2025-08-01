from typing import Dict, Callable, Awaitable, Optional
from ..data_models import DocumentType, ProcessedDocument, FileType, SavedDocument
from .pdf_processor import process_pdf
from .docx_processor import process_docx
from .eml_processor import process_eml
from .txt_processor import process_txt
from .image_processor import process_image

# Type alias for processor functions
Processor = Callable[[str, DocumentType, str], Awaitable[ProcessedDocument]]

# Map FileType enum to processor functions
PROCESSOR_MAP: Dict[str, Processor] = {
    "application/pdf": process_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": process_docx,
    "application/msword": process_docx,
    "message/rfc822": process_eml,
    "text/plain": process_txt,
    "image/jpeg": process_image,
    "image/png": process_image,
    "image/gif": process_image,
    "image/bmp": process_image,
    "image/tiff": process_image,
}

def get_processor(file_type: str) -> Optional[Processor]:
    """
    Returns the appropriate processor for a given file content type, or None if unsupported.
    """
    return PROCESSOR_MAP.get(file_type)