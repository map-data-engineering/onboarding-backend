from django.contrib import admin

from .models import Application, PortalSettings, Question, QuizSession, SessionQuestion
from .permissions import can_delete


@admin.register(PortalSettings)
class PortalSettingsAdmin(admin.ModelAdmin):
    """
    The single row holding the application deadline.

    Also editable from the staff panel, which is where staff are told to change
    it; this is the fallback for a superuser who is already in /admin/.
    """

    list_display = ("application_deadline", "is_open", "updated_at")
    readonly_fields = ("updated_at",)

    @admin.display(boolean=True, description="Accepting applications")
    def is_open(self, portal):
        return portal.is_open

    def has_add_permission(self, request):
        # Singleton: add the row by opening the panel (or the API), never by hand,
        # so a second row can't appear and disagree with the first.
        return not PortalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


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

    def has_delete_permission(self, request, obj=None):
        """
        Superusers only, matching the panel.

        Django would otherwise grant this from the `delete_application` model
        permission, so a reviewer given "all application permissions" in the group
        editor would get here what the panel refuses them -- and the admin's bulk
        delete action is the easiest place in the project to remove 500 records by
        accident. The panel is the interface reviewers are meant to use; this keeps
        the back door from being wider than the front one.
        """
        return can_delete(request.user)
