from rest_framework import serializers

from .models import Application, Question, QuizSession, SessionQuestion
from .services import _deadline


class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


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

    class Meta:
        model = QuizSession
        fields = ["id", "score", "total", "completed_at"]
