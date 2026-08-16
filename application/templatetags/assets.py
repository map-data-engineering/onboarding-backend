"""
`{% static_v 'js/panel.js' %}` -- a static URL with a content fingerprint.

Filenames here are unhashed on purpose (see the STORAGES note in settings: the
Manifest storage backend was switched off because it aborts collectstatic on a
missing CSS reference). The cost of that is browsers happily serving a cached
copy of panel.js for as long as WhiteNoise's max-age allows, which is how a
deploy can leave a button on screen with none of its JavaScript behind it --
the template is read fresh from disk every request, the script is not.

Appending ?v=<hash of the bytes actually being served> makes the URL change
whenever the file does, so the cache is bypassed exactly when it needs to be and
used the rest of the time. Hashes are computed once per file and remembered;
`collectstatic` is followed by a reload in every deployment path we support, so
there is no need to re-stat on each render.

This closes the browser-cache half of asset staleness. The other half -- a
STATIC_ROOT that collectstatic never refreshed -- is caught by
`application.checks.check_collected_static_is_current`.
"""

import hashlib
from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static

register = template.Library()

_fingerprints = {}


def _served_file(path):
    """
    The file a browser will actually receive for `path`, or None.

    In production that is the collected copy under STATIC_ROOT, which is what
    WhiteNoise serves. With DEBUG on, runserver's staticfiles handler serves the
    app's own copy instead, so prefer the finders' answer there -- fingerprinting
    a stale collected file would pin the browser to content it is not being sent.
    """
    found = finders.find(path)
    if found:
        return Path(found)
    try:
        return Path(staticfiles_storage.path(path))
    except (NotImplementedError, ValueError):
        return None


def fingerprint(path):
    """Short content hash for a static file, or "" if it cannot be read."""
    if path not in _fingerprints:
        candidate = _served_file(path)
        try:
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()[:8]
        except (OSError, AttributeError):
            # Missing file: fall back to an unversioned URL rather than breaking
            # the page. The static tag itself will still render the right path.
            digest = ""
        _fingerprints[path] = digest
    return _fingerprints[path]


@register.simple_tag
def static_v(path):
    url = static(path)
    digest = fingerprint(path)
    return f"{url}?v={digest}" if digest else url
