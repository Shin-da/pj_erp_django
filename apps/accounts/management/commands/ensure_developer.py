"""Create the single developer login. Does not touch other employees."""

from django.core.management.base import BaseCommand

from apps.accounts.developer import DEFAULT_CODE, ensure_developer_account


class Command(BaseCommand):
    help = "Create or update the developer login (employee_code=dev). Ordinary staff are not changed."

    def add_arguments(self, parser):
        parser.add_argument("--code", default=DEFAULT_CODE)
        parser.add_argument("--first-name", default="Jeffmathew")
        parser.add_argument("--last-name", default="Garcia")
        parser.add_argument("--password", default="", help="Set a password. Otherwise a new one is generated.")
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Replace the password even if the account already exists.",
        )

    def handle(self, *args, **opts):
        user, created, password_set = ensure_developer_account(
            password=opts["password"],
            code=opts["code"],
            first_name=opts["first_name"],
            last_name=opts["last_name"],
            reset_password=opts["reset_password"],
            generate_if_missing=True,
        )
        if user is None:
            self.stdout.write(self.style.WARNING("No password supplied. Developer login was not created."))
            return
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {user.employee_code}."))
        if password_set:
            self.stdout.write("Password saved. It is not printed.")
        else:
            self.stdout.write("Password left unchanged. Pass --reset-password to issue a new one.")
