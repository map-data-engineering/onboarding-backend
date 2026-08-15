"""
Short-lived signed links for CV downloads.

A browser following a plain `<a href>` sends no `Authorization` header, so the
standalone frontends cannot reach a header-authenticated endpoint by clicking a
link. Instead the staff-only detail endpoint mints a signature, and the download
view accepts it in place of credentials.

The signature carries the applicant id and is bound to it on the way back out,
so a link minted for one applicant cannot fetch another's file. It expires,
which the old public `/media/` URL never did.

Lives in its own module because both the serializer (which signs) and the view
(which verifies) need it, and importing one from the other would be circular.
"""

from django.core import signing

# Namespaced so a signature minted here cannot be replayed against another
# `signing` caller that happens to share SECRET_KEY.
CV_LINK_SALT = "application.cv-download"

# The URL *is* the credential once minted, so keep the window short. Long enough
# to click a button on a page you already have open; short enough that a link
# pasted into a chat is dead by the time anyone else opens it.
CV_LINK_MAX_AGE = 900  # seconds (15 minutes)


def sign_cv_link(application_id):
    """Return a signature authorising a download of this applicant's CV."""
    return signing.dumps(str(application_id), salt=CV_LINK_SALT)


def unsign_cv_link(signature, application_id):
    """
    Validate `signature` for `application_id`.

    Returns None when it is good, or a human-readable reason when it is not, so
    the caller decides which HTTP error to raise.
    """
    try:
        signed_id = signing.loads(signature, salt=CV_LINK_SALT, max_age=CV_LINK_MAX_AGE)
    except signing.SignatureExpired:
        return "This download link has expired. Reload the page and try again."
    except signing.BadSignature:
        return "Invalid download link."

    if str(signed_id) != str(application_id):
        return "This download link is for a different applicant."
    return None
