from fastapi import UploadFile
from ..data_models import ProcessedDocument, DocumentType, FileType

async def process_txt(file: UploadFile, document_type: DocumentType) -> ProcessedDocument:
    """
    Processes a TXT file by reading its content.
    """
    print(f"Processing TXT: {file.filename}")
    
    content = await file.read()
    
    return ProcessedDocument(
        file_name=file.filename,
        content_type=file.content_type,
        content=content.decode('utf-8'),
        document_type=document_type,
        file_type=FileType.TXT
    )