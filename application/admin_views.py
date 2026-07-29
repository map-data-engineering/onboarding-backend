"""
Staff-only API for the custom admin panel (/api/admin/).

Auth is token-based:
  1. POST /api/admin/login/ with staff username + password -> returns a token.
  2. Send `Authorization: Token <token>` on every other admin request.

All endpoints except login require an authenticated staff user (is_staff=True).
"""

from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
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
from .models import Application


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
      ?page=    page number (page size is 25)
    """
    from django.db.models import Q

    qs = Application.objects.select_related("quiz").order_by("-created_at")

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(institution__icontains=search)
        )

    # Reuse the project's default PageNumberPagination.
    from rest_framework.pagination import PageNumberPagination

    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ApplicationListSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_application_detail(request, application_id):
    """Full applicant record + CV URL + quiz summary."""
    application = get_object_or_404(Application, pk=application_id)
    serializer = ApplicationDetailSerializer(application, context={"request": request})
    return Response(serializer.data)


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
