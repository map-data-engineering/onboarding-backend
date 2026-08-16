"""
Regression tests for the static-staleness check.

The bug these guard against had no visible symptom: STATIC_ROOT held a copy of
panel.js from months earlier, templates rendered the current markup on top of
it, and the Export CSV button simply did nothing when clicked. Nothing was
logged and `curl` reported the file as correct, because curl does not ask for
gzip and WhiteNoise only substitutes the stale .gz for clients that do.
"""

import gzip
import re
import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from application.checks import check_collected_static_is_current

CURRENT = b"console.log('current');\n"
OUTDATED = b"console.log('outdated');\n"


class StaticFreshnessCheckTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source_dir = self.tmp / "src"
        self.static_root = self.tmp / "collected"
        (self.source_dir / "js").mkdir(parents=True)
        (self.static_root / "js").mkdir(parents=True)
        self.source = self.source_dir / "js" / "panel.js"
        self.collected = self.static_root / "js" / "panel.js"
        self.source.write_bytes(CURRENT)

    def run_check(self):
        with override_settings(
            STATIC_ROOT=str(self.static_root),
            STATICFILES_DIRS=[str(self.source_dir)],
            BASE_DIR=str(self.tmp),
        ):
            return check_collected_static_is_current(None)

    def ids(self, warnings):
        return [w.id for w in warnings]

    def test_matching_copies_are_silent(self):
        self.collected.write_bytes(CURRENT)
        self.assertEqual(self.run_check(), [])

    def test_outdated_collected_copy_is_reported(self):
        self.collected.write_bytes(OUTDATED)
        warnings = self.run_check()
        self.assertEqual(self.ids(warnings), ["application.W001"])
        self.assertIn("js/panel.js", warnings[0].msg)

    def test_uncollected_file_is_reported(self):
        warnings = self.run_check()
        self.assertEqual(self.ids(warnings), ["application.W001"])
        self.assertIn("never collected", warnings[0].msg)

    def test_outdated_gzip_is_reported_even_when_plain_file_matches(self):
        """The actual production failure: fresh panel.js, months-old panel.js.gz."""
        self.collected.write_bytes(CURRENT)
        self.collected.with_suffix(".js.gz").write_bytes(gzip.compress(OUTDATED))
        warnings = self.run_check()
        self.assertEqual(self.ids(warnings), ["application.W001"])
        self.assertIn("panel.js.gz", warnings[0].msg)

    def test_matching_gzip_is_silent(self):
        self.collected.write_bytes(CURRENT)
        self.collected.with_suffix(".js.gz").write_bytes(gzip.compress(CURRENT))
        self.assertEqual(self.run_check(), [])

    def test_missing_static_root_is_not_an_error(self):
        """A fresh checkout has never run collectstatic; nothing is being served yet."""
        shutil.rmtree(self.static_root)
        self.assertEqual(self.run_check(), [])

    def test_non_executable_assets_are_ignored(self):
        (self.source_dir / "img").mkdir()
        (self.source_dir / "img" / "logo.png").write_bytes(b"not-really-a-png")
        self.collected.write_bytes(CURRENT)
        self.assertEqual(self.run_check(), [])


class CsrfTokenMetaTests(TestCase):
    """
    Every page must expose a usable CSRF token to api.js.

    Without it the panel sent an empty X-CSRFToken header, and Django rejected
    that as "CSRF token ... has incorrect length" -- but only for staff who also
    had a Django session, since DRF's SessionAuthentication is what enforces CSRF.
    A clean browser signed in fine, which is exactly why this survived testing.
    """

    PAGES = {"applicant portal": "/", "staff panel": "/panel/"}

    def test_pages_expose_a_valid_csrf_token(self):
        for label, url in self.PAGES.items():
            with self.subTest(page=label):
                html = self.client.get(url).content.decode()
                match = re.search(r'<meta name="csrf-token" content="([^"]*)"', html)
                self.assertIsNotNone(match, f"{label} has no csrf-token meta tag")
                token = match.group(1)
                # Django rejects anything that is not CSRF_TOKEN_LENGTH characters.
                self.assertEqual(len(token), 64, f"{label} rendered a {len(token)}-char token")
                self.assertRegex(token, r"^[A-Za-z0-9]+$")

    def test_template_comments_do_not_leak_into_the_markup(self):
        """A multi-line {# #} renders literally; {% comment %} is required."""
        for label, url in self.PAGES.items():
            with self.subTest(page=label):
                html = self.client.get(url).content.decode()
                self.assertNotIn("{#", html)
                self.assertNotIn("SessionAuthentication", html)
