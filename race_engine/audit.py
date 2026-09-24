"""Regression harness for the race engine.

Runs the bundled configs across a fixed set of seeds and reports the metrics
that decide whether a course produces the expected archetype and a realistic
finish, without a person re-running six configs by hand. See README.md's
"Regression audit" and "Realism status" sections for how this is used to
validate engine changes.

Usage:
    python -m race_engine.audit
    python -m race_engine.audit --configs sprinters_classic,san_remo
    python -m race_engine.audit --seeds 1,7,42 --json out.json
    python -m race_engine.audit --baseline audit_baseline.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from race_engine.config import _VALID_WIND_BANDS, load_config
from race_engine.models import RaceState

_CONFIGS_DIR = Path(__file__).parent / "configs"

DEFAULT_SEEDS = [1, 7, 42, 123, 2024]

# Expected winning archetype per course, by id prefix (gc/pu/ru/sp/do).
# Test data, not engine knowledge — configs carry none (see README.md).
EXPECTED_ARCHETYPE = {
    "sprinters_classic": "sp",
    "san_remo": {"pu", "sp"},
    "lombardia": {"gc", "pu"},
    "classics_hilly": {"gc", "pu"},
    "summit_finish": "gc",
    "mountain_stage": "gc",
}

ARCHETYPE_NAMES = {
    "gc": "GC climber",
    "pu": "puncheur",
    "ru": "rouleur",
    "sp": "sprinter",
    "do": "domestique",
}

GAP_THRESHOLDS = (5.0, 30.0, 60.0)
FRONT_GAP_TRIGGER = 100.0  # meters off the front counted as "shelled"
DEFAULT_TICK_CAP_MULTIPLIER = 3.0


def _archetype(rider_id: str) -> str:
    for prefix in ("gc", "pu", "ru", "sp", "do"):
        if rider_id.startswith(prefix):
            return prefix
    return rider_id


@dataclass
class RunResult:
    config: str
    seed: int
    winner_id: str
    winner_archetype: str
    winner_time: int
    winner_avg_kmh: float
    gap_1st_2nd: float
    gap_1st_last: float
    within_5s: int
    within_30s: int
    within_60s: int
    stamina_zero_count: int
    last_over_winner_ratio: float
    first_shelled_tick: int | None
    first_shelled_position: float | None
    surge_ticks: dict[str, int] = field(default_factory=dict)
    hit_tick_cap: bool = False
    dnf_riders: list[str] = field(default_factory=list)


def _run_one(
    config_path: str,
    seed: int,
    tick_cap_multiplier: float,
    wind_override: bool | None = None,
    wind_band_override: str | None = None,
) -> RunResult:
    random.seed(seed)
    cfg = load_config(config_path)
    riders, course = cfg["riders"], cfg["course"]
    wind_enabled = cfg["wind_enabled"] if wind_override is None else wind_override
    wind_band = wind_band_override if wind_band_override is not None else cfg["wind_band"]
    state = RaceState.create_initial_state(
        riders, course, wind=wind_enabled, wind_band=wind_band, seed=seed
    )

    surge_ticks: dict[str, int] = {rs.rider.id: 0 for rs in state.rider_states}
    first_shelled_tick: int | None = None
    first_shelled_position: float | None = None

    # A soft cap: once any rider finishes, stop after tick_cap_multiplier x
    # that tick, rather than let a Finding-2 death-spiral run unbounded.
    finish_tick: int | None = None
    hard_cap = None

    while not state.is_finished():
        state.tick()
        t = state.current_time

        positions = [rs.position for rs in state.rider_states if not rs.finished]
        if positions:
            front = max(rs.position for rs in state.rider_states)
            for rs in state.rider_states:
                if rs.finished:
                    continue
                if rs.surging:
                    surge_ticks[rs.rider.id] += 1
                if first_shelled_tick is None and front - rs.position > FRONT_GAP_TRIGGER:
                    first_shelled_tick = t
                    first_shelled_position = front

        if finish_tick is None and any(rs.finished for rs in state.rider_states):
            finish_tick = t
            hard_cap = int(finish_tick * tick_cap_multiplier)
        if hard_cap is not None and t >= hard_cap:
            break

    results = state.get_results()
    dnf_riders = [rs.rider.id for rs in results if not rs.finished]
    finished = [rs for rs in results if rs.finished]

    winner = finished[0]
    winner_time = winner.finish_time
    winner_avg_kmh = (course.total_distance / winner_time) * 3.6

    def _time_of(rs) -> float:
        return rs.finish_time if rs.finished else float(state.current_time)

    gap_1st_2nd = _time_of(finished[1]) - winner_time if len(finished) > 1 else 0.0
    all_times = [_time_of(rs) for rs in results]
    gap_1st_last = max(all_times) - winner_time

    within = {}
    for threshold in GAP_THRESHOLDS:
        within[threshold] = sum(
            1 for rs in results if _time_of(rs) - winner_time <= threshold
        )

    stamina_zero_count = sum(1 for rs in results if rs.stamina <= 0.0)
    last_over_winner_ratio = max(all_times) / winner_time if winner_time else 0.0

    return RunResult(
        config=Path(config_path).stem,
        seed=seed,
        winner_id=winner.rider.id,
        winner_archetype=_archetype(winner.rider.id),
        winner_time=winner_time,
        winner_avg_kmh=winner_avg_kmh,
        gap_1st_2nd=gap_1st_2nd,
        gap_1st_last=gap_1st_last,
        within_5s=within[5.0],
        within_30s=within[30.0],
        within_60s=within[60.0],
        stamina_zero_count=stamina_zero_count,
        last_over_winner_ratio=last_over_winner_ratio,
        first_shelled_tick=first_shelled_tick,
        first_shelled_position=first_shelled_position,
        surge_ticks=surge_ticks,
        hit_tick_cap=hard_cap is not None and state.current_time >= hard_cap and not state.is_finished(),
        dnf_riders=dnf_riders,
    )


def _config_path(name: str) -> Path:
    p = Path(name)
    if p.suffix != ".json":
        p = _CONFIGS_DIR / f"{name}.json"
    elif not p.exists() and (_CONFIGS_DIR / p.name).exists():
        p = _CONFIGS_DIR / p.name
    return p


def _discover_configs() -> list[str]:
    return sorted(
        p.stem
        for p in _CONFIGS_DIR.glob("*.json")
        if not p.stem.startswith("_")
    )


def _expected_ok(config: str, archetype: str) -> bool:
    expected = EXPECTED_ARCHETYPE.get(config)
    if expected is None:
        return True
    if isinstance(expected, set):
        return archetype in expected
    return archetype == expected


def run_audit(
    configs: list[str],
    seeds: list[int],
    jobs: int,
    tick_cap_multiplier: float,
    wind_override: bool | None = None,
    wind_band_override: str | None = None,
) -> list[RunResult]:
    tasks = [
        (str(_config_path(cfg)), seed, tick_cap_multiplier, wind_override, wind_band_override)
        for cfg in configs
        for seed in seeds
    ]
    if jobs <= 1:
        return [_run_one(*t) for t in tasks]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(_run_one_star, tasks))


def _run_one_star(task: tuple[str, int, float, bool | None, str | None]) -> RunResult:
    return _run_one(*task)


def _summarize(results: list[RunResult]) -> dict[str, Any]:
    by_config: dict[str, list[RunResult]] = {}
    for r in results:
        by_config.setdefault(r.config, []).append(r)

    summary: dict[str, Any] = {}
    for config, runs in by_config.items():
        n = len(runs)
        expected_hits = sum(1 for r in runs if _expected_ok(config, r.winner_archetype))
        summary[config] = {
            "runs": n,
            "expected_archetype_hits": f"{expected_hits}/{n}",
            "winners": [f"{r.winner_id}({r.seed})" for r in runs],
            "avg_winner_kmh": sum(r.winner_avg_kmh for r in runs) / n,
            "avg_gap_1st_last": sum(r.gap_1st_last for r in runs) / n,
            "avg_within_5s": sum(r.within_5s for r in runs) / n,
            "max_first_shelled_position": max(
                (r.first_shelled_position for r in runs if r.first_shelled_position is not None),
                default=None,
            ),
            "any_stamina_zero": any(r.stamina_zero_count > 0 for r in runs),
            "any_hit_tick_cap": any(r.hit_tick_cap for r in runs),
            "total_dnf": sum(len(r.dnf_riders) for r in runs),
        }
    return summary


def _print_report(results: list[RunResult], baseline: dict[str, Any] | None) -> None:
    summary = _summarize(results)
    for config, s in summary.items():
        print(f"\n== {config} ==")
        print(f"  expected archetype hits: {s['expected_archetype_hits']}")
        print(f"  winners: {', '.join(s['winners'])}")
        print(f"  avg winner speed: {s['avg_winner_kmh']:.1f} km/h")
        print(f"  avg 1st-last gap: {s['avg_gap_1st_last']:.0f} s")
        print(f"  avg riders within 5s: {s['avg_within_5s']:.1f}")
        if s["max_first_shelled_position"] is not None:
            print(f"  worst >100m-off-front position: {s['max_first_shelled_position']/1000:.1f} km")
        if s["any_stamina_zero"]:
            print("  WARNING: at least one run had a rider finish at stamina 0")
        if s["any_hit_tick_cap"]:
            print("  WARNING: at least one run hit the tick cap (possible Finding 2 regression)")
        if s["total_dnf"] > 0:
            print(f"  time-cut DNFs: {s['total_dnf']}")

        if baseline and config in baseline:
            b = baseline[config]
            d_kmh = s["avg_winner_kmh"] - b["avg_winner_kmh"]
            d_gap = s["avg_gap_1st_last"] - b["avg_gap_1st_last"]
            d_within = s["avg_within_5s"] - b["avg_within_5s"]
            print(
                f"  delta vs baseline: kmh {d_kmh:+.1f}, "
                f"1st-last {d_gap:+.0f}s, within5s {d_within:+.1f}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", type=str, default=None, help="comma-separated config names (default: all bundled)")
    parser.add_argument("--seeds", type=str, default=None, help="comma-separated seeds (default: 1,7,42,123,2024)")
    parser.add_argument("--jobs", type=int, default=1, help="parallel worker processes (default: 1)")
    parser.add_argument("--json", type=str, default=None, help="write per-run results to this JSON file")
    parser.add_argument("--baseline", type=str, default=None, help="prior --json output to diff against")
    parser.add_argument(
        "--tick-cap",
        type=float,
        default=DEFAULT_TICK_CAP_MULTIPLIER,
        help="stop a run at this multiple of the winner's finish tick (default: 3.0)",
    )
    wind_group = parser.add_mutually_exclusive_group()
    wind_group.add_argument("--wind", action="store_true", default=None, help="force wind on for every config, overriding each config's own setting")
    wind_group.add_argument("--no-wind", dest="wind", action="store_false", help="force wind off for every config, overriding each config's own setting")
    parser.add_argument("--wind-band", type=str, default=None, choices=sorted(_VALID_WIND_BANDS), help="force this weather band for every config")
    args = parser.parse_args(argv)

    configs = args.configs.split(",") if args.configs else _discover_configs()
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else DEFAULT_SEEDS

    baseline_summary = None
    if args.baseline:
        with open(args.baseline, "r", encoding="utf-8") as f:
            baseline_raw = json.load(f)
        baseline_summary = _summarize([RunResult(**r) for r in baseline_raw])

    print(f"Running {len(configs)} configs x {len(seeds)} seeds ({len(configs) * len(seeds)} runs)...", file=sys.stderr)
    results = run_audit(configs, seeds, args.jobs, args.tick_cap, args.wind, args.wind_band)

    _print_report(results, baseline_summary)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        print(f"\nWrote {len(results)} run results to {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
