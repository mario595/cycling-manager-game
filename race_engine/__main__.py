from __future__ import annotations

import sys
from pathlib import Path

from race_engine.config import ConfigError, load_config
from race_engine.models import run_race

_PUBLIC_DIR = Path("race_player/public")


def main(argv: list[str]) -> int:
    """Entry point.

    `python -m race_engine config.json [--seed N]` runs a race from a config
    file, writing the brotli-compressed JSONL log to
    `race_player/public/<name>.jsonl.br`. `--seed N` makes the run
    reproducible.
    """
    if not argv:
        print("usage: python -m race_engine <config.json> [--seed N]")
        return 2

    arg = argv[0]
    if not arg.endswith(".json"):
        print(f"error: unsupported argument {arg!r} (expected .json config)")
        return 2

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

    log_path = str(_PUBLIC_DIR / (Path(arg).stem + ".jsonl.br"))
    _PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    try:
        cfg = load_config(arg)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 1

    results, sample_count, tick_interval = run_race(
        cfg["riders"],
        cfg["course"],
        log_path=log_path,
        seed=seed,
        verbose=True,
        team_codes=cfg["team_codes"],
        wind=cfg["wind_enabled"],
        wind_band=cfg["wind_band"],
    )
    print(
        f"Log saved to: {log_path} "
        f"({sample_count} samples every {tick_interval}s)"
    )
    print()
    print("Results:")
    for i, rs in enumerate(results, 1):
        print(
            f"  {i}. {rs.rider.name:13s} - {rs.finish_time:>5d}s "
            f"(energy={rs.energy:5.1f}, stamina={rs.stamina:5.1f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
