"""A tester's diary: one Markdown file, one `## <real UTC time>` section per
visit. The next visit reads the last few entries, which is how a tester notices
that something changed oddly between two visits."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ENTRY_MARK = "\n## "


class Diary:
    def __init__(self, directory: Path | str, slug: str, title: str):
        self.path = Path(directory) / "diaries" / f"{slug}.md"
        self.title = title

    def last_entries(self, count: int = 5) -> list[str]:
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8")
        sections = text.split(ENTRY_MARK)[1:]
        return ["## " + section.strip() for section in sections[-count:]]

    def append(self, entry: str, at: datetime | None = None) -> None:
        at = at or datetime.now(timezone.utc)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(f"# {self.title}: diary\n", encoding="utf-8")
        stamp = at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        # A heading inside the entry would be read back as a new entry.
        body = entry.strip().replace(ENTRY_MARK, "\n### ")
        if body.startswith("## "):
            body = "### " + body[3:]
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {stamp}\n\n{body}\n")
