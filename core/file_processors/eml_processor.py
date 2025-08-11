from __future__ import annotations

import mimetypes
import os
from email import policy
from email.parser import BytesParser

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.core.logging_config import get_module_logger


logger = get_module_logger(__name__)


async def process_eml(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """
    Processes an EML file by extracting its headers and body content from a given path.
    """
    logger.debug(f"Processing EML: {original_filename}")

    with open(file_path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if "text/plain" in content_type:
                body = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8"
                )
                break
    else:
        body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")

    full_text = f"Subject: {msg['subject']}\nFrom: {msg['from']}\nTo: {msg['to']}\nDate: {msg['date']}\n\n{body}"

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    logger.info(
        f"✅ Fixed: Created FileMetadata for {original_filename}, size: {file_size}"
    )

    return ProcessedDocument(
        file_name=original_filename,
        content=full_text,
        document_type=document_type,
        file_type=FileType.EML,
        metadata=file_metadata,
    )
