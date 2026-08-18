"""
Three tiers of staff access for the admin panel.

* **Superuser** — everything, and the only tier that may leave with data or see
  the ranking: the CSV exports and the shortlist builder. This is what
  `createsuperuser` gives you.
* **Reviewer** — any other staff account: browse applicants, read the written
  answers and CVs, change decisions, delete, move the deadline. No exports and no
  shortlist.
* **Viewer** — staff, but read-only: the applicant list, counts, details and quiz
  breakdowns, and nothing else. No decisions, no deletes, no bulk actions.

The two restrictions on reviewers are deliberate and different in kind:

  * An **export** hands over the whole filtered applicant database as one file --
    names, emails, phone numbers, institutions and free-text answers -- which then
    lives on somebody's laptop, outside every access check here. Reading records
    one at a time in the panel leaves the data where it is.
  * The **shortlist** is the selection itself: a ranking with the cut line drawn
    and the diversity floors applied. Circulating it before the panel has met
    turns "who should we read closely?" into "who is in", and the people best
    placed to argue with a ranking are the ones who never see it as provisional.

Membership of the `VIEWER_GROUP` Django group is what marks an account read-only,
so that tier is visible and changeable from the Django admin without a migration
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


def can_export(user):
    """
    True only for superusers: the CSV exports and the shortlist builder.

    Deliberately `is_superuser` rather than "not a viewer". A reviewer needs to
    read applications to do their job; nobody needs a copy of the whole applicant
    table, or the ranking with the cut line drawn, in order to review one person.
    Keeping both to the superuser tier means granting them is an explicit act
    (`createsuperuser`, or the Django admin) rather than a side effect of being
    given a staff login.
    """
    return bool(user and user.is_authenticated and user.is_staff and user.is_superuser)


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


class CanExportApplicants(BasePermission):
    """
    Superusers only. Guards the CSV exports and the shortlist builder.

    The panel hides these controls for everyone else, but that is presentation:
    this is the check that a hand-made request runs into.
    """

    message = (
        "Exports and the shortlist are restricted to superuser accounts. "
        "Ask an administrator to run it, or to upgrade your account."
    )

    def has_permission(self, request, view):
        return can_export(request.user)
