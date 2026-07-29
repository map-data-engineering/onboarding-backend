from django.core.management.base import BaseCommand

from application.models import Question

C = Question.Category

# Correct answers taken from the form's knowledge-check items.
QUESTIONS = [
    (C.R, "Which function is used to import a CSV file into R?",
     ["read.csv()", "load.csv()", "import.csv()", "open.csv()"], "read.csv()"),
    (C.R, "Which package is commonly used for data visualization in R?",
     ["dplyr", "ggplot2", "tidyr", "stringr"], "ggplot2"),
    (C.SPATIAL, "Which package is primarily used for handling spatial vector data in R?",
     ["sf", "randomForest", "shiny", "glm"], "sf"),
    (C.SPATIAL, "Which of the following best describes spatial data?",
     ["Data collected over time only", "Data associated with geographic locations",
      "Data stored in spreadsheets", "Data collected from surveys only"],
     "Data associated with geographic locations"),
    (C.SPATIAL, "Which coordinate system is commonly used by GPS devices?",
     ["UTM", "WGS84", "NAD83", "Lambert"], "WGS84"),
    (C.SPATIAL, "Which file format is commonly used for vector spatial data?",
     ["GeoTIFF", "Shapefile (.shp)", "CSV", "XLSX"], "Shapefile (.shp)"),
    (C.SPATIAL, "Which data type is best suited for representing malaria prevalence surfaces?",
     ["Point", "Polygon", "Raster", "Table"], "Raster"),
    (C.SPATIAL, "What does spatial autocorrelation mean?",
     ["Nearby locations tend to have similar values.", "Data collected automatically.",
      "Multiple variables are correlated.", "Locations are randomly distributed."],
     "Nearby locations tend to have similar values."),
    (C.BAYESIAN, "In Bayesian statistics, what is combined with observed data to obtain the posterior distribution?",
     ["Prior distribution", "Sample mean", "Correlation coefficient", "Variance"],
     "Prior distribution"),
    (C.BAYESIAN, "Which statement best describes Bayesian inference?",
     ["It ignores prior information.", "It combines prior beliefs with observed data.",
      "It only works for large datasets.", "It cannot estimate uncertainty."],
     "It combines prior beliefs with observed data."),
    (C.BAYESIAN, "What is the posterior distribution?",
     ["Distribution before observing data.", "Updated probability after observing data.",
      "Distribution of residuals.", "Distribution of predictors."],
     "Updated probability after observing data."),
    (C.APPLICATION, "Which health application commonly uses spatial models?",
     ["Disease risk mapping", "Text mining", "Financial forecasting", "Image compression"],
     "Disease risk mapping"),
]


class Command(BaseCommand):
    help = "Seed the scored quiz questions from the application form."

    def handle(self, *args, **options):
        created = 0
        for category, text, options, correct in QUESTIONS:
            _, was_created = Question.objects.get_or_create(
                text=text,
                defaults={
                    "category": category,
                    "options": options,
                    "correct_answer": correct,
                    "time_limit_seconds": 40,
                },
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new question(s)."))
