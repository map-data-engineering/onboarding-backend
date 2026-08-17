from rest_framework import serializers

from . import assessment, validators
from .models import Application, Question, QuizSession, SessionQuestion
from .services import GRACE_SECONDS, PASS_MARK, _deadline, has_passed, options_for


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


def _choice_fields(questions):
    """Build required ChoiceFields from an {field: [options]} map."""
    return {
        name: serializers.ChoiceField(choices=options, required=True, allow_blank=False)
        for name, options in questions.items()
    }


class EligibilitySerializer(serializers.ModelSerializer):
    """Step 2. Options are validated against the server's list, not the form's."""

    class Meta:
        model = Application
        fields = list(assessment.ELIGIBILITY_QUESTIONS)

    def get_fields(self):
        return _choice_fields(assessment.ELIGIBILITY_QUESTIONS)


class ExperienceSerializer(serializers.ModelSerializer):
    """Step 3 — all eight answers required."""

    class Meta:
        model = Application
        fields = list(assessment.EXPERIENCE_QUESTIONS)

    def get_fields(self):
        return _choice_fields(assessment.EXPERIENCE_QUESTIONS)


class ApplicationFinalStepSerializer(serializers.ModelSerializer):
    """Step 6 — the applicant's own work, motivation and expectations, plus the CV."""

    class Meta:
        model = Application
        fields = [
            "motivation",
            "expectations",
            "written_dataset",
            "written_code",
            "written_why_not_ols",
            "written_other",
            "cv",
        ]
        extra_kwargs = {
            "cv": {"required": True, "allow_null": False},
            "motivation": {"required": True, "allow_blank": False},
            "expectations": {"required": True, "allow_blank": False},
            "written_dataset": {"required": True, "allow_blank": False},
            "written_code": {"required": True, "allow_blank": False},
            "written_why_not_ols": {"required": True, "allow_blank": False},
            "written_other": {"required": False, "allow_blank": True},
        }

    # 300 words each. The textareas carry a maxlength and a live counter, but a
    # character cap is not a word cap and neither survives a hand-made request.
    def validate_motivation(self, value):
        return validators.validate_word_limit(value, label="Your motivation")

    def validate_expectations(self, value):
        return validators.validate_word_limit(value, label="Your expectations")

    def validate_written_other(self, value):
        return validators.validate_word_limit(value, label="This answer")

    # Minimums matching the prompts' "about 80 words" / "a sentence or two", so a
    # single character can't pass for an answer. Deliberately low: the panel
    # judges quality, this only rejects blanks.
    def validate_written_dataset(self, value):
        if len(value.strip()) < 25:
            raise serializers.ValidationError("Please describe the dataset in a sentence or two.")
        return validators.validate_word_limit(value, label="This answer")

    def validate_written_why_not_ols(self, value):
        if len(value.strip()) < 15:
            raise serializers.ValidationError("A sentence is enough, but please answer.")
        return validators.validate_word_limit(value, label="This answer")

    def validate_cv(self, value):
        """PDF only, 5 MB, 2 pages — see validators.validate_cv."""
        return validators.validate_cv(value)


class QuestionPublicSerializer(serializers.ModelSerializer):
    """What the applicant is allowed to see. Note: NO correct_answer."""

    # "Spatial data" rather than "SPATIAL" -- the code is for filtering, not display.
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Question
        fields = ["id", "text", "code", "category", "category_label",
                  "options", "time_limit_seconds"]


class CurrentQuestionSerializer(serializers.Serializer):
    """Wraps the served question with its position and server-computed deadline."""

    session = serializers.UUIDField(source="session_id")
    position = serializers.IntegerField()
    total = serializers.SerializerMethodField()
    question = serializers.SerializerMethodField()
    time_limit_seconds = serializers.IntegerField(source="question.time_limit_seconds")
    deadline = serializers.SerializerMethodField()
    # The slack built into `deadline` on top of time_limit_seconds. The client
    # counts down to the advertised limit and lets the grace cover the round
    # trip, so an applicant told "25 seconds" doesn't watch a 28-second clock.
    grace_seconds = serializers.SerializerMethodField()

    def get_total(self, item):
        return item.session.total

    def get_question(self, item):
        # Serialise the question, then swap in this applicant's own option order
        # (see services.build_session -- options are shuffled per session).
        data = QuestionPublicSerializer(item.question).data
        data["options"] = options_for(item)
        return data

    def get_grace_seconds(self, item):
        return GRACE_SECONDS

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
