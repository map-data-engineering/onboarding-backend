from django.contrib import admin

from .models import Application, Question, QuizSession, SessionQuestion


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "category", "correct_answer", "is_active")
    list_filter = ("category", "is_active")


class SessionQuestionInline(admin.TabularInline):
    model = SessionQuestion
    extra = 0
    readonly_fields = (
        "question",
        "position",
        "served_at",
        "answered_at",
        "submitted_answer",
        "is_correct",
        "timed_out",
    )


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = ("application", "score", "total", "completed_at")
    inlines = [SessionQuestionInline]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "email",
        "institution",
        "quiz_status",
        "decision",
        "created_at",
    )
    list_filter = ("decision",)
    search_fields = ("first_name", "last_name", "email")

    @admin.display(description="Status")
    def quiz_status(self, application):
        # Application.status is derived from the score, so it can't be a
        # list_filter here -- use the staff panel's ?status= filter for that.
        return application.status_display
