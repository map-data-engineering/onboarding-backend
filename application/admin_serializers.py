"""Serializers for the staff-only custom admin panel (/api/admin/)."""

from rest_framework import serializers

from .cv_links import sign_cv_link
from . import assessment
from .models import PASS_MARK, Application, SessionQuestion


class ApplicationListSerializer(serializers.ModelSerializer):
    """Compact row for the applicants table."""

    quiz_status = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    # PASS / FAIL / PENDING — derived from the score (see Application.status).
    status = serializers.CharField(read_only=True)
    # Composite out of 100 and the review flags, so the table can be scanned.
    composite = serializers.SerializerMethodField()
    flags = serializers.SerializerMethodField()

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
            "composite",
            "flags",
            "decision",
            "quiz_status",
            "score",
            "total",
        ]

    def get_composite(self, application):
        return assessment.compute_score(application)["total"]

    def get_flags(self, application):
        return assessment.compute_flags(application)

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
    assessment = serializers.SerializerMethodField()
    claim_summary = serializers.SerializerMethodField()

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
            # Step 2-3: eligibility and experience
            "elig_attend",
            "elig_laptop",
            "elig_data",
            "elig_funding",
            "ineligible_reason",
            "exp_rfreq",
            "exp_rself",
            "exp_bayes",
            "exp_glm",
            "exp_dtype",
            "exp_when",
            "exp_share",
            "exp_use",
            # Step 4: honesty check
            "claims",
            "claim_summary",
            # Step 6: their own work
            "written_dataset",
            "written_code",
            "written_why_not_ols",
            "written_other",
            # Legacy free text from the original single-page form
            "motivation",
            "expectations",
            "cv",
            "created_at",
            "final_submitted_at",
            "status",
            "pass_mark",
            "assessment",
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

    def get_assessment(self, application):
        """Composite score components + review flags, recomputed on every read."""
        return assessment.compute_score(application)

    def get_claim_summary(self, application):
        """How many real functions were claimed, and how many invented ones."""
        summary = assessment.claim_summary(application.claims)
        summary["real_total"] = len(assessment.CLAIM_REAL)
        summary["fake_total"] = len(assessment.CLAIM_FAKE)
        summary["fake_names"] = assessment.CLAIM_FAKE
        return summary

    def get_cv(self, application):
        """
        Staff-only download endpoint, not the raw MEDIA_URL path: media is only
        served by Django when DEBUG is on, and those URLs need no auth.

        The `sig` is what lets a frontend render this as a plain `<a href>` --
        a link click sends no Authorization header. Only staff can reach this
        serializer, so minting it here keeps the gate intact, and it expires
        after CV_LINK_MAX_AGE.
        """
        if not application.cv:
            return None
        url = f"/api/admin/applications/{application.pk}/cv/?sig={sign_cv_link(application.pk)}"
        request = self.context.get("request")
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
