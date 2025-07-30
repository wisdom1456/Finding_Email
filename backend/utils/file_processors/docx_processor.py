from fastapi import UploadFile
from ..data_models import ProcessedFile, FileMetadata, DocumentType, FileType
import docx
import io

async def process_docx(file: UploadFile, document_type: DocumentType) -> ProcessedFile:
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

    metadata = FileMetadata(
        filename=file.filename,
        content_type=file.content_type,
        size=len(content)
    )
    
    return ProcessedFile(
        metadata=metadata,
        content=full_text,
        document_type=document_type
    )