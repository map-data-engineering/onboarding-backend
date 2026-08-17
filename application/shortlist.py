"""
Ranking and shortlist building for the staff panel.

The design assumption is 500 applicants for 25 seats. At 20:1 the job is not to
pick the best 25 by machine -- it is to rank everyone automatically so that humans
read 60 applications instead of 500, and to make the diversity floors explicit
rather than something someone tries to fix by hand at the end.

Two rules are baked in, and both are deliberate:

  * **Floors first, then merit.** Seats reserved by a floor are filled before the
    open seats, from the highest-ranked applicants who satisfy it. Applying floors
    at the shortlist stage rather than at the final 25 matters: a shortlist of 60
    that is lopsided by gender or institution is very hard to correct afterwards,
    and at 20:1 being wrong at the margins on an individual technical score costs
    far less than a homogeneous room does.
  * **Scores are recomputed here**, by assessment.compute_score, from the stored
    answers. Nothing trusts a number that came from a browser.

Everything in this module is a pure function over Application objects, so the API,
the CSV export and the tests all see the same allocation.
"""

from . import assessment, countries

# Travel-certainty handling. Unconfirmed travel is the largest single cause of
# no-shows, and a no-show is a seat that cannot be reallocated -- offers go out
# once, shortly before the workshop.
TRAVEL_PREFER = "prefer"   # fill from confirmed applicants first, then the rest
TRAVEL_ONLY = "only"       # exclude unconfirmed applicants entirely
TRAVEL_IGNORE = "ignore"   # rank purely on merit
TRAVEL_MODES = (TRAVEL_PREFER, TRAVEL_ONLY, TRAVEL_IGNORE)

# Which applications are eligible to be ranked at all.
POOL_SUBMITTED = "submitted"   # completed the final step (written answers + CV)
POOL_SCORED = "scored"         # finished the knowledge check, may not have submitted
POOL_ALL = "all"
POOLS = (POOL_SUBMITTED, POOL_SCORED, POOL_ALL)

DEFAULTS = {
    "seats": 25,
    "min_women": 10,
    "min_tanzania": 12,
    "max_per_institution": 3,
    "drop_bluff": True,
    "travel": TRAVEL_PREFER,
    "waitlist": 10,
    "pool": POOL_SUBMITTED,
}

# Above this share of the questions correct, the knowledge check has stopped
# discriminating: most applicants are at the ceiling and the ranking is really
# being driven by the other three components.
CEILING_RATIO = 0.78


def is_tanzania_based(application):
    """
    Whether this applicant counts toward the Tanzania-based floor.

    A substring test rather than `== "Tanzania"`, because records created before
    the country dropdown existed hold free text ("United Republic of Tanzania",
    "tanzania"), and a floor that silently skipped those would have been met on
    paper and missed in the room.
    """
    return countries.TANZANIA.lower() in (application.country_of_residence or "").lower()


def is_woman(application):
    return (application.gender or "") == "Female"


def institution_key(application):
    return (application.institution or "").strip().lower()


def rank(applications):
    """
    Applications with their recomputed score, best first.

    Ties break on the knowledge check and then on who applied first, so the order
    is stable between two calls -- a shortlist that reshuffles under the panel
    when they press the button again is a shortlist nobody trusts.
    """
    scored = [(app, assessment.compute_score(app)) for app in applications]
    scored.sort(
        key=lambda pair: (-pair[1]["total"], -pair[1]["correct"], pair[0].created_at)
    )
    return scored


def filter_pool(applications, pool=POOL_SUBMITTED):
    """Applications eligible for ranking under `pool` (see POOLS)."""
    if pool == POOL_ALL:
        return list(applications)
    if pool == POOL_SCORED:
        return [
            app for app in applications
            if getattr(app, "quiz", None) is not None and app.quiz.is_complete
        ]
    return [app for app in applications if app.final_submitted_at is not None]


def travel_confirmed(flags):
    """Neither flagged as unconfirmed nor as unable to attend without support."""
    return "TRAVEL-UNCONFIRMED" not in flags and "UNFUNDED" not in flags


