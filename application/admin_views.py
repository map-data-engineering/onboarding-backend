"""
Staff-only API for the custom admin panel (/api/admin/).

Auth is token-based:
  1. POST /api/admin/login/ with staff username + password -> returns a token.
  2. Send `Authorization: Token <token>` on every other admin request.

All endpoints except login require an authenticated staff user (is_staff=True).
"""

import os
import re

from django.contrib.auth import authenticate
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .admin_serializers import (
    ApplicationDetailSerializer,
    ApplicationListSerializer,
    SessionQuestionBreakdownSerializer,
)
from . import shortlist as shortlisting
from .cv_links import unsign_cv_link
from .exports import applications_csv_response
from .models import PASS_MARK, Application
from .permissions import CanReviewApplicants, IsStaff, can_review, is_viewer


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login(request):
    """Exchange staff credentials for an auth token."""
    username = request.data.get("username")
    password = request.data.get("password")
    if not username or not password:
        return Response(
            {"detail": "username and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_staff:
        # Same message whether the user doesn't exist, the password is wrong, or
        # the account isn't staff -- don't leak which.
        return Response(
            {"detail": "Invalid credentials or not a staff account."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": _user_payload(user)})


def _user_payload(user):
    """
    Identity + capabilities.

    The panel hides the decision, delete, bulk and export controls when
    `can_review` is false. That is presentation only -- every one of those
    endpoints enforces the same rule server-side.
    """
    return {
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "role": "viewer" if is_viewer(user) else "reviewer",
        "can_review": can_review(user),
        "can_export": can_review(user),
    }


@api_view(["POST"])
@permission_classes([IsStaff])
def admin_logout(request):
    """Invalidate the caller's token."""
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsStaff])
def admin_me(request):
    """Return the authenticated staff user (handy for verifying a token)."""
    return Response(_user_payload(request.user))


class InvalidFilter(Exception):
    """Raised by _filtered_applications for a query param the caller got wrong."""

    def __init__(self, payload):
        self.payload = payload


def _filtered_applications(request):
    """
    Applicants matching the request's ?search= and ?status= filters, newest first.

    Shared by the list and the CSV export so the two can never disagree about
    what "the current filters" mean -- an export that quietly returned everyone
    would be worse than no export at all.
    """
    from django.db.models import Count, Q

    qs = Application.objects.select_related("quiz").order_by("-created_at")

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(institution__icontains=search)
        )

    # `status` is a derived property (Application.status), so filtering means
    # re-deriving it in SQL: count the correct answers and compare to PASS_MARK.
    status_filter = (request.query_params.get("status") or "").lower()
    if status_filter in {"pass", "fail", "pending"}:
        finished = Q(quiz__completed_at__isnull=False)
        if status_filter == "pending":
            qs = qs.filter(~finished)
        else:
            qs = qs.annotate(
                correct_count=Count("quiz__items", filter=Q(quiz__items__is_correct=True))
            ).filter(finished)
            qs = (
                qs.filter(correct_count__gte=PASS_MARK)
                if status_filter == "pass"
                else qs.filter(correct_count__lt=PASS_MARK)
            )
    elif status_filter:
        raise InvalidFilter({"status": ["Must be one of ['pass', 'fail', 'pending']."]})

    return qs


@api_view(["GET"])
@permission_classes([IsStaff])
def admin_applications(request):
    """
    Paginated list of applicants. Open to viewers as well as reviewers.

    Query params:
      ?search=  filter by first/last name, email, or institution (case-insensitive)
      ?status=  pass | fail | pending  (the knowledge-check outcome)
      ?page=    page number (page size is 25)
    """
    try:
        qs = _filtered_applications(request)
    except InvalidFilter as bad:
        return Response(bad.payload, status=status.HTTP_400_BAD_REQUEST)

    # Reuse the project's default PageNumberPagination.
    from rest_framework.pagination import PageNumberPagination

    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ApplicationListSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([CanReviewApplicants])
def admin_applications_export(request):
    """
    Download the applicants matching the current filters as CSV.

    Takes the same ?search= and ?status= params as the list, so the file contains
    exactly the rows on screen -- not the whole table. Restricted to reviewers:
    view-only accounts can read records individually but not bulk-export them.
    """
    try:
        qs = _filtered_applications(request)
    except InvalidFilter as bad:
        return Response(bad.payload, status=status.HTTP_400_BAD_REQUEST)

    return applications_csv_response(qs, request=request)


def _shortlist_options(data):
    """
    Read the builder's controls off a request body, with the defaults filled in.

    Anything unparseable falls back to its default rather than 400-ing: these come
    from number inputs in the panel, and an empty box should mean "the default",
    not "the shortlist you were looking at has gone".
    """
    options = {}
    for name in ("seats", "min_women", "min_tanzania", "max_per_institution", "waitlist"):
        try:
            options[name] = int(data.get(name, shortlisting.DEFAULTS[name]))
        except (TypeError, ValueError):
            options[name] = shortlisting.DEFAULTS[name]

    travel = data.get("travel", shortlisting.DEFAULTS["travel"])
    options["travel"] = travel if travel in shortlisting.TRAVEL_MODES else shortlisting.DEFAULTS["travel"]

    pool = data.get("pool", shortlisting.DEFAULTS["pool"])
    options["pool"] = pool if pool in shortlisting.POOLS else shortlisting.DEFAULTS["pool"]

    drop = data.get("drop_bluff", shortlisting.DEFAULTS["drop_bluff"])
    options["drop_bluff"] = drop in (True, "true", "1", 1, "on")
    return options


def _shortlist_queryset():
    """Every application, with the rows the score needs, ready to rank in memory."""
    return (
        Application.objects.select_related("quiz")
        .prefetch_related("quiz__items__question")
        .order_by("created_at")
    )


@api_view(["GET", "POST"])
@permission_classes([IsStaff])
def admin_shortlist(request):
    """
    Rank every application and allocate seats under the panel's floors.

    Body (all optional -- see shortlist.DEFAULTS):
      seats, min_women, min_tanzania, max_per_institution, waitlist : integers
      travel : "prefer" | "only" | "ignore"
      pool   : "submitted" | "scored" | "all"
      drop_bluff : bool

    GET returns the defaults applied to the current pool, so opening the panel
    shows a shortlist rather than an empty form. Open to viewers: it computes a
    ranking, it does not record a decision.
    """
    data = request.data if request.method == "POST" else request.query_params
    options = _shortlist_options(data)
    result = shortlisting.build_shortlist(_shortlist_queryset(), **options)

    return Response(
        {
            "settings": result["settings"],
            "floors": result["floors"],
            "stats": result["stats"],
            "rows": [
                {
                    "id": str(row["application"].pk),
                    "rank": row["rank"],
                    "shortlisted": row["shortlisted"],
                    "waitlisted": row["waitlisted"],
                    "first_name": row["application"].first_name,
                    "last_name": row["application"].last_name,
                    "email": row["application"].email,
                    "institution": row["application"].institution,
                    "country_of_residence": row["application"].country_of_residence,
                    "gender": row["application"].gender,
                    "decision": row["application"].decision,
                    "total": row["score"]["total"],
                    "knowledge": row["score"]["knowledge"],
                    "honesty": row["score"]["honesty"],
                    "relevance": row["score"]["relevance"],
                    "impact": row["score"]["impact"],
                    "correct": row["score"]["correct"],
                    "of": row["score"]["of"],
                    "flags": row["score"]["flags"],
                }
                for row in result["rows"]
            ],
        }
    )


@api_view(["POST"])
@permission_classes([CanReviewApplicants])
def admin_shortlist_export(request):
    """
    CSV of the ranking just built, with Rank, Shortlisted and Waitlisted columns.

    Takes the same body as the builder plus `only_shortlist`, so the panel can
    hand over either the full ranking or the picks alone. Reviewers only, like the
    other export.
    """
    options = _shortlist_options(request.data)
    result = shortlisting.build_shortlist(_shortlist_queryset(), **options)

    rows = result["rows"]
    if request.data.get("only_shortlist") in (True, "true", "1", 1, "on"):
        rows = [row for row in rows if row["shortlisted"] or row["waitlisted"]]

    overlay = {
        row["application"].pk: {
            "rank": row["rank"],
            "shortlisted": "Yes" if row["shortlisted"] else "",
            "waitlisted": "Yes" if row["waitlisted"] else "",
        }
        for row in rows
    }
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    return applications_csv_response(
        [row["application"] for row in rows],
        request=request,
        filename=f"shortlist-{stamp}.csv",
        shortlist=overlay,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsStaff])
