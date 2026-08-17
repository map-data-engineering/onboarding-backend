"""
Eligibility rules, the honesty check, and the composite score staff rank on.

All of it lives server-side on purpose. The client renders these questions but
never decides anything: which function names are invented, whether an answer set
rules someone out, and what an application scores are all computed here, from the
stored record.
"""

import random

from django.conf import settings

from .models import PASS_MARK

# --- Honesty check -----------------------------------------------------------
# Real R functions...
CLAIM_REAL = [
    "read.csv", "group_by", "ggplot", "glm",
    "st_read", "st_transform", "rast", "predict",
]
# ...and names that look plausible but do not exist. Claiming to have *used* one
# is the signal; admitting you don't know a function costs nothing.
CLAIM_FAKE = ["st_reproject", "read.shapefile", "spatial_join_df", "raster_scale2"]

CLAIM_CHOICES = ("used", "heard", "no")


def claim_catalogue():
    """The function names to show, shuffled so the fakes aren't clustered."""
    names = CLAIM_REAL + CLAIM_FAKE
    random.shuffle(names)
    return names


def claim_summary(claims):
    """Count real functions used, fakes claimed, and outright bluffs."""
    claims = claims or {}
    real_used = sum(1 for f in CLAIM_REAL if claims.get(f) == "used")
    fakes_claimed = sum(1 for f in CLAIM_FAKE if claims.get(f) in ("used", "heard"))
    bluffs = sum(1 for f in CLAIM_FAKE if claims.get(f) == "used")
    return {"real_used": real_used, "fakes_claimed": fakes_claimed, "bluffs": bluffs}


# --- Eligibility -------------------------------------------------------------
ELIGIBILITY_QUESTIONS = {
    "elig_attend": [
        "Yes, all four days",
        "Only part of the period",
        "No",
    ],
    "elig_laptop": ["Yes", "No", "I am not sure"],
    "elig_data": [
        "Yes, I work with it now",
        "Not yet, but I expect to within six months",
        "No",
    ],
    "elig_funding": [
        "My institution has agreed to cover it",
        "I will cover it myself",
        "Likely covered, but not yet confirmed",
        "I could not attend without financial support",
    ],
}

NO_FUNDING_ANSWER = "I could not attend without financial support"

# Advisory answers -- they raise a flag rather than ending the application.
UNCONFIRMED_TRAVEL_ANSWER = "Likely covered, but not yet confirmed"


def portal_setting(name):
    """One value from settings.PORTAL, read at call time so tests can override it."""
    return settings.PORTAL[name]


def funding_gate():
    """
    Whether "could not attend without support" ends the application.

    Read from settings on every call rather than captured at import: the gate is
    the one selection rule most likely to be changed between rounds, and a module
    constant would need a redeploy (and would ignore override_settings in tests).
    """
    return bool(portal_setting("FUNDING_GATE"))


def eligibility_problem(answers):
    """
    Why this applicant cannot be considered, or "" if they can.

    Returning the reason rather than a bare boolean lets the portal say something
    useful and lets staff see it later on the record.
    """
    if answers.get("elig_attend") == "No":
        return (
            "This is a four-day in-person course, so we cannot consider applications "
            "from people who cannot attend the full period."
        )
    if answers.get("elig_data") == "No":
        return (
            "The course is built around participants' own spatial data, so we cannot "
            "consider applications from people who do not expect to work with it."
        )
    if funding_gate() and answers.get("elig_funding") == NO_FUNDING_ANSWER:
        return (
            "We have no funding for participant travel, accommodation or subsistence, "
            "and no way to create any. We would rather tell you plainly now than have "
            "you spend fifteen minutes on an application we could not honour."
        )
    return ""


# --- Experience --------------------------------------------------------------
EXPERIENCE_QUESTIONS = {
    "exp_rfreq": ["Most weeks", "Most months", "A few times a year", "Rarely or never"],
    "exp_rself": [
        "Beginner — I can run scripts others have written",
        "Intermediate — I write my own analysis scripts",
        "Advanced — I write functions and packages",
    ],
    "exp_bayes": ["None", "Beginner", "Intermediate", "Advanced"],
    "exp_glm": ["Yes, several times", "Yes, once or twice", "No"],
    "exp_dtype": [
        "Survey or sampling points with coordinates",
        "Counts or rates aggregated to districts, wards or facilities",
        "Raster or gridded environmental data",
        "Locations of events or cases (point patterns)",
        "A mixture of these",
        "None yet",
    ],
    "exp_when": [
        "I have an analysis waiting for these methods now",
        "Within six months",
        "Within a year",
        "No specific plan yet",
    ],
    "exp_share": [
        "Yes, and I have a specific team in mind",
        "Yes, in principle",
        "Possibly",
        "No",
    ],
    "exp_use": ["Yes, regularly", "Sometimes", "No"],
}


