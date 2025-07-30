"""
Service for processing uploaded documents.
This will eventually contain the logic for PDF.co integration and document parsing.
"""

def process_document(file):
    """
    Processes a single document.
    Placeholder for future implementation.
    """
    # In the future, this will call PDF.co or other services
    # to extract text and metadata.
    print(f"Processing document: {file.name}")
    return {"filename": file.name, "content": "dummy content", "status": "processed"}