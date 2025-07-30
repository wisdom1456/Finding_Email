import os
import requests
from typing import List, Dict, Any
from fastapi import UploadFile

class DocumentProcessor:
    def __init__(self):
        self.pdfco_api_key = os.getenv("PDFCO_API_KEY")
        self.pdfco_url = "https://api.pdf.co/v1/pdf/convert/to/text"

    async def process_files(self, files: List[UploadFile]) -> List[Dict[str, Any]]:
        # This will contain the logic to process uploaded files,
        # distinguishing between intake forms and case documents,
        # and using PDF.co for PDF processing.
        processed_files = []
        for file in files:
            content = await file.read()
            # In a real implementation, we would call PDF.co or other services here.
            processed_files.append({
                "filename": file.filename,
                "content_type": file.content_type,
                "text": content.decode("utf-8", errors="ignore") # simple text extraction for now
            })
        return processed_files