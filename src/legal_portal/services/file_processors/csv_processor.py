from __future__ import annotations

import csv
import mimetypes
import os

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


async def process_csv(
    file_path: str,
    document_type: DocumentType,
    original_filename: str,
    progress_callback=None,
) -> ProcessedDocument:
    """Process a CSV file by reading its content from a path and converting to structured text."""
    logger.debug(f"Processing CSV: {original_filename}")

    # Read the CSV file
    with open(file_path, encoding="utf-8", newline="") as f:
        csv_reader = csv.reader(f)
        rows = list(csv_reader)

    # Convert CSV to formatted text representation
    if not rows:
        content = "Empty CSV file"
    else:
        # Format as a table-like text structure
        lines = []
        lines.append("CSV Data:")
        lines.append("=" * 80)

        # Process each row
        for i, row in enumerate(rows):
            if i == 0:
                # Header row
                lines.append("Headers:")
                lines.append(" | ".join(row))
                lines.append("-" * 80)
            else:
                # Data rows
                if i == 1:
                    lines.append("Data:")
                lines.append(f"Row {i}: {' | '.join(row)}")

        lines.append("=" * 80)
        lines.append(f"Total rows: {len(rows)}")
        if rows:
            lines.append(f"Columns: {len(rows[0])}")

        content = "\n".join(lines)

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    logger.info(f"✅ Processed CSV file: {original_filename}, size: {file_size}, rows: {len(rows)}")

    return ProcessedDocument(
        file_name=original_filename,
        content=content,
        document_type=document_type,
        file_type=FileType.CSV,
        metadata=file_metadata,
    )
