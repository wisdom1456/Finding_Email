import fitz  # PyMuPDF
import os
from ..utils.data_models import SavedDocument

class PDFCompressor:
    """
    A service class for compressing PDF files using PyMuPDF.
    """

    def __init__(self, size_threshold_mb: int = 10):
        self.size_threshold_bytes = size_threshold_mb * 1024 * 1024

    async def compress_pdf_if_needed(self, document: SavedDocument) -> SavedDocument:
        """
        Compresses a PDF if it exceeds a certain size threshold.
        Returns a new SavedDocument pointing to the compressed file if compression occurred.
        """
        try:
            file_size = os.path.getsize(document.tmp_path)
            if file_size > self.size_threshold_bytes:
                print(f"PDF '{document.filename}' exceeds size threshold. Compressing...")
                
                # Define a new path for the compressed file
                original_dir = os.path.dirname(document.tmp_path)
                base_name = os.path.basename(document.tmp_path)
                new_filename = f"compressed_{base_name}"
                compressed_path = os.path.join(original_dir, new_filename)

                # Perform compression
                await self._compress_pdf(document.tmp_path, compressed_path)

                new_file_size = os.path.getsize(compressed_path)
                print(f"Compression complete. Original size: {file_size} bytes, New size: {new_file_size} bytes.")

                # Return a new SavedDocument pointing to the compressed file
                return SavedDocument(tmp_path=compressed_path, filename=document.filename)

        except Exception as e:
            print(f"Could not compress PDF {document.filename}. Error: {e}. Using original file.")
            # If compression fails, return the original document to proceed without interruption
        
        return document

    async def _compress_pdf(self, input_path: str, output_path: str):
        """
        Compresses a PDF using PyMuPDF's optimization features.
        """
        with fitz.open(input_path) as doc:
            # Use save with garbage collection, deflation, and cleaning
            doc.save(
                output_path,
                garbage=4,      # Remove unused objects
                deflate=True,   # Compress streams
                clean=True      # Clean content streams
            )