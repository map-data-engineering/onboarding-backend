"""
Core quiz logic. Everything here is server-authoritative:
the client can never grant itself more time or change the shuffle.
"""

import random
from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import PASS_MARK, QuizSession, SessionQuestion, Question

# Extra seconds allowed on top of the question limit to absorb network latency,
# so a genuine answer sent at ~25s isn't rejected because it arrived at 25.6s.
GRACE_SECONDS = 3

# PASS_MARK lives in models.py -- Application.status is derived from it too -- and
# is re-exported here, alongside the grading logic that applies it.
__all__ = [
    "GRACE_SECONDS",
    "PASS_MARK",
    "build_session",
    "current_item",
    "has_passed",
    "options_for",
    "submit_answer",
]


def has_passed(session):
    """True once the quiz is finished with at least PASS_MARK correct answers."""
    return session.is_complete and session.score >= PASS_MARK


def build_session(application):
    """Create the one-and-only session for an application with a shuffled order."""
    if QuizSession.objects.filter(application=application).exists():
        # No restarts: a restart would hand out a fresh timer and a new shuffle.
        raise ValidationError("A quiz session already exists for this application.")

    questions = list(Question.objects.filter(is_active=True))
    if not questions:
        raise ValidationError("No active questions are configured.")

    random.shuffle(questions)  # shuffled ONCE, per applicant, then frozen

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
    if now > _deadline(item):
        item.timed_out = True
        item.is_correct = False
        item.submitted_answer = ""
        item.answered_at = _deadline(item)
    else:
        item.submitted_answer = answer
        item.is_correct = answer == item.question.correct_answer
        item.answered_at = now

    item.save()
    _maybe_complete(session)
    return item
