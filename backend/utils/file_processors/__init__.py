from .pdf_processor import process_pdf
from .docx_processor import process_docx
from .eml_processor import process_eml
from .txt_processor import process_txt
from .image_processor import process_image

PROCESSORS = {
    "application/pdf": process_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": process_docx,
    "application/msword": process_docx,
    "message/rfc822": process_eml,
    "text/plain": process_txt,
    "image/jpeg": process_image,
    "image/png": process_image,
}