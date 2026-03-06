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
    assert subscription["signature_expected"] is True
    assert subscription["signature_review_recommended"] is False

    business_search = by_name[
        "Cuchillo Greens Grow1 Business Search _ An Official New Mexico Government Website.pdf"
    ]
    assert business_search["authority_level"] == "official_record"

    email_update = by_name["2.14.23 Update from Cuchillo Greens!.pdf"]
    assert email_update["authority_level"] == "party_communication"


def test_registry_includes_attorney_enrichment():
    """Test that registry rows include attorney enrichment data when present on the document."""
    service = DocumentRegistryService()

    doc = ProcessedDocument(
        file_name="Sample_Contract.pdf",
        content="Sample contract content...",
        document_type=DocumentType.CASE_DOCUMENT,
        file_type=FileType.PDF,
        metadata=FileMetadata(
            file_name="Sample_Contract.pdf",
            file_type=FileType.PDF,
            file_size=1024,
        ),
        attorney_enrichment={
            "document_type_override": "purchase_agreement",
            "relevance_level": "critical",
            "key_facts": {"date": "2024-03-15", "amount": "$425,000"},
            "attorney_notes": "Key disclosure doc",
            "document_relationships": [{"related_doc_id": "doc-456", "relationship_type": "modifies"}],
        },
        extraction_quality="high",
        extraction_method="test",
    )

    registry = service.build_registry([doc], [])

    assert len(registry) == 1
    row = registry[0]
    assert row["document_type_override"] == "purchase_agreement"
    assert row["relevance_level"] == "critical"
    assert row["key_facts"] == {"date": "2024-03-15", "amount": "$425,000"}
    assert row["attorney_notes"] == "Key disclosure doc"
    assert len(row["document_relationships"]) == 1
    assert row["document_relationships"][0]["related_doc_id"] == "doc-456"


def test_registry_enrichment_fields_default_to_none_when_absent():
    """Test that registry rows include enrichment keys with None values when no enrichment is present."""
    service = DocumentRegistryService()

    doc = ProcessedDocument(
        file_name="Plain_Document.pdf",
        content="Plain document with no enrichment.",
        document_type=DocumentType.CASE_DOCUMENT,
        file_type=FileType.PDF,
        metadata=FileMetadata(
            file_name="Plain_Document.pdf",
            file_type=FileType.PDF,
            file_size=512,
        ),
        extraction_quality="high",
        extraction_method="test",
    )

    registry = service.build_registry([doc], [])

    assert len(registry) == 1
    row = registry[0]
    assert row["document_type_override"] is None
    assert row["relevance_level"] is None
    assert row["key_facts"] is None
    assert row["attorney_notes"] is None
    assert row["document_relationships"] is None


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
    assert registry[0]["signature_expected"] is True
    assert registry[0]["signature_review_recommended"] is True


# ------------------------------------------------------------------ #
#  Tests for staged enrichment methods
# ------------------------------------------------------------------ #


