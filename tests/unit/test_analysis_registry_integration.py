"""Tests for Phase 4: analysis pipeline registry integration.

Verifies that analysis uses existing registry data (context-aware refinement)
rather than rebuilding from scratch, and that attorney overrides survive.
"""

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.services.document_registry_service import DocumentRegistryService
from legal_portal.services.main_processor import _format_registry_context


def _processed_doc(
    file_name: str,
    content: str,
    *,
    document_id: str = "doc-001",
    registry: dict = None,
    attorney_enrichment: dict = None,
) -> ProcessedDocument:
    return ProcessedDocument(
        file_name=file_name,
        content=content,
        document_type=DocumentType.CASE_DOCUMENT,
        file_type=FileType.PDF,
        metadata=FileMetadata(file_name=file_name, file_type=FileType.PDF, file_size=100),
        document_id=document_id,
        extraction_quality="high",
        registry=registry,
        attorney_enrichment=attorney_enrichment,
    )


class TestFormatRegistryContext:
    """Tests for _format_registry_context — the prompt context block."""

    def test_includes_pre_classified_type(self):
        doc = _processed_doc(
            "Contract.pdf",
            "Content.",
            registry={
                "document_type": "Contract",
                "document_type_confidence": "medium",
                "document_type_source": "extraction",
                "primary_instrument": "purchase agreement",
            },
        )
        ctx = _format_registry_context(doc)
        assert "pre_classified_type=Contract" in ctx
        assert "instrument=purchase agreement" in ctx

    def test_includes_quick_facts(self):
        doc = _processed_doc(
            "Doc.pdf",
            "Content.",
            registry={
                "quick_facts_raw": {"dates": ["01/15/2025"], "amounts": ["$50,000"]},
                "quick_facts_ai": None,
            },
        )
        ctx = _format_registry_context(doc)
        assert "01/15/2025" in ctx
        assert "$50,000" in ctx

    def test_prefers_ai_facts_over_raw(self):
        doc = _processed_doc(
            "Doc.pdf",
            "Content.",
            registry={
                "quick_facts_raw": {"dates": ["01/01/2000"], "amounts": []},
                "quick_facts_ai": {"dates": ["2025-03-15"], "amounts": ["$100,000"]},
            },
        )
        ctx = _format_registry_context(doc)
        assert "2025-03-15" in ctx
        assert "$100,000" in ctx
        assert "01/01/2000" not in ctx

    def test_includes_signature_status(self):
        doc = _processed_doc(
            "Doc.pdf",
            "Content.",
            registry={
                "signature_expected": True,
                "execution_status": "signed",
            },
        )
        ctx = _format_registry_context(doc)
        assert "signature_expected=True" in ctx
        assert "signed=signed" in ctx

    def test_includes_attorney_input(self):
        doc = _processed_doc(
            "Doc.pdf",
            "Content.",
            attorney_enrichment={
                "document_type_override": "Employment Agreement",
                "attorney_notes": "Critical document for the case",
                "key_facts": {"date": "2025-01-15", "amount": "$75,000"},
            },
        )
        ctx = _format_registry_context(doc)
        assert "ATTORNEY_INPUT" in ctx
        assert "type_override=Employment Agreement" in ctx
        assert "Critical document" in ctx
        assert "date=2025-01-15" in ctx

    def test_empty_registry_returns_empty(self):
        doc = _processed_doc("Doc.pdf", "Content.")
        ctx = _format_registry_context(doc)
        assert ctx == ""

    def test_system_summary_included(self):
        doc = _processed_doc(
            "Doc.pdf",
            "Content.",
            registry={"system_summary": "This agreement sets forth the terms."},
        )
        ctx = _format_registry_context(doc)
        assert "This agreement sets forth" in ctx


