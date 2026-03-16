"""CLIO data transformer.

Converts CLIO API responses to ProcessedDocument format for the legal portal workflow.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

from legal_portal.core.data_models import (
    ClioCommunication,
    ClioContact,
    ClioImportResult,
    ClioMatter,
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.services.integrations.clio_context_builder import ClioContextBuilder
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class ClioDataTransformer:
    """Service for transforming CLIO data to application format."""

    def __init__(self):
        """Initialize transformer with context builder."""
        self.context_builder = ClioContextBuilder()

    def transform_clio_import(  # noqa: D417
        self,
        matter: ClioMatter,
        communications: List[ClioCommunication],
        notes: List[Dict],
        documents: List[Dict],
        contacts: List[ClioContact],
    ) -> Tuple[List[ProcessedDocument], ClioImportResult]:
        """Complete transformation of CLIO data.

        Parameters
        ----------
            matter: CLIO matter object
            communications: List of communications
            notes: List of note dictionaries
            documents: List of document metadata dictionaries
            contacts: List of contacts

        Returns
        -------
            Tuple of (processed_docs, import_result)

        """
        logger.info(f"Transforming CLIO data for matter {matter.display_number}")
        start_time = time.time()

        processed_docs = []
        errors = []

        # Transform communications to documents
        for comm in communications:
            try:
                doc = self._communication_to_document(comm)
                processed_docs.append(doc)
            except Exception as e:
                error_msg = f"Failed to process communication {comm.id}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Transform notes to documents
        for note in notes:
            try:
                doc = self._note_to_document(note)
                processed_docs.append(doc)
            except Exception as e:
                error_msg = f"Failed to process note {note.get('id', 'unknown')}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Build rich context for letter
        logger.info("Building matter context for letter generation")
        matter_context = self.context_builder.build_matter_context(matter, communications, contacts)

        # Auto-populate Q&A
        auto_qa = self.context_builder.extract_qa_pairs_from_matter(matter)

        # Calculate statistics
        date_range = None
        if communications:
            dates = [c.date for c in communications]
            date_range = (min(dates), max(dates))

        total_size = sum(len(doc.content.encode("utf-8")) for doc in processed_docs)
        duration = time.time() - start_time

        result = ClioImportResult(
            matter=matter,
            communications_imported=len(communications),
            documents_imported=len(documents),
            notes_imported=len(notes),
            contacts=contacts,
            matter_context=matter_context,
            auto_populated_qa=auto_qa,
            errors=errors,
            date_range=date_range,
            total_file_size_bytes=total_size,
            import_duration_seconds=duration,
        )

        logger.info(
            f"Transformation complete: {len(processed_docs)} documents, {len(errors)} errors, {duration:.2f}s"
        )

        return processed_docs, result

    def _communication_to_document(self, comm: ClioCommunication) -> ProcessedDocument:  # noqa: D417
        """Convert CLIO communication to ProcessedDocument.

        Parameters
        ----------
            comm: ClioCommunication object

        Returns
        -------
            ProcessedDocument with formatted email content

        """
        # Format content with headers
        recipient_names = ", ".join([r.name for r in comm.recipients])

        content = f"""From: {comm.sender.name}
To: {recipient_names}
Date: {comm.date.strftime("%B %d, %Y at %I:%M %p")}
Subject: {comm.subject}

{comm.body}
"""

        # Create safe filename
        date_str = comm.date.strftime("%Y%m%d")
        subject_safe = comm.subject[:30].replace("/", "_").replace("\\", "_").replace(":", "_")
        filename = f"Email_{date_str}_{subject_safe}.txt"

        return ProcessedDocument(
            file_name=filename,
            content=content,
            document_type=DocumentType.CORRESPONDENCE,
            file_type=FileType.TXT,
            metadata=FileMetadata(
                file_name=filename, file_type=FileType.TXT, file_size=len(content.encode("utf-8"))
            ),
            extraction_quality="high",
            extraction_method="clio_api",
        )

    def _note_to_document(self, note: Dict) -> ProcessedDocument:  # noqa: D417
        """Convert CLIO note to ProcessedDocument.

        Parameters
        ----------
            note: Note dictionary from CLIO API

        Returns
        -------
            ProcessedDocument with formatted note content

        """
        subject = note.get("subject", "No subject")
        detail = note.get("detail", "")
        date = note.get("date", "")

        content = f"""Case Note
Date: {date}
Subject: {subject}

{detail}
"""

        # Create safe filename
        subject_safe = subject[:30].replace("/", "_").replace("\\", "_").replace(":", "_")
        filename = f"Note_{date}_{subject_safe}.txt"

        return ProcessedDocument(
            file_name=filename,
            content=content,
            document_type=DocumentType.CASE_DOCUMENT,
            file_type=FileType.TXT,
            metadata=FileMetadata(
                file_name=filename, file_type=FileType.TXT, file_size=len(content.encode("utf-8"))
            ),
            extraction_quality="high",
            extraction_method="clio_api",
        )
