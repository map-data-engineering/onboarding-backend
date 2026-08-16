"""
Two tiers of staff access for the admin panel.

* **Reviewer** — any staff account: browse applicants, change decisions, delete,
  export. This is what `createsuperuser` gives you.
* **Viewer** — staff, but read-only: the applicant list, counts, details and quiz
  breakdowns, and nothing else. No decisions, no deletes, no bulk actions, no
  CSV export (a viewer can read records one at a time; handing over the whole
  applicant database in one file is a different thing).

Membership of the `VIEWER_GROUP` Django group is what marks an account read-only,
so the tier is visible and changeable from the Django admin without a migration
or a code change. Create one with `manage.py create_viewer <username>`.

Superusers are never read-only, even if someone adds them to the group by
mistake -- otherwise you could lock every reviewer out of the panel.
"""

from django.contrib.auth.models import Group
from rest_framework.permissions import BasePermission

VIEWER_GROUP = "Applicant viewers"


def ensure_viewer_group():
    """Create the viewer group if it doesn't exist yet. Returns the group."""
    group, _ = Group.objects.get_or_create(name=VIEWER_GROUP)
    return group


def is_viewer(user):
    """True for a staff account restricted to read-only access."""
    if not user or not user.is_authenticated or user.is_superuser:
        return False
    return user.groups.filter(name=VIEWER_GROUP).exists()


def can_review(user):
    """True for staff who may change or delete applicant records."""
    return bool(user and user.is_authenticated and user.is_staff and not is_viewer(user))


class IsStaff(BasePermission):
    """Any staff account — reviewers and viewers alike. Read endpoints use this."""

    message = "Staff access is required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class CanReviewApplicants(BasePermission):
    """Staff who are not view-only. Guards every state-changing endpoint."""

    message = "Your account has view-only access to applicants."

    def has_permission(self, request, view):
        return can_review(request.user)