class TestBuildInitialRegistry:
    """Tests for build_initial_registry (Stage 1: extraction heuristics only)."""

    def test_contract_filename(self):
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Subscription_Agreement_Final.pdf",
            "This Subscription Agreement is entered into as of 01/15/2025 for $50,000.",
            signature_detection={"status": "not_detected", "confidence": "none"},
        )
        reg = service.build_initial_registry(doc)

        assert reg["document_type"] == "Contract"
        assert reg["document_type_confidence"] == "medium"
        assert reg["document_type_source"] == "extraction"
        assert reg["primary_instrument"] == "subscription agreement"
        assert reg["signature_expected"] is True
        assert reg["signature_review_recommended"] is True
        assert reg["enrichment_stage"] == "extraction"
        assert reg["is_key_document"] is False
        assert reg["legal_significance"] is None
        # Quick facts should have extracted the date and amount
        assert any("01/15/2025" in d for d in reg["quick_facts_raw"]["dates"])
        assert any("$50,000" in a for a in reg["quick_facts_raw"]["amounts"])
        assert reg["dates_mentioned"] == reg["quick_facts_raw"]["dates"]
        assert reg["amounts_mentioned"] == reg["quick_facts_raw"]["amounts"]

    def test_email_filename(self):
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Update from Company.eml",
            "Subject: Project Update\nFrom: john@example.com\nHere is the latest update.",
            file_type=FileType.EML,
        )
        reg = service.build_initial_registry(doc)

        assert reg["document_type"] == "Correspondence"
        assert reg["signature_expected"] is False
        assert reg["signature_review_recommended"] is False

    def test_photo_filename(self):
        service = DocumentRegistryService()
        doc = _processed_doc(
            "IMG_0531.jpg",
            "",
            file_type=FileType.IMAGE,
        )
        reg = service.build_initial_registry(doc)

        assert reg["document_type"] == "Photo/Media"
        assert reg["signature_expected"] is False
        assert reg["signature_review_recommended"] is False

    def test_system_summary_generated(self):
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Contract.pdf",
            "PAGE 1\nThis agreement sets forth the terms and conditions for the sale of property located at 123 Main Street.",
        )
        reg = service.build_initial_registry(doc)

        assert reg["system_summary"] is not None
        assert "terms and conditions" in reg["system_summary"]

    def test_preserves_attorney_enrichment(self):
        service = DocumentRegistryService()
        doc = ProcessedDocument(
            file_name="Doc.pdf",
            content="Some content.",
            document_type=DocumentType.CASE_DOCUMENT,
            file_type=FileType.PDF,
            metadata=FileMetadata(file_name="Doc.pdf", file_type=FileType.PDF, file_size=100),
            attorney_enrichment={
                "document_type_override": "Contract",
                "attorney_notes": "Important doc",
            },
            extraction_quality="high",
            extraction_method="test",
        )
        reg = service.build_initial_registry(doc)

        assert reg["document_type_override"] == "Contract"
        assert reg["attorney_notes"] == "Important doc"

    def test_system_summary_skips_ocr_garbage(self):
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Scan.pdf",
            "!@#$%^&*()_+~`|}{[]\\:;?/>.<,\n...:::///!!!@@@###\nThis is the actual content of the scanned document.",
        )
        reg = service.build_initial_registry(doc)
        assert reg["system_summary"] is not None
        assert "actual content" in reg["system_summary"]

    def test_system_summary_skips_email_headers(self):
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Message.eml",
            "From: john@example.com\nTo: jane@example.com\nDate: 2025-01-15\nSubject: Re: Contract Review\nThis email discusses the contract terms and amendments.",
        )
        reg = service.build_initial_registry(doc)
        assert reg["system_summary"] is not None
        assert "contract terms" in reg["system_summary"].lower()

    def test_system_summary_fallback_on_garbage_only(self):
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Contractor_Contract.JPG",
            "!@#$% ^^& *()_ +++\n:::///!!!@@@",
        )
        reg = service.build_initial_registry(doc)
        assert reg["system_summary"] is not None
        assert "document" in reg["system_summary"].lower()

    def test_system_summary_fallback_on_empty_text(self):
        service = DocumentRegistryService()
        doc = _processed_doc("Invoice_2025.pdf", "")
        reg = service.build_initial_registry(doc)
        assert reg["system_summary"] is not None
        assert "document" in reg["system_summary"].lower()


