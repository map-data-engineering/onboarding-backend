"""CSV export of applicant records for the staff panel."""

import csv
from django.http import StreamingHttpResponse
from django.utils import timezone

from .models import PASS_MARK

COLUMNS = [
    ("id", "ID"),
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("nationality", "Nationality"),
    ("country_of_residence", "Country of residence"),
    ("gender", "Gender"),
    ("institution", "Institution"),
    ("institution_type", "Institution type"),
    ("role", "Role"),
    ("education", "Education"),
    ("r_experience", "R experience"),
    ("bayesian_knowledge", "Bayesian knowledge"),
    ("status", "Status"),
    ("score", "Score"),
    ("total", "Total questions"),
    ("pass_mark", "Pass mark"),
    ("quiz_status", "Quiz status"),
    ("quiz_completed_at", "Quiz completed at"),
    ("decision", "Decision"),
    ("decision_at", "Decision at"),
    ("created_at", "Applied at"),
    ("final_submitted_at", "Final submission at"),
    ("motivation", "Motivation"),
    ("expectations", "Expectations"),
    ("cv_url", "CV URL"),
]


class _Echo:
    """A file-like object whose write() returns the line, for streaming csv output."""

    def write(self, value):
        return value


def _sanitize(value):
    """
    Render a value for CSV, defusing spreadsheet formula injection.

    Excel and Sheets execute a cell that starts with =, +, - or @, and applicants
    type these fields themselves -- a motivation beginning `=HYPERLINK(...)` would
    run when staff open the export. Prefixing with an apostrophe keeps the text
    readable and inert.
    """
    if value is None:
        return ""
    if hasattr(value, "isoformat"):  # datetimes -> stable, sortable text
        return timezone.localtime(value).isoformat() if timezone.is_aware(value) else value.isoformat()
    text = str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _row(application, request):
    quiz = getattr(application, "quiz", None)
    cv_url = ""
    if application.cv:
        path = f"/api/admin/applications/{application.pk}/cv/"
        cv_url = request.build_absolute_uri(path) if request else path

    values = {
        "id": application.pk,
        "first_name": application.first_name,
        "last_name": application.last_name,
        "email": application.email,
        "phone": application.phone,
        "nationality": application.nationality,
        "country_of_residence": application.country_of_residence,
        "gender": application.gender,
        "institution": application.institution,
        "institution_type": application.institution_type,
        "role": application.role,
        "education": application.education,
        "r_experience": application.r_experience,
        "bayesian_knowledge": application.bayesian_knowledge,
        "status": application.status_display,
        "score": quiz.score if quiz else "",
        "total": quiz.total if quiz else "",
        "pass_mark": PASS_MARK,
        "quiz_status": (
            "Not started" if quiz is None else "Completed" if quiz.is_complete else "In progress"
        ),
        "quiz_completed_at": quiz.completed_at if quiz else None,
        "decision": application.get_decision_display(),
        "decision_at": application.decision_at,
        "created_at": application.created_at,
        "final_submitted_at": application.final_submitted_at,
        "motivation": application.motivation,
        "expectations": application.expectations,
        "cv_url": cv_url,
    }
    return [_sanitize(values[key]) for key, _ in COLUMNS]


def applications_csv_response(queryset, request=None, filename=None):
    """
    Stream `queryset` as a CSV download.

    Streaming (rather than building one big string) keeps memory flat regardless
    of how many applicants match, and lets the browser start the download
    immediately.
    """
    writer = csv.writer(_Echo())

    def rows():
        # UTF-8 BOM so Excel detects the encoding and renders accented names
        # correctly instead of mojibake.
        yield "﻿"
        yield writer.writerow([label for _, label in COLUMNS])
        for application in queryset.iterator():
            yield writer.writerow(_row(application, request))

    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    name = filename or f"applicants-{stamp}.csv"
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response
