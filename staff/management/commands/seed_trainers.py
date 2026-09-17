from __future__ import annotations

import random

from django.core.management.base import BaseCommand

from staff.generation import INITIAL_POOL_SIZE, generate_trainer_pool
from staff.models import Trainer


class Command(BaseCommand):
    help = (
        "Add freshly generated trainers to the shared hiring pool. "
        "Non-destructive: it only adds, and existing trainers (pool or "
        "hired) are never touched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=INITIAL_POOL_SIZE,
            help=f"Trainers to add (default {INITIAL_POOL_SIZE}).",
        )
        parser.add_argument(
            "--rng-seed", type=int, default=None,
            help="Seed the generator for a reproducible pool.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        rng = random.Random(options["rng_seed"]) if options["rng_seed"] is not None else None

        pool = generate_trainer_pool(count, rng=rng)
        Trainer.objects.bulk_create(pool)

        self.stdout.write(f"added {len(pool)} trainer(s) to the pool")