class TestEnrichWithAI:
    """Tests for enrich_with_ai (Stage 4: AI enrichment)."""

    def test_upgrades_low_confidence_type(self):
        service = DocumentRegistryService()
        doc = _processed_doc("Generic_Document.pdf", "Contract terms here.")
        reg = service.build_initial_registry(doc)

        assert reg["document_type"] == "Other"
        assert reg["document_type_confidence"] == "low"

        enriched = service.enrich_with_ai(
            reg,
            {
                "document_type": "Contract",
                "legal_significance": "Defines investment terms.",
                "relevance_to_case": "Core document.",
                "important_details": ["Clause 5 limits liability"],
            },
        )

        assert enriched["document_type"] == "Contract"
        assert enriched["document_type_confidence"] == "high"
        assert enriched["document_type_source"] == "ai"
        assert enriched["legal_significance"] == "Defines investment terms."
        assert enriched["enrichment_stage"] == "ai_analysis"

    def test_preserves_attorney_override(self):
        service = DocumentRegistryService()
        doc = ProcessedDocument(
            file_name="Doc.pdf",
            content="Content.",
            document_type=DocumentType.CASE_DOCUMENT,
            file_type=FileType.PDF,
            metadata=FileMetadata(file_name="Doc.pdf", file_type=FileType.PDF, file_size=100),
            attorney_enrichment={"document_type_override": "Correspondence"},
            extraction_quality="high",
            extraction_method="test",
        )
        reg = service.build_initial_registry(doc)

        enriched = service.enrich_with_ai(
            reg,
            {"document_type": "Contract", "legal_significance": "Some sig"},
        )

        # AI should NOT overwrite the type because attorney override exists
        assert enriched["document_type_override"] == "Correspondence"
        assert enriched["document_type"] != "Contract"  # kept original
        # AI suggestion should still be stored for reference
        assert enriched["ai_suggested_document_type"] == "Contract"

    def test_medium_confidence_stores_suggestion_only(self):
        """AI should NOT auto-replace when current confidence is medium."""
        service = DocumentRegistryService()
        # Contract filename gives medium confidence
        doc = _processed_doc("Subscription_Agreement.pdf", "Content here.")
        reg = service.build_initial_registry(doc)

        assert reg["document_type"] == "Contract"
        assert reg["document_type_confidence"] == "medium"

        enriched = service.enrich_with_ai(
            reg,
            {"document_type": "Legal Filing"},
        )

        # Should NOT replace — medium confidence is not auto-replaced
        assert enriched["document_type"] == "Contract"
        assert enriched["document_type_confidence"] == "medium"
        # But AI suggestion is stored
        assert enriched["ai_suggested_document_type"] == "Legal Filing"

    def test_fact_sources_separated(self):
        """AI facts should go into quick_facts_ai, not merge into quick_facts_raw."""
        service = DocumentRegistryService()
        doc = _processed_doc("Doc.pdf", "Date: 01/01/2025, Amount: $100")
        reg = service.build_initial_registry(doc)

        assert reg["quick_facts_raw"]["dates"] == ["01/01/2025"]
        assert reg["quick_facts_ai"] is None

        enriched = service.enrich_with_ai(
            reg,
            {
                "parties": ["Acme Corp"],
                "structured_data": {
                    "dates": [{"date": "January 1, 2025"}],
                    "amounts": [{"amount": "$100.00"}],
                },
            },
        )

        # quick_facts_raw should be unchanged
        assert enriched["quick_facts_raw"]["dates"] == ["01/01/2025"]
        # AI facts in separate field
        assert enriched["quick_facts_ai"]["parties"] == ["Acme Corp"]
        assert len(enriched["quick_facts_ai"]["dates"]) >= 1

    def test_adds_key_document_from_fact_matrix(self):
        service = DocumentRegistryService()
        doc = _processed_doc("Agreement.pdf", "Agreement content.")
        reg = service.build_initial_registry(doc)

        enriched = service.enrich_with_ai(
            reg,
            {"document_type": "Contract"},
            key_doc={"document_name": "Agreement.pdf", "significance": "Primary contract"},
        )

        assert enriched["is_key_document"] is True
        assert enriched["key_document_significance"] == "Primary contract"

    def test_ai_data_updates_top_level_mentions(self):
        """AI-extracted data should update top-level mention fields."""
        service = DocumentRegistryService()
        doc = _processed_doc(
            "Doc.pdf",
            "On 01/01/2025 for $100.",
        )
        reg = service.build_initial_registry(doc)
        assert reg["dates_mentioned"] == ["01/01/2025"]
        assert reg["amounts_mentioned"] == ["$100"]

        enriched = service.enrich_with_ai(
            reg,
            {
                "parties": ["Acme Corp", "Jane Doe"],
                "structured_data": {
                    "dates": [{"date": "January 1, 2025", "event": "Signing"}],
                    "amounts": [{"amount": "$100.00", "description": "Investment"}],
                },
            },
        )

        # Top-level mentions updated with AI data (richer)
        assert enriched["parties_mentioned"] == ["Acme Corp", "Jane Doe"]
        assert any("January 1, 2025" in d for d in enriched["dates_mentioned"])
        # But raw facts preserved separately
        assert enriched["quick_facts_raw"]["dates"] == ["01/01/2025"]


class TestExtractQuickFacts:
    """Tests for _extract_quick_facts regex extraction."""

    def test_extracts_dates_and_amounts(self):
        service = DocumentRegistryService()
        text = "Agreement dated 03/15/2025 for $425,000. Second payment of $50,000 due Jan 1, 2026."
        facts = service._extract_quick_facts(text)

        assert len(facts["dates"]) >= 2
        assert "03/15/2025" in facts["dates"]
        assert len(facts["amounts"]) >= 1
        assert "$425,000" in facts["amounts"]

    def test_handles_empty_text(self):
        service = DocumentRegistryService()
        facts = service._extract_quick_facts("")
        assert facts == {"dates": [], "amounts": []}

    def test_iso_dates(self):
        service = DocumentRegistryService()
        facts = service._extract_quick_facts("Signed on 2025-03-15.")
        assert "2025-03-15" in facts["dates"]


