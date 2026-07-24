import asyncio
from worker.db_progress_manager import DBProgressManager


class _FakeTable:
    def __init__(self, sink): self.sink = sink
    def update(self, payload): self.sink["payload"] = payload; return self
    def eq(self, *a, **k): return self
    def execute(self): return type("R", (), {"data": [{}]})()


class _FakeSB:
    def __init__(self, sink): self.sink = sink
    def table(self, _): return _FakeTable(self.sink)


def test_publish_progress_forwards_item_stats():
    sink = {}
    pm = DBProgressManager(_FakeSB(sink), "job-1", min_write_interval=0)
    # _check_cancelled reads status; fake returns {} → not cancelled
    asyncio.run(pm.publish_progress(
        "chan", message="Batch 1 complete (12/12 docs summarized)",
        phase="document_analysis", percent=40,
        stats={"items_done": 12, "items_total": 71},
    ))
    assert sink["payload"]["progress"]["stats"] == {"items_done": 12, "items_total": 71}
