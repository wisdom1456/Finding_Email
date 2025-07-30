import pytesseract
from PIL import Image
from fastapi import UploadFile
from typing import IO
from utils.data_models import ProcessedFile, DocumentType, FileType

async def process_image(file: UploadFile, doc_type: DocumentType) -> ProcessedFile:
    """
    Processes an uploaded image file, extracting text using OCR.
    """
    try:
        image = Image.open(file.file)
        # Convert image to grayscale for better OCR results
        image = image.convert('L')
        text = pytesseract.image_to_string(image)
    except Exception as e:
        # Handle exceptions during image processing
        text = f"Error processing image: {e}"

    return ProcessedFile(
        file_name=file.filename,
        content_type=file.content_type,
        document_type=doc_type,
        file_type=FileType.IMAGE,
        text_content=text,
        page_count=1  # Assuming single-page images for now
    )