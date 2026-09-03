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
    climbers = [
        Rider(
            id=f"c{i}",
            name=f"Climber {i}",
            attributes=RiderAttributes(climb=cp, sprint=40, flat=sp, resistance=rp, positioning=50),
        )
        for i, (cp, sp, rp) in enumerate(
            [
                (92, 45, 72),
                (90, 42, 70),
                (87, 38, 68),
            ],
            start=1,
        )
    ]
    rouleurs = [
        Rider(
            id=f"r{i}",
            name=f"Rouleur {i}",
            attributes=RiderAttributes(climb=cp, sprint=sp, flat=fp, resistance=rp, positioning=65),
        )
        for i, (cp, sp, fp, rp) in enumerate(
            [
                (62, 63, 78, 86),
                (60, 60, 75, 85),
                (58, 57, 72, 84),
            ],
            start=1,
        )
    ]
    sprinters = [
        Rider(
            id=f"s{i}",
            name=f"Sprinter {i}",
            attributes=RiderAttributes(climb=cp, sprint=sp, flat=fp, resistance=rp, positioning=65),
        )
        for i, (cp, sp, fp, rp) in enumerate(
            [
                (33, 95, 80, 62),
                (31, 93, 79, 60),
                (29, 89, 77, 58),
                (27, 85, 76, 56),
            ],
            start=1,
        )
    ]
    doms = [
        Rider(
            id=f"d{i}",
            name=f"Domestique {i}",
            attributes=RiderAttributes(climb=cp, sprint=sp, flat=fp, resistance=rp, positioning=65),
        )
        for i, (cp, sp, fp, rp) in enumerate(
            [
                (57, 52, 74, 77),
                (55, 50, 72, 75),
                (53, 48, 70, 73),
            ],
            start=1,
        )
    ]

    riders = climbers + rouleurs + sprinters + doms

    log_path = "race.jsonl"
    if len(sys.argv) > 1:
        log_path = sys.argv[1]

    course = Course(
        segments=[
            Segment(length=7000.0, gradient=0.0),
            Segment(length=1000.0, gradient=5.0),
            Segment(length=3000.0, gradient=6.0),
            Segment(length=1000.0, gradient=8.0),
            Segment(length=500.0, gradient=16.0),
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


if __name__ == "__main__":
    main()
