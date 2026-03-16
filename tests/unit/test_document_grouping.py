import pytest
from legal_portal.services.documents.document_registry_service import DocumentRegistryService
from legal_portal.core.data_models import DocumentGroup, GroupType


def _make_doc(name, doc_id=None, content="", registry=None):
    """Helper to create a minimal document dict for grouping tests."""
    return {
        "id": doc_id or f"id_{name}",
        "file_name": name,
        "extracted_text": content,
        "metadata": {"registry": registry or {}},
        "file_type": "application/pdf",
    }


class TestEmailThreadGrouping:
    def test_groups_emails_by_subject(self):
        docs = [
            _make_doc("e1.eml", content="Subject: Loan Agreement Review\nFrom: alice@ex.com\n\nPlease review."),
            _make_doc("e2.eml", content="Subject: Re: Loan Agreement Review\nFrom: bob@ex.com\n\nApproved."),
            _make_doc("e3.eml", content="Subject: Re: Loan Agreement Review\nFrom: alice@ex.com\n\nThanks."),
            _make_doc("lease.pdf", content="LEASE AGREEMENT"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        threads = [g for g in groups if g.group_type == GroupType.EMAIL_THREAD]
        assert len(threads) == 1
        assert threads[0].member_count == 3

    def test_single_email_not_grouped(self):
        docs = [_make_doc("e1.eml", content="Subject: Hello\nFrom: a@b.com\n\nHi")]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        assert len([g for g in groups if g.group_type == GroupType.EMAIL_THREAD]) == 0


class TestContractFamilyGrouping:
    def test_groups_contract_with_amendments(self):
        docs = [
            _make_doc("purchase_agreement.pdf"),
            _make_doc("purchase_agreement_amendment_1.pdf"),
            _make_doc("purchase_agreement_exhibit_a.pdf"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        families = [g for g in groups if g.group_type == GroupType.CONTRACT_FAMILY]
        assert len(families) == 1
        assert families[0].member_count == 3
        assert families[0].canonical_document_id == "id_purchase_agreement.pdf"

    def test_unrelated_contracts_not_grouped(self):
        docs = [
            _make_doc("lease.pdf"),
            _make_doc("purchase_agreement.pdf"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        assert len([g for g in groups if g.group_type == GroupType.CONTRACT_FAMILY]) == 0


class TestBankStatementGrouping:
    def test_groups_when_all_three_signals_match(self):
        """Requires institution + account hint + statement pattern."""
        docs = [
            _make_doc("chase_statement_jan_2024.pdf",
                       content="CHASE BANK\nStatement Period: January 1-31, 2024\nAccount: ****4521"),
            _make_doc("chase_statement_feb_2024.pdf",
                       content="CHASE BANK\nStatement Period: February 1-28, 2024\nAccount: ****4521"),
            _make_doc("chase_statement_mar_2024.pdf",
                       content="CHASE BANK\nStatement Period: March 1-31, 2024\nAccount: ****4521"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        bank_groups = [g for g in groups if g.group_type == GroupType.BANK_STATEMENTS]
        assert len(bank_groups) == 1
        assert bank_groups[0].member_count == 3

    def test_no_group_without_institution(self):
        """Must have institution match to group."""
        docs = [
            _make_doc("statement_jan.pdf", content="Statement Period: January\nAccount: ****4521"),
            _make_doc("statement_feb.pdf", content="Statement Period: February\nAccount: ****4521"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        bank_groups = [g for g in groups if g.group_type == GroupType.BANK_STATEMENTS]
        assert len(bank_groups) == 0

    def test_no_group_without_account(self):
        """Must have account hint to group."""
        docs = [
            _make_doc("chase_statement_jan.pdf", content="CHASE BANK\nStatement Period: January"),
            _make_doc("chase_statement_feb.pdf", content="CHASE BANK\nStatement Period: February"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        bank_groups = [g for g in groups if g.group_type == GroupType.BANK_STATEMENTS]
        assert len(bank_groups) == 0

    def test_separates_different_accounts(self):
        docs = [
            _make_doc("chase_jan_a.pdf", content="CHASE BANK\nStatement Period: Jan\nAccount: ****4521"),
            _make_doc("chase_feb_a.pdf", content="CHASE BANK\nStatement Period: Feb\nAccount: ****4521"),
            _make_doc("chase_jan_b.pdf", content="CHASE BANK\nStatement Period: Jan\nAccount: ****7890"),
            _make_doc("chase_feb_b.pdf", content="CHASE BANK\nStatement Period: Feb\nAccount: ****7890"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        bank_groups = [g for g in groups if g.group_type == GroupType.BANK_STATEMENTS]
        assert len(bank_groups) == 2


class TestPhotoSequenceGrouping:
    def test_groups_sequential_photos(self):
        docs = [
            _make_doc("photo_001.jpg"),
            _make_doc("photo_002.jpg"),
            _make_doc("photo_003.jpg"),
            _make_doc("lease.pdf"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        photo_groups = [g for g in groups if g.group_type == GroupType.PHOTO_SEQUENCE]
        assert len(photo_groups) == 1
        assert photo_groups[0].member_count == 3


class TestNoGroups:
    def test_single_doc_no_group(self):
        docs = [_make_doc("lease.pdf")]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        assert len(groups) == 0

    def test_unrelated_docs_no_group(self):
        docs = [
            _make_doc("lease.pdf"),
            _make_doc("notice.pdf"),
            _make_doc("deed.pdf"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        assert len(groups) == 0


class TestGroupAuthorityScore:
    def test_group_inherits_max_authority(self):
        docs = [
            _make_doc("e1.eml", content="Subject: Test\nFrom: a@b\n\nHi",
                       registry={"authority_score": 64}),
            _make_doc("e2.eml", content="Subject: Re: Test\nFrom: c@d\n\nReply",
                       registry={"authority_score": 72}),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        assert len(groups) == 1
        assert groups[0].authority_score == 72


class TestDocumentInOneGroupOnly:
    def test_no_double_grouping(self):
        """A document can only appear in one group."""
        docs = [
            _make_doc("photo_001.jpg"),
            _make_doc("photo_002.jpg"),
            _make_doc("photo_003.jpg"),
        ]
        service = DocumentRegistryService()
        groups = service.detect_document_groups(docs)
        all_ids = []
        for g in groups:
            all_ids.extend(g.member_document_ids)
        assert len(all_ids) == len(set(all_ids))
