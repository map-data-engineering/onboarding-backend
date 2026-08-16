"""Create (or convert) a view-only staff account for the applicant panel."""

import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from application.permissions import VIEWER_GROUP, ensure_viewer_group


class Command(BaseCommand):
    help = (
        "Create a staff account that can browse applicants but not change them. "
        "Re-running on an existing user converts that account to view-only."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--password",
            help="Set non-interactively (e.g. in a script). Omit to be prompted.",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Remove view-only status instead, promoting the account to a full reviewer.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        group = ensure_viewer_group()

        if options["revoke"]:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f"No such user: {username}") from None
            user.groups.remove(group)
            self.stdout.write(
                self.style.SUCCESS(f"{username} is now a full reviewer (view-only removed).")
            )
            return

        user, created = User.objects.get_or_create(
            username=username, defaults={"email": options["email"]}
        )

        if created:
            password = options["password"]
            if not password:
                password = getpass.getpass("Password: ")
                if password != getpass.getpass("Password (again): "):
                    raise CommandError("Passwords do not match.")
            if not password:
                raise CommandError("A password is required for a new account.")
            user.set_password(password)
        elif options["password"]:
            user.set_password(options["password"])

        if user.is_superuser:
            # A superuser bypasses the viewer group by design (see permissions.py),
            # so silently "restricting" one would be a lie.
            raise CommandError(
                f"{username} is a superuser; superusers are always full reviewers. "
                f"Remove superuser status first if you really want a view-only account."
            )

        user.is_staff = True  # required to reach /panel/ at all
        if options["email"]:
            user.email = options["email"]
        user.save()
        user.groups.add(group)

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} view-only account '{username}' (group: {VIEWER_GROUP}).\n"
                f"They can sign in at /panel/ and see applicants, counts, details and quiz "
                f"breakdowns — but cannot change decisions, delete, or export."
            )
        )
