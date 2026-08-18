"""
The migration-history repair: does it fake the right amount, and refuse the rest?

The failure this exists for showed up on the production MySQL box: `decision` was
in the schema, `django_migrations` had no row for the migration that adds it, and
`migrate` stopped on `(1060, "Duplicate column name 'decision'")`. The repair is
mechanical but the *extent* of it is a judgement -- fake one migration too many
and Django believes in a column that is not there -- so the reasoning is a pure
function and these are its tests.
"""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from application.migration_repair import additions, plan_repair


def present_from(existing):
    """A schema probe over a literal set of addition tuples."""
    return lambda addition: addition in existing


class PlanRepairTests(TestCase):
    """`plan_repair` over hand-built histories: the shapes, not this app's files."""

    COL_A = ("column", "t", "a")
    COL_B = ("column", "t", "b")
    TABLE = ("table", "later")

    def test_a_healthy_history_is_left_alone(self):
        """Nothing present yet -- an ordinary migrate, no faking."""
        plan = plan_repair([("0001", {self.COL_A}), ("0002", {self.COL_B})], present_from(set()))
        self.assertTrue(plan.safe)
        self.assertFalse(plan.needs_faking)
        self.assertEqual(plan.apply_for_real, ["0001", "0002"])

    def test_it_fakes_up_to_the_last_migration_already_in_the_schema(self):
        """The production case: early migrations applied, the new one genuinely pending."""
        plan = plan_repair(
            [("0001", {self.COL_A}), ("0002", {self.COL_B}), ("0003", {self.TABLE})],
            present_from({self.COL_A, self.COL_B}),
        )
        self.assertTrue(plan.safe)
        self.assertEqual(plan.fake_through, "0002")
        self.assertEqual(plan.apply_for_real, ["0003"])

    def test_a_migration_that_adds_nothing_rides_along_with_its_neighbours(self):
        """
        An AlterField-only migration is invisible to schema probing.

        It contributes no evidence, so it must not become the frontier on its own
        (nothing would be faked) nor block one -- it follows whatever the
        migrations around it prove.
        """
        plan = plan_repair(
            [("0001", {self.COL_A}), ("0002_alter", set()), ("0003", {self.COL_B}), ("0004", {self.TABLE})],
            present_from({self.COL_A, self.COL_B}),
        )
        self.assertEqual(plan.fake_through, "0003")
        self.assertEqual(plan.apply_for_real, ["0004"])

    def test_it_refuses_a_half_applied_migration(self):
        """
        One column of two present: neither faking nor applying is correct.

        Faking leaves Django believing in the missing column; applying stops on the
        one that exists. The right answer is to stop and say so.
        """
        plan = plan_repair([("0001", {self.COL_A, self.COL_B})], present_from({self.COL_A}))
        self.assertFalse(plan.safe)
        self.assertIsNone(plan.fake_through)
        self.assertIn("only partly in the database", plan.problems[0])
        self.assertIn("t.b", plan.problems[0])          # names what is missing

    def test_it_refuses_when_the_divergence_is_out_of_order(self):
        """
        A gap *behind* the frontier means faking would skip real schema work.

        0001 is absent but 0002 is present, so the ledger and the schema did not
        diverge at a single point and this cannot be reasoned about.
        """
        plan = plan_repair(
            [("0001", {self.COL_A}), ("0002", {self.COL_B})],
            present_from({self.COL_B}),
        )
        self.assertFalse(plan.safe)
        self.assertIsNone(plan.fake_through)
        self.assertIn("diverged out of order", plan.problems[0])

    def test_nothing_is_faked_when_only_the_newest_migration_is_pending(self):
        """The ordinary deploy: one new migration, schema otherwise in step."""
        plan = plan_repair([("0009", {self.TABLE})], present_from(set()))
        self.assertFalse(plan.needs_faking)
        self.assertEqual(plan.apply_for_real, ["0009"])


class AdditionsTests(TestCase):
    """Reading this app's real migration files: what does each one physically add?"""

    def setUp(self):
        self.disk = MigrationLoader(None, ignore_no_migrations=True).disk_migrations

    def migration(self, prefix):
        for (app_label, name), migration in self.disk.items():
            if app_label == "application" and name.startswith(prefix):
                return migration
        self.fail(f"no migration starting {prefix}")

    def test_the_migration_that_broke_the_deploy_is_read_as_two_columns(self):
        self.assertEqual(
            additions(self.migration("0003"), "application"),
            {
                ("column", "application_application", "decision"),
                ("column", "application_application", "decision_at"),
            },
        )

    def test_the_new_migration_is_read_as_a_table(self):
        """0009 creates PortalSettings; its AlterField and RunPython add nothing."""
        self.assertEqual(
            additions(self.migration("0009"), "application"),
            {("table", "application_portalsettings")},
        )

    def test_an_alterfield_only_migration_adds_nothing(self):
        self.assertEqual(additions(self.migration("0005"), "application"), set())

    def test_every_migration_in_this_app_can_be_read_without_error(self):
        """
        A guard for future migrations: unknown operations must be ignored, not crash.

        `additions` is the thing standing between a broken deploy and a repair, so
        it has to survive whatever ends up in this directory.
        """
        for (app_label, name), migration in self.disk.items():
            if app_label == "application":
                with self.subTest(migration=name):
                    for addition in additions(migration, "application"):
                        self.assertIn(addition[0], ("table", "column"))


class RepairCommandTests(TestCase):
    """The command against the test database, which is correctly migrated."""

    def test_on_a_healthy_database_it_reports_nothing_pending(self):
        from io import StringIO

        out = StringIO()
        call_command("repair_migrations", stdout=out)
        self.assertIn("Nothing pending", out.getvalue())

    def test_the_schema_probe_sees_this_database_as_it_is(self):
        """The introspection half: it must find a real column and miss a fictional one."""
        from application.management.commands.repair_migrations import _schema_probe

        present = _schema_probe(connection)
        self.assertTrue(present(("table", "application_application")))
        self.assertTrue(present(("column", "application_application", "decision")))
        self.assertTrue(present(("table", "application_portalsettings")))
        self.assertFalse(present(("table", "application_nonexistent")))
        self.assertFalse(present(("column", "application_application", "not_a_column")))

    def test_a_dry_run_changes_nothing(self):
        """Default is report-only -- `--apply` is the opt-in."""
        from io import StringIO

        recorded_before = self._recorded()
        call_command("repair_migrations", stdout=StringIO())
        self.assertEqual(self._recorded(), recorded_before)

    def _recorded(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM django_migrations WHERE app='application'")
            return sorted(row[0] for row in cursor.fetchall())
