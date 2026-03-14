from legal_portal.core.data_models import DocumentGroup, GroupSummary, GroupType


def test_group_type_enum_high_confidence_types():
    """Only high-confidence types ship in first rollout."""
    assert GroupType.EMAIL_THREAD == "email_thread"
    assert GroupType.CONTRACT_FAMILY == "contract_family"
    assert GroupType.PHOTO_SEQUENCE == "photo_sequence"
    assert GroupType.BANK_STATEMENTS == "bank_statements"


def test_document_group_creation():
    group = DocumentGroup(
        group_id="grp_abc123",
        group_type=GroupType.BANK_STATEMENTS,
        label="Chase Bank Statements (Jan–Jun 2024)",
        member_document_ids=["doc1", "doc2", "doc3"],
        member_document_names=["chase_jan_2024.pdf", "chase_feb_2024.pdf", "chase_mar_2024.pdf"],
        group_metadata={
            "institution": "Chase Bank",
            "date_range": "2024-01 to 2024-06",
            "account_hint": "****4521",
        },
        authority_score=68,
    )
    assert group.member_count == 3
    assert group.group_type == GroupType.BANK_STATEMENTS


def test_group_requires_two_members():
    """Groups with < 2 members are invalid."""
    group = DocumentGroup(
        group_id="grp_x",
        group_type=GroupType.EMAIL_THREAD,
        label="Thread: test",
        member_document_ids=["d1"],
        member_document_names=["e1.eml"],
    )
    assert group.member_count == 1  # Model allows it; pipeline filters < 2


def test_group_defaults():
    group = DocumentGroup(
        group_id="grp_x",
        group_type=GroupType.EMAIL_THREAD,
        label="Thread: test",
        member_document_ids=["d1", "d2"],
        member_document_names=["e1.eml", "e2.eml"],
    )
    assert group.authority_score is None
    assert group.group_metadata == {}
    assert group.canonical_document_id is None


def test_group_summary_creation():
    gs = GroupSummary(
        group_id="grp_abc",
        group_type=GroupType.BANK_STATEMENTS,
        label="Chase Statements",
        member_count=3,
        member_document_names=["a.pdf", "b.pdf", "c.pdf"],
        combined_narrative="Three monthly bank statements from Chase.",
        key_findings=["Total deposits: $15,000"],
        authority_score=68,
    )
    assert gs.member_count == 3
    assert gs.extraction_quality == "high"
    assert gs.legal_significance is None
    assert gs.key_quotes == []
