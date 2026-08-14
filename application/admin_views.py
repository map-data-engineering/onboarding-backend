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
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .admin_serializers import (
    ApplicationDetailSerializer,
    ApplicationListSerializer,
    SessionQuestionBreakdownSerializer,
)
from .models import PASS_MARK, Application


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
    return Response(
        {
            "token": token.key,
            "user": {
                "username": user.username,
                "email": user.email,
                "is_superuser": user.is_superuser,
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_logout(request):
    """Invalidate the caller's token."""
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_me(request):
    """Return the authenticated staff user (handy for verifying a token)."""
    user = request.user
    return Response(
        {
            "username": user.username,
            "email": user.email,
            "is_superuser": user.is_superuser,
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_applications(request):
    """
    Paginated list of applicants.

    Query params:
      ?search=  filter by first/last name, email, or institution (case-insensitive)
      ?status=  pass | fail | pending  (the knowledge-check outcome)
      ?page=    page number (page size is 25)
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
        return Response(
            {"status": ["Must be one of ['pass', 'fail', 'pending']."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Reuse the project's default PageNumberPagination.
    from rest_framework.pagination import PageNumberPagination

    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ApplicationListSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAdminUser])
def admin_application_detail(request, application_id):
    """
    GET    -> full applicant record + CV URL + quiz summary
    PATCH  -> update the review decision ({"decision": "SELECTED"|"REJECTED"|"PENDING"})
    DELETE -> delete the applicant (and their uploaded CV + quiz, via cascade)
    """
    application = get_object_or_404(Application, pk=application_id)

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
@permission_classes([IsAdminUser])
def admin_application_cv(request, application_id):
    """
    Stream an applicant's CV back to the staff panel as a download.

    Uploaded files live under MEDIA_ROOT, which Django only serves itself when
    DEBUG is on — in production the old /media/... link 404s. Serving the file
    through the API keeps it working in both, and keeps CVs staff-only instead
    of readable by anyone who guesses the media URL.
    """
    application = get_object_or_404(Application, pk=application_id)
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
@permission_classes([IsAdminUser])
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
@permission_classes([IsAdminUser])
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
