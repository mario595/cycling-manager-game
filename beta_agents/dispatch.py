"""`python -m beta_agents dispatch`: start the testers' workflow when one of
them is due (#160).

GitHub runs the workflow's hourly schedule only when it has room: in the
testers' first week it ran 20 of about 170, roughly one every 6 to 10 hours,
so a tester due at 7½ hours often waited for the run after next. The staging
machine's scheduler runs this every hour instead (deploy/crontab). It reads
each tester's diary from the `beta-diaries` branch, applies the same rule as
`due`, and only if someone is due asks GitHub for a `workflow_dispatch` run
with `tester: due`. An hour with nobody due costs no Actions minutes, which
are limited on a private repository.

It does nothing without `BETA_DISPATCH_TOKEN`: a fine-grained token on this
repository with Actions read and write and Contents read. Production and local
machines never set it. GitHub's schedule stays on as the backup.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime
from typing import Callable

from . import testers
from .diary import last_stamp
from .game_api import Response, Transport, urllib_transport

API = "https://api.github.com"
WORKFLOW = "beta-agents.yml"
DIARY_BRANCH = "beta-diaries"
DEFAULT_REPO = "mario595/cycling-manager-game"
DEFAULT_REF = "master"


class DispatchError(RuntimeError):
    pass


def dispatch(env: dict[str, str], now: datetime, transport: Transport = urllib_transport, echo=print) -> int:
    token = env.get("BETA_DISPATCH_TOKEN")
    if not token:
        echo("No BETA_DISPATCH_TOKEN: the testers are not dispatched from here.")
        return 0
    repo = env.get("BETA_DISPATCH_REPO") or DEFAULT_REPO
    ref = env.get("BETA_DISPATCH_REF") or DEFAULT_REF

    def github(method: str, path: str, body: dict | None = None, accept: str = "application/vnd.github+json") -> Response:
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "velodra-beta-dispatch/1",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            return transport(method, f"{API}/repos/{repo}{path}", headers, data, 30.0)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise DispatchError(f"{method} {path}: GitHub unreachable ({error})") from error

    try:
        # The branch always exists once the testers have visited, so a 404
        # here means the token cannot read the repository's contents. Stop
        # rather than treat every tester as due and dispatch every hour.
        branch = github("GET", f"/branches/{DIARY_BRANCH}")
        if branch.status != 200:
            raise DispatchError(
                f"GET /branches/{DIARY_BRANCH} answered {branch.status}; "
                "check that the token can read this repository's contents"
            )
        last_visits = {t.slug: _last_visit(github, t.slug) for t in testers.TESTERS}

        due = testers.due(now, lambda t: last_visits[t.slug])
        if not due:
            echo("Nobody is due.")
            return 0
        echo("Due: " + " ".join(t.slug for t in due))
        answer = github("POST", f"/actions/workflows/{WORKFLOW}/dispatches", {"ref": ref, "inputs": {"tester": "due"}})
        if answer.status != 204:
            raise DispatchError(f"the dispatch answered {answer.status}: {str(answer.body)[:300]}")
        echo(f"Dispatched {WORKFLOW} on {ref}.")
        return 0
    except DispatchError as error:
        echo(f"Dispatch failed: {error}")
        return 1


def _last_visit(github: Callable[..., Response], slug: str) -> datetime | None:
    response = github("GET", f"/contents/diaries/{slug}.md?ref={DIARY_BRANCH}", accept="application/vnd.github.raw+json")
    if response.status == 404:
        return None  # a tester with no diary is due at once
    if response.status != 200:
        raise DispatchError(f"reading diaries/{slug}.md answered {response.status}: {str(response.body)[:200]}")
    text = response.body if isinstance(response.body, str) else json.dumps(response.body)
    return last_stamp(text)
