"""A tester's diary: one Markdown file, one `## <real UTC time>` section per
visit. The next visit reads the last few entries, which is how a tester notices
that something changed oddly between two visits."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ENTRY_MARK = "\n## "
STAMP = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC$", re.MULTILINE)
# The harness's reading of the team (snapshot.py), kept in the entry as one
# HTML comment: GitHub's Markdown hides it, and the next visit compares with it.
READING = re.compile(r"^<!-- reading: (.*) -->$", re.MULTILINE)


class Diary:
    def __init__(self, directory: Path | str, slug: str, title: str):
        self.path = Path(directory) / "diaries" / f"{slug}.md"
        self.title = title

    def _sections(self) -> list[str]:
        if not self.path.exists():
            return []
        return self.path.read_text(encoding="utf-8").split(ENTRY_MARK)[1:]

    def last_entries(self, count: int = 5) -> list[str]:
        """The last `count` entries, without the harness's reading comments,
        which are for the harness, not the model."""
        sections = self._sections()[-count:]
        return [READING.sub("", "## " + section.strip()).strip() for section in sections]

    def entry_count(self) -> int:
        return len(self._sections())

    def last_reading(self) -> dict | None:
        """The reading saved with the newest entry, or None if the newest entry
        has none (an entry from before readings, or a failed visit's). Only
        the newest counts: comparing across two visits would read as one."""
        sections = self._sections()
        if not sections:
            return None
        match = READING.search(sections[-1])
        if not match:
            return None
        try:
            reading = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        return reading if isinstance(reading, dict) else None

    def last_visit_at(self) -> datetime | None:
        """When the last entry was written, or None for an empty diary."""
        if not self.path.exists():
            return None
        return last_stamp(self.path.read_text(encoding="utf-8"))

    def append(self, entry: str, at: datetime | None = None, reading: dict | None = None) -> None:
        at = at or datetime.now(timezone.utc)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(f"# {self.title}: diary\n", encoding="utf-8")
        stamp = at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        # A heading inside the entry would be read back as a new entry.
        body = entry.strip().replace(ENTRY_MARK, "\n### ")
        if body.startswith("## "):
            body = "### " + body[3:]
        body = READING.sub("", body).strip()  # only the harness writes a reading
        if reading is not None:
            body += "\n\n<!-- reading: " + json.dumps(reading, ensure_ascii=False, sort_keys=True).replace("--", "- -") + " -->"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {stamp}\n\n{body}\n")


def last_stamp(text: str) -> datetime | None:
    """The time of a diary's last entry, from its text, or None if it has
    none. The dispatcher (dispatch.py) reads diaries this way from GitHub."""
    stamps = STAMP.findall(text)
    if not stamps:
        return None
    return datetime.strptime(stamps[-1], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