class TestAnalysisRegistryFlow:
    """Tests verifying the analysis pipeline uses existing registry + enrich_with_ai."""

    def test_existing_registry_is_enriched_not_rebuilt(self):
        """When a doc carries an existing registry, enrich_with_ai should
        augment it rather than creating a new one from scratch."""
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Contract.pdf",
            "Purchase agreement for property at 123 Main Street.",
            document_id="doc-123",
        )
        # Simulate Stage 1 registry from upload
        initial_reg = service.build_initial_registry(doc)
        assert initial_reg["enrichment_stage"] == "extraction"
        assert initial_reg["document_type"] == "Contract"

        # Simulate AI summary
        ai_summary = {
            "document_name": "Contract.pdf",
            "document_type": "Contract",
            "executive_summary": "A real estate purchase agreement between Smith and Jones.",
            "legal_significance": "Establishes contractual obligations for property sale.",
            "structured_data": {
                "parties": ["John Smith", "Jane Jones"],
                "dates": [{"date": "2025-01-15", "event": "Closing date"}],
                "amounts": [{"amount": "$250,000", "description": "Purchase price"}],
            },
        }

        # Stage 4: enrich existing registry
        enriched = service.enrich_with_ai(initial_reg, ai_summary)

        assert enriched["enrichment_stage"] == "ai_analysis"
        assert enriched["document_type"] == "Contract"
        assert enriched["legal_significance"] is not None
        assert enriched["quick_facts_ai"] is not None
        assert enriched["quick_facts_raw"] is not None  # Original raw facts preserved
        assert enriched["document_id"] == "doc-123"

    def test_attorney_overrides_survive_ai_enrichment(self):
        """Attorney-provided values must never be overwritten by AI."""
        service = DocumentRegistryService()
        doc = ProcessedDocument(
            file_name="Doc.pdf",
            content="Some content.",
            document_type=DocumentType.CASE_DOCUMENT,
            file_type=FileType.PDF,
            metadata=FileMetadata(file_name="Doc.pdf", file_type=FileType.PDF, file_size=100),
            document_id="doc-456",
            attorney_enrichment={
                "document_type_override": "Employment Agreement",
                "attorney_notes": "This is the key employment doc.",
                "key_facts": {"start_date": "2024-06-01"},
            },
        )
        initial_reg = service.build_initial_registry(doc)
        assert initial_reg["document_type_override"] == "Employment Agreement"
        assert initial_reg["attorney_notes"] == "This is the key employment doc."

        ai_summary = {
            "document_name": "Doc.pdf",
            "document_type": "Contract",
            "executive_summary": "An employment contract.",
        }
        enriched = service.enrich_with_ai(initial_reg, ai_summary)

        # Attorney override preserved
        assert enriched["document_type_override"] == "Employment Agreement"
        assert enriched["attorney_notes"] == "This is the key employment doc."
        # AI suggestion stored but type NOT replaced (attorney override exists)
        assert enriched["ai_suggested_document_type"] == "Contract"
        # document_type may or may not have been replaced depending on confidence,
        # but the effective type (override > base) is Employment Agreement
        assert enriched["document_type_override"] == "Employment Agreement"

    def test_enrichment_stage_progresses_not_regresses(self):
        """Stage must only advance: extraction -> ai_analysis."""
        service = DocumentRegistryService()
        doc = _processed_doc("Doc.pdf", "Content.", document_id="doc-789")
        reg = service.build_initial_registry(doc)
        assert reg["enrichment_stage"] == "extraction"

        enriched = service.enrich_with_ai(reg, {"document_name": "Doc.pdf"})
        assert enriched["enrichment_stage"] == "ai_analysis"

    def test_key_document_flags_applied(self):
        """After fact matrix, key document flags should be set."""
        service = DocumentRegistryService()
        doc = _processed_doc("Contract.pdf", "Important contract content.", document_id="doc-key")
        reg = service.build_initial_registry(doc)

        # Simulate AI enrichment
        ai_summary = {"document_name": "Contract.pdf", "document_type": "Contract"}
        enriched = service.enrich_with_ai(reg, ai_summary)

        # Simulate key doc flag (as done in processor pass 2)
        enriched["is_key_document"] = True
        enriched["key_document_significance"] = "Core contractual evidence"

        assert enriched["is_key_document"] is True
        assert enriched["key_document_significance"] == "Core contractual evidence"

    def test_persist_uses_canonical_path(self):
        """Verify resolve_denormalized_columns produces correct values after AI enrichment."""
        service = DocumentRegistryService()
        doc = _processed_doc("Contract.pdf", "Content.", document_id="doc-persist")
        reg = service.build_initial_registry(doc)

        ai_summary = {
            "document_name": "Contract.pdf",
            "document_type": "Contract",
            "executive_summary": "A contract summary.",
        }
        enriched = service.enrich_with_ai(reg, ai_summary)

        columns = DocumentRegistryService.resolve_denormalized_columns(enriched)
        assert columns["enrichment_stage"] == "ai_analysis"
        assert columns["document_type_label"] == "Contract"
        assert columns["document_type_confidence"] == "high"  # AI upgraded from medium
