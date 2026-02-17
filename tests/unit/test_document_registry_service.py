"""Unit tests for authoritative document registry construction."""

from legal_portal.core.data_models import (
    DocumentSummaryStructured,
    DocumentType,
    FactMatrix,
    FileMetadata,
    FileType,
    KeyDocument,
    ProcessedDocument,
)
from legal_portal.services.document_registry_service import DocumentRegistryService


def _processed_doc(
    file_name: str,
    content: str,
    *,
    signature_detection=None,
    document_type: DocumentType = DocumentType.CASE_DOCUMENT,
    file_type: FileType = FileType.PDF,
) -> ProcessedDocument:
    return ProcessedDocument(
        file_name=file_name,
        content=content,
        document_type=document_type,
        file_type=file_type,
        metadata=FileMetadata(file_name=file_name, file_type=file_type, file_size=len(content)),
        signature_detection=signature_detection,
        extraction_quality="high",
        extraction_method="test",
    )


def test_document_registry_assigns_authority_tiers_and_execution():
    service = DocumentRegistryService()

    processed_documents = [
        _processed_doc(
            "Subscription_Agreement_EJAJ-TX_Final120.doc.pdf",
            "Subscription Agreement for Class B Units.",
            signature_detection={
                "status": "signed",
                "confidence": "high",
                "detection_source": "pdf_signature",
                "signer_names": ["Erica Corley"],
                "signing_date": "2022-02-28",
            },
        ),
        _processed_doc(
            "Cuchillo Greens Grow1 Business Search _ An Official New Mexico Government Website.pdf",
            "Official New Mexico Business Search record.",
        ),
        _processed_doc(
            "2.14.23 Update from Cuchillo Greens!.pdf",
            "Email update from Simon Holguin to Erica Corley.",
        ),
    ]

    summaries = [
        DocumentSummaryStructured(
            document_name="Subscription_Agreement_EJAJ-TX_Final120.doc.pdf",
            document_type="Contract",
            legal_significance="Defines investor rights and obligations.",
            relevance_to_case="Core investment terms and standing.",
            parties=["EJAJ-TX, LLC", "Cuchillo Greens Grow 1 LLC"],
        ),
        DocumentSummaryStructured(
            document_name="Cuchillo Greens Grow1 Business Search _ An Official New Mexico Government Website.pdf",
            document_type="Notice",
            legal_significance="Confirms entity registration details.",
            relevance_to_case="Supports entity identity and service targets.",
        ),
        DocumentSummaryStructured(
            document_name="2.14.23 Update from Cuchillo Greens!.pdf",
            document_type="Correspondence",
            legal_significance="Contains updates and potential admissions.",
            relevance_to_case="Supports representation timeline.",
        ),
    ]

    fact_matrix = FactMatrix(
        parties=[],
        timeline=[],
        financial_data=[],
        key_documents=[
            KeyDocument(
                document_name="Subscription_Agreement_EJAJ-TX_Final120.doc.pdf",
                document_type="Contract",
                significance="Primary investment contract.",
            )
        ],
        preliminary_issues=[],
    )

    registry = service.build_registry(
        processed_documents=processed_documents,
        document_summaries=summaries,
        fact_matrix=fact_matrix,
    )

    by_name = {row["document_name"]: row for row in registry}

    subscription = by_name["Subscription_Agreement_EJAJ-TX_Final120.doc.pdf"]
    assert subscription["authority_level"] == "controlling_signed_instrument"
    assert subscription["execution_status"] == "signed"
    assert subscription["primary_instrument"] == "subscription agreement"
    assert subscription["is_key_document"] is True

    business_search = by_name[
        "Cuchillo Greens Grow1 Business Search _ An Official New Mexico Government Website.pdf"
    ]
    assert business_search["authority_level"] == "official_record"

    email_update = by_name["2.14.23 Update from Cuchillo Greens!.pdf"]
    assert email_update["authority_level"] == "party_communication"


def test_document_registry_includes_summary_only_entries():
    service = DocumentRegistryService()

    summaries = [
        DocumentSummaryStructured(
            document_name="1_2_MEMO_TERMS_FOR_FINANCING_Cuchillo_Greens_Grow1__LLC.pdf",
            document_type="Contract",
            legal_significance="Memorializes financing terms and repayment structure.",
            relevance_to_case="Supports what was promised to investors.",
        )
    ]

    registry = service.build_registry(
        processed_documents=[],
        document_summaries=summaries,
        fact_matrix=None,
    )

    assert len(registry) == 1
    assert registry[0]["document_name"] == "1_2_MEMO_TERMS_FOR_FINANCING_Cuchillo_Greens_Grow1__LLC.pdf"
    assert registry[0]["authority_level"] == "controlling_instrument"
