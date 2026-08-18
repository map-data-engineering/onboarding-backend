"""
Core quiz logic. Everything here is server-authoritative:
the client can never grant itself more time or change the shuffle.
"""

import random
from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Min
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import PASS_MARK, QuizSession, SessionQuestion, Question

# Extra seconds allowed on top of the question limit to absorb network latency,
# so a genuine answer sent at ~30s isn't rejected because it arrived at 30.6s.
GRACE_SECONDS = 3

# PASS_MARK lives in models.py -- Application.status is derived from it too -- and
# is re-exported here, alongside the grading logic that applies it.
__all__ = [
    "GRACE_SECONDS",
    "PASS_MARK",
    "build_session",
    "current_item",
    "draw_questions",
    "has_passed",
    "options_for",
    "quiz_shape",
    "remaining_seconds",
    "submit_answer",
]


def has_passed(session):
    """
    True once the quiz is finished with at least PASS_MARK correct answers.

    A grade, no longer a gate: it is reported on the result screen and drives
    Application.status, the BELOW-PASS flag and the panel's pass/fail filter, but
    nothing in the applicant journey is withheld on the strength of it (see
    views.application_finalize).
    """
    return session.is_complete and session.score >= PASS_MARK


def draw_questions():
    """
    A random per-applicant draw from the bank, honouring settings.PORTAL["QUOTA"].

    Serving the whole bank would make one paper that every applicant sits, and at
    twenty applicants per seat inside a handful of institutions the answers travel
    faster than the deadline does. Drawing 14 of 24 instead means the useful thing
    to pass on ("the answer is B for the buffer question") is usually about a
    question the next applicant never sees.

    The quota is by category so the shape of the paper is stable even though its
    contents are not -- nobody should get five Bayesian questions by luck.
    """
    quota = dict(settings.PORTAL["QUOTA"])
    picked, leftovers = [], []

    for category, wanted in quota.items():
        pool = list(Question.objects.filter(is_active=True, category=category))
        random.shuffle(pool)
        picked.extend(pool[:wanted])
        # A category with spares keeps them aside: if another category is short of
        # its quota we would rather serve a paper of the intended length than one
        # two questions shorter, since PASS_MARK is an absolute count.
        leftovers.extend(pool[wanted:])

    shortfall = sum(quota.values()) - len(picked)
    if shortfall > 0 and leftovers:
        random.shuffle(leftovers)
        picked.extend(leftovers[:shortfall])

    # Anything outside the quota's categories (an old question kept active, say)
    # is deliberately not drawn: the quota is the definition of the paper.
    random.shuffle(picked)  # drawn and ordered ONCE, per applicant, then frozen
    return picked


def quiz_shape():
    """
    What the applicant is told before starting: how many questions, how long each.

    Derived from the bank and the quota rather than written into the page copy,
    which is how "Twelve multiple-choice questions" survived three changes to the
    question set.
    """
    quota = settings.PORTAL["QUOTA"]
    active = Question.objects.filter(is_active=True, category__in=list(quota))
    available = {
        category: active.filter(category=category).count() for category in quota
    }
    bounds = active.aggregate(low=Min("time_limit_seconds"), high=Max("time_limit_seconds"))
    return {
        "questions": sum(min(n, available.get(c, 0)) for c, n in quota.items()),
        "bank_size": active.count(),
        "seconds_min": bounds["low"],
        "seconds_max": bounds["high"],
        "pass_mark": PASS_MARK,
    }


def build_session(application):
    """Create the one-and-only session for an application with a shuffled draw."""
    if QuizSession.objects.filter(application=application).exists():
        # No restarts: a restart would hand out a fresh timer and a new shuffle.
        raise ValidationError("A quiz session already exists for this application.")

    questions = draw_questions()
    if not questions:
        raise ValidationError("No active questions are configured.")

    session = QuizSession.objects.create(application=application)
    SessionQuestion.objects.bulk_create(
        [
            SessionQuestion(
                session=session,
                question=q,
                position=i,
                # Options are shuffled per applicant too, so "the answer is B"
                # is useless to pass around. Frozen with the question order.
                option_order=random.sample(list(q.options), len(q.options)),
            )
            for i, q in enumerate(questions)
        ]
    )
    return session


