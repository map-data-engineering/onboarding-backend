from django.core.management.base import BaseCommand
from django.conf import settings

from application.models import Question

C = Question.Category

# Seconds allowed per question. One flat value: every question in the bank uses it,
# and an entry can still override it by adding a sixth element to its tuple.
#
# It is worth knowing what a flat clock costs. The longer scenario items here run to
# four or five lines with numbers in them, and 30 seconds is tight for those --
# tightest for the applicants reading in a second language, who are most of the
# pool. If timeouts cluster on the same few questions (the panel flags TIMEOUTS, and
# the per-question breakdown shows which), give those items their own longer `secs`
# rather than raising this for everything.
DEFAULT_SECONDS = 30

# The question bank. Each applicant sits a random draw from it -- 14 questions,
# by the per-category quota in settings.PORTAL["QUOTA"] -- with the options
# shuffled, so a paper is effectively unique per applicant and answers cannot
# circulate inside an institution.
#
# Two rules when editing:
#
#   * Keep at least two spare questions per category beyond its quota, or the
#     "draw" serves every applicant the same items.
#   * Every question is a novel scenario with its own numbers, asking for a
#     consequence or a next action. That is deliberate and it is the only thing
#     that makes the timer meaningful: there is no phrase to search for, because
#     the situation does not exist anywhere else. A recall item ("which function
#     reads a CSV?") is answered in five seconds by anyone with a second device,
#     so it ranks nobody.
#
# Every question runs on DEFAULT_SECONDS (30s). That is far too short to search for
# an unfamiliar result, read it and evaluate it, which is the point of the clock.
#
# Nothing here tests INLA or inlabru. The published prerequisites are R plus
# regression and GLMs, and that is all the bank covers.
#
# Each entry is (category, text, options, correct_answer[, code[, seconds]]).
QUESTIONS = [
    # ---- R programming (quota 3) ----
    (C.R, "What does this return?",
     ["TRUE", "FALSE", "NA", "Error"],
     "NA",
     "x <- c(2, 4, 6, NA)\nmean(x) > 4"),
    (C.R, "A data frame d has 100 rows and two columns: district (10 unique values) "
          "and cases. How many rows does the result have?",
     ["10", "100", "1", "110"],
     "100",
     "d %>% group_by(district) %>% mutate(total = sum(cases))"),
    (C.R, "A data frame v has one row per village. What does this return?",
     ["The number of Dodoma villages with at least one case",
      "The number of villages in Dodoma",
      "The total cases in Dodoma",
      "All villages with cases, in any region"],
     "The number of Dodoma villages with at least one case",
     'nrow(v[v$region == "Dodoma" & v$cases > 0, ])'),
    (C.R, "A column was read in from CSV and contains \"1,240\" for one district. "
          "What happens?",
     ["Returns the total, ignoring the comma",
      "Returns an error, because the column is not numeric",
      "Returns NA",
      "Returns the values pasted together as text"],
     "Returns an error, because the column is not numeric",
     'class(d$cases)\n# [1] "character"\nsum(d$cases)'),
    (C.R, "Table a has 200 rows, one per household. Table b has 240 rows, with some "
          "households appearing twice. How many rows will the join return?",
     ["200", "240",
      "More than 200, because duplicated matches expand rows",
      "440"],
     "More than 200, because duplicated matches expand rows",
     'left_join(a, b, by = "household_id")'),

    # ---- Spatial data (quota 5) ----
    (C.SPATIAL, "Your survey points are stored in EPSG:4326 (longitude / latitude). You "
                "run st_buffer(points, 5) intending a 5 km buffer. What do you actually get?",
     ["A 5 km buffer as intended",
      "A 5 metre buffer",
      "A buffer of 5 degrees",
      "An error, because buffering needs a projected CRS"],
     "A buffer of 5 degrees",
     ""),
    (C.SPATIAL, "You overlay survey points on a district boundary layer. The points plot "
                "correctly; the boundaries appear thousands of kilometres away. Both layers "
                "have a CRS assigned. Most likely explanation?",
     ["The boundary file is corrupted",
      "The points have too few decimal places",
      "The layers must be merged into one object before plotting",
      "The two CRSs differ, so the coordinates refer to different systems"],
     "The two CRSs differ, so the coordinates refer to different systems",
     ""),
    (C.SPATIAL, "You extract elevation values from a raster to 500 survey points and get NA "
                "for about a third of them. Most likely cause?",
     ["The raster resolution is too coarse",
      "The points and raster are in different CRSs, or some points fall outside "
      "the raster extent",
      "There are too many points to extract at once",
      "Elevation values below sea level return NA"],
     "The points and raster are in different CRSs, or some points fall outside "
     "the raster extent",
     ""),
    (C.SPATIAL, "You have prevalence measured at 60 survey clusters and want a continuous "
                "prevalence surface for the whole country. What is the core statistical "
                "challenge?",
     ["Converting the 60 points into a shapefile",
      "That 60 points is too few to calculate a national mean",
      "Predicting at unobserved locations by borrowing strength from nearby observations",
      "Ensuring all points use WGS84"],
     "Predicting at unobserved locations by borrowing strength from nearby observations",
     ""),
    (C.SPATIAL, "The same household survey is aggregated two ways. At ward level the "
                "association between poverty and disease looks strong; at district level it "
                "looks weak. Which statement is correct?",
     ["The district result is more reliable, because larger units average out noise",
      "The ward result is more reliable, because there are more units",
      "The difference means there is an error in the data",
      "The strength of association depends on the units used, so conclusions must "
      "state the spatial scale"],
     "The strength of association depends on the units used, so conclusions must "
     "state the spatial scale",
     ""),
    (C.SPATIAL, "You fit a standard GLM with no spatial term. The residuals turn out to be "
                "strongly clustered in space. What is the most important consequence?",
     ["The coefficient estimates are biased upward",
      "The model cannot generate predictions",
      "Standard errors are too small, so effects look more significant than they are",
      "The R-squared value is invalid"],
     "Standard errors are too small, so effects look more significant than they are",
     ""),
    (C.SPATIAL, "You have 3,000 survey points and 184 district polygons, and need a count of "
                "points falling inside each district. Both layers share a CRS. What is the "
                "operation you need?",
     ["A spatial join, testing which polygon contains each point",
      "Merging the two tables on a shared ID column",
      "Rasterising both layers to a common grid first",
      "Computing the distance from each point to each district centroid"],
     "A spatial join, testing which polygon contains each point",
     ""),

    # ---- General statistics (quota 3) ----
    (C.GENERAL, "You have repeated observations from 30 villages. You include village as a "
                "random effect rather than a fixed effect mainly because:",
     ["It is faster to compute",
      "It accounts for correlation within villages and shares information across them",
      "Random effects always fit the data better",
      "Fixed effects cannot be used with categorical variables"],
     "It accounts for correlation within villages and shares information across them",
     ""),
    (C.GENERAL, "You compare two models and obtain DIC values of 148.2 and 147.9. What "
                "should you conclude?",
     ["The second model is clearly better",
      "The first is better, because higher DIC means more explained variation",
      "DIC cannot be used to compare these models",
      "The difference is too small to prefer either; decide on other grounds"],
     "The difference is too small to prefer either; decide on other grounds",
     ""),
    (C.GENERAL, "You model counts of reported cases across 184 districts, whose populations "
                "range from 12,000 to 4.1 million. You fit a Poisson model with a log link "
                "using raw case counts as the response and no other adjustment. What is the "
                "main problem?",
     ["Nothing — Poisson with a log link is correct for count data",
      "A Gaussian model should be used because the counts are large",
      "Without an offset for population at risk, the model largely reproduces "
      "population size rather than disease risk",
      "The log link should be replaced with an identity link"],
     "Without an offset for population at risk, the model largely reproduces "
     "population size rather than disease risk",
     ""),
    (C.GENERAL, "Case counts across districts have a mean of 47 and a variance of 890. You "
                "fit a standard Poisson GLM. What should you expect?",
     ["A good fit, since Poisson is designed for counts",
      "Standard errors that are too small, making covariates look more significant "
      "than they are",
      "Coefficient estimates biased toward zero",
      "The model will fail to converge"],
     "Standard errors that are too small, making covariates look more significant "
     "than they are",
     ""),
    (C.GENERAL, "A model is fitted on survey data collected in 2018–2022 and used to predict "
                "prevalence for 2027. What is the main caution?",
     ["Predictions extrapolate beyond the observed period, so uncertainty is understated",
      "The model cannot produce predictions for future dates",
      "Prevalence must first be converted to counts",
      "Nothing, provided the model fitted well"],
     "Predictions extrapolate beyond the observed period, so uncertainty is understated",
     ""),

    # ---- Bayesian statistics (quota 2) ----
    (C.BAYESIAN, "You have only 12 observations and use a strongly informative prior. "
                 "Compared with using a vague prior, the posterior will be:",
     ["Identical, because the data always dominates",
      "Pulled toward the prior, but wider",
      "Unaffected, because priors only matter for large samples",
      "Pulled toward the prior, and narrower"],
     "Pulled toward the prior, and narrower",
     ""),
    (C.BAYESIAN, "A model gives a 95% credible interval for prevalence of [0.12, 0.18]. "
                 "Which interpretation is correct?",
     ["If we repeated the survey many times, 95% of such intervals would contain "
      "the true value",
      "Given the model and data, there is a 95% probability the true prevalence "
      "lies in this range",
      "95% of the surveyed individuals have prevalence values in this range",
      "The estimate is correct 95% of the time"],
     "Given the model and data, there is a 95% probability the true prevalence "
     "lies in this range",
     ""),
    (C.BAYESIAN, "You keep the same prior but increase the sample size from 100 to 10,000 "
                 "observations. The influence of the prior on the posterior will:",
     ["Increase, because there is more information to weight",
      "Stay the same, because the prior is fixed",
      "Decrease, because the likelihood increasingly dominates",
      "Become impossible to determine"],
     "Decrease, because the likelihood increasingly dominates",
     ""),
    (C.BAYESIAN, "For the same fitted model, you compute a 95% interval for the mean "
                 "prevalence at a location, and a 95% interval for a new observation at that "
                 "location. How do they compare?",
     ["They are identical",
      "The interval for a new observation is wider, because it adds "
      "observation-level variability",
      "The interval for the mean is wider, because it averages more values",
      "Neither can be computed without refitting"],
     "The interval for a new observation is wider, because it adds "
     "observation-level variability",
     ""),

    # ---- Health applications (quota 1) ----
    (C.APPLICATION, "A national dataset records malaria cases diagnosed at health facilities. "
                    "If you map raw case counts by location, what will the map mostly show?",
     ["The true geographic distribution of disease burden",
      "Population density alone",
      "Where people access health facilities, rather than where infection occurs",
      "Seasonal variation in transmission"],
     "Where people access health facilities, rather than where infection occurs",
     ""),
    (C.APPLICATION, "District A tests 200 people and finds 60 positive. District B tests "
                    "4,000 and finds 800 positive. A colleague concludes District A has the "
                    "higher burden of disease. What is the problem?",
     ["Test positivity depends on who gets tested, so it is not a measure of "
      "population burden",
      "District B has more cases, so it clearly has higher burden",
      "The percentages should be compared, not the counts",
      "Nothing — 30% is higher than 20%"],
     "Test positivity depends on who gets tested, so it is not a measure of "
     "population burden",
     ""),
    (C.APPLICATION, "You aggregate a fine-scale prevalence surface to district averages for "
                    "a national report. What is mainly lost?",
     ["Nothing, provided the averages are population-weighted",
      "The coordinate reference system",
      "Localised hotspots, which are averaged away within districts",
      "The ability to compute uncertainty"],
     "Localised hotspots, which are averaged away within districts",
     ""),
]


