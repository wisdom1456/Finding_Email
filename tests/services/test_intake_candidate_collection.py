"""Tests for intake candidate detection and AI-selection swap logic.

`is_intake_candidate` mirrors the existing mechanical detection conditions in
`_download_and_extract_documents` (analysis_orchestrator.py) exactly, so it
can be used to build a candidate list without altering that logic.

`apply_intake_selection` is the pure post-loop swap: given the mechanically
chosen intake path, the leftover file_paths, the collected candidates, and an
optional AI selection result, it returns the (possibly updated) intake path
and file_paths — without touching global state or the mechanical loop.
"""
from types import SimpleNamespace

from legal_portal.services.analysis.analysis_orchestrator import (
    apply_intake_selection,
    build_intake_selection_candidates,
    is_intake_candidate,
    reorder_intake_by_selection,
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


# ---------------------------------------------------------------------------
# reorder_intake_by_selection (live pipeline: process_case_background)
# ---------------------------------------------------------------------------


def _pdoc(doc_id: str) -> SimpleNamespace:
    # Stand-in for ProcessedDocument: only .document_id is consulted.
    return SimpleNamespace(document_id=doc_id)


def test_reorder_moves_winner_to_front_preserving_rest_order():
    a, b, c = _pdoc("a"), _pdoc("b"), _pdoc("c")
    result = reorder_intake_by_selection([a, b, c], "b")
    assert result == [b, a, c]
    # membership unchanged — nothing dropped or added
    assert set(id(p) for p in result) == {id(a), id(b), id(c)}


def test_reorder_winner_already_front_is_unchanged():
    a, b = _pdoc("a"), _pdoc("b")
    result = reorder_intake_by_selection([a, b], "a")
    assert result == [a, b]


def test_reorder_unknown_id_is_unchanged():
    a, b = _pdoc("a"), _pdoc("b")
    result = reorder_intake_by_selection([a, b], "nope")
    assert result == [a, b]


def test_reorder_does_not_mutate_input_list():
    a, b = _pdoc("a"), _pdoc("b")
    original = [a, b]
    reorder_intake_by_selection(original, "b")
    assert original == [a, b]


# ---------------------------------------------------------------------------
# build_intake_selection_candidates (live pipeline: process_case_background)
# ---------------------------------------------------------------------------


def test_candidates_use_real_file_type_from_document_rows():
    from legal_portal.core.data_models import FileType

    # Live-pipeline pdocs are constructed with a hardcoded FileType.PDF
    # fallback; the candidate builder must report the REAL type from the
    # original document rows instead.
    pdocs = [
        SimpleNamespace(document_id="a", file_name="Intake.docx", file_type=FileType.PDF),
        SimpleNamespace(document_id="b", file_name="Intake.pdf", file_type=FileType.PDF),
    ]
    documents = [
        {
            "id": "a",
            "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        {"id": "b", "file_type": "application/pdf"},
    ]
    candidates = build_intake_selection_candidates(pdocs, documents)
    assert candidates == [
        {
            "id": "a",
            "file_name": "Intake.docx",
            "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        {"id": "b", "file_name": "Intake.pdf", "file_type": "application/pdf"},
    ]


def test_candidates_fall_back_to_pdoc_file_type_when_row_missing():
    from legal_portal.core.data_models import FileType

    pdocs = [SimpleNamespace(document_id="x", file_name="Intake.pdf", file_type=FileType.PDF)]
    candidates = build_intake_selection_candidates(pdocs, documents=[])
    assert candidates == [
        {"id": "x", "file_name": "Intake.pdf", "file_type": "application/pdf"}
    ]
