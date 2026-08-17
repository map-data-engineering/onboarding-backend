from django.core.management.base import BaseCommand

from application.models import Question

C = Question.Category

# Seconds allowed per question. The model stores this per question, so a long
# scenario item can be given more room by setting `secs` on its tuple below.
DEFAULT_SECONDS = 25

# The canonical question set, transcribed from "Onboarding Portal - Knowledge
# Check Questions": R x2, spatial x4, general statistics x2, Bayesian x3,
# health applications x1 = 12.
#
# Each entry is (category, text, options, correct_answer[, code[, seconds]]).
# `code` renders under the question in a monospaced block; `seconds` overrides
# DEFAULT_SECONDS. Editing this list is enough -- the command below updates
# existing questions in place and retires anything no longer listed.
QUESTIONS = [
    # ---- R programming ----
    (C.R, "Which of the following will not allow you to import a CSV file into R?",
     ["import.csv()", "read_csv()", "fread()", "read.csv()"],
     "import.csv()"),
    (C.R, "A data frame d has 100 rows and two columns: district (10 unique values) "
          "and cases. How many rows does the result have?",
     ["10", "100", "1", "110"],
     "100",
     "d %>% group_by(district) %>% mutate(total = sum(cases))"),

    # ---- Spatial data ----
    (C.SPATIAL, "Your survey points are stored in EPSG:4326 (longitude / latitude) WGS84. "
                "You run st_buffer(points, 5) intending a 5 km buffer. "
                "What do you actually get?",
     ["A 5 km buffer as intended",
      "A 5 metre buffer",
      "A buffer of 5 degrees",
      "An error, because buffering needs a projected CRS"],
     "A buffer of 5 degrees"),
    (C.SPATIAL, "Which data type is best suited for representing malaria prevalence surfaces?",
     ["Point", "Polygon", "Raster", "Table"],
     "Raster"),
    (C.SPATIAL, "What does spatial autocorrelation mean?",
     ["Nearby locations tend to have similar values.",
      "Data collected automatically.",
      "Multiple variables are correlated.",
      "Locations are randomly distributed."],
     "Nearby locations tend to have similar values."),
    (C.SPATIAL, "Which file format is commonly used for vector spatial data?",
     ["GeoTIFF (.tiff)", "Shapefile (.shp)", "CSV (.csv)", "XLSX (.xlsx)"],
     "Shapefile (.shp)"),

    # ---- General statistics ----
    (C.GENERAL, "You have repeated observations from 30 villages. You include village as a "
                "random effect rather than a fixed effect mainly because:",
     ["It is faster to compute the effects",
      "It accounts for correlation within villages",
      "Random effects always fit the data better",
      "Fixed effects cannot be used with categorical variables"],
     "It accounts for correlation within villages"),
    (C.GENERAL, "You compare two models and obtain DIC values of 148.2 and 147.9. "
                "What should you conclude?",
     ["The second model is clearly better",
      "The first model is better, because higher DIC means more explained variation",
      "The difference is too small to prefer either; decide on other grounds",
      "DIC cannot be used to compare these models"],
     "The difference is too small to prefer either; decide on other grounds"),

    # ---- Bayesian statistics ----
    (C.BAYESIAN, "You have only 12 observations and use a strongly informative prior. "
                 "Compared with using a vague prior, the posterior will be:",
     ["Pulled toward the prior, and narrower",
      "Identical, because the data always dominates",
      "Pulled toward the prior, but wider",
      "Unaffected, because priors only matter for large samples"],
     "Pulled toward the prior, and narrower"),
    (C.BAYESIAN, "Which statement best describes Bayesian inference?",
     ["It ignores prior information.",
      "It combines prior beliefs with observed data.",
      "It only works for large datasets.",
      "It cannot estimate uncertainty."],
     "It combines prior beliefs with observed data."),
    (C.BAYESIAN, "A model gives a 95% credible interval for prevalence of [0.12, 0.18]. "
                 "Which interpretation is correct?",
     ["If we repeated the survey many times, 95% of such intervals would contain the true value",
      "Given the model and data, there is a 95% probability the true prevalence lies in this range",
      "95% of the surveyed individuals have prevalence values in this range",
      "The estimate is correct 95% of the time"],
     "Given the model and data, there is a 95% probability the true prevalence lies in this range"),

    # ---- Health applications ----
    (C.APPLICATION, "A national dataset records monthly malaria cases diagnosed at health "
                    "facilities. If you map raw case counts by location, what will the map "
                    "mostly show?",
     ["Where people access health facilities",
      "The true geographic distribution of disease burden",
      "Population density alone",
      "Seasonal variation in transmission"],
     "Where people access health facilities"),
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
        # build_session() only ever picks up is_active=True.
        superseded = Question.objects.exclude(text__in=[q[1] for q in QUESTIONS])
        deactivated = superseded.filter(is_active=True).update(is_active=False)

        deleted = 0
        if not options["keep_retired"]:
            unused = superseded.filter(sessionquestion__isnull=True)
            deleted, _ = unused.delete()

        active = Question.objects.filter(is_active=True)
        by_category = ", ".join(
            f"{Question.Category(c).label}: {active.filter(category=c).count()}"
            for c in active.values_list("category", flat=True).distinct().order_by("category")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} question(s) created, {updated} updated, "
                f"{deactivated} retired, {deleted} deleted.\n"
                f"{active.count()} active ({by_category}) at {DEFAULT_SECONDS}s each."
            )
        )
