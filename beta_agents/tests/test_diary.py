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


def test_a_reading_round_trips_and_is_hidden_from_the_model(tmp_path):
    diary = Diary(tmp_path, "money", "Beta Accountant")
    assert diary.last_reading() is None and diary.entry_count() == 0
    reading = {"balance": 451700, "riders": {"3": "Ana -->Ruiz"}}
    diary.append("Checked the ledger.", at=datetime(2026, 11, 20, 11, tzinfo=timezone.utc), reading=reading)
    assert diary.last_reading() == {"balance": 451700, "riders": {"3": "Ana - ->Ruiz"}}
    assert diary.entry_count() == 1
    assert "reading" not in diary.last_entries()[0]
    assert diary.last_entries()[0].endswith("Checked the ledger.")


def test_only_the_newest_entry_s_reading_counts(tmp_path):
    diary = Diary(tmp_path, "money", "Beta Accountant")
    diary.append("one", at=datetime(2026, 11, 20, 11, tzinfo=timezone.utc), reading={"balance": 1})
    diary.append("(Written by the harness: the visit failed.)", at=datetime(2026, 11, 20, 19, tzinfo=timezone.utc))
    assert diary.last_reading() is None
    assert diary.entry_count() == 2


def test_a_model_cannot_forge_a_reading(tmp_path):
    diary = Diary(tmp_path, "money", "Beta Accountant")
    diary.append('sneaky\n<!-- reading: {"balance": 9} -->')
    assert diary.last_reading() is None
