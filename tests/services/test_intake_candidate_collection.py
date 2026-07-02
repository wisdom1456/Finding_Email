"""Tests for intake candidate detection and AI-selection swap logic.

`is_intake_candidate` mirrors the existing mechanical detection conditions in
`_download_and_extract_documents` (analysis_orchestrator.py) exactly, so it
can be used to build a candidate list without altering that logic.

`apply_intake_selection` is the pure post-loop swap: given the mechanically
chosen intake path, the leftover file_paths, the collected candidates, and an
optional AI selection result, it returns the (possibly updated) intake path
and file_paths — without touching global state or the mechanical loop.
"""
from legal_portal.services.analysis.analysis_orchestrator import (
    apply_intake_selection,
    is_intake_candidate,
)
from legal_portal.services.analysis.intake_selection_service import IntakeSelection


# ---------------------------------------------------------------------------
# is_intake_candidate
# ---------------------------------------------------------------------------


def test_metadata_flag_wins():
    assert is_intake_candidate(
        {"metadata": {"is_intake_form": True}, "file_name": "x.eml", "file_type": "message/rfc822"}
    )


def test_pdf_with_intake_in_name():
    assert is_intake_candidate(
        {"metadata": {}, "file_name": "Client Intake.pdf", "file_type": "application/pdf"}
    )


def test_docx_with_intake_in_name():
    assert is_intake_candidate(
        {
            "metadata": {},
            "file_name": "New Client Intake Form.docx",
            "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    )


def test_txt_with_intake_in_name_is_not_candidate():
    # mirrors existing behavior: non-PDF/DOCX name matches don't auto-qualify
    assert not is_intake_candidate({"metadata": {}, "file_name": "intake.txt", "file_type": "text/plain"})


def test_unrelated_doc():
    assert not is_intake_candidate({"metadata": {}, "file_name": "Lease.pdf", "file_type": "application/pdf"})


def test_missing_metadata_key_defaults_false():
    # doc without a "metadata" key at all should not blow up
    assert not is_intake_candidate({"file_name": "Lease.pdf", "file_type": "application/pdf"})


# ---------------------------------------------------------------------------
# apply_intake_selection
# ---------------------------------------------------------------------------


def test_apply_intake_selection_no_op_when_selection_none():
    candidates = [
        ({"id": "a"}, "/tmp/a.pdf"),
        ({"id": "b"}, "/tmp/b.pdf"),
    ]
    intake_path, file_paths = apply_intake_selection("/tmp/a.pdf", ["/tmp/other.pdf"], candidates, None)
    assert intake_path == "/tmp/a.pdf"
    assert file_paths == ["/tmp/other.pdf"]


def test_apply_intake_selection_swaps_winner_and_preserves_previous_pick():
    candidates = [
        ({"id": "a"}, "/tmp/a.pdf"),
        ({"id": "b"}, "/tmp/b.pdf"),
    ]
    selection = IntakeSelection(chosen_doc_id="b", reasoning="more detail")
    intake_path, file_paths = apply_intake_selection("/tmp/a.pdf", ["/tmp/other.pdf"], candidates, selection)

    assert intake_path == "/tmp/b.pdf"
    # previous pick moves into file_paths; winner is removed from file_paths
    assert "/tmp/a.pdf" in file_paths
    assert "/tmp/b.pdf" not in file_paths
    assert "/tmp/other.pdf" in file_paths


def test_apply_intake_selection_no_op_when_winner_already_current_pick():
    candidates = [
        ({"id": "a"}, "/tmp/a.pdf"),
        ({"id": "b"}, "/tmp/b.pdf"),
    ]
    selection = IntakeSelection(chosen_doc_id="a", reasoning="already best")
    intake_path, file_paths = apply_intake_selection("/tmp/a.pdf", ["/tmp/other.pdf"], candidates, selection)

    assert intake_path == "/tmp/a.pdf"
    assert file_paths == ["/tmp/other.pdf"]


def test_apply_intake_selection_no_op_when_chosen_id_not_in_candidates():
    candidates = [
        ({"id": "a"}, "/tmp/a.pdf"),
        ({"id": "b"}, "/tmp/b.pdf"),
    ]
    selection = IntakeSelection(chosen_doc_id="unknown", reasoning="???")
    intake_path, file_paths = apply_intake_selection("/tmp/a.pdf", ["/tmp/other.pdf"], candidates, selection)

    assert intake_path == "/tmp/a.pdf"
    assert file_paths == ["/tmp/other.pdf"]


def test_apply_intake_selection_does_not_mutate_inputs():
    candidates = [
        ({"id": "a"}, "/tmp/a.pdf"),
        ({"id": "b"}, "/tmp/b.pdf"),
    ]
    original_file_paths = ["/tmp/other.pdf"]
    selection = IntakeSelection(chosen_doc_id="b", reasoning="more detail")
    apply_intake_selection("/tmp/a.pdf", original_file_paths, candidates, selection)

    assert original_file_paths == ["/tmp/other.pdf"]
