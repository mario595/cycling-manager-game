from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from accounts.tokens import revoke_token


class Command(BaseCommand):
    help = "Revoke an account's API token. The next request using it is refused (#130)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError(f"no account with email {options['email']}")
        if revoke_token(user):
            self.stdout.write(f"revoked the API token for {user.email}")
        else:
            self.stdout.write(f"{user.email} has no API token")
