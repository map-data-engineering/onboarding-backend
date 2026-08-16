"""
Regression tests for the static-staleness check.

The bug these guard against had no visible symptom: STATIC_ROOT held a copy of
panel.js from months earlier, templates rendered the current markup on top of
it, and the Export CSV button simply did nothing when clicked. Nothing was
logged and `curl` reported the file as correct, because curl does not ask for
gzip and WhiteNoise only substitutes the stale .gz for clients that do.
"""

import gzip
import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

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