# --- Composite score ---------------------------------------------------------
# Knowledge 45 + honesty 20 + relevance 20 + impact 15 = 100.
def _points(value, table):
    return table.get(value, 0)


def has_own_code(application):
    """Whether real R code was pasted -- machine-checkable, and a strong signal."""
    code = (application.written_code or "").strip()
    return len(code) >= 20 and code.lower() != "none"


def compute_score(application):
    """
    The composite the panel ranks on, recomputed from the stored record.

    Derived rather than stored so it can never disagree with the answers, and so
    changing a weight re-scores everyone without a migration.
    """
    quiz = getattr(application, "quiz", None)
    total_questions = quiz.total if quiz else 0
    correct = quiz.score if quiz else 0
    knowledge = (correct / total_questions * 45) if total_questions else 0.0

    # Honesty: each real function used is worth a point, each fake claimed costs
    # three. Floored at zero -- there is no negative total for bluffing, it just
    # wipes out this component.
    summary = claim_summary(application.claims)
    raw = summary["real_used"]
    for name in CLAIM_FAKE:
        if (application.claims or {}).get(name) in ("used", "heard"):
            raw -= 3
    honesty = max(0, min(raw, len(CLAIM_REAL))) / len(CLAIM_REAL) * 20

    relevance = (
        _points(application.exp_rfreq,
                {"Most weeks": 6, "Most months": 4, "A few times a year": 2, "Rarely or never": 0})
        + _points(application.exp_glm,
                  {"Yes, several times": 4, "Yes, once or twice": 2, "No": 0})
        + _points(application.elig_data,
                  {"Yes, I work with it now": 3,
                   "Not yet, but I expect to within six months": 1, "No": 0})
        + _points(application.exp_when,
                  {"I have an analysis waiting for these methods now": 3,
                   "Within six months": 2, "Within a year": 1, "No specific plan yet": 0})
        + (4 if has_own_code(application) else 0)
    )

    impact = (
        _points(application.exp_share,
                {"Yes, and I have a specific team in mind": 7, "Yes, in principle": 5,
                 "Possibly": 2, "No": 0})
        + _points(application.exp_use, {"Yes, regularly": 5, "Sometimes": 3, "No": 0})
        + (0 if application.exp_dtype in ("", "None yet") else 3)
    )

    return {
        "knowledge": round(knowledge, 1),
        "honesty": round(honesty, 1),
        "relevance": round(float(relevance), 1),
        "impact": round(float(impact), 1),
        "total": round(knowledge + honesty + relevance + impact, 1),
        "correct": correct,
        "of": total_questions,
        "flags": compute_flags(application),
    }


def compute_flags(application):
    """Short labels staff can scan a list by. Each one is a reason to look closer."""
    flags = []
    quiz = getattr(application, "quiz", None)

    if application.final_submitted_at and not has_own_code(application):
        flags.append("NO-CODE")
    if claim_summary(application.claims)["bluffs"]:
        flags.append("BLUFF")

    if quiz and quiz.total:
        ratio = quiz.score / quiz.total
        if application.exp_rself.startswith("Advanced") and ratio < 0.4:
            flags.append("INCONSISTENT")

        items = list(quiz.items.all())
        answered = [i for i in items if i.answered_at and i.served_at]
        allowed = sum(i.question.time_limit_seconds for i in answered)
        used = sum((i.answered_at - i.served_at).total_seconds() for i in answered)
        if allowed and used / allowed < 0.2:
            flags.append("RUSHED")
        if sum(1 for i in items if i.timed_out) > 3:
            flags.append("TIMEOUTS")
        if quiz.is_complete and quiz.score < PASS_MARK:
            flags.append("BELOW-PASS")

    if application.elig_laptop and application.elig_laptop != "Yes":
        flags.append("NO-LAPTOP")
    if application.elig_funding == UNCONFIRMED_TRAVEL_ANSWER:
        flags.append("TRAVEL-UNCONFIRMED")
    if application.elig_funding == NO_FUNDING_ANSWER:
        flags.append("UNFUNDED")

    return flags
