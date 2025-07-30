from typing import Dict, Callable, Awaitable, Optional
from fastapi import UploadFile
from ..data_models import DocumentType, ProcessedDocument, FileType
from .pdf_processor import process_pdf
from .docx_processor import process_docx
from .eml_processor import process_eml
from .txt_processor import process_txt
from .image_processor import process_image

# Type alias for processor functions
Processor = Callable[[UploadFile, DocumentType], Awaitable[ProcessedDocument]]

# Map FileType enum to processor functions
PROCESSOR_MAP: Dict[str, Processor] = {
    "application/pdf": process_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": process_docx,
    "application/msword": process_docx,
    "message/rfc822": process_eml,
    "text/plain": process_txt,
    "image/jpeg": process_image,
    "image/png": process_image,
}

def get_processor(file_type: FileType) -> Optional[Processor]:
    """
    Returns the appropriate processor for a given file type, or None if unsupported.
    """
    return PROCESSOR_MAP.get(file_type)