class Command(BaseCommand):
    help = "Seed/refresh the knowledge-check question bank."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-retired",
            action="store_true",
            help="Deactivate superseded questions but never delete them, even if unused.",
        )

    def handle(self, *args, **options):
        created = updated = 0

        for entry in QUESTIONS:
            category, text, choices, correct = entry[:4]
            code = entry[4] if len(entry) > 4 else ""
            seconds = entry[5] if len(entry) > 5 else DEFAULT_SECONDS
            assert correct in choices, f"correct_answer not among options: {text!r}"

            _, was_created = Question.objects.update_or_create(
                text=text,
                defaults={
                    "category": category,
                    "code": code,
                    "options": choices,
                    "correct_answer": correct,
                    "time_limit_seconds": seconds,
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        # Retire anything not in the canonical list. Questions already used in a
        # quiz can't be deleted (SessionQuestion.question is PROTECTed, and old
        # sessions must stay auditable), so those are just deactivated --
        # draw_questions() only ever picks up is_active=True.
        superseded = Question.objects.exclude(text__in=[q[1] for q in QUESTIONS])
        deactivated = superseded.filter(is_active=True).update(is_active=False)

        deleted = 0
        if not options["keep_retired"]:
            unused = superseded.filter(sessionquestion__isnull=True)
            deleted, _ = unused.delete()

        active = Question.objects.filter(is_active=True)
        quota = settings.PORTAL["QUOTA"]
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} question(s) created, {updated} updated, "
                f"{deactivated} retired, {deleted} deleted."
            )
        )

        # Report per category against the quota, because a category that has
        # slipped to its quota or below is the failure that hides: the draw still
        # works, it just serves every applicant the same questions.
        thin = []
        for category, wanted in quota.items():
            available = active.filter(category=category).count()
            label = Question.Category(category).label
            self.stdout.write(f"  {label}: {available} active, {wanted} drawn")
            if available <= wanted:
                thin.append(f"{label} ({available} active, {wanted} drawn)")

        drawn = sum(min(w, active.filter(category=c).count()) for c, w in quota.items())
        self.stdout.write(
            f"{active.count()} active in the bank; {drawn} drawn per applicant."
        )
        if thin:
            self.stdout.write(
                self.style.WARNING(
                    "No spare questions in: " + ", ".join(thin) + ". Every applicant "
                    "will see the same items from these categories -- add more, or "
                    "lower the quota in settings.PORTAL."
                )
            )
