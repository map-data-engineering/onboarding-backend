from django.core.management.base import BaseCommand

from application.models import Question

C = Question.Category

# The canonical question set, transcribed from "Onboarding Portal - Knowledge
# Check Questions" (docx). Categories follow that document's headings, so there
# are no health-application items: R x2, spatial x4, Bayesian x6.
#
# Editing this list is enough -- the command below updates existing questions in
# place and retires anything no longer listed here.
QUESTIONS = [
    # ---- R programming ----
    (C.R, "Which function is used to import a CSV file into R?",
     ["read.csv()", "load.csv()", "import.csv()", "open.csv()"],
     "read.csv()"),
    (C.R, "Which package is commonly used for data visualization in R?",
     ["dplyr", "ggplot2", "tidyr", "stringr"],
     "ggplot2"),

    # ---- Spatial data ----
    (C.SPATIAL, "Which package is primarily used for handling spatial vector data in R?",
     ["sf", "randomForest", "shiny", "glm"],
     "sf"),
    (C.SPATIAL, "Which of the following best describes spatial data?",
     ["Data collected over time only",
      "Data associated with geographic locations",
      "Data stored in spreadsheets",
      "Data collected from surveys only"],
     "Data associated with geographic locations"),
    (C.SPATIAL, "A Coordinate Reference System (CRS) matters because:",
     ["It determines the file size of the dataset",
      "It defines how coordinates map onto the Earth; two layers in different CRSs "
      "will not align, and distances may be in degrees rather than metres",
      "It is only needed when printing maps",
      "It sets the colour palette used for plotting"],
     "It defines how coordinates map onto the Earth; two layers in different CRSs "
     "will not align, and distances may be in degrees rather than metres"),
    (C.SPATIAL, "What does spatial autocorrelation mean?",
     ["Nearby locations tend to have similar values.",
      "Data collected automatically.",
      "Multiple variables are correlated.",
      "Locations are randomly distributed."],
     "Nearby locations tend to have similar values."),

    # ---- Bayesian statistics ----
    (C.BAYESIAN, "Your response variable is a count of cases per district. "
                 "The most appropriate standard GLM family is:",
     ["Gaussian with an identity link",
      "Poisson with a log link",
      "Binomial with a logit link",
      "Gamma with an inverse link"],
     "Poisson with a log link"),
    (C.BAYESIAN, "In Bayesian statistics, what is combined with observed data to "
                 "obtain the posterior distribution?",
     ["Prior distribution", "Sample mean", "Correlation coefficient", "Variance"],
     "Prior distribution"),
    (C.BAYESIAN, "Which statement best describes Bayesian inference?",
     ["It ignores prior information.",
      "It combines prior beliefs with observed data.",
      "It only works for large datasets.",
      "It cannot estimate uncertainty."],
     "It combines prior beliefs with observed data."),
    (C.BAYESIAN, "In a logistic regression for presence/absence data, what is being "
                 "modelled as a linear function of the covariates?",
     ["The log-odds (logit) of presence",
      "The probability itself",
      "The count of presences",
      "The variance of the response"],
     "The log-odds (logit) of presence"),
    (C.BAYESIAN, "You have repeated observations from 30 villages. You include village "
                 "as a random effect rather than a fixed effect mainly because:",
     ["It is faster to compute",
      "It accounts for correlation within villages and shares information across them, "
      "without estimating 30 separate free parameters",
      "Random effects always fit the data better",
      "Fixed effects cannot be used with categorical variables"],
     "It accounts for correlation within villages and shares information across them, "
     "without estimating 30 separate free parameters"),
    # NB: the source document marks no answer for this one. Seeded with the only
    # statistically defensible option -- a lower DIC is the better model.
    (C.BAYESIAN, "You compare four models and get DIC (Deviance Information Criteria) "
                 "values of 148, 273, 338 and 147. Which is preferred, and why?",
     ["338 — higher DIC means more variance explained",
      "273 — the middle value avoids over- and under-fitting",
      "147 — lower DIC indicates a better trade-off between fit and complexity",
      "DIC cannot be used to compare models"],
     "147 — lower DIC indicates a better trade-off between fit and complexity"),
]


class Command(BaseCommand):
    help = "Seed/refresh the scored quiz questions from the knowledge-check document."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-retired",
            action="store_true",
            help="Deactivate superseded questions but never delete them, even if unused.",
        )

    def handle(self, *args, **options):
        created = updated = 0

        for category, text, choices, correct in QUESTIONS:
            assert correct in choices, f"correct_answer not among options: {text!r}"
            _, was_created = Question.objects.update_or_create(
                text=text,
                defaults={
                    "category": category,
                    "options": choices,
                    "correct_answer": correct,
                    "time_limit_seconds": 40,
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        # Retire anything not in the canonical list. Questions already used in a
        # quiz can't be deleted (SessionQuestion.question is PROTECTed, and old
        # sessions must stay auditable), so those are just deactivated --
        # build_session() only ever picks up is_active=True.
        superseded = Question.objects.exclude(text__in=[q[1] for q in QUESTIONS])
        deactivated = superseded.filter(is_active=True).update(is_active=False)

        deleted = 0
        if not options["keep_retired"]:
            unused = superseded.filter(sessionquestion__isnull=True)
            deleted, _ = unused.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"{created} question(s) created, {updated} updated, "
                f"{deactivated} retired, {deleted} deleted. "
                f"{Question.objects.filter(is_active=True).count()} active."
            )
        )