def build_shortlist(applications, **options):
    """
    Allocate seats, then a waitlist, returning the full ranking either way.

    Returns {"rows": [...], "floors": {...}, "stats": {...}} where every row is
    {"application", "score", "rank", "shortlisted", "waitlisted"} -- the panel
    renders the whole ranking with the picks marked, because the applications the
    panel most needs to read are the ones just either side of the cut line.
    """
    settings = {**DEFAULTS, **{k: v for k, v in options.items() if v is not None}}
    seats = max(0, int(settings["seats"]))
    min_women = max(0, int(settings["min_women"]))
    min_tanzania = max(0, int(settings["min_tanzania"]))
    max_per_institution = max(1, int(settings["max_per_institution"]))
    waitlist_size = max(0, int(settings["waitlist"]))
    travel = settings["travel"] if settings["travel"] in TRAVEL_MODES else TRAVEL_PREFER

    ranked = rank(filter_pool(applications, settings["pool"]))

    eligible = [
        (app, score) for app, score in ranked
        if not (settings["drop_bluff"] and "BLUFF" in score["flags"])
    ]
    if travel == TRAVEL_ONLY:
        eligible = [
            (app, score) for app, score in eligible if travel_confirmed(score["flags"])
        ]

    picked, per_institution = [], {}
    chosen_ids = set()

    def fits(app):
        return per_institution.get(institution_key(app), 0) < max_per_institution

    def take(app, score):
        picked.append((app, score))
        chosen_ids.add(app.pk)
        key = institution_key(app)
        per_institution[key] = per_institution.get(key, 0) + 1

    def fill(candidates, predicate=None, target=None):
        """
        Take candidates in rank order until the seats (or a floor) are filled.

        `predicate` restricts who is considered; `target` is how many picks
        satisfying it are needed, counted across everyone already chosen -- an
        applicant who is both a woman and Tanzania-based counts toward both
        floors, which is why the floors are checked against `picked` rather than
        tallied per pass.
        """
        for app, score in candidates:
            if len(picked) >= seats:
                return
            if target is not None and sum(1 for a, _ in picked if predicate(a)) >= target:
                return
            if app.pk in chosen_ids or not fits(app):
                continue
            if predicate and not predicate(app):
                continue
            take(app, score)

    # In "prefer" mode the entire allocation runs over confirmed applicants first
    # and is then repeated over everyone, so unconfirmed travel is used only for
    # seats that would otherwise stay empty. On a simulated pool where 40% were
    # unconfirmed this cut unconfirmed participants in the final 25 from twelve to
    # zero, for about three points of median score -- cheap, against no-shows.
    if travel == TRAVEL_PREFER:
        passes = [
            [pair for pair in eligible if travel_confirmed(pair[1]["flags"])],
            eligible,
        ]
    else:
        passes = [eligible]

    for candidates in passes:
        fill(candidates, predicate=is_woman, target=min_women)
        fill(candidates, predicate=is_tanzania_based, target=min_tanzania)
        fill(candidates)   # remaining seats, purely on merit

    # Waitlist: the next best applicants not already holding a seat, in rank
    # order. Institution caps do not apply -- a waitlisted place is only used when
    # someone declines, and the cap is re-checked then.
    waitlisted = [
        app.pk for app, _ in eligible if app.pk not in chosen_ids
    ][:waitlist_size]
    waitlisted_ids = set(waitlisted)

    rows = [
        {
            "application": app,
            "score": score,
            "rank": index + 1,
            "shortlisted": app.pk in chosen_ids,
            "waitlisted": app.pk in waitlisted_ids,
        }
        for index, (app, score) in enumerate(ranked)
    ]

    return {
        "rows": rows,
        "floors": _floor_status(picked, min_women, min_tanzania, max_per_institution, seats),
        "stats": pool_stats(ranked),
        "settings": {**settings, "waitlisted": len(waitlisted_ids)},
    }


def _median(values):
    values = sorted(values)
    if not values:
        return 0.0
    middle = len(values) // 2
    if len(values) % 2:
        return float(values[middle])
    return (values[middle - 1] + values[middle]) / 2


def _floor_status(picked, min_women, min_tanzania, max_per_institution, seats):
    """Whether each floor was met, for the status pills above the table."""
    women = sum(1 for app, _ in picked if is_woman(app))
    tanzania = sum(1 for app, _ in picked if is_tanzania_based(app))
    unconfirmed = sum(1 for _, score in picked if not travel_confirmed(score["flags"]))

    counts = {}
    for app, _ in picked:
        label = (app.institution or "—").strip() or "—"
        counts[label] = counts.get(label, 0) + 1
    largest = max(counts.items(), key=lambda pair: pair[1]) if counts else ("—", 0)

    return {
        "shortlisted": len(picked),
        "seats": seats,
        "seats_filled": len(picked) >= seats,
        "women": women,
        "women_required": min_women,
        "women_met": women >= min_women,
        "tanzania": tanzania,
        "tanzania_required": min_tanzania,
        "tanzania_met": tanzania >= min_tanzania,
        "travel_unconfirmed": unconfirmed,
        "max_per_institution": max_per_institution,
        "largest_institution": largest[0],
        "largest_institution_count": largest[1],
        "median_score": round(_median([score["total"] for _, score in picked]), 1),
    }


def pool_stats(ranked):
    """
    Headline numbers for the panel, plus the one piece of advice worth automating.

    If the median applicant is near the ceiling of the knowledge check then the
    questions are not discriminating and the ranking is being driven by the other
    components -- staff should know that before they trust the order, and it is
    not something anyone notices by looking at a table.

    Takes the output of rank(): [(application, score), ...].
    """
    scores = [score for _, score in ranked]
    totals = [score["total"] for score in scores]
    correct = [score["correct"] for score in scores]
    of = next((score["of"] for score in scores if score["of"]), 0)
    median_correct = _median(correct)

    if not scores:
        advice = "No applications in this pool yet."
    elif of and median_correct >= of * CEILING_RATIO:
        advice = (
            f"The knowledge check is not discriminating. A median of {median_correct:g} "
            f"of {of} correct means most applicants are near the ceiling, so the ranking "
            f"is being driven by the other components. Consider harder questions before "
            f"the next round."
        )
    else:
        advice = (
            f"Median knowledge check is {median_correct:g} of {of} correct, which gives a "
            f"usable spread for ranking. It is 45 of the 100 points — read the written "
            f"answers of everyone near the cut line before deciding."
        )

    return {
        "applications": len(scores),
        "median_score": round(_median(totals), 1),
        "median_correct": median_correct,
        "questions": of,
        "bluff": sum(1 for score in scores if "BLUFF" in score["flags"]),
        # Asked of the record directly rather than read off the NO-CODE flag,
        # which is only raised once an application has been finalised -- in a pool
        # that includes unsubmitted applications the flag's absence means "not
        # asked yet", not "supplied code".
        "with_code": sum(1 for app, _ in ranked if assessment.has_own_code(app)),
        "women": sum(1 for app, _ in ranked if is_woman(app)),
        "tanzania": sum(1 for app, _ in ranked if is_tanzania_based(app)),
        "travel_unconfirmed": sum(
            1 for score in scores if "TRAVEL-UNCONFIRMED" in score["flags"]
        ),
        "advice": advice,
    }
