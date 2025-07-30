from fastapi import UploadFile
from ..data_models import ProcessedDocument, DocumentType, FileType
import docx
import io

async def process_docx(file: UploadFile, document_type: DocumentType) -> ProcessedDocument:
    """
    Processes a DOCX file by extracting its content.
    """
    print(f"Processing DOCX: {file.filename}")
    
    content = await file.read()
    
    # Use python-docx to read the content
    try:
        document = docx.Document(io.BytesIO(content))
        full_text = "\n".join([para.text for para in document.paragraphs])
    except Exception as e:
        # Placeholder for docx2txt for .doc files or other fallbacks
        print(f"Could not process {file.filename} with python-docx: {e}")
        full_text = f"Could not extract content from {file.filename}."

    return ProcessedDocument(
        file_name=file.filename,
        content_type=file.content_type,
        content=full_text,
        document_type=document_type,
        file_type=FileType.DOCX
    )