class TestEnrichCrossDocument:
    """Tests for enrich_cross_document (Stage 2: cross-doc relationships)."""

    def test_email_thread_grouping(self):
        service = DocumentRegistryService()
        docs = [
            _processed_doc(
                "email1.eml",
                "Subject: Project Update\nFrom: a@b.com\nBody 1",
                file_type=FileType.EML,
            ),
            _processed_doc(
                "email2.eml",
                "Subject: Re: Project Update\nFrom: c@d.com\nBody 2",
                file_type=FileType.EML,
            ),
        ]
        registries = [service.build_initial_registry(d) for d in docs]
        enriched = service.enrich_cross_document(registries, docs)

        # Both emails should have suggested_relationships
        assert enriched[0].get("suggested_relationships")
        assert enriched[0]["suggested_relationships"][0]["type"] == "email_thread"
        assert "email2.eml" in enriched[0]["suggested_relationships"][0]["related_documents"]


class TestValidateRegistryIntegrity:
    """Tests for validate_registry_integrity diagnostic."""

    def test_healthy_document(self):
        service = DocumentRegistryService()
        doc = _processed_doc("Contract.pdf", "Some contract content here.")
        registry = service.build_initial_registry(doc)
        columns = DocumentRegistryService.resolve_denormalized_columns(registry)
        document = {**columns, "metadata": {"registry": registry}}
        issues = DocumentRegistryService.validate_registry_integrity(document)
        assert issues == []

    def test_detects_column_mismatch(self):
        service = DocumentRegistryService()
        doc = _processed_doc("Contract.pdf", "Some contract content here.")
        registry = service.build_initial_registry(doc)
        columns = DocumentRegistryService.resolve_denormalized_columns(registry)
        # Intentionally corrupt a column
        columns["document_type_label"] = "WRONG"
        document = {**columns, "metadata": {"registry": registry}}
        issues = DocumentRegistryService.validate_registry_integrity(document)
        assert any("document_type_label" in i for i in issues)

    def test_detects_missing_registry(self):
        document = {"metadata": {}}
        issues = DocumentRegistryService.validate_registry_integrity(document)
        assert any("missing" in i for i in issues)

    def test_detects_invalid_enrichment_stage(self):
        service = DocumentRegistryService()
        doc = _processed_doc("Doc.pdf", "Content.")
        registry = service.build_initial_registry(doc)
        registry["enrichment_stage"] = "bogus"
        columns = DocumentRegistryService.resolve_denormalized_columns(registry)
        document = {**columns, "metadata": {"registry": registry}}
        issues = DocumentRegistryService.validate_registry_integrity(document)
        assert any("enrichment_stage" in i for i in issues)

    def test_detects_inconsistent_ai_fields_without_ai_stage(self):
        """AI-derived fields present but enrichment_stage != ai_analysis."""
        service = DocumentRegistryService()
        doc = _processed_doc("Doc.pdf", "Some content here for analysis.")
        registry = service.build_initial_registry(doc)
        # Stage is 'extraction' but we add AI-derived fields
        assert registry["enrichment_stage"] == "extraction"
        registry["legal_significance"] = "High legal significance"
        registry["quick_facts_ai"] = {"dates": ["2025-01-01"]}
        columns = DocumentRegistryService.resolve_denormalized_columns(registry)
        document = {**columns, "metadata": {"registry": registry}}
        issues = DocumentRegistryService.validate_registry_integrity(document)
        assert any("inconsistent_enrichment_stage" in i for i in issues)
        assert any("legal_significance" in i for i in issues)
        assert any("quick_facts_ai" in i for i in issues)

    def test_no_inconsistency_at_ai_stage(self):
        """AI fields present with ai_analysis stage should not trigger warning."""
        service = DocumentRegistryService()
        doc = _processed_doc("Doc.pdf", "Some content here for analysis.")
        registry = service.build_initial_registry(doc)
        registry["enrichment_stage"] = "ai_analysis"
        registry["legal_significance"] = "High"
        registry["quick_facts_ai"] = {"dates": ["2025-01-01"]}
        columns = DocumentRegistryService.resolve_denormalized_columns(registry)
        document = {**columns, "metadata": {"registry": registry}}
        issues = DocumentRegistryService.validate_registry_integrity(document)
        assert not any("inconsistent" in i for i in issues)


