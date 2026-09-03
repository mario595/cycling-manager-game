from __future__ import annotations

import sys

from race_engine.config import ConfigError, build_race
from race_engine.models import run_race


def main(argv: list[str]) -> int:
    """Entry point.

    - `python -m race_engine config.json [log.jsonl] [--seed N]` runs a race
      from a config file, writing the JSONL log (defaults to `race.jsonl`).
      `--seed N` makes the run reproducible.
    - `python -m race_engine path/to.log.jsonl` opens a log in the viewer
      (requires a TTY; falls back gracefully otherwise).
    """
    if not argv:
        print("usage: python -m race_engine <config.json> [log.jsonl] [--seed N]")
        print("   or: python -m race_engine <race.jsonl>")
        return 2

    arg = argv[0]
    if arg.endswith(".jsonl"):
        from race_engine.player import main as player_main

        return player_main()
    if not arg.endswith(".json"):
        print(f"error: unsupported argument {arg!r} (expected .json config or .jsonl log)")
        return 2

    log_path = "race.jsonl"
    seed: int | None = None
    rest = argv[1:]
    if rest and "--seed" in rest:
        idx = rest.index("--seed")
        if idx + 1 < len(rest):
            try:
                seed = int(rest[idx + 1])
            except ValueError:
                print("error: --seed requires an integer", file=sys.stderr)
                return 2
            rest = rest[:idx] + rest[idx + 2 :]
        else:
            print("error: --seed requires an integer", file=sys.stderr)
            return 2
    if rest:
        log_path = rest[0]

    try:
        riders, course = build_race(arg)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 1

    results = run_race(riders, course, log_path=log_path, seed=seed)
    print(f"Log saved to: {log_path}")
    print()
    print("Results:")
    for i, rs in enumerate(results, 1):
        print(
            f"  {i}. {rs.rider.name:13s} - {rs.finish_time:>5d}s "
            f"(energy={rs.energy:5.1f}, stamina={rs.stamina:5.1f})"
        )
    print()
    print(f"To view: python -m race_engine.player {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))