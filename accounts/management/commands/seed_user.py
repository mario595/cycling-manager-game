from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.models import User

DEMO_EMAIL = "test@mail.com"
DEMO_PASSWORD = "123456789"


class Command(BaseCommand):
    help = (
        "Create the shared demo account used for manual review "
        f"({DEMO_EMAIL} / {DEMO_PASSWORD}). Idempotent: an existing user "
        "is left untouched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email", default=DEMO_EMAIL,
            help=f"Email to seed (default {DEMO_EMAIL}).",
        )
        parser.add_argument(
            "--password", default=DEMO_PASSWORD,
            help="Password for a user that gets created (default the demo password).",
        )

    def handle(self, *args, **options):
        email = options["email"]
        user, created = User.objects.get_or_create(email=email)
        if not created:
            self.stdout.write(f"demo user {email} already exists — password left untouched")
            return
        user.set_password(options["password"])
        user.save(update_fields=["password"])
        self.stdout.write(f"created demo user {email}")