class TestEnrichCrossDocumentContractFamily:
    """Tests for contract family detection in enrich_cross_document."""

    def test_detects_base_plus_addendum(self):
        service = DocumentRegistryService()
        docs = [
            _processed_doc("Purchase_Agreement.pdf", "Base contract content."),
            _processed_doc("Purchase_Agreement_Addendum.pdf", "Addendum content."),
        ]
        registries = [service.build_initial_registry(d) for d in docs]
        enriched = service.enrich_cross_document(registries, docs)

        # Both should have contract_family relationship
        base_rels = [r for r in (enriched[0].get("suggested_relationships") or []) if r["type"] == "contract_family"]
        addendum_rels = [r for r in (enriched[1].get("suggested_relationships") or []) if r["type"] == "contract_family"]
        assert len(base_rels) == 1
        assert "Purchase_Agreement_Addendum.pdf" in base_rels[0]["related_documents"]
        assert len(addendum_rels) == 1
        assert "Purchase_Agreement.pdf" in addendum_rels[0]["related_documents"]

    def test_detects_exhibit(self):
        service = DocumentRegistryService()
        docs = [
            _processed_doc("Contract.pdf", "Main contract."),
            _processed_doc("Contract_Exhibit_A.pdf", "Exhibit A."),
        ]
        registries = [service.build_initial_registry(d) for d in docs]
        enriched = service.enrich_cross_document(registries, docs)

        base_rels = [r for r in (enriched[0].get("suggested_relationships") or []) if r["type"] == "contract_family"]
        assert len(base_rels) == 1

    def test_no_false_positive_unrelated_docs(self):
        service = DocumentRegistryService()
        docs = [
            _processed_doc("Contract.pdf", "A contract."),
            _processed_doc("Invoice.pdf", "An invoice."),
        ]
        registries = [service.build_initial_registry(d) for d in docs]
        enriched = service.enrich_cross_document(registries, docs)

        for reg in enriched:
            family_rels = [r for r in (reg.get("suggested_relationships") or []) if r["type"] == "contract_family"]
            assert len(family_rels) == 0

    def test_detects_amendment(self):
        service = DocumentRegistryService()
        docs = [
            _processed_doc("Lease_Agreement.pdf", "Lease."),
            _processed_doc("Lease_Agreement_Amendment.pdf", "Amendment."),
            _processed_doc("Lease_Agreement_Amendment_2.pdf", "Second amendment."),
        ]
        registries = [service.build_initial_registry(d) for d in docs]
        enriched = service.enrich_cross_document(registries, docs)

        base_rels = [r for r in (enriched[0].get("suggested_relationships") or []) if r["type"] == "contract_family"]
        assert len(base_rels) == 1
        assert len(base_rels[0]["related_documents"]) == 2  # Both amendments


class TestResolveEffectiveType:
    """Tests for resolve_effective_type and naming clarity."""

    def test_override_wins(self):
        reg = {"document_type": "Contract", "document_type_override": "Employment Agreement"}
        assert DocumentRegistryService.resolve_effective_type(reg) == "Employment Agreement"

    def test_base_type_when_no_override(self):
        reg = {"document_type": "Contract", "document_type_override": None}
        assert DocumentRegistryService.resolve_effective_type(reg) == "Contract"

    def test_fallback_to_other(self):
        reg = {"document_type": None, "document_type_override": None}
        assert DocumentRegistryService.resolve_effective_type(reg) == "Other"

    def test_columns_use_effective_type(self):
        reg = {"document_type": "Contract", "document_type_override": "Employment Agreement"}
        cols = DocumentRegistryService.resolve_denormalized_columns(reg)
        assert cols["document_type_label"] == "Employment Agreement"

    def test_ai_suggestion_not_in_effective(self):
        """ai_suggested_document_type is stored but NOT used in effective type resolution."""
        reg = {
            "document_type": "Other",
            "document_type_confidence": "low",
            "ai_suggested_document_type": "Contract",
        }
        # AI suggestion is stored but resolve_effective_type only checks override > base
        assert DocumentRegistryService.resolve_effective_type(reg) == "Other"
