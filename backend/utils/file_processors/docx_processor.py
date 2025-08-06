from ..data_models import ProcessedDocument, DocumentType, FileType
import docx
import io
import mimetypes

async def process_docx(file_path: str, document_type: DocumentType, original_filename: str) -> ProcessedDocument:
    """
    Processes a DOCX file by extracting its content from a given path.
    """
    print(f"Processing DOCX: {original_filename}")
    
    try:
        with open(file_path, "rb") as f:
            document = docx.Document(io.BytesIO(f.read()))
            full_text = "\n".join([para.text for para in document.paragraphs])
    except Exception as e:
        print(f"Could not process {original_filename} with python-docx: {e}")
        full_text = f"Could not extract content from {original_filename}."

    content_type, _ = mimetypes.guess_type(file_path)

    return ProcessedDocument(
        file_name=original_filename,
        content=full_text,
        document_type=document_type,
        file_type=FileType.DOCX,
        metadata={'content_type': content_type}
    )