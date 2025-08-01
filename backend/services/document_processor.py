import asyncio
from fastapi import UploadFile, HTTPException, status
from typing import List, Dict, Callable, Awaitable
from ..utils.data_models import FileType, DocumentType, ProcessedDocument, SavedDocument
from ..utils.file_processors.pdf_processor import process_pdf
from ..utils.file_processors.docx_processor import process_docx
from ..utils.file_processors.eml_processor import process_eml
from ..utils.file_processors.txt_processor import process_txt
import mimetypes
from ..services.pdf_compressor import PDFCompressor

# Maps file content types to their respective processing functions
from ..utils.file_processors import PROCESSOR_MAP

class DocumentProcessor:
    """
    A service class for processing uploaded documents.
    It identifies file types, categorizes them, and extracts content.
    """
    def __init__(self):
        self.pdf_compressor = PDFCompressor()


    def _get_document_type(self, filename: str, intake_filenames: List[str]) -> DocumentType:
        """Determines if a file is an intake form or a general case document."""
        if filename in intake_filenames:
            return DocumentType.INTAKE_FORM
        return DocumentType.CASE_DOCUMENT

    async def process_documents(self, files: List[SavedDocument], intake_filenames: List[str]) -> List[ProcessedDocument]:
        """
        Asynchronously processes a list of saved files from their temporary paths.
        """
        processing_tasks = []
        for file in files:
            # Compress PDF if it's large
            if file.filename.lower().endswith('.pdf'):
                file = await self.pdf_compressor.compress_pdf_if_needed(file)

            doc_type = self._get_document_type(file.filename, intake_filenames)
            content_type, _ = mimetypes.guess_type(file.tmp_path)
            
            processor = PROCESSOR_MAP.get(content_type)
            if not processor:
                 # Fallback for incorrect mimetypes
                if file.filename.endswith(".pdf"):
                    processor = PROCESSOR_MAP.get("application/pdf")
                elif file.filename.endswith(".docx"):
                    processor = PROCESSOR_MAP.get("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                elif file.filename.endswith(".doc"):
                     processor = PROCESSOR_MAP.get("application/msword")
                elif file.filename.endswith(".txt"):
                    processor = PROCESSOR_MAP.get("text/plain")
                elif file.filename.endswith(".eml"):
                    processor = PROCESSOR_MAP.get("message/rfc822")
            
            if not processor:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"No processor available for file '{file.filename}' with content type '{content_type}'",
                )
            
            processing_tasks.append(processor(file.tmp_path, doc_type, file.filename))
        return await asyncio.gather(*processing_tasks)