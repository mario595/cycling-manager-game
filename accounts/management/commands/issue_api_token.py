from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from accounts.tokens import issue_token


class Command(BaseCommand):
    help = (
        "Issue an API token for an account and print it. The token is shown "
        "once and cannot be recovered; issuing again replaces the old one, "
        "which stops working immediately (#130)."
    )

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError(f"no account with email {options['email']}")
        key = issue_token(user)
        self.stdout.write(key)
        self.stderr.write(
            f"API token for {user.email}. Shown once — store it now. "
            "Send it as 'Authorization: Bearer <token>'."
        )
