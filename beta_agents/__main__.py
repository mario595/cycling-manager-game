"""`python -m beta_agents <command>`; see beta_agents/README.md.

    visit <tester>      one visit (reads BETA_KEY_<TESTER> and BETA_LLM_API_KEY)
    due [--hour H]      the testers due at this UTC hour, one per line
    register <tester>   create the tester's account; prints the token command
    tools               list the tools generated from the server's schema
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone

from . import testers
from .diary import Diary
from .game_api import GameAPI, GameAPIError
from .llm import DEFAULT_BASE_URL, DEFAULT_MODEL, ChatClient, LLMError
from .tools import Toolbox, operations_from_schema
from .visit import DEFAULT_MAX_STEPS, run_visit

DEFAULT_GAME_URL = "https://velodra.fly.dev"


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    env = dict(os.environ) if env is None else env
    parser = argparse.ArgumentParser(prog="python -m beta_agents")
    parser.add_argument("--base-url", default=env.get("BETA_BASE_URL") or DEFAULT_GAME_URL, help="the game server")
    sub = parser.add_subparsers(dest="command", required=True)

    visit = sub.add_parser("visit", help="run one visit")
    visit.add_argument("tester")
    visit.add_argument("--diary-dir", default=env.get("BETA_DIARY_DIR", "."))
    visit.add_argument("--max-steps", type=int, default=int(env.get("BETA_MAX_STEPS") or DEFAULT_MAX_STEPS))

    due = sub.add_parser("due", help="list the testers due now")
    due.add_argument("--hour", type=int, default=None)

    register = sub.add_parser("register", help="create a tester's account")
    register.add_argument("tester")

    sub.add_parser("tools", help="list the generated tools")

    args = parser.parse_args(argv)
    try:
        if args.command == "due":
            hour = datetime.now(timezone.utc).hour if args.hour is None else args.hour
            for tester in testers.due(hour):
                print(tester.slug)
            return 0
        if args.command == "register":
            return _register(testers.get(args.tester), args.base_url)
        if args.command == "tools":
            api = GameAPI(args.base_url, env.get("BETA_KEY") or _first_key(env))
            for op in operations_from_schema(api.schema()):
                print(f"{op.name:32} {op.method:6} {op.path}")
            print("finish_visit (harness)")
            return 0
        return _visit(testers.get(args.tester), args, env)
    except KeyError as error:
        print(error.args[0], file=sys.stderr)
        return 2
    except (GameAPIError, LLMError) as error:
        print(f"Visit skipped: {error}", file=sys.stderr)
        return 1


def _visit(tester: testers.Tester, args, env: dict[str, str]) -> int:
    key = env.get(tester.secret_name)
    if not key:
        print(f"Visit skipped: no game key in {tester.secret_name}.", file=sys.stderr)
        return 1
    api = GameAPI(args.base_url, key)
    toolbox = Toolbox(api, operations_from_schema(api.schema()))
    llm = ChatClient(
        api_key=env.get("BETA_LLM_API_KEY", ""),
        model=env.get("BETA_LLM_MODEL") or DEFAULT_MODEL,
        base_url=env.get("BETA_LLM_BASE_URL") or DEFAULT_BASE_URL,
        min_interval=float(env.get("BETA_LLM_MIN_INTERVAL") or 6.0),
    )
    diary = Diary(args.diary_dir, tester.slug, tester.display_name)
    print(f"[{tester.slug}] visiting {args.base_url} with {llm.model}")
    outcome = run_visit(tester, toolbox, llm, diary, max_steps=args.max_steps)
    print(
        f"[{tester.slug}] model calls={llm.calls} prompt_tokens={llm.prompt_tokens} "
        f"completion_tokens={llm.completion_tokens} game_requests={api.calls}"
    )
    return 1 if outcome.error else 0


def _register(tester: testers.Tester, base_url: str) -> int:
    api = GameAPI(base_url, key=None)
    response = api.call(
        "POST",
        "/api/accounts/register/",
        body={"email": tester.email, "password": secrets.token_urlsafe(24), "display_name": tester.display_name},
    )
    if response.status not in (200, 201):
        print(f"Registering {tester.email} failed with {response.status}: {response.body}", file=sys.stderr)
        return 1
    print(f"Registered {tester.email}. Now issue its key on the server and store it as {tester.secret_name}:")
    print(f"  fly ssh console --app velodra -C \"su app -s /bin/sh -c 'cd /app && python manage.py issue_api_token {tester.email}'\"")
    return 0


def _first_key(env: dict[str, str]) -> str | None:
    for tester in testers.TESTERS:
        if env.get(tester.secret_name):
            return env[tester.secret_name]
    return None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
