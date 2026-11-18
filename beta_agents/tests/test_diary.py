from datetime import datetime, timezone

from beta_agents.diary import Diary


def test_append_and_read_back(tmp_path):
    diary = Diary(tmp_path, "youth", "Beta Youth")
    assert diary.last_entries() == []
    for day in range(1, 8):
        diary.append(f"visit {day}\n## not a heading", at=datetime(2026, 11, day, 9, tzinfo=timezone.utc))
    text = diary.path.read_text()
    assert text.startswith("# Beta Youth: diary\n")
    entries = diary.last_entries(5)
    assert len(entries) == 5
    assert entries[0].startswith("## 2026-11-03 09:00 UTC")
    assert "visit 7" in entries[-1] and "### not a heading" in entries[-1]


def test_entry_starting_with_a_heading(tmp_path):
    diary = Diary(tmp_path, "x", "X")
    diary.append("## Summary\nok")
    assert len(diary.last_entries()) == 1


def test_last_visit_at(tmp_path):
    diary = Diary(tmp_path, "racer", "Beta Racer")
    assert diary.last_visit_at() is None
    diary.append("one", at=datetime(2026, 11, 13, 13, 25, tzinfo=timezone.utc))
    diary.append("two\n\n## a heading the model wrote", at=datetime(2026, 11, 13, 13, 28, tzinfo=timezone.utc))
    assert diary.last_visit_at() == datetime(2026, 11, 13, 13, 28, tzinfo=timezone.utc)
