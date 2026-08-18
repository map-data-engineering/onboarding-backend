"""
Admin-editable deadline, and 30 seconds per question.

The deadline moves from settings.PORTAL (a string, changed only by a redeploy) to
a single database row the panel can edit, so intake closes on the date the
applicant page is advertising.

The question clock goes from 25s to 30s for every question already in the bank,
not just for new ones: leaving the default alone would have meant a paper whose
timings depended on when each question happened to be seeded.
"""

from django.db import migrations, models

import application.models


def bump_time_limits(apps, schema_editor):
    """Every existing question gets the new 30-second allowance."""
    Question = apps.get_model("application", "Question")
    Question.objects.exclude(time_limit_seconds=30).update(time_limit_seconds=30)


def restore_previous_limits(apps, schema_editor):
    """Back to the 25 seconds this replaced (the reverse of the data change)."""
    Question = apps.get_model("application", "Question")
    Question.objects.filter(time_limit_seconds=30).update(time_limit_seconds=25)


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0008_alter_application_cv"),
    ]

    operations = [
        migrations.CreateModel(
            name="PortalSettings",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(default=1, primary_key=True, serialize=False),
                ),
                (
                    "application_deadline",
                    models.DateField(
                        default=application.models.default_deadline,
                        help_text=(
                            "Last day applications are accepted, inclusive. Applicants "
                            "can start and submit all day on this date; intake closes "
                            "the following midnight."
                        ),
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "portal settings",
                "verbose_name_plural": "portal settings",
            },
        ),
        migrations.AlterField(
            model_name="question",
            name="time_limit_seconds",
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.RunPython(bump_time_limits, restore_previous_limits),
    ]
