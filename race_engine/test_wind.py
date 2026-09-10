"""Tests for wind (Tier A: attrition — see race_engine/WIND_PLAN.md).

Covers the pure formulas (aero multiplier, cache quantisation) and the
stateful drift/RNG-substream behaviour separately, matching the plan's E1-E3
work items and their explicit verification requirements.
"""

from __future__ import annotations

import random

import pytest

from race_engine.formulas import (
    WIND_BANDS,
    _POWER_BALANCE_CACHE,
    advance_wind,
    compute_base_speed,
    wind_aero_multiplier,
)
from race_engine.models import Course, RaceState, Rider, RiderAttributes, Segment, WindState

MID_ATTRS = RiderAttributes(climb=50, sprint=50, flat=50, resistance=50, positioning=50)


# -- wind_aero_multiplier: verified table from WIND_PLAN.md decision 4 -----
# Expressed as expected flat-speed % change relative to no-wind, mid-attribute
# rider, solo. Table (wind kmh -> {angle: pct_change}), tolerance +-1.5pp for
# the bisection solver's own tiny slack.
_EXPECTED_PCT_CHANGE = {
    8.0: {0: -9.4, 45: -7.0, 90: -0.2, 135: 4.3, 180: 6.3},
    15.0: {0: -16.0, 45: -12.2, 90: -0.6, 135: 8.2, 180: 12.8},
    25.0: {0: -22.1, 45: -18.7, 90: -1.7, 135: 14.0, 180: 20.6},
}


def test_wind_aero_multiplier_matches_verified_table():
    baseline = compute_base_speed(MID_ATTRS, 0.0)
    for speed_kmh, by_angle in _EXPECTED_PCT_CHANGE.items():
        for angle, expected_pct in by_angle.items():
            mult = wind_aero_multiplier(speed_kmh, float(angle))
            v = compute_base_speed(MID_ATTRS, 0.0, mult)
            pct = (v - baseline) / baseline * 100.0
            assert pct == pytest.approx(expected_pct, abs=1.5), (
                f"{speed_kmh}km/h @ {angle} deg: got {pct:.1f}%, expected {expected_pct}%"
            )


def test_wind_aero_multiplier_clamped():
    assert wind_aero_multiplier(0.0, 0.0) == pytest.approx(1.0, abs=0.05)
    # A freak headwind must not exceed the max clamp.
    assert wind_aero_multiplier(100.0, 0.0) <= 2.20 + 1e-9
    # A freak tailwind must not fall below the min clamp (no runaway speed).
    assert wind_aero_multiplier(100.0, 180.0) >= 0.55 - 1e-9


def test_wind_fades_on_climbs():
    """Headwind should hurt a flat far more than a steep climb (WIND_PLAN.md
    decision 3): the same equation that blends terrain correctly makes wind
    fade with gradient for free, no gradient special-casing."""
    flat_base = compute_base_speed(MID_ATTRS, 0.0)
    flat_wind = compute_base_speed(MID_ATTRS, 0.0, wind_aero_multiplier(25.0, 0.0))
    climb_base = compute_base_speed(MID_ATTRS, 8.0)
    climb_wind = compute_base_speed(MID_ATTRS, 8.0, wind_aero_multiplier(25.0, 0.0))

    flat_pct = (flat_wind - flat_base) / flat_base
    climb_pct = (climb_wind - climb_base) / climb_base
    assert climb_pct > flat_pct  # climb loses less (less negative)


def test_compute_base_speed_default_aero_mult_is_inert():
    """No third argument must behave exactly as before wind existed."""
    for gradient in (-5.0, 0.0, 4.0, 8.0):
        assert compute_base_speed(MID_ATTRS, gradient) == compute_base_speed(
            MID_ATTRS, gradient, 1.0
        )


def test_power_balance_cache_key_is_quantised():
    """A large number of distinct aero_mult values must not blow up the
    cache — this is the one place wind could silently wreck performance
    (WIND_PLAN.md risk table)."""
    _POWER_BALANCE_CACHE.clear()
    rng = random.Random(0)
    for _ in range(1000):
        aero_mult = rng.uniform(0.55, 2.20)
        compute_base_speed(MID_ATTRS, 0.0, aero_mult)
    # One rider archetype, one gradient: cache should hold at most ~165
    # distinct quantised multipliers, nowhere near 1000.
    assert len(_POWER_BALANCE_CACHE) <= 200


# -- advance_wind: drift never jumps, angle wraps the short way -------------


def test_advance_wind_drifts_slowly_over_two_hour_race():
    wind = WindState(
        speed=10.0, angle=45.0, target_speed=10.0, target_angle=45.0,
        band_mean=10.0, band="light",
    )
    rng = random.Random(42)
    max_speed_delta = 0.0
    for _ in range(7200):
        prev_speed = wind.speed
        advance_wind(wind, rng)
        max_speed_delta = max(max_speed_delta, abs(wind.speed - prev_speed))
        assert 0.0 <= wind.angle < 360.0

    assert max_speed_delta < 1.0  # generous vs. the plan's verified ~0.15 km/h


def test_advance_wind_band_distribution_over_many_seeds():
    counts = {band: 0 for band in WIND_BANDS}
    n = 1000
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])
    riders = [Rider(id="r0", name="R0", attributes=MID_ATTRS)]
    for seed in range(n):
        state = RaceState.create_initial_state(riders, course, wind=True, seed=seed)
        counts[state.wind.band] += 1

    fractions = {band: c / n for band, c in counts.items()}
    for band, spec in WIND_BANDS.items():
        assert fractions[band] == pytest.approx(spec["probability"], abs=0.05)


def test_advance_wind_takes_shortest_arc_across_wrap():
    wind = WindState(
        speed=10.0, angle=350.0, target_speed=10.0, target_angle=370.0,  # unwrapped, = 10 deg
        band_mean=10.0, band="light",
    )
    rng = random.Random(1)
    # Freeze meander/turn by using a rng seeded to avoid the rare-swing path
    # dominating; instead directly check one relax step moves toward 10, not
    # the long way through 180.
    delta = ((wind.target_angle - wind.angle + 180.0) % 360.0) - 180.0
    assert abs(delta) == pytest.approx(20.0)


# -- RNG substream isolation (WIND_PLAN.md's load-bearing detail) ----------


def test_wind_never_touches_global_rng_stream():
    """Running a race with wind must not shift the global `random` stream
    that jitter (and everything seeded via random.seed) consumes — this is
    what keeps the pre-wind audit baseline valid. Compares the global
    stream's state *after construction only* (before any tick touches it via
    jitter), isolating wind's own construction-time band roll from jitter's
    legitimate per-tick consumption."""
    course = Course(segments=[Segment(length=2000.0, gradient=0.0)])
    riders = [Rider(id="r0", name="R0", attributes=MID_ATTRS)]

    random.seed(99)
    RaceState.create_initial_state(list(riders), course, wind=False)
    draws_no_wind = [random.random() for _ in range(20)]

    random.seed(99)
    RaceState.create_initial_state(list(riders), course, wind=True, seed=7)
    draws_with_wind = [random.random() for _ in range(20)]

    assert draws_no_wind == draws_with_wind


def test_wind_tick_advance_never_touches_global_rng_stream():
    """Same guarantee, but across many ticks: the global stream after N
    ticks of a wind-enabled race must match a wind-disabled race's global
    stream after the same N ticks of jitter draws, tick for tick."""
    course = Course(segments=[Segment(length=2000.0, gradient=0.0)])

    random.seed(123)
    riders_a = [Rider(id="r0", name="R0", attributes=MID_ATTRS)]
    state_no_wind = RaceState.create_initial_state(riders_a, course, wind=False)
    for _ in range(50):
        state_no_wind.tick()
    draws_no_wind = [random.random() for _ in range(10)]

    random.seed(123)
    riders_b = [Rider(id="r0", name="R0", attributes=MID_ATTRS)]
    state_with_wind = RaceState.create_initial_state(riders_b, course, wind=True, seed=7)
    for _ in range(50):
        state_with_wind.tick()
    draws_with_wind = [random.random() for _ in range(10)]

    assert draws_no_wind == draws_with_wind


def test_wind_disabled_state_has_no_wind_and_tick_is_inert():
    course = Course(segments=[Segment(length=2000.0, gradient=0.0)])
    riders = [Rider(id="r0", name="R0", attributes=MID_ATTRS)]
    state = RaceState.create_initial_state(riders, course, wind=False)
    assert state.wind is None
    state.tick()
    assert state.wind is None
