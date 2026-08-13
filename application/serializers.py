from rest_framework import serializers

from .models import Application, Question, QuizSession, SessionQuestion
from .services import PASS_MARK, _deadline, has_passed


class ApplicationSerializer(serializers.ModelSerializer):
    """
    Step 1 of the journey: contact + profile only.

    Motivation, expectations and the CV are deliberately NOT accepted here — they
    are collected in the final step, and only from applicants who score at least
    PASS_MARK on the quiz (see ApplicationFinalStepSerializer).
    """

    class Meta:
        model = Application
        exclude = ["motivation", "expectations", "cv", "final_submitted_at"]
        read_only_fields = ["id", "created_at", "decision", "decision_at"]


class ApplicationFinalStepSerializer(serializers.ModelSerializer):
    """Final step: the CV upload plus the two free-text answers."""

    class Meta:
        model = Application
        fields = ["motivation", "expectations", "cv"]
        extra_kwargs = {
            "cv": {"required": True, "allow_null": False},
            "motivation": {"required": True, "allow_blank": False},
            "expectations": {"required": True, "allow_blank": False},
        }


class QuestionPublicSerializer(serializers.ModelSerializer):
    """What the applicant is allowed to see. Note: NO correct_answer."""

    class Meta:
        model = Question
        fields = ["id", "text", "category", "options", "time_limit_seconds"]


class CurrentQuestionSerializer(serializers.Serializer):
    """Wraps the served question with its position and server-computed deadline."""

    session = serializers.UUIDField(source="session_id")
    position = serializers.IntegerField()
    total = serializers.SerializerMethodField()
    question = QuestionPublicSerializer()
    time_limit_seconds = serializers.IntegerField(source="question.time_limit_seconds")
    deadline = serializers.SerializerMethodField()

    def get_total(self, item):
        return item.session.total

    def get_deadline(self, item):
        # ISO timestamp the client renders a countdown against; the server still
        # enforces it independently on submit.
        return _deadline(item).isoformat()


class AnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()


class ResultSerializer(serializers.ModelSerializer):
    score = serializers.IntegerField(read_only=True)
    total = serializers.IntegerField(read_only=True)
    # Tells the client whether to show the final step (CV + free text).
    passed = serializers.SerializerMethodField()
    pass_mark = serializers.SerializerMethodField()
    application = serializers.UUIDField(source="application_id", read_only=True)
    final_submitted = serializers.SerializerMethodField()

    class Meta:
        model = QuizSession
        fields = [
            "id",
            "application",
            "score",
            "total",
            "completed_at",
            "passed",
            "pass_mark",
            "final_submitted",
        ]

    def get_passed(self, session):
        return has_passed(session)

    def get_pass_mark(self, session):
        return PASS_MARK

    def get_final_submitted(self, session):
        return session.application.final_submitted_at is not None
