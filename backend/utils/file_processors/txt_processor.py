from fastapi import UploadFile
from ..data_models import ProcessedFile, FileMetadata, DocumentType, FileType

async def process_txt(file: UploadFile, document_type: DocumentType) -> ProcessedFile:
    """
    Processes a TXT file by reading its content.
    """
    print(f"Processing TXT: {file.filename}")
    
    content = await file.read()
    
    metadata = FileMetadata(
        filename=file.filename,
        content_type=file.content_type,
        size=len(content)
    )
    
    return ProcessedFile(
        metadata=metadata,
        content=content.decode('utf-8'),
        document_type=document_type
    )