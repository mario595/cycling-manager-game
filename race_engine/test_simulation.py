from __future__ import annotations

import sys

from race_engine import (
    Course,
    Rider,
    RiderAttributes,
    Segment,
    run_race,
)


def main() -> None:
    climber = Rider(
        id="1",
        name="Climber",
        attributes=RiderAttributes(climb=90, sprint=40, flat=50, resistance=70),
    )
    rouleur = Rider(
        id="3",
        name="Rouleur",
        attributes=RiderAttributes(climb=60, sprint=60, flat=75, resistance=85),
    )

    sprinters = [
        Rider(
            id=f"s{i}",
            name=f"Sprinter {i}",
            attributes=RiderAttributes(climb=30, sprint=95, flat=78, resistance=60),
        )
        for i in range(1, 5)
    ]
    doms = [
        Rider(
            id=f"d{i}",
            name=f"Domestique {i}",
            attributes=RiderAttributes(climb=55, sprint=50, flat=72, resistance=75),
        )
        for i in range(1, 4)
    ]

    riders = [climber, rouleur] + sprinters + doms

    log_path = "race.jsonl"
    if len(sys.argv) > 1:
        log_path = sys.argv[1]

    course = Course(
        segments=[
            Segment(length=15000.0, gradient=0.0),
            Segment(length=1000.0, gradient=5.0),
            Segment(length=3000.0, gradient=6.0),
            Segment(length=1000.0, gradient=8.0),
            Segment(length=500.0, gradient=12.0),
            Segment(length=5500.0, gradient=-5)
        ]
    )

    print("Running race...")
    results = run_race(riders, course, log_path=log_path)

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


if __name__ == "__main__":
    main()
