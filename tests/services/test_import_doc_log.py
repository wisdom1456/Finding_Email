from legal_portal.services.cases.import_doc_log import MAX_LOG_ENTRIES, append_entry, set_outcome


def test_append_creates_downloading_entry():
    log = []
    e = append_entry(log, 1, "Lease Agreement.pdf", 1048576)
    assert log == [e]
    assert e == {"i": 1, "name": "Lease Agreement.pdf", "size_bytes": 1048576, "outcome": "downloading"}


def test_name_trimmed_to_80_chars():
    e = append_entry([], 1, "x" * 200, 10)
    assert len(e["name"]) == 80


def test_set_outcome_and_failed_reason():
    e = append_entry([], 1, "a.pdf", 1)
    set_outcome(e, "failed", reason="r" * 300)
    assert e["outcome"] == "failed"
    assert len(e["reason"]) == 120


def test_cap_drops_oldest():
    log = []
    for i in range(MAX_LOG_ENTRIES + 10):
        append_entry(log, i + 1, f"doc{i}", 1)
    assert len(log) == MAX_LOG_ENTRIES
    assert log[0]["i"] == 11  # oldest 10 dropped


def test_every_document_gets_exactly_one_entry():
    log = []
    for i in range(69):
        append_entry(log, i + 1, f"doc {i}", i)
    assert [e["i"] for e in log] == list(range(1, 70))
