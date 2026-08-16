"""
A system check for the failure mode that keeps costing us an afternoon.

Templates are read from the app directory on every request, but WhiteNoise
serves JavaScript and CSS out of STATIC_ROOT -- the snapshot `collectstatic`
took. Skip that step during a deploy and the two drift apart: the panel renders
the new markup, including buttons for features whose code is not in the JS being
served, and clicking them does nothing at all. No error, no console message,
nothing in the log. It has happened to the CV download and again to the CSV
export.

`manage.py check` (which `runserver` runs on start) now says so plainly, listing
the files that differ, so the problem surfaces before a deploy rather than as a
button that quietly does nothing afterwards.
"""

import hashlib
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.checks import Warning, register

# Only the assets a browser executes. A stale image is cosmetic; stale JS is the
# bug this check exists to catch.
WATCHED_SUFFIXES = (".js", ".css")


def _digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _app_static_dirs():
    """
    Static directories belonging to this project -- not to its dependencies.

    Third-party packages are deliberately out of scope. collectstatic decides
    what to copy by modification time, and a wheel installed with preserved
    mtimes can leave django.contrib.admin's CSS differing from the collected
    copy no matter how many times you run it. Reporting that would make this
    warning permanent, and a warning nobody can clear is a warning everybody
    learns to scroll past -- which is precisely the habit that let the stale
    panel.js through.
    """
    base = Path(settings.BASE_DIR).resolve()
    dirs = [Path(d) for d in getattr(settings, "STATICFILES_DIRS", [])]
    for app_config in apps.get_app_configs():
        candidate = Path(app_config.path) / "static"
        if not candidate.is_dir():
            continue
        try:
            candidate.resolve().relative_to(base)
        except ValueError:
            continue  # installed elsewhere, e.g. site-packages
        dirs.append(candidate)
    return dirs


def _stale_compressed_siblings(collected, name):
    """
    Report .gz/.br copies whose contents no longer match `collected`.

    Checking the plain file alone is not enough, and assuming otherwise is what
    hid this for months: WhiteNoise prefers the compressed sibling for any
    request advertising gzip or brotli, so a current panel.js and a stale
    panel.js.gz means curl sees the fix and every browser sees the old code.
    """
    import gzip

    problems = []
    expected = _digest(collected)

    gz = collected.with_suffix(collected.suffix + ".gz")
    if gz.exists():
        try:
            if hashlib.sha256(gzip.decompress(gz.read_bytes())).hexdigest() != expected:
                problems.append(f"{name}.gz (compressed copy is out of date)")
        except (OSError, gzip.BadGzipFile):
            problems.append(f"{name}.gz (unreadable)")

    br = collected.with_suffix(collected.suffix + ".br")
    if br.exists():
        try:
            import brotli

            if hashlib.sha256(brotli.decompress(br.read_bytes())).hexdigest() != expected:
                problems.append(f"{name}.br (compressed copy is out of date)")
        except ImportError:
            # No brotli library available to verify with. Fall back to mtime,
            # which is coarse but still catches a sibling left behind by an
            # older collectstatic.
            if br.stat().st_mtime + 1 < collected.stat().st_mtime:
                problems.append(f"{name}.br (older than the file it compresses)")
        except OSError:
            problems.append(f"{name}.br (unreadable)")

    return problems


@register()
def check_collected_static_is_current(app_configs, **kwargs):
    """Warn when STATIC_ROOT holds a different version of a JS/CSS file than the source."""
    static_root = getattr(settings, "STATIC_ROOT", None)
    if not static_root:
        return []
    root = Path(static_root)
    if not root.is_dir():
        # Nobody has run collectstatic yet. That is the normal state of a fresh
        # checkout and WhiteNoise is not serving from it, so there is nothing to
        # be stale against.
        return []

    stale = []
    for source_dir in _app_static_dirs():
        for source in source_dir.rglob("*"):
            if not source.is_file() or source.suffix.lower() not in WATCHED_SUFFIXES:
                continue
            name = source.relative_to(source_dir).as_posix()
            collected = root / source.relative_to(source_dir)
            if not collected.exists():
                stale.append(f"{name} (never collected)")
                continue
            if _digest(source) != _digest(collected):
                stale.append(name)
                continue
            stale.extend(_stale_compressed_siblings(collected, name))

    if not stale:
        return []

    listed = ", ".join(sorted(stale)[:10])
    if len(stale) > 10:
        listed += f", and {len(stale) - 10} more"
    return [
        Warning(
            "STATIC_ROOT is out of date with the app's static files: " + listed,
            hint=(
                "Run `python manage.py collectstatic --noinput` and reload the app. "
                "Until you do, WhiteNoise serves the older copy whenever DEBUG is off "
                "-- including the .gz it hands to every browser -- so newly added "
                "buttons can render with none of their JavaScript behind them."
            ),
            id="application.W001",
        )
    ]
