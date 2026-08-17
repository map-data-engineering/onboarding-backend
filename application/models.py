import uuid

from django.db import models

# Minimum score that counts as a pass: it unlocks the final step (motivation,
# expectations, CV) and drives Application.status. An absolute count, not a
# percentage -- revisit it if the number of seeded questions changes.
PASS_MARK = 7


class Question(models.Model):
    """A scored multiple-choice question (the knowledge-check items on the form)."""

    class Category(models.TextChoices):
        R = "R", "R programming"
        SPATIAL = "SPATIAL", "Spatial data"
        GENERAL = "GENERAL", "General statistics"
        BAYESIAN = "BAYESIAN", "Bayesian statistics"
        APPLICATION = "APPLICATION", "Health applications"

    text = models.CharField(max_length=500)
    # Optional code sample shown under the question in a monospaced block, so a
    # snippet like `d %>% group_by(district)` keeps its formatting instead of
    # being wrapped into the prose.
    code = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    # e.g. ["read.csv()", "load.csv()", "import.csv()", "open.csv()"]
    options = models.JSONField(help_text="List of option strings shown to the applicant.")
    # Must match one of the strings in `options` exactly. NEVER exposed to the client.
    correct_answer = models.CharField(max_length=255)
    time_limit_seconds = models.PositiveIntegerField(default=25)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.text[:60]


class Application(models.Model):
    """An applicant's submission (contact info, profile, motivation, CV)."""

    class Decision(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SELECTED = "SELECTED", "Selected"
        REJECTED = "REJECTED", "Rejected"

    class Status(models.TextChoices):
        """Outcome of the knowledge check — derived from the score, never set by hand."""

        PENDING = "PENDING", "Pending"  # quiz not started, or still in progress
        PASS = "PASS", "Pass"           # score >= PASS_MARK
        FAIL = "FAIL", "Fail"           # quiz finished below PASS_MARK

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Contact
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    nationality = models.CharField(max_length=100)
    country_of_residence = models.CharField(max_length=100)
    gender = models.CharField(max_length=10)

    # Profile
    institution = models.CharField(max_length=200)
    institution_type = models.CharField(max_length=50)
    role = models.CharField(max_length=150)
    education = models.CharField(max_length=30)

    # Self-rated fields (NOT scored — they are opinions, not right/wrong)
    r_experience = models.CharField(max_length=30)
    bayesian_knowledge = models.CharField(max_length=30)

    # Free text — collected in the final step, only for applicants who pass the quiz.
    motivation = models.TextField(blank=True)
    expectations = models.TextField(blank=True)

    # File upload — also collected in the final step (see PASS_MARK in services.py).
    cv = models.FileField(upload_to="cvs/", blank=False)

    # Set when the applicant completes the final step (motivation/expectations/CV).
    final_submitted_at = models.DateTimeField(null=True, blank=True)

    # Staff review outcome (set from the staff panel).
    decision = models.CharField(
        max_length=10, choices=Decision.choices, default=Decision.PENDING
    )
    decision_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} <{self.email}>"

    @property
    def status(self):
        """
        Pass/fail on the knowledge check.

        Derived from the quiz on every read rather than stored, so it can never
        drift from the actual score (and changing PASS_MARK re-grades everyone).
        Distinct from `decision`, which is the staff's review outcome.
        """
        quiz = getattr(self, "quiz", None)
        if quiz is None or not quiz.is_complete:
            return self.Status.PENDING
        return self.Status.PASS if quiz.score >= PASS_MARK else self.Status.FAIL

    @property
    def status_display(self):
        return self.Status(self.status).label


class QuizSession(models.Model):
    """One graded attempt per application. The shuffled order lives in `items`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="quiz"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def score(self):
        return self.items.filter(is_correct=True).count()

    @property
    def total(self):
        return self.items.count()

    @property
    def is_complete(self):
        return self.completed_at is not None


class SessionQuestion(models.Model):
    """A single question inside a session: its shuffled position and its timing."""

    session = models.ForeignKey(
        QuizSession, on_delete=models.CASCADE, related_name="items"
    )
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    position = models.PositiveIntegerField()  # shuffled order, 0-based

    # The option order this applicant sees, shuffled once when the session is
    # built and then frozen. Two applicants from the same institution get "the
    # answer is C" wrong if they compare notes, and re-fetching a question can't
    # reshuffle the options under someone mid-answer.
    option_order = models.JSONField(null=True, blank=True)

    served_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    submitted_answer = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(default=False)
    timed_out = models.BooleanField(default=False)

    class Meta:
        unique_together = ("session", "position")
        ordering = ["position"]
