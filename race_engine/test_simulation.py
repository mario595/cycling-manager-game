from __future__ import annotations

from race_engine import (
    Course,
    RaceState,
    Rider,
    RiderAttributes,
    Segment,
)


def run_race(name: str, riders: list[Rider], course: Course) -> None:
    race = RaceState.create_initial_state(riders=riders, course=course)

    print(f"=== {name} ===")
    print(f"Course: {course.total_distance / 1000:.1f}km")
    print(f"Segments: {[(f'{s.length/1000:.1f}km', f'{s.gradient}%') for s in course.segments]}")

    while not race.is_finished():
        race.tick()

    print()
    print("Results:")
    for i, rs in enumerate(race.get_results(), 1):
        print(
            f"  {i}. {rs.rider.name:10s} - {rs.finish_time:>5d}s "
            f"(energy={rs.energy:5.1f}, stamina={rs.stamina:5.1f})"
        )
    print()


def main() -> None:
    climber = Rider(
        id="1",
        name="Climber",
        attributes=RiderAttributes(climb=90, sprint=40, flat=50, resistance=70),
    )
    sprinter = Rider(
        id="2",
        name="Sprinter",
        attributes=RiderAttributes(climb=30, sprint=95, flat=80, resistance=60),
    )
    rouleur = Rider(
        id="3",
        name="Rouleur",
        attributes=RiderAttributes(climb=60, sprint=60, flat=75, resistance=85),
    )
    riders = [climber, sprinter, rouleur]

    # Short race: 10km
    short_course = Course(
        segments=[
            Segment(length=5000.0, gradient=0.0),
            Segment(length=3000.0, gradient=6.0),
            Segment(length=2000.0, gradient=-4.0),
        ]
    )
    run_race("Short Race (10km)", riders, short_course)

    # Mountain stage: 15km
    mountain_course = Course(
        segments=[
            Segment(length=3000.0, gradient=0.0),
            Segment(length=5000.0, gradient=7.0),
            Segment(length=2000.0, gradient=4.0),
            Segment(length=2000.0, gradient=-5.0),
            Segment(length=3000.0, gradient=0.0),
        ]
    )
    run_race("Mountain Stage (15km)", riders, mountain_course)

    # Long flat: 50km
    flat_course = Course(
        segments=[
            Segment(length=25000.0, gradient=0.0),
            Segment(length=5000.0, gradient=2.0),
            Segment(length=20000.0, gradient=0.0),
        ]
    )
    run_race("Long Flat (50km)", riders, flat_course)


if __name__ == "__main__":
    main()
