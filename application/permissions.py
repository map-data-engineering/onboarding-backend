"""
Three tiers of staff access for the admin panel.

* **Superuser** — everything, and the only tier that can **delete an applicant**
  or run the **shortlist builder**. This is what `createsuperuser` gives you.
* **Reviewer** — any other staff account: browse applicants, read the written
  answers and CVs, change decisions, run bulk decisions, export the CSV, move the
  deadline. Cannot delete, and cannot see the shortlist.
* **Viewer** — staff, but read-only: the applicant list, counts, details and quiz
  breakdowns, and nothing else. No decisions, no bulk actions, no deletes, no
  export.

What sits at the superuser tier is what cannot be walked back:

  * A **delete** takes an application, its CV and its quiz out of the database for
    good, and an applicant who was deleted by mistake looks exactly like one who
    never applied. Every other reviewer action is a field you can set back --
    a wrong decision is an edit, a wrong delete is a support email during the week
    offers go out. So it is the one destructive verb the reviewer tier does not
    get; a reviewer who believes a record should go says so, and a superuser does
    it.
  * The **shortlist** is the selection itself: a ranking with the cut line drawn
    and the diversity floors applied. Circulating it before the panel has met
    turns "who should we read closely?" into "who is in", and the people best
    placed to argue with a ranking are the ones who never see it as provisional.

**Exporting is a reviewer action.** A CSV is a real disclosure -- the filtered
applicant table, names and emails and free text, on somebody's laptop and outside
every check in this file -- but it is the disclosure a reviewer already has by
reading the panel, in a form they can work in. Gating it does not keep the data
in; it just makes reviewers read 500 applications through a web page. Viewers stay
out of it: handing the whole database to an account whose defining property is
that it changes nothing is the case where the file really is the whole point.

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
    True for reviewers and superusers: the applicant CSV.

    Same rule as `can_review`, and that is the point -- an export is the data a
    reviewer already reads, in a form they can sort and filter. Viewers are
    excluded: an account that exists to change nothing has no use for the whole
    table in one file.
    """
    return can_review(user)


def can_delete(user):
    """
    True only for superusers: removing an applicant record.

    The one destructive action in the panel, and the only one no other field can
    undo -- see the tier notes at the top of this module.
    """
    return bool(user and user.is_authenticated and user.is_staff and user.is_superuser)


def can_shortlist(user):
    """True only for superusers: building or exporting the ranking."""
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
    """Reviewers and superusers. Guards the applicant CSV."""

    message = "Your account has view-only access, which does not include the CSV export."

    def has_permission(self, request, view):
        return can_export(request.user)


class CanDeleteApplicants(BasePermission):
    """
    Superusers only. Guards deleting applicant records, one or in bulk.

    The panel hides the delete controls for everyone else, but that is
    presentation: this is the check a hand-made request runs into.
    """

    message = (
        "Deleting applicants is restricted to superuser accounts. "
        "Ask an administrator to remove the record."
    )

    def has_permission(self, request, view):
        return can_delete(request.user)


class CanBuildShortlist(BasePermission):
    """Superusers only. Guards the shortlist builder and its CSV."""

    message = (
        "The shortlist is restricted to superuser accounts. "
        "Ask an administrator to run it, or to upgrade your account."
    )

    def has_permission(self, request, view):
        return can_shortlist(request.user)
