from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from . import services
from .models import Application, QuizSession
from .serializers import (
    AnswerSerializer,
    ApplicationSerializer,
    CurrentQuestionSerializer,
    ResultSerializer,
)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def application_create(request):
    """Create an applicant. MultiPart/Form parsers let the CV file upload (Q30) work."""
    serializer = ApplicationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


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
