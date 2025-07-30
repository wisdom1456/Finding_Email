import fitz  # PyMuPDF
from fastapi import UploadFile
from ..data_models import ProcessedFile, DocumentType, FileMetadata, FileType

async def process_pdf(file: UploadFile, document_type: DocumentType) -> ProcessedFile:
    """
    Processes a PDF file by extracting its text content using PyMuPDF.
    """
    print(f"Processing PDF: {file.filename}")
    
    content = await file.read()
    text_content = ""
    
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc:
                text_content += page.get_text()
    except Exception as e:
        print(f"Error processing PDF {file.filename}: {e}")
        # Return a processed file with an error message in content
        text_content = f"Error extracting text from {file.filename}."

    metadata = FileMetadata(
        filename=file.filename,
        content_type=file.content_type,
        size=len(content)
    )
    
    return ProcessedFile(
        file_name=file.filename,
        content=text_content,
        file_type=FileType.PDF,
        document_type=document_type,
        metadata=metadata
    )