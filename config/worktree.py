"""Per-worktree identity: database names and a development server port.

Several agents work in parallel, each in its own git worktree under
`.claude/worktrees/`, against a single Postgres instance. Anything they would
otherwise share is a collision waiting to happen:

- the **test database**. `pytest-django` builds `test_<NAME>`, so two runs with
  the same `NAME` drop and recreate the same database underneath each other.
- the **development database**. Two branches with different migrations applied
  to one schema corrupt each other.
- the **runserver port**. Two servers cannot both hold 8000.

All three are derived here from the worktree's directory name, so isolation is
automatic and there is no environment variable for anyone to forget.

**The main checkout is deliberately unchanged** — it keeps `cycling_manager`
and port 8000, so existing local data and habits survive. Only worktrees get a
suffix.

Nothing here imports Django: settings import it, and so can a plain script.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# config/worktree.py -> config/ -> the repository (or worktree) root.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Postgres truncates identifiers at 63 bytes; past that two long worktree names
# would silently become the same database.
_MAX_IDENTIFIER = 63

# Ports are drawn from this range, which is above the usual 8000 and well below
# Vite's 5173.
_PORT_BASE = 8000
_PORT_SPAN = 1000


def worktree_name() -> str | None:
    """This worktree's name, or None when running from the main checkout.

    A worktree is recognised by its parent directory: `EnterWorktree` and the
    documented `git worktree add` both place them under `.claude/worktrees/`.
    """
    if REPO_ROOT.parent.name != "worktrees":
        return None
    slug = re.sub(r"[^a-z0-9_]+", "_", REPO_ROOT.name.lower()).strip("_")
    return slug or None


def database_name() -> str:
    """The development database for this checkout."""
    name = worktree_name()
    if name is None:
        return "cycling_manager"
    return f"cycling_manager_{name}"[:_MAX_IDENTIFIER]


def test_database_name() -> str:
    """The database `pytest-django` should build for this checkout.

    Django creates and drops this itself; nothing needs to pre-create it.
    """
    name = worktree_name()
    if name is None:
        return "test_cycling_manager"
    return f"test_cycling_manager_{name}"[:_MAX_IDENTIFIER]


def runserver_port() -> int:
    """A stable development port for this checkout.

    Stable rather than "first free", so a branch keeps the same URL across
    restarts and can be bookmarked. Two worktrees can in principle hash to the
    same port; whoever starts second gets "address already in use" and should
    step up by one rather than killing the first.
    """
    name = worktree_name()
    if name is None:
        return _PORT_BASE
    digest = hashlib.sha256(name.encode()).digest()
    return _PORT_BASE + int.from_bytes(digest[:2], "big") % _PORT_SPAN


if __name__ == "__main__":
    print(f"worktree:  {worktree_name() or '(main checkout)'}")
    print(f"database:  {database_name()}")
    print(f"test db:   {test_database_name()}")
    print(f"port:      {runserver_port()}")
