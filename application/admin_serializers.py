"""Serializers for the staff-only custom admin panel (/api/admin/)."""

from rest_framework import serializers

from .models import PASS_MARK, Application, SessionQuestion


class ApplicationListSerializer(serializers.ModelSerializer):
    """Compact row for the applicants table."""

    quiz_status = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    # PASS / FAIL / PENDING — derived from the score (see Application.status).
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "institution",
            "country_of_residence",
            "created_at",
            "status",
            "decision",
            "quiz_status",
            "score",
            "total",
        ]

    def _quiz(self, application):
        # OneToOne related_name="quiz"; may not exist yet.
        return getattr(application, "quiz", None)

    def get_quiz_status(self, application):
        quiz = self._quiz(application)
        if quiz is None:
            return "not_started"
        return "completed" if quiz.is_complete else "in_progress"

    def get_score(self, application):
        quiz = self._quiz(application)
        return quiz.score if quiz else None

    def get_total(self, application):
        quiz = self._quiz(application)
        return quiz.total if quiz else None


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """Full applicant record, including the CV URL and quiz summary."""

    cv = serializers.SerializerMethodField()
    quiz_status = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    completed_at = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    pass_mark = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "nationality",
            "country_of_residence",
            "gender",
            "institution",
            "institution_type",
            "role",
            "education",
            "r_experience",
            "bayesian_knowledge",
            "motivation",
            "expectations",
            "cv",
            "created_at",
            "final_submitted_at",
            "status",
            "pass_mark",
            "decision",
            "decision_at",
            "quiz_status",
            "score",
            "total",
            "completed_at",
        ]

    def _quiz(self, application):
        return getattr(application, "quiz", None)

    def get_pass_mark(self, application):
        return PASS_MARK

    def get_cv(self, application):
        if not application.cv:
            return None
        request = self.context.get("request")
        url = application.cv.url
        return request.build_absolute_uri(url) if request else url

    def get_quiz_status(self, application):
        quiz = self._quiz(application)
        if quiz is None:
            return "not_started"
        return "completed" if quiz.is_complete else "in_progress"

    def get_score(self, application):
        quiz = self._quiz(application)
        return quiz.score if quiz else None

    def get_total(self, application):
        quiz = self._quiz(application)
        return quiz.total if quiz else None

    def get_completed_at(self, application):
        quiz = self._quiz(application)
        return quiz.completed_at if quiz else None


class SessionQuestionBreakdownSerializer(serializers.ModelSerializer):
    """Per-question detail for a session. Reveals the correct answer (staff-only)."""

    question_text = serializers.CharField(source="question.text")
    category = serializers.CharField(source="question.category")
    correct_answer = serializers.CharField(source="question.correct_answer")

    class Meta:
        model = SessionQuestion
        fields = [
            "position",
            "question_text",
            "category",
            "submitted_answer",
            "correct_answer",
            "is_correct",
            "timed_out",
            "served_at",
            "answered_at",
        ]