def options_for(item):
    """The option order this applicant should see (falls back to the canonical order)."""
    stored = item.option_order
    if not stored:
        return list(item.question.options)
    # Guard against a question whose options were edited after the session was
    # built: anything added is appended, anything removed is dropped.
    canonical = list(item.question.options)
    kept = [o for o in stored if o in canonical]
    return kept + [o for o in canonical if o not in kept]


def _deadline(item):
    return item.served_at + timedelta(
        seconds=item.question.time_limit_seconds + GRACE_SECONDS
    )


def remaining_seconds(item):
    """
    Seconds left on this question, as the server sees them, clamped to 0..limit.

    The client used to derive this itself by subtracting `Date.now()` from the
    `deadline` timestamp, which silently made the applicant's device clock part of
    the grading. A phone five minutes fast reported a negative remainder on the
    first tick, so the page auto-submitted a blank answer for every question and
    the applicant scored zero with nothing on screen to explain it; a clock five
    minutes slow showed a five-minute countdown and then had every answer thrown
    away as late. Sending the remainder instead makes the arithmetic happen where
    the deadline is enforced.

    The grace is excluded deliberately: an applicant told "40 seconds" should see
    40, and the grace exists to cover the round trip of the answer sent at zero,
    not to be advertised as extra time.
    """
    limit = float(item.question.time_limit_seconds)
    if item.served_at is None:      # not started yet: the full allowance
        return limit
    left = (_deadline(item) - timedelta(seconds=GRACE_SECONDS) - timezone.now()).total_seconds()
    # Clamped, so a clock adjustment on the server (or a question whose limit was
    # edited mid-session) can never hand out more time than the limit or ask the
    # client to render a negative one.
    return round(max(0.0, min(limit, left)), 1)


def _finalize_expired(session):
    """If the current question was served but its window has closed, lock it as timed out."""
    item = (
        session.items.filter(answered_at__isnull=True, served_at__isnull=False)
        .order_by("position")
        .first()
    )
    if item and timezone.now() > _deadline(item):
        item.timed_out = True
        item.is_correct = False
        item.answered_at = _deadline(item)
        item.save(update_fields=["timed_out", "is_correct", "answered_at"])
        _maybe_complete(session)


def _maybe_complete(session):
    if not session.items.filter(answered_at__isnull=True).exists():
        if session.completed_at is None:
            session.completed_at = timezone.now()
            session.save(update_fields=["completed_at"])


def current_item(session):
    """
    Return the question the applicant should answer now, starting its clock
    on first serve. Re-fetching does NOT reset the clock.
    """
    if session.is_complete:
        return None

    _finalize_expired(session)  # roll past any question they let expire

    item = (
        session.items.filter(answered_at__isnull=True)
        .order_by("position")
        .first()
    )
    if item is None:
        _maybe_complete(session)
        return None

    if item.served_at is None:  # first time this question is shown -> start clock
        item.served_at = timezone.now()
        item.save(update_fields=["served_at"])
    return item


def submit_answer(session, answer):
    """Grade the current question, honouring the server-side deadline."""
    if session.is_complete:
        raise ValidationError("This quiz is already complete.")

    # NB: do NOT call _finalize_expired() here. It would mark the current
    # (expired) question as answered, after which the query below would find no
    # active question and raise -- which is exactly what happens on the client's
    # auto-submit when the timer runs out, leaving the applicant stuck. Instead
    # we grade the expired case ourselves in the `now > deadline` branch so the
    # timed-out question is recorded and the caller can advance to the next one.
    item = (
        session.items.filter(answered_at__isnull=True, served_at__isnull=False)
        .order_by("position")
        .first()
    )
    if item is None:
        raise ValidationError("No active question to answer. Fetch the current question first.")

    now = timezone.now()
    if now > _deadline(item) or not (answer or "").strip():
        # Either the window closed, or the clock ran out with nothing selected and
        # the page submitted an empty answer. Both are "unanswered", and recording
        # them the same way keeps the panel's TIMEOUTS flag meaning what it says --
        # a blank stored as a wrong answer would look like a considered mistake.
        item.timed_out = True
        item.is_correct = False
        item.submitted_answer = ""
        item.answered_at = min(now, _deadline(item))
    else:
        item.submitted_answer = answer
        item.is_correct = answer == item.question.correct_answer
        item.answered_at = now

    item.save()
    _maybe_complete(session)
    return item
