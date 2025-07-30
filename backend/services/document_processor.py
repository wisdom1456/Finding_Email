import asyncio
from fastapi import UploadFile, HTTPException, status
from typing import List, Dict, Callable, Awaitable
from utils.data_models import FileType, DocumentType, ProcessedFile
from utils.file_processors.pdf_processor import process_pdf
from utils.file_processors.docx_processor import process_docx
from utils.file_processors.eml_processor import process_eml
from utils.file_processors.txt_processor import process_txt

# Maps file content types to their respective processing functions
from utils.file_processors import PROCESSORS
PROCESSOR_MAP: Dict[str, Callable[[UploadFile, DocumentType], Awaitable[ProcessedFile]]] = PROCESSORS

class DocumentProcessor:
    """
    A service class for processing uploaded documents.
    It identifies file types, categorizes them, and extracts content.
    """

    def _get_document_type(self, file: UploadFile) -> DocumentType:
        """Determines if a file is an intake form or a general case document."""
        if file.filename and "intake" in file.filename.lower():
            return DocumentType.INTAKE_FORM
        return DocumentType.CASE_DOCUMENT

    async def process_documents(self, files: List[UploadFile]) -> List[ProcessedFile]:
        """
        Asynchronously processes a list of uploaded files.
        """
        processing_tasks = []
        for file in files:
            doc_type = self._get_document_type(file)
            processor = PROCESSOR_MAP.get(file.content_type)

            if not processor:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"No processor available for file type '{file.content_type}'",
                )
            
            processing_tasks.append(processor(file, doc_type))

        processed_files = await asyncio.gather(*processing_tasks)
        return processed_files