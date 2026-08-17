from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from . import assessment, countries, services, validators
from .models import Application, QuizSession
from .serializers import (
    AnswerSerializer,
    ApplicationFinalStepSerializer,
    ApplicationSerializer,
    CurrentQuestionSerializer,
    EligibilitySerializer,
    ExperienceSerializer,
    ResultSerializer,
)


@api_view(["GET"])
def portal_config(request):
    """
    Everything the applicant page needs before it can render a single screen.

    The preparation screen's limits, the deadline, the country dropdowns and the
    shape of the knowledge check all live server-side, so the page cannot promise
    "4 MB" while the upload endpoint enforces 5, or say "twelve questions" after
    the quota changed. The page is copy; this is the source of truth.
    """
    return Response(
        {
            "contact_email": assessment.portal_setting("CONTACT_EMAIL"),
            "deadline": assessment.portal_setting("DEADLINE"),
            "duration": assessment.portal_setting("DURATION"),
            "funding_gate": assessment.funding_gate(),
            "limits": {
                "cv_max_mb": round(validators.CV_MAX_BYTES / (1024 * 1024), 1),
                "cv_max_pages": validators.CV_MAX_PAGES,
                "max_words": validators.MAX_WORDS,
            },
            "quiz": services.quiz_shape(),
            "countries": countries.COUNTRY_GROUPS,
        }
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
            "ineligible_reason": application.ineligible_reason,
            # Which steps are already answered, so a reload resumes in the right
            # place instead of asking everything again.
            "completed": {
                "eligibility": bool(application.elig_attend),
                "experience": bool(application.exp_rfreq),
                "claims": bool(application.claims),
            },
            "quiz": ResultSerializer(session).data if session else None,
        }
    )


@api_view(["POST"])
def application_eligibility(request, application_id):
    """
    Step 2 — four practical questions, answered before any real effort.

    Enforced here rather than in the browser: an applicant who cannot attend, has
    no spatial data, or needs funding we do not have is stopped now, and the
    reason is stored so staff can see why the journey ended.
    """
    application = get_object_or_404(Application, pk=application_id)
    serializer = EligibilitySerializer(application, data=request.data)
    serializer.is_valid(raise_exception=True)
    application = serializer.save()

    problem = assessment.eligibility_problem(serializer.validated_data)
    if problem:
        application.ineligible_reason = problem
        application.save(update_fields=["ineligible_reason"])
        return Response({"eligible": False, "reason": problem})

    if application.ineligible_reason:  # they changed an answer -- let them through
        application.ineligible_reason = ""
        application.save(update_fields=["ineligible_reason"])
    return Response({"eligible": True, "reason": ""})


@api_view(["POST"])
def application_experience(request, application_id):
    """Step 3 — experience, data and plans. All eight answers are required."""
    application = get_object_or_404(Application, pk=application_id)
    serializer = ExperienceSerializer(application, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response({"saved": True})


@api_view(["GET", "POST"])
def application_claims(request, application_id):
    """
    Step 4 — the honesty check.

    GET returns the function names to show, shuffled. Which of them are invented
    is never sent to the client; the grading in assessment.py is the only place
    that knows, so the answer can't be read out of the page source.
    """
    application = get_object_or_404(Application, pk=application_id)

    if request.method == "GET":
        return Response({"functions": assessment.claim_catalogue()})

    claims = request.data.get("claims")
    if not isinstance(claims, dict) or not claims:
        return Response(
            {"claims": ["Answer for every function."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    known = set(assessment.CLAIM_REAL) | set(assessment.CLAIM_FAKE)
    unknown = set(claims) - known
    if unknown:
        return Response(
            {"claims": [f"Unknown function(s): {', '.join(sorted(unknown))}."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if set(claims) != known:
        return Response(
            {"claims": ["Answer for every function."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    bad = {v for v in claims.values()} - set(assessment.CLAIM_CHOICES)
    if bad:
        return Response(
            {"claims": [f"Each answer must be one of {list(assessment.CLAIM_CHOICES)}."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    application.claims = claims
    application.save(update_fields=["claims"])
    # Deliberately no feedback about which names were fake -- that would leak the
    # answer to the next applicant from the same institution.
    return Response({"saved": True})


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
    if application.ineligible_reason:
        return Response(
            {"detail": application.ineligible_reason}, status=status.HTTP_403_FORBIDDEN
        )
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
    """Submit an answer for the current question; server enforces the time window."""
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
