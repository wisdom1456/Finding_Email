from legal_portal.core.data_models import DocumentGroup, GroupType
from legal_portal.services.group_quality_metrics import GroupingMetrics, build_grouping_metrics


def test_build_grouping_metrics():
    groups = [
        DocumentGroup(
            group_id="grp_1",
            group_type=GroupType.EMAIL_THREAD,
            label="Thread: test",
            member_document_ids=["d1", "d2", "d3"],
            member_document_names=["e1.eml", "e2.eml", "e3.eml"],
        ),
        DocumentGroup(
            group_id="grp_2",
            group_type=GroupType.BANK_STATEMENTS,
            label="Chase Statements",
            member_document_ids=["d4", "d5"],
            member_document_names=["s1.pdf", "s2.pdf"],
        ),
    ]
    metrics = build_grouping_metrics("case_123", 10, groups)
    assert metrics.groups_detected == 2
    assert metrics.grouped_documents == 5
    assert metrics.ungrouped_documents == 5
    assert metrics.groups_by_type == {"email_thread": 1, "bank_statements": 1}


def test_token_reduction_pct():
    m = GroupingMetrics(
        case_id="c", total_documents=10, groups_detected=1,
        grouped_documents=5, ungrouped_documents=5,
        tokens_before=10000, tokens_after=7000,
    )
    assert m._token_reduction_pct() == "30.0%"


def test_token_reduction_none_when_no_data():
    m = GroupingMetrics(
        case_id="c", total_documents=10, groups_detected=0,
        grouped_documents=0, ungrouped_documents=10,
    )
    assert m._token_reduction_pct() is None
