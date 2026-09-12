"""
Issue a new API key for an external system.

The raw key is printed exactly once — nothing here can show it again
afterwards, only the hash is kept. If it's lost, revoke this client
(--revoke) and issue a new one.

Usage:
    python manage.py create_api_client "Reseller portal (Jane's team)"
    python manage.py create_api_client "Old integration" --revoke
"""

from django.core.management.base import BaseCommand, CommandError

from apps.api.models import ApiClient


class Command(BaseCommand):
    help = "Issue (or revoke) an API key for an external system."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Label for who/what holds this key.")
        parser.add_argument("--notes", default="")
        parser.add_argument(
            "--revoke", action="store_true",
            help="Deactivate the most recent active client with this exact name instead of creating one.",
        )

    def handle(self, *args, **opts):
        name = opts["name"].strip()
        if not name:
            raise CommandError("Name is required.")

        if opts["revoke"]:
            client = ApiClient.objects.filter(name=name, is_active=True).order_by("-created_at").first()
            if client is None:
                raise CommandError(f"No active client named {name!r}.")
            client.is_active = False
            client.save(update_fields=["is_active", "updated_at"])
            self.stdout.write(self.style.WARNING(f"Revoked: {client}"))
            return

        client, raw_key = ApiClient.create_with_key(name, notes=opts["notes"])
        self.stdout.write(self.style.SUCCESS(f"Created client: {client}"))
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("API key (shown once — store it now):"))
        self.stdout.write(f"  {raw_key}")
        self.stdout.write("")
        self.stdout.write("Send as header:  Authorization: Api-Key " + raw_key)
