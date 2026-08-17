"""CSV export of applicant records for the staff panel."""

import csv
from django.http import StreamingHttpResponse
from django.utils import timezone

from . import assessment
from .models import PASS_MARK

# The first three are blank in the plain applicant export and filled in by the
# shortlist export, which passes an overlay keyed by application id. Keeping one
# column set means the two files open the same way in a spreadsheet.
SHORTLIST_COLUMNS = [
    ("rank", "Rank"),
    ("shortlisted", "Shortlisted"),
    ("waitlisted", "Waitlisted"),
]

COLUMNS = SHORTLIST_COLUMNS + [
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
    ("composite", "Composite score /100"),
    ("score_knowledge", "Knowledge /45"),
    ("score_honesty", "Honesty /20"),
    ("score_relevance", "Relevance /20"),
    ("score_impact", "Impact /15"),
    ("flags", "Flags"),
    ("quiz_status", "Quiz status"),
    ("quiz_completed_at", "Quiz completed at"),
    ("elig_attend", "Can attend"),
    ("elig_laptop", "Laptop"),
    ("elig_data", "Has spatial data"),
    ("elig_funding", "Travel funding"),
    ("ineligible_reason", "Ineligible reason"),
    ("exp_rfreq", "Writes R"),
    ("exp_rself", "Self-rated R"),
    ("exp_bayes", "Bayesian familiarity"),
    ("exp_glm", "Fitted a GLM"),
    ("exp_dtype", "Data type"),
    ("exp_when", "Would apply methods"),
    ("exp_share", "Would share internally"),
    ("exp_use", "Analyses used for decisions"),
    ("claims_real_used", "Real functions used"),
    ("claims_fakes_claimed", "Invented functions claimed"),
    ("claims_bluffs", "Invented functions claimed as used"),
    ("decision", "Decision"),
    ("decision_at", "Decision at"),
    ("created_at", "Applied at"),
    ("final_submitted_at", "Final submission at"),
    ("written_dataset", "Dataset described"),
    ("written_code", "Own R code"),
    ("written_why_not_ols", "Why not OLS"),
    ("written_other", "Anything else"),
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


def _row(application, request, shortlist=None):
    quiz = getattr(application, "quiz", None)
    cv_url = ""
    if application.cv:
        path = f"/api/admin/applications/{application.pk}/cv/"
        cv_url = request.build_absolute_uri(path) if request else path

    scored = assessment.compute_score(application)
    claims = assessment.claim_summary(application.claims)

    placing = (shortlist or {}).get(application.pk, {})

    values = {
        "rank": placing.get("rank", ""),
        "shortlisted": placing.get("shortlisted", ""),
        "waitlisted": placing.get("waitlisted", ""),
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
        "composite": scored["total"],
        "score_knowledge": scored["knowledge"],
        "score_honesty": scored["honesty"],
        "score_relevance": scored["relevance"],
        "score_impact": scored["impact"],
        "flags": " ".join(scored["flags"]),
        "quiz_status": (
            "Not started" if quiz is None else "Completed" if quiz.is_complete else "In progress"
        ),
        "quiz_completed_at": quiz.completed_at if quiz else None,
        "elig_attend": application.elig_attend,
        "elig_laptop": application.elig_laptop,
        "elig_data": application.elig_data,
        "elig_funding": application.elig_funding,
        "ineligible_reason": application.ineligible_reason,
        "exp_rfreq": application.exp_rfreq,
        "exp_rself": application.exp_rself,
        "exp_bayes": application.exp_bayes,
        "exp_glm": application.exp_glm,
        "exp_dtype": application.exp_dtype,
        "exp_when": application.exp_when,
        "exp_share": application.exp_share,
        "exp_use": application.exp_use,
        "claims_real_used": claims["real_used"],
        "claims_fakes_claimed": claims["fakes_claimed"],
        "claims_bluffs": claims["bluffs"],
        "decision": application.get_decision_display(),
        "decision_at": application.decision_at,
        "created_at": application.created_at,
        "final_submitted_at": application.final_submitted_at,
        "written_dataset": application.written_dataset,
        "written_code": application.written_code,
        "written_why_not_ols": application.written_why_not_ols,
        "written_other": application.written_other,
        "motivation": application.motivation,
        "expectations": application.expectations,
        "cv_url": cv_url,
    }
    return [_sanitize(values[key]) for key, _ in COLUMNS]


def applications_csv_response(queryset, request=None, filename=None, shortlist=None):
    """
    Stream `queryset` as a CSV download.

    Streaming (rather than building one big string) keeps memory flat regardless
    of how many applicants match, and lets the browser start the download
    immediately.

    `queryset` may also be an ordinary list: the shortlist export has already
    ranked its applications in memory and the file must keep that order, which a
    re-query would not preserve. `shortlist` is the {id: {rank, shortlisted,
    waitlisted}} overlay for those columns.
    """
    writer = csv.writer(_Echo())
    # A queryset streams; a list is already resident, and calling .iterator() on
    # one would raise.
    source = queryset.iterator() if hasattr(queryset, "iterator") else queryset

    def rows():
        # UTF-8 BOM so Excel detects the encoding and renders accented names
        # correctly instead of mojibake.
        yield "﻿"
        yield writer.writerow([label for _, label in COLUMNS])
        for application in source:
            yield writer.writerow(_row(application, request, shortlist))

    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    name = filename or f"applicants-{stamp}.csv"
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response
