from ..data_models import ProcessedDocument, DocumentType, FileType
import mimetypes

async def process_txt(file_path: str, document_type: DocumentType, original_filename: str) -> ProcessedDocument:
    """
    Processes a TXT file by reading its content from a given path.
    """
    print(f"Processing TXT: {original_filename}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    content_type, _ = mimetypes.guess_type(file_path)
    
    return ProcessedDocument(
        file_name=original_filename,
        content=content,
        document_type=document_type,
        file_type=FileType.TXT,
        metadata={'content_type': content_type}
    )