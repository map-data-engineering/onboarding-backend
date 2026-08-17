from django.urls import path

from . import admin_views, views

urlpatterns = [
    # ---- Applicant-facing (open) ----
    # Step 1: contact + profile (no CV yet)
    path("applications/", views.application_create),
    # Where the applicant is in the journey (used to resume after a reload)
    path("applications/<uuid:application_id>/status/", views.application_status),
    # Steps 2-4: eligibility gate, experience, honesty check
    path("applications/<uuid:application_id>/eligibility/", views.application_eligibility),
    path("applications/<uuid:application_id>/experience/", views.application_experience),
    path("applications/<uuid:application_id>/claims/", views.application_claims),
    # Final step: motivation, expectations + CV — only if the quiz was passed
    path("applications/<uuid:application_id>/finalize/", views.application_finalize),
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
    # CSV of whatever ?search=/?status= currently select (reviewers only)
    path("admin/applications/export/", admin_views.admin_applications_export),
    path("admin/applications/bulk/", admin_views.admin_applications_bulk),
    path("admin/applications/<uuid:application_id>/", admin_views.admin_application_detail),
    path("admin/applications/<uuid:application_id>/quiz/", admin_views.admin_application_quiz),
    path("admin/applications/<uuid:application_id>/cv/", admin_views.admin_application_cv),
]
