from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from . import services
from .models import Application, QuizSession
from .serializers import (
    AnswerSerializer,
    ApplicationFinalStepSerializer,
    ApplicationSerializer,
    CurrentQuestionSerializer,
    ResultSerializer,
)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def application_create(request):
    """
    Create an applicant from the first form (contact + profile only).

    The CV, motivation and expectations are collected later — see
    application_finalize.
    """
    serializer = ApplicationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def application_status(request, application_id):
    """
    Where an applicant is in the journey — used by the client to resume.

    404 here means the stored application_id is stale (e.g. the record was
    deleted), which tells the client to clear its state and start over.
    """
    application = get_object_or_404(Application, pk=application_id)
    session = getattr(application, "quiz", None)
    return Response(
        {
            "id": str(application.id),
            "final_submitted": application.final_submitted_at is not None,
            "quiz": ResultSerializer(session).data if session else None,
        }
    )


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def application_finalize(request, application_id):
    """
    Final submission: motivation, expectations and the CV upload.

    Gated server-side — the applicant must have finished the quiz with a score of
    at least services.PASS_MARK. The client hiding the form is not enough.
    """
    application = get_object_or_404(Application, pk=application_id)
    session = getattr(application, "quiz", None)

    if session is None or not session.is_complete:
        return Response(
            {"detail": "Complete the knowledge check before submitting your application."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not services.has_passed(session):
        return Response(
            {
                "detail": (
                    f"A score of at least {services.PASS_MARK} is required to "
                    f"complete your application."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    if application.final_submitted_at is not None:
        return Response(
            {"detail": "This application has already been submitted."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ApplicationFinalStepSerializer(
        application, data=request.data, partial=False
    )
    serializer.is_valid(raise_exception=True)
    application = serializer.save(final_submitted_at=timezone.now())

    return Response(
        {
            "id": str(application.id),
            "submitted_at": application.final_submitted_at,
            **serializer.data,
        }
    )


@api_view(["POST"])
def quiz_start(request, application_id):
    """Create the shuffled session for an application and return the first question."""
    application = get_object_or_404(Application, pk=application_id)
    session = services.build_session(application)
    item = services.current_item(session)
    return Response(
        CurrentQuestionSerializer(item).data, status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
def quiz_current(request, session_id):
    """Fetch the current question. Re-fetching does not reset the timer."""
    session = get_object_or_404(QuizSession, pk=session_id)
    item = services.current_item(session)
    if item is None:
        return Response(ResultSerializer(session).data)  # finished
    return Response(CurrentQuestionSerializer(item).data)


@api_view(["POST"])
def quiz_answer(request, session_id):
    """Submit an answer for the current question; server enforces the 40s window."""
    session = get_object_or_404(QuizSession, pk=session_id)
    payload = AnswerSerializer(data=request.data)
    payload.is_valid(raise_exception=True)

    item = services.submit_answer(session, payload.validated_data["answer"])
    nxt = services.current_item(session)

    return Response(
        {
            "timed_out": item.timed_out,
            "accepted": not item.timed_out,
            "finished": nxt is None,
            # Whether it was correct is intentionally withheld until the end;
            # expose item.is_correct here only if you want instant feedback.
            "next": CurrentQuestionSerializer(nxt).data if nxt else None,
            "result": ResultSerializer(session).data if nxt is None else None,
        }
    )


@api_view(["GET"])
def quiz_result(request, session_id):
    session = get_object_or_404(QuizSession, pk=session_id)
    return Response(ResultSerializer(session).data)
