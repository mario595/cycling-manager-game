"""What a trainer costs. Derived from the speciality score, never stored —
see specs/trainer-hiring-fee-salary-plan.md, Design decision 1."""

#: The speciality band a generated trainer's peak skill lives in — 70 to 95
#: (staff/generation.py's _SPECIALITY_BAND). Duplicated here so this module
#: stays self-contained arithmetic; keep the two in step.
_SPECIALITY_BAND = (70, 95)

#: Weekly salary at the bottom of the speciality band (70) and at the top
#: (95). Interpolated linearly between; a trainer's score cannot fall
#: outside _SPECIALITY_BAND, but clamp anyway so a hand-made Trainer in a
#: test cannot produce a negative salary.
SALARY_AT_MIN_SPECIALITY = 1_500
SALARY_AT_MAX_SPECIALITY = 4_500

#: The hire fee is this multiple of the weekly salary. Load-bearing: it is
#: the only thing deterring fire-and-rehire, since firing is free and has no
#: cooldown (staff/README.md). Twelve weeks is a full season, so dodging a
#: few lean weeks never pays.
FEE_WEEKS_OF_SALARY = 12


def _round_to_nearest_50(value: int) -> int:
    """Integer nearest-50 rounding, so prices read as prices rather than as
    hash output."""
    return 50 * ((value + 25) // 50)


def weekly_salary(trainer) -> int:
    """A trainer's weekly salary, scaled linearly off their speciality
    score. Clamped to the speciality band so an out-of-band trainer in a
    test cannot end up with a negative salary. Whole credits — the ledger
    is BigIntegerField, never Decimal."""
    score = getattr(trainer, trainer.speciality)
    clamped = min(max(score, _SPECIALITY_BAND[0]), _SPECIALITY_BAND[1])
    raw = SALARY_AT_MIN_SPECIALITY + (
        (clamped - _SPECIALITY_BAND[0])
        * (SALARY_AT_MAX_SPECIALITY - SALARY_AT_MIN_SPECIALITY)
        // (_SPECIALITY_BAND[1] - _SPECIALITY_BAND[0])
    )
    return _round_to_nearest_50(raw)


def hire_fee(trainer) -> int:
    """The one-off fee to hire a trainer: FEE_WEEKS_OF_SALARY times their
    weekly salary. That multiple is what makes fire-and-rehire never pay —
    the fee is the cooldown firing deliberately lacks (staff/README.md)."""
    return FEE_WEEKS_OF_SALARY * weekly_salary(trainer)