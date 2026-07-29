from django.urls import path

from . import admin_views, views

urlpatterns = [
    # ---- Applicant-facing (open) ----
    # Submit the applicant + CV
    path("applications/", views.application_create),
    # Begin the timed, shuffled quiz for that applicant
    path("applications/<uuid:application_id>/quiz/start/", views.quiz_start),
    # One-question-at-a-time flow
    path("quiz/<uuid:session_id>/current/", views.quiz_current),
    path("quiz/<uuid:session_id>/answer/", views.quiz_answer),
    path("quiz/<uuid:session_id>/result/", views.quiz_result),
    # ---- Custom admin panel (staff-only, token auth) ----
    path("admin/login/", admin_views.admin_login),
    path("admin/logout/", admin_views.admin_logout),
    path("admin/me/", admin_views.admin_me),
    path("admin/applications/", admin_views.admin_applications),
    path("admin/applications/<uuid:application_id>/", admin_views.admin_application_detail),
    path("admin/applications/<uuid:application_id>/quiz/", admin_views.admin_application_quiz),
]
