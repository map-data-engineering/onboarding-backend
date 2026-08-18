"""
Deciding what to do when the schema is ahead of the migration ledger.

A deployed database can end up with columns that `django_migrations` has no record
of creating -- most often because the migration files were renumbered or rewritten
after that database was built. `migrate` then tries to add a column that is
already there and stops on `(1060, "Duplicate column name ...")`.

The repair is to record the already-present migrations as applied (`--fake`) and
run the rest for real. Choosing *where* to stop faking is the part worth getting
right: fake one migration too many and Django believes in a column that does not
exist, which fails later and further from the cause.

So the decision is made here, as a pure function over "what does this migration
add" and "is that already in the database", and it is allowed to refuse. The
management command does the introspection and the applying; this module contains
the reasoning and the safety checks, and can be tested without a damaged database
to hand.
"""

from dataclasses import dataclass, field


def additions(migration, app_label):
    """
    The tables and columns a migration physically adds.

    Returns a set of `("table", name)` and `("column", table, name)` tuples --
    the things whose presence in the database is evidence that this migration has
    already run. Operations that add nothing (AlterField, RunPython, index and
    option changes) contribute nothing, and a migration made only of those is
    decided by its neighbours rather than on its own.
    """
    found = set()
    for operation in migration.operations:
        name = type(operation).__name__
        if name == "CreateModel":
            found.add(("table", _table_for(operation.name, app_label, operation.options)))
        elif name == "AddField":
            table = _table_for(operation.model_name, app_label, {})
            found.add(("column", table, _column_for(operation.field, operation.name)))
    return found


def _table_for(model_name, app_label, options):
    return (options or {}).get("db_table") or f"{app_label}_{model_name.lower()}"


def _column_for(field, name):
    if getattr(field, "db_column", None):
        return field.db_column
    # A ForeignKey's column is the attname: `author` -> `author_id`.
    if getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False):
        return f"{name}_id"
    return name


@dataclass
class RepairPlan:
    """What to fake, what to apply, and why -- or the reason for refusing."""

    fake_through: str | None = None      # last migration to record as applied
    apply_for_real: list = field(default_factory=list)
    already_present: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    @property
    def safe(self):
        return not self.problems

    @property
    def needs_faking(self):
        return self.fake_through is not None


def plan_repair(pending, is_present):
    """
    Work out which pending migrations are already in the database.

    `pending` is an ordered list of `(name, additions)`. `is_present` answers
    whether one addition tuple exists in the live schema.

    The rule: find the **last** pending migration whose additions are all present
    already, and fake everything up to and including it. Everything after that
    runs for real.

    It refuses -- returning problems rather than a plan -- in the two cases where
    faking would make things worse:

      * a migration only **partly** present. Half its columns exist, so neither
        faking it (Django believes in the missing half) nor applying it (it stops
        on the existing half) is right. This needs a person.
      * a migration **before** the frontier that is entirely absent. The ledger
        and the schema have diverged in an order this cannot reason about, and
        faking over the gap would skip real work.
    """
    plan = RepairPlan()
    states = []

    for name, adds in pending:
        if not adds:
            states.append((name, None))          # no evidence either way
            continue
        present = {a for a in adds if is_present(a)}
        if not present:
            states.append((name, False))
        elif present == adds:
            states.append((name, True))
            plan.already_present.append(name)
        else:
            missing = sorted(_describe(a) for a in adds - present)
            plan.problems.append(
                f"{name} is only partly in the database (missing: {', '.join(missing)}). "
                "Faking it would leave Django believing in columns that are not there. "
                "This one needs a person."
            )
            states.append((name, "partial"))

    if plan.problems:
        return plan

    frontier = max((i for i, (_, s) in enumerate(states) if s is True), default=None)
    if frontier is None:
        # Nothing is already present: an ordinary, healthy `migrate`.
        plan.apply_for_real = [name for name, _ in pending]
        return plan

    for name, state in states[:frontier]:
        if state is False:
            plan.problems.append(
                f"{name} adds nothing that is in the database, yet a later migration "
                f"({states[frontier][0]}) is already applied. The ledger and the schema "
                "have diverged out of order -- repairing this by faking would skip real "
                "schema changes. Restore from a backup, or fix by hand."
            )
    if plan.problems:
        return plan

    plan.fake_through = states[frontier][0]
    plan.apply_for_real = [name for name, _ in pending[frontier + 1:]]
    return plan


def _describe(addition):
    if addition[0] == "table":
        return f"table {addition[1]}"
    return f"{addition[1]}.{addition[2]}"
