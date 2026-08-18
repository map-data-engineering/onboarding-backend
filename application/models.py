import uuid
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

# The benchmark the knowledge check is graded against: it drives
# Application.status, the BELOW-PASS flag and the panel's pass/fail filter. An
# absolute count, not a percentage -- revisit it if the size of the draw changes.
#
# The benchmark, as an absolute count out of the 14 questions drawn per applicant
# (settings.PORTAL["QUOTA"]) -- not a percentage. Because status is derived on read
# rather than stored, changing this re-grades everyone, including applications
# already submitted, so move it deliberately and expect the panel's Pass/Fail
# filter to shift under the reviewers.
#
# It is a grade, NOT a gate. Scoring below it no longer stops anyone submitting: an
# applicant who misses the mark on a 30-second-a-question paper may still be the
# right person in the room, and the panel is better placed to weigh a weak quiz
# against a strong CV than a hard cut-off is. See views.application_finalize.
PASS_MARK = 7

# Fallback deadline for the round, used as the initial value of
# PortalSettings.application_deadline. Staff change the live value from the panel
# (or the Django admin); this is only what a fresh database starts with, and it
# must stay a plain literal-ish callable because migrations serialise it.
FALLBACK_DEADLINE = date(2026, 8, 30)


def default_deadline():
    """
    The deadline a fresh install starts with: PORTAL["DEADLINE"] or 30 Aug 2026.

    Read at call time (not at import) so a deployment can seed a different date
    through the environment without a migration, and so tests can override it.
    """
    raw = (settings.PORTAL.get("DEADLINE") or "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            # A malformed PORTAL_DEADLINE must not take the portal down: fall
            # back to the literal rather than raising on every model default.
            pass
    return FALLBACK_DEADLINE


class PortalSettings(models.Model):
    """
    The one row of round-specific configuration staff can change themselves.

    The deadline used to be a string in settings.PORTAL, which meant moving it
    was a code change and a redeploy -- so in practice it went stale and the
    portal kept accepting applications after the date it was advertising. Keeping
    it in the database lets the panel move it, and lets the API close intake on
    the date the applicant page is displaying, because both read this row.
    """

    # Singleton: always pk=1, so there is exactly one answer to "when does this
    # close?" and no way to end up with two rows disagreeing.
    SINGLETON_PK = 1

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_PK)
    application_deadline = models.DateField(
        default=default_deadline,
        help_text=(
            "Last day applications are accepted, inclusive. Applicants can start "
            "and submit all day on this date; intake closes the following midnight."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "portal settings"
        verbose_name_plural = "portal settings"

    def __str__(self):
        return f"Applications close {self.application_deadline.isoformat()}"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK  # never allow a second row
        # A freshly constructed instance still has _state.adding set, so Django
        # would INSERT and collide with the row already holding pk=1. Saving
        # PortalSettings(application_deadline=…) should overwrite the singleton,
        # which is the whole point of pinning the primary key.
        if self._state.adding and type(self).objects.filter(pk=self.pk).exists():
            self._state.adding = False
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """The settings row, created with the defaults on first use."""
        row, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return row

    @property
    def is_open(self):
        """
        Whether applications are still being accepted.

        Compared against the local date rather than a timestamp: the deadline is
        advertised as a day, so it stays open for the whole of that day in the
        project's timezone instead of expiring at an hour nobody was told about.
        """
        return timezone.localdate() <= self.application_deadline

    @property
    def deadline_display(self):
        """"Sunday 30 August 2026" — what the applicant page prints."""
        return self.application_deadline.strftime("%A %d %B %Y").replace(" 0", " ")


def applications_open():
    """Shorthand for PortalSettings.load().is_open."""
    return PortalSettings.load().is_open


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
    # 30 seconds per question. Long enough to read a scenario item and think,
    # short enough that looking an unfamiliar result up on a second device and
    # evaluating it does not fit -- which is the entire point of the clock.
    time_limit_seconds = models.PositiveIntegerField(default=30)
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

    # --- Step 2: eligibility ------------------------------------------------
    # Practical questions answered before any effort is invested, so someone who
    # cannot take up a place is told immediately rather than after 15 minutes.
    elig_attend = models.CharField(max_length=60, blank=True)
    elig_laptop = models.CharField(max_length=60, blank=True)
    elig_data = models.CharField(max_length=80, blank=True)
    elig_funding = models.CharField(max_length=80, blank=True)
    # Set when the eligibility answers rule the applicant out; the journey stops.
    ineligible_reason = models.CharField(max_length=200, blank=True)

    # --- Step 3: experience and plans ---------------------------------------
    exp_rfreq = models.CharField(max_length=60, blank=True)
    exp_rself = models.CharField(max_length=80, blank=True)
    exp_bayes = models.CharField(max_length=30, blank=True)
    exp_glm = models.CharField(max_length=40, blank=True)
    exp_dtype = models.CharField(max_length=80, blank=True)
    exp_when = models.CharField(max_length=80, blank=True)
    exp_share = models.CharField(max_length=60, blank=True)
    exp_use = models.CharField(max_length=30, blank=True)

    # --- Step 4: honesty check ----------------------------------------------
    # {"st_read": "used", "st_reproject": "heard", ...}. Some of the function
    # names offered are invented; claiming one is what this step measures.
    claims = models.JSONField(default=dict, blank=True)

    # --- Step 5: the applicant's own work -----------------------------------
    # Collected before the knowledge check, from every eligible applicant. It used
    # to sit after the quiz and be unlocked only by a passing score, which meant
    # the panel never saw the CV or the motivation of anyone who scored 7.
    written_dataset = models.TextField(blank=True)      # a dataset they analysed
    written_code = models.TextField(blank=True)         # 5-15 lines of their own R
    written_why_not_ols = models.TextField(blank=True)  # why OLS would be a poor choice
    written_other = models.TextField(blank=True)        # anything else for the panel

    # Also step 5. Capped at 300 words each by the serializer (not at the DB
    # level, so the limit can change without a migration).
    motivation = models.TextField(blank=True)
    expectations = models.TextField(blank=True)

    # File upload — also collected in the "your own work" step.
    cv = models.FileField(upload_to="cvs/", blank=True)

    # Set when the applicant completes the work step (motivation/expectations/CV),
    # which is also what unlocks the knowledge check.
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
