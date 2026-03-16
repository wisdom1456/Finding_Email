"""Unit tests for chunk_service document ID tracking."""

from legal_portal.core.data_models import DocumentType, FileMetadata, FileType, ProcessedDocument
from legal_portal.services.documents.chunk_service import ChunkService, build_document_tracking_ids, create_chunk_state


def make_processed_doc(
    file_name: str,
    content: str = "content",
    document_id: str | None = None,
) -> ProcessedDocument:
    """Build a minimal ProcessedDocument for chunking tests."""
    return ProcessedDocument(
        file_name=file_name,
        content=content,
        document_type=DocumentType.CASE_DOCUMENT,
        file_type=FileType.PDF,
        metadata=FileMetadata(file_name=file_name, file_type=FileType.PDF, file_size=len(content)),
        document_id=document_id,
        extraction_method="test",
        extraction_quality="high",
    )


def test_build_document_tracking_ids_prefers_document_id():
    docs = [
        make_processed_doc(file_name="contract.pdf", document_id="doc-1"),
        make_processed_doc(file_name="invoice.pdf", document_id="doc-2"),
    ]

    tracking_ids = build_document_tracking_ids(docs)

    assert tracking_ids == ["doc-1", "doc-2"]


def test_build_document_tracking_ids_handles_duplicates():
    docs = [
        make_processed_doc(file_name="contract.pdf", document_id="dup-id"),
        make_processed_doc(file_name="contract-copy.pdf", document_id="dup-id"),
    ]

    tracking_ids = build_document_tracking_ids(docs)

    assert tracking_ids[0] == "dup-id"
    assert tracking_ids[1] == "dup-id__dup2"


def test_create_balanced_chunks_uses_tracking_ids():
    docs = [
        make_processed_doc(file_name="one.pdf", content="A" * 1000),
        make_processed_doc(file_name="two.pdf", content="B" * 1000),
    ]
    expected_ids = sorted(build_document_tracking_ids(docs))

    plan = ChunkService(max_tokens_per_chunk=50000).create_balanced_chunks(docs)
    plan_ids = sorted(doc_id for chunk in plan.chunks for doc_id in chunk.doc_ids)

    assert plan_ids == expected_ids


def test_create_chunk_state_uses_resolved_document_ids():
    docs = [
        make_processed_doc(file_name="named.pdf", document_id="doc-abc"),
        make_processed_doc(file_name="unnamed.pdf", document_id=None),
    ]

    chunk_state = create_chunk_state(docs, max_tokens_per_chunk=50000)

    assert "doc-abc" in chunk_state["documents"]
    fallback_ids = [doc_id for doc_id in chunk_state["documents"] if doc_id != "doc-abc"]
    assert len(fallback_ids) == 1
    assert fallback_ids[0].startswith("doc_unnamed.pdf_")
