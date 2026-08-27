"""Copy pj_erp_prod onto pj_erp_dev so the working copy matches the snapshot.

Does NOT drop/create databases — pj_dev is not allowed CREATEDB, and dropping
the dest catalog first is how we lost pj_erp_dev on the first run. Both
catalogs must already exist; this wipes the dest *schema* and restores a dump.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Replace contents of pj_erp_dev with a dump of pj_erp_prod (local catalogs only)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Do not prompt")

    def handle(self, *args, **opts):
        prod = settings.DB_NAME_BY_PROFILE["prod"]
        dev = settings.DB_NAME_BY_PROFILE["dev"]
        if prod == dev:
            raise CommandError("dev and prod database names are the same — refusing to clone.")
        if not opts["yes"]:
            raise CommandError(f"This wipes {dev} and reloads it from {prod}. Re-run with --yes.")

        user = settings.DATABASES["default"]["USER"]
        password = settings.DATABASES["default"]["PASSWORD"]
        host = settings.DATABASES["default"]["HOST"]
        port = str(settings.DATABASES["default"]["PORT"])

        psql = shutil.which("psql")
        pg_dump = shutil.which("pg_dump")
        if not psql or not pg_dump:
            raise CommandError(
                "psql/pg_dump not on PATH. Install PostgreSQL client tools, or re-run "
                "`import_mssql_snapshot --flush` with DJANGO_DB_PROFILE=dev."
            )

        env = os.environ.copy()
        env["PGPASSWORD"] = password
        env["PGUSER"] = user
        env["PGHOST"] = host
        env["PGPORT"] = port

        def exists(name: str) -> bool:
            r = subprocess.run(
                [psql, "-d", "postgres", "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{name}'"],
                env=env, capture_output=True, text=True,
            )
            return r.returncode == 0 and r.stdout.strip() == "1"

        if not exists(prod):
            raise CommandError(
                f"{prod} does not exist. Create it as a Postgres superuser first:\n"
                f'  psql -U postgres -h localhost -c "ALTER USER {user} CREATEDB;"\n'
                f'  psql -U postgres -h localhost -c "CREATE DATABASE {prod} OWNER {user};"\n'
                f'  psql -U postgres -h localhost -c "CREATE DATABASE {dev} OWNER {user};"'
            )
        if not exists(dev):
            raise CommandError(
                f"{dev} does not exist (it may have been dropped). Recreate it as a Postgres superuser:\n"
                f'  psql -U postgres -h localhost -c "CREATE DATABASE {dev} OWNER {user};"'
            )

        self.stdout.write(f"Wiping schema in {dev}...")
        wipe = subprocess.run(
            [psql, "-d", dev, "-v", "ON_ERROR_STOP=1", "-c",
             "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO CURRENT_USER; GRANT ALL ON SCHEMA public TO public;"],
            env=env, capture_output=True, text=True,
        )
        if wipe.returncode != 0:
            raise CommandError(wipe.stderr or wipe.stdout or f"Failed to wipe {dev}")

        self.stdout.write(f"Dumping {prod} into {dev}...")
        dump = subprocess.run(
            [pg_dump, "--no-owner", "--no-acl", prod],
            env=env, capture_output=True,
        )
        if dump.returncode != 0:
            raise CommandError(dump.stderr.decode("utf-8", "replace") or f"pg_dump {prod} failed")
        restore = subprocess.run(
            [psql, "-d", dev, "-v", "ON_ERROR_STOP=1"],
            env=env, input=dump.stdout, capture_output=True,
        )
        if restore.returncode != 0:
            err = (restore.stderr or restore.stdout).decode("utf-8", "replace")
            raise CommandError(err or f"restore into {dev} failed")

        self.stdout.write(self.style.SUCCESS(
            f"{dev} now matches {prod}. Switch with DJANGO_DB_PROFILE=dev."
        ))
