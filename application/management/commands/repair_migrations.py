"""
Recover a database whose schema is ahead of its migration ledger, then migrate.

Run this when `migrate` stops on `Duplicate column name` / `table already exists`:
it compares the pending migrations against the live schema, records the ones that
are demonstrably already applied, and then runs the genuine remainder.

    python manage.py repair_migrations              # say what it would do, change nothing
    python manage.py repair_migrations --apply      # do it

It refuses rather than guessing when the evidence is ambiguous -- see
`application/migration_repair.py` for the two cases and why they need a person.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor

from application.migration_repair import additions, plan_repair

APP_LABEL = "application"


class Command(BaseCommand):
    help = (
        "Repair a migration history that has fallen behind the database schema "
        "(the 'Duplicate column name' failure on deploy), then apply what is left."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually fake and migrate. Without it, this only reports the plan.",
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Database alias to repair (default: %(default)s).",
        )

    def handle(self, *args, **options):
        connection = connections[options["database"]]
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes(APP_LABEL)
        plan = executor.migration_plan(targets)

        pending = [
            (migration.name, additions(migration, APP_LABEL))
            for migration, backwards in plan
            if not backwards and migration.app_label == APP_LABEL
        ]
        if not pending:
            self.stdout.write(self.style.SUCCESS("Nothing pending: the ledger is up to date."))
            return

        present = _schema_probe(connection)
        repair = plan_repair(pending, present)

        # Label from the plan, not from the evidence: an AlterField-only migration
        # shows no columns to probe for but is still faked when it sits behind the
        # frontier, and calling that "to apply" would misdescribe what happens.
        to_apply = set(repair.apply_for_real)
        self.stdout.write(f"{len(pending)} migration(s) pending in '{APP_LABEL}':")
        for name, _ in pending:
            if name in repair.already_present:
                mark = "already in the database -> record as applied"
            elif not repair.safe:
                mark = "?"
            elif name in to_apply:
                mark = "will be applied"
            else:
                mark = "adds nothing on its own -> record as applied"
            self.stdout.write(f"  {name:<56} {mark}")

        if not repair.safe:
            for problem in repair.problems:
                self.stderr.write(self.style.ERROR(f"\n{problem}"))
            raise CommandError(
                "Refusing to repair automatically. Nothing has been changed -- "
                "take a backup and fix this by hand."
            )

        if not repair.needs_faking:
            self.stdout.write(
                "\nThe schema matches the ledger; this is an ordinary migrate, "
                "no repair needed."
            )
        else:
            self.stdout.write(
                f"\nPlan: record {APP_LABEL} up to and including "
                f"{self.style.MIGRATE_LABEL(repair.fake_through)} as applied (no schema "
                f"change -- those columns and tables are already there), then apply "
                f"{len(repair.apply_for_real)} migration(s) for real:"
            )
            for name in repair.apply_for_real:
                self.stdout.write(f"  {name}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("\nDry run -- nothing changed. Re-run with --apply.")
            )
            return

        if repair.needs_faking:
            call_command(
                "migrate", APP_LABEL, repair.fake_through,
                fake=True, database=options["database"], verbosity=options.get("verbosity", 1),
            )
        call_command("migrate", database=options["database"], verbosity=options.get("verbosity", 1))
        self.stdout.write(self.style.SUCCESS("\nRepaired and migrated. Reload the web app."))


def _schema_probe(connection):
    """Answer 'is this table/column in the live schema?' from one introspection pass."""
    with connection.cursor() as cursor:
        tables = set(connection.introspection.table_names(cursor))
        columns = {}
        for table in tables:
            try:
                columns[table] = {
                    description.name
                    for description in connection.introspection.get_table_description(cursor, table)
                }
            except Exception:  # noqa: BLE001 -- a table we cannot describe is a table we ignore
                columns[table] = set()

    def present(addition):
        if addition[0] == "table":
            return addition[1] in tables
        _, table, column = addition
        return column in columns.get(table, set())

    return present
