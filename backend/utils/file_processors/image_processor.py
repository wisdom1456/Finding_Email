import pytesseract
from PIL import Image
from io import BytesIO
from ..data_models import ProcessedDocument, DocumentType, FileType
import mimetypes

async def process_image(file_path: str, document_type: DocumentType, original_filename: str) -> ProcessedDocument:
    """
    Processes an image file by extracting text using OCR from a given path.
    """
    print(f"Processing Image: {original_filename}")
    
    text_content = ""

    try:
        with open(file_path, "rb") as f:
            image = Image.open(BytesIO(f.read()))
            # Convert image to grayscale for better OCR results
            image = image.convert('L')
            text_content = pytesseract.image_to_string(image)
            print(f"Successfully extracted text from {original_filename}")
    except Exception as e:
        print(f"Error processing image {original_filename}: {e}")
        text_content = f"Error extracting text from {original_filename}."
        
    content_type, _ = mimetypes.guess_type(file_path)

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.IMAGE,
        metadata={'content_type': content_type}
    )