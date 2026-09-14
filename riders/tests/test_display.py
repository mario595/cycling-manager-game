from __future__ import annotations

import pytest

from riders.display import to_display_scale


@pytest.mark.parametrize(
    "value, expected",
    [
        (1, 0),
        (4, 0),
        (5, 0),  # round-half-to-even: 0.5 -> 0
        (45, 4),  # round-half-to-even: 4.5 -> 4
        (50, 5),
        (55, 6),  # round-half-to-even: 5.5 -> 6
        (94, 9),
        (100, 10),
    ],
)
def test_to_display_scale(value, expected):
    assert to_display_scale(value) == expected


def test_to_display_scale_is_lossy():
    """Two riders can look identical on the display scale but differ — the
    property specs/rider-attributes.md calls out by name."""
    assert to_display_scale(71) == to_display_scale(74) == 7
