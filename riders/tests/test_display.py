from __future__ import annotations

import pytest

from riders.display import to_display_scale


@pytest.mark.parametrize(
    "value, expected",
    [
        (1, 0),
        (4, 0),
        (5, 0),
        (9, 0),
        (10, 1),
        (45, 4),
        (50, 5),
        (55, 5),  # floors, not rounds: not yet a 6
        (59, 5),
        (60, 6),
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