def admin_application_detail(request, application_id):
    """
    GET    -> full applicant record + CV URL + quiz summary (viewers included)
    PATCH  -> update the review decision ({"decision": "SELECTED"|"REJECTED"|"PENDING"})
    DELETE -> delete the applicant (and their uploaded CV + quiz, via cascade)

    Reading is open to any staff account; PATCH and DELETE are reviewers only.
    """
    application = get_object_or_404(Application, pk=application_id)

    # One view, three methods -- so the write check lives here rather than in a
    # permission class, which would have to allow the GET through anyway.
    if request.method in ("PATCH", "DELETE") and not can_review(request.user):
        raise PermissionDenied(CanReviewApplicants.message)

    if request.method == "DELETE":
        if application.cv:
            application.cv.delete(save=False)  # remove the file from disk too
        application.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if request.method == "PATCH":
        decision = request.data.get("decision")
        valid = {c[0] for c in Application.Decision.choices}
        if decision not in valid:
            return Response(
                {"decision": [f"Must be one of {sorted(valid)}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        application.decision = decision
        application.decision_at = timezone.now()
        application.save(update_fields=["decision", "decision_at"])

    serializer = ApplicationDetailSerializer(application, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])  # authorised below: staff credentials OR a signed link
def admin_application_cv(request, application_id):
    """
    Stream an applicant's CV back to the staff panel as a download.

    Uploaded files live under MEDIA_ROOT, which Django only serves itself when
    DEBUG is on — in production the old /media/... link 404s. Serving the file
    through the API keeps it working in both, and keeps CVs staff-only instead
    of readable by anyone who guesses the media URL.

    Two ways in, because a browser following a plain link cannot send an
    `Authorization` header (the standalone frontends render the CV as an
    `<a href>`, and a link click carries no headers):

      1. Staff credentials — a token or an admin session, as everywhere else.
      2. `?sig=` — a short-lived signature minted by the detail endpoint, which
         only staff can call. It expires after CV_LINK_MAX_AGE, so a leaked URL
         stops working; contrast the old /media/ path, which never did.
    """
    application = get_object_or_404(Application, pk=application_id)

    signature = request.query_params.get("sig")
    if signature:
        problem = unsign_cv_link(signature, application.pk)
        if problem:
            raise PermissionDenied(problem)
    elif not request.user.is_authenticated:
        # Match the IsStaff permission exactly: 401 when nobody is logged in, 403 when
        # someone is but isn't staff. A blanket 401 would tell a signed-in
        # non-staff user to "authenticate", which they already have.
        raise NotAuthenticated()
    elif not request.user.is_staff:
        raise PermissionDenied()

    if not application.cv:
        raise Http404("This applicant has not uploaded a CV.")

    try:
        handle = application.cv.open("rb")
    except FileNotFoundError:
        # Row still references a file that is no longer on disk.
        raise Http404("The CV file is missing from storage.") from None

    # Download as "Firstname-Lastname-CV.pdf" rather than the stored hash-ish name.
    extension = os.path.splitext(application.cv.name)[1] or ""
    stem = f"{application.first_name}-{application.last_name}-CV".strip("-")
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", stem) + extension

    return FileResponse(handle, as_attachment=True, filename=filename)


@api_view(["POST"])
@permission_classes([CanReviewApplicants])
def admin_applications_bulk(request):
    """
    Act on several applicants at once (used by the staff panel's checkboxes).

    Body: {"ids": ["<uuid>", ...], "action": "select"|"reject"|"pending"|"delete"}
    """
    ids = request.data.get("ids") or []
    action = request.data.get("action")
    if not ids:
        return Response(
            {"detail": "No applicant ids provided."}, status=status.HTTP_400_BAD_REQUEST
        )

    qs = Application.objects.filter(pk__in=ids)

    if action == "delete":
        deleted = 0
        for application in qs:
            if application.cv:
                application.cv.delete(save=False)
            application.delete()
            deleted += 1
        return Response({"deleted": deleted})

    action_to_decision = {
        "select": Application.Decision.SELECTED,
        "reject": Application.Decision.REJECTED,
        "pending": Application.Decision.PENDING,
    }
    if action in action_to_decision:
        decision = action_to_decision[action]
        updated = qs.update(decision=decision, decision_at=timezone.now())
        return Response({"updated": updated, "decision": decision})

    return Response(
        {"detail": "action must be one of: select, reject, pending, delete."},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
@permission_classes([IsStaff])
def admin_application_quiz(request, application_id):
    """Per-question breakdown of an applicant's quiz (with correct answers)."""
    application = get_object_or_404(Application, pk=application_id)
    quiz = getattr(application, "quiz", None)
    if quiz is None:
        return Response(
            {"detail": "This applicant has not started the quiz."},
            status=status.HTTP_404_NOT_FOUND,
        )

    items = quiz.items.select_related("question").order_by("position")
    return Response(
        {
            "session": str(quiz.id),
            "score": quiz.score,
            "total": quiz.total,
            "completed_at": quiz.completed_at,
            "questions": SessionQuestionBreakdownSerializer(items, many=True).data,
        }
    )
