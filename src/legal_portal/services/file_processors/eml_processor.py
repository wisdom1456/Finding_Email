from __future__ import annotations

import os
from email import policy
from email.parser import BytesParser

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Try to import html2text for HTML email conversion
try:
    import html2text
    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False
    logger.warning("html2text not available - HTML emails will use raw HTML")


async def process_eml(
    file_path: str,
    document_type: DocumentType,
    original_filename: str,
    progress_callback=None,
) -> ProcessedDocument:
    """Process an EML file by extracting its headers and body content from a given path.

    Extracts both text/plain and text/html content (converting HTML to plain text).
    Sets proper extraction metadata for quality validation.

    Args:
    ----
        file_path: Path to the .eml file
        document_type: Document type classification
        original_filename: Original name of the file
        progress_callback: Optional callback for progress updates

    Returns:
    -------
        ProcessedDocument with extracted email content and metadata

    """
    logger.debug(f"Processing EML: {original_filename}")

    body = ""
    extraction_method = "email_parser"
    extraction_quality = "high"
    extraction_error = None

    try:
        # Parse the email file
        with open(file_path, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)

        # Extract body content - try text/plain first, then text/html
        text_parts = []
        html_parts = []

        if msg.is_multipart():
            # Walk through all parts and collect text content
            for part in msg.walk():
                content_type = part.get_content_type()

                # Skip container parts
                if content_type.startswith("multipart/"):
                    continue

                try:
                    # Get the payload
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue

                    # Decode to string
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        content = payload.decode(charset, errors="replace")
                    except (UnicodeDecodeError, LookupError):
                        # Fallback to utf-8 if charset is invalid
                        content = payload.decode("utf-8", errors="replace")

                    # Collect text and HTML parts separately
                    if content_type == "text/plain":
                        text_parts.append(content)
                    elif content_type == "text/html":
                        html_parts.append(content)

                except Exception as e:
                    logger.warning(f"Failed to decode email part ({content_type}): {e}")
                    continue
        else:
            # Simple non-multipart email
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    try:
                        content = payload.decode(charset, errors="replace")
                    except (UnicodeDecodeError, LookupError):
                        content = payload.decode("utf-8", errors="replace")

                    if msg.get_content_type() == "text/html":
                        html_parts.append(content)
                    else:
                        text_parts.append(content)
            except Exception as e:
                logger.warning(f"Failed to decode email body: {e}")
                extraction_error = f"Decode error: {str(e)}"

        # Prefer text/plain, but use HTML if that's all we have
        if text_parts:
            body = "\n\n".join(text_parts)
            extraction_method = "text/plain"
        elif html_parts and HTML2TEXT_AVAILABLE:
            # Convert HTML to plain text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.ignore_emphasis = False
            body = "\n\n".join([h.handle(html) for html in html_parts])
            extraction_method = "html2text"
            logger.info(f"Converted HTML email to text for {original_filename}")
        elif html_parts:
            # No html2text available - use raw HTML (better than nothing)
            body = "\n\n".join(html_parts)
            extraction_method = "raw_html"
            logger.warning(f"Using raw HTML for {original_filename} (html2text not available)")
        else:
            # No content found
            logger.warning(f"No text or HTML content found in {original_filename}")
            body = ""
            extraction_quality = "low"
            extraction_error = "No text/plain or text/html parts found"

        # Build full email text with headers
        subject = msg.get('subject', '(No Subject)')
        from_addr = msg.get('from', '(Unknown)')
        to_addr = msg.get('to', '(Unknown)')
        date = msg.get('date', '(No Date)')

        full_text = (
            f"Subject: {subject}\n"
            f"From: {from_addr}\n"
            f"To: {to_addr}\n"
            f"Date: {date}\n"
            f"\n{body}"
        )

        # Determine extraction quality based on content length
        content_length = len(full_text.strip())
        if content_length == 0:
            extraction_quality = "low"
            extraction_error = extraction_error or "Empty email content"
        elif content_length < 100:
            extraction_quality = "medium"
        else:
            extraction_quality = "high"

        logger.info(
            f"✅ Extracted email content from {original_filename}: "
            f"{content_length} chars, method={extraction_method}, quality={extraction_quality}"
        )

    except Exception as e:
        logger.error(f"Failed to process email {original_filename}: {e}")
        full_text = f"Error processing email: {str(e)}"
        extraction_method = "error"
        extraction_quality = "low"
        extraction_error = str(e)

    # Get file metadata
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    return ProcessedDocument(
        file_name=original_filename,
        content=full_text,
        document_type=document_type,
        file_type=FileType.EML,
        metadata=file_metadata,
        extraction_method=extraction_method,
        extraction_quality=extraction_quality,
        extraction_error=extraction_error,
    )
