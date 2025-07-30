from fastapi import UploadFile
from ..data_models import ProcessedDocument, DocumentType, FileType
import email
from email import policy
from email.parser import BytesParser

async def process_eml(file: UploadFile, document_type: DocumentType) -> ProcessedDocument:
    """
    Processes an EML file by extracting its headers and body content.
    """
    print(f"Processing EML: {file.filename}")
    
    content = await file.read()
    
    msg = BytesParser(policy=policy.default).parsebytes(content)
    
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if "text/plain" in content_type:
                body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
                break
    else:
        body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8')

    full_text = f"Subject: {msg['subject']}\nFrom: {msg['from']}\nTo: {msg['to']}\nDate: {msg['date']}\n\n{body}"

    return ProcessedDocument(
        file_name=file.filename,
        content_type=file.content_type,
        content=full_text,
        document_type=document_type,
        file_type=FileType.EML
    )