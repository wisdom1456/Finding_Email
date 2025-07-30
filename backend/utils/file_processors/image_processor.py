import pytesseract
from PIL import Image
from fastapi import UploadFile
from typing import IO
from io import BytesIO
from ..data_models import ProcessedDocument, DocumentType, FileType

async def process_image(file: UploadFile, document_type: DocumentType) -> ProcessedDocument:
    """
    Processes an image file by extracting text using OCR.
    """
    print(f"Processing Image: {file.filename}")
    
    content = await file.read()
    text_content = ""

    try:
        image = Image.open(BytesIO(content))
        # Convert image to grayscale for better OCR results
        image = image.convert('L')
        text_content = pytesseract.image_to_string(image)
        print(f"Successfully extracted text from {file.filename}")
    except Exception as e:
        print(f"Error processing image {file.filename}: {e}")
        text_content = f"Error extracting text from {file.filename}."

    return ProcessedDocument(
        file_name=file.filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.IMAGE,
    )