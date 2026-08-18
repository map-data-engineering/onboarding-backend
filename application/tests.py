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

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from application import assessment, countries, services, shortlist, validators
from application.checks import check_collected_static_is_current
from application.models import Application, Question

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


def make_question(category, index, seconds=45):
    """One throwaway question in `category`, distinct from every other."""
    return Question.objects.create(
        text=f"{category} scenario {index}?",
        category=category,
        options=["a", "b", "c", "d"],
        correct_answer="a",
        time_limit_seconds=seconds,
    )


def portal_settings(**overrides):
    """settings.PORTAL with a few keys replaced, for override_settings."""
    from django.conf import settings

    return {**settings.PORTAL, **overrides}


class QuestionDrawTests(TestCase):
    """
    The draw is what stops answers circulating: every applicant sits a different
    paper, but always one with the same shape.
    """

    QUOTA = {"R": 2, "SPATIAL": 3, "GENERAL": 1, "BAYESIAN": 1, "APPLICATION": 1}

    def setUp(self):
        for category in self.QUOTA:
            for index in range(5):
                make_question(category, index)

    def draw(self):
        with override_settings(PORTAL=portal_settings(QUOTA=self.QUOTA)):
            return services.draw_questions()

    def test_draw_honours_the_per_category_quota(self):
        drawn = self.draw()
        self.assertEqual(len(drawn), sum(self.QUOTA.values()))
        for category, wanted in self.QUOTA.items():
            self.assertEqual(sum(1 for q in drawn if q.category == category), wanted)

    def test_two_applicants_get_different_papers(self):
        """Not a guarantee for any single pair, but not the same paper ten times."""
        first = {q.pk for q in self.draw()}
        self.assertTrue(
            any({q.pk for q in self.draw()} != first for _ in range(10)),
            "ten draws produced the identical question set every time",
        )

    def test_retired_questions_are_never_drawn(self):
        Question.objects.filter(category="SPATIAL").update(is_active=False)
        drawn = self.draw()
        self.assertEqual(sum(1 for q in drawn if q.category == "SPATIAL"), 0)

    def test_a_short_category_is_topped_up_from_the_spares(self):
        """
        PASS_MARK is an absolute count, so a paper two questions shorter than
        intended would quietly raise the bar for whoever received it.
        """
        spatial = Question.objects.filter(category="SPATIAL")
        spatial.exclude(pk=spatial.first().pk).delete()
        drawn = self.draw()
        self.assertEqual(len(drawn), sum(self.QUOTA.values()))
        self.assertEqual(sum(1 for q in drawn if q.category == "SPATIAL"), 1)

    def test_quiz_shape_reports_what_the_applicant_is_told(self):
        make_question("R", 99, seconds=35)
        with override_settings(PORTAL=portal_settings(QUOTA=self.QUOTA)):
            shape = services.quiz_shape()
        self.assertEqual(shape["questions"], sum(self.QUOTA.values()))
        self.assertEqual(shape["seconds_min"], 35)
        self.assertEqual(shape["seconds_max"], 45)


class QuizTimingTests(TestCase):
    """
    The countdown the applicant watches and the deadline the server enforces have
    to be the same number. They were not: the page derived the remainder from the
    device clock, so a phone a few minutes fast auto-submitted every question blank
    (score zero, nothing on screen to explain it) and a phone a few minutes slow
    showed a long countdown and had every answer thrown away as late.
    """

    def setUp(self):
        from datetime import timedelta

        self.timedelta = timedelta
        for index in range(3):
            make_question("R", index, seconds=40)
        application = Application.objects.create(
            **APPLICANT, email="timing@example.org", gender="Female", institution="IHI",
            country_of_residence=countries.TANZANIA, nationality=countries.TANZANIA,
        )
        with override_settings(PORTAL=portal_settings(QUOTA={"R": 3})):
            self.session = services.build_session(application)

    def serve(self, seconds_ago=0):
        """Serve the current question, pretending it was served `seconds_ago`."""
        item = services.current_item(self.session)
        if seconds_ago:
            item.served_at = timezone.now() - self.timedelta(seconds=seconds_ago)
            item.save(update_fields=["served_at"])
        return item

    def test_an_unserved_question_offers_its_full_allowance(self):
        item = self.session.items.first()
        self.assertEqual(services.remaining_seconds(item), 40.0)

    def test_the_remainder_counts_down_from_when_it_was_served(self):
        item = self.serve(seconds_ago=10)
        self.assertAlmostEqual(services.remaining_seconds(item), 30.0, delta=1.0)

    def test_the_remainder_never_exceeds_the_limit(self):
        """A clock adjustment must not hand out more time than the question allows."""
        item = self.serve()
        item.served_at = timezone.now() + self.timedelta(minutes=5)
        item.save(update_fields=["served_at"])
        self.assertEqual(services.remaining_seconds(item), 40.0)

    def test_the_remainder_never_goes_negative(self):
        item = self.serve(seconds_ago=600)
        self.assertEqual(services.remaining_seconds(item), 0.0)

    def test_the_grace_is_not_advertised_as_extra_time(self):
        item = self.serve()
        self.assertLessEqual(services.remaining_seconds(item), 40.0)
        # ...but the server's own deadline does include it.
        self.assertGreater(
            (services._deadline(item) - item.served_at).total_seconds(), 40.0
        )

    def test_the_api_sends_the_remainder_with_every_question(self):
        self.serve(seconds_ago=5)
        payload = self.client.get(f"/api/quiz/{self.session.id}/current/").json()
        self.assertIn("remaining_seconds", payload)
        self.assertLessEqual(payload["remaining_seconds"], payload["time_limit_seconds"])
        self.assertGreater(payload["remaining_seconds"], 0)

    def test_an_answer_after_the_deadline_is_recorded_and_the_session_advances(self):
        """
        The auto-submit at zero arrives just after the deadline on a slow
        connection. It must move the applicant on, not strand them.
        """
        expired = self.serve(seconds_ago=600)
        response = self.client.post(
            f"/api/quiz/{self.session.id}/answer/",
            {"answer": ""},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["timed_out"])
        self.assertFalse(body["accepted"])
        self.assertIsNotNone(body["next"])       # the next question, with its own clock
        self.assertEqual(body["next"]["remaining_seconds"], 40.0)

        expired.refresh_from_db()
        self.assertTrue(expired.timed_out)
        self.assertFalse(expired.is_correct)

    def test_the_automatic_submission_with_nothing_selected_is_accepted(self):
        """
        The exact request the page sends at zero when no option was chosen. A
        CharField that refused blanks made this a 400, which is how an applicant
        ended up stuck on a question with a stopped clock.
        """
        item = self.serve()
        response = self.client.post(
            f"/api/quiz/{self.session.id}/answer/",
            {"answer": ""},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.json()["next"])

        item.refresh_from_db()
        # Recorded as unanswered rather than as a wrong answer, so the panel's
        # TIMEOUTS flag keeps meaning "questions left unanswered".
        self.assertTrue(item.timed_out)
        self.assertEqual(item.submitted_answer, "")
        self.assertFalse(item.is_correct)

    def test_an_omitted_answer_field_is_treated_the_same_way(self):
        self.serve()
        response = self.client.post(
            f"/api/quiz/{self.session.id}/answer/", {}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["timed_out"])

    def test_a_real_answer_in_time_is_still_graded(self):
        item = self.serve()
        response = self.client.post(
            f"/api/quiz/{self.session.id}/answer/",
            {"answer": item.question.correct_answer},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["accepted"])
        item.refresh_from_db()
        self.assertTrue(item.is_correct)
        self.assertFalse(item.timed_out)

    def test_abandoning_a_question_expires_only_that_one(self):
        """Coming back later loses the question they walked away from, not the rest."""
        abandoned = self.serve(seconds_ago=600)
        nxt = services.current_item(self.session)   # rolls past the expired one
        abandoned.refresh_from_db()
        self.assertTrue(abandoned.timed_out)
        self.assertEqual(nxt.position, abandoned.position + 1)
        self.assertAlmostEqual(services.remaining_seconds(nxt), 40.0, delta=1.0)


class PhoneValidationTests(SimpleTestCase):
    """A shortlisted applicant whose number cannot be dialled is no use to anyone."""

    def test_punctuation_is_accepted_and_the_value_is_kept_verbatim(self):
        for number in ("+255 712 345 678", "+44 (0)20 7946 0958", "+1-202-555-0173"):
            with self.subTest(number=number):
                self.assertEqual(validators.validate_phone(number), number)

    def test_a_local_number_is_rejected_with_the_reason(self):
        with self.assertRaises(ValidationError) as caught:
            validators.validate_phone("0712345678")
        self.assertIn("outside your country", str(caught.exception))

    def test_letters_and_impossible_lengths_are_rejected(self):
        for number in ("+255abc7123", "+1234", "+1234567890123456789"):
            with self.subTest(number=number):
                with self.assertRaises(ValidationError):
                    validators.validate_phone(number)


class PortalConfigTests(TestCase):
    """
    The applicant page renders nothing until this responds, so it has to hold the
    limits the API actually enforces -- that is the whole reason it exists.
    """

    def test_config_reports_the_enforced_limits_and_the_country_list(self):
        data = self.client.get("/api/config/").json()
        self.assertEqual(data["limits"]["cv_max_pages"], validators.CV_MAX_PAGES)
        self.assertEqual(data["limits"]["max_words"], validators.MAX_WORDS)
        self.assertEqual(
            data["limits"]["cv_max_mb"],
            round(validators.CV_MAX_BYTES / (1024 * 1024), 1),
        )
        pinned = data["countries"][0]["countries"]
        self.assertEqual(pinned[0], countries.TANZANIA)
        self.assertEqual(sum(len(g["countries"]) for g in data["countries"]), 195)

    def test_the_funding_gate_is_read_from_settings_not_captured_at_import(self):
        with override_settings(PORTAL=portal_settings(FUNDING_GATE=False)):
            self.assertFalse(self.client.get("/api/config/").json()["funding_gate"])
            # With the gate off the applicant continues, flagged, rather than stopping.
            self.assertEqual(
                assessment.eligibility_problem(
                    {"elig_funding": assessment.NO_FUNDING_ANSWER}
                ),
                "",
            )
        with override_settings(PORTAL=portal_settings(FUNDING_GATE=True)):
            self.assertNotEqual(
                assessment.eligibility_problem(
                    {"elig_funding": assessment.NO_FUNDING_ANSWER}
                ),
                "",
            )


# Fields every test applicant shares; the ones that matter per test are passed in.
APPLICANT = {
    "first_name": "A", "last_name": "Applicant", "phone": "+255712345678",
    "institution_type": "University", "role": "Analyst", "education": "MSc",
    "r_experience": "Intermediate", "bayesian_knowledge": "Beginner",
}


class CountryDropdownTests(TestCase):
    """
    Free text gave three spellings of Tanzania in one export, and the panel's
    Tanzania-based floor matches on the stored string.
    """

    def payload(self, **overrides):
        return {
            **APPLICANT,
            "email": "a@example.org",
            "gender": "Female",
            "institution": "IHI",
            "country_of_residence": countries.TANZANIA,
            "nationality": countries.TANZANIA,
            **overrides,
        }

    def test_a_country_off_the_list_is_rejected(self):
        response = self.client.post(
            "/api/applications/",
            self.payload(country_of_residence="United Republic of Tanzania"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("country_of_residence", response.json())

    def test_a_local_phone_number_is_rejected_by_the_api(self):
        response = self.client.post(
            "/api/applications/",
            self.payload(phone="0712345678"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json())

    def test_a_listed_country_is_accepted(self):
        response = self.client.post(
            "/api/applications/", self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201, response.content)


class ShortlistTests(TestCase):
    """
    Floors first, then merit -- and the floors are applied when cutting to the
    shortlist, not at the final 25, because a lopsided shortlist cannot be fixed
    afterwards.
    """

    def applicant(self, *, code=True, gender="Male", country="Kenya",
                  institution="Inst", claims=None, submitted=True, funding=None):
        """One application whose composite is driven by `code`/`claims`."""
        index = Application.objects.count()
        return Application.objects.create(
            **APPLICANT,
            email=f"a{index}@example.org",
            gender=gender,
            institution=institution,
            country_of_residence=country,
            nationality=country,
            elig_attend="Yes, all four days",
            elig_laptop="Yes",
            elig_data="Yes, I work with it now",
            elig_funding=funding or "My institution has agreed to cover it",
            exp_rfreq="Most weeks",
            exp_rself="Intermediate — I write my own analysis scripts",
            exp_bayes="Beginner",
            exp_glm="Yes, several times",
            exp_dtype="A mixture of these",
            exp_when="I have an analysis waiting for these methods now",
            exp_share="Yes, and I have a specific team in mind",
            exp_use="Yes, regularly",
            claims=claims if claims is not None else {"read.csv": "used"},
            written_code="library(sf)\npts <- st_read('x.gpkg')" if code else "",
            final_submitted_at=timezone.now() if submitted else None,
        )

    def build(self, **options):
        return shortlist.build_shortlist(Application.objects.all(), **options)

    def test_only_submitted_applications_are_ranked_by_default(self):
        self.applicant()
        self.applicant(submitted=False)
        self.assertEqual(len(self.build()["rows"]), 1)
        self.assertEqual(len(self.build(pool=shortlist.POOL_ALL)["rows"]), 2)

    def test_seats_are_capped_and_the_waitlist_takes_the_next_best(self):
        for _ in range(6):
            self.applicant()
        result = self.build(seats=2, waitlist=2, min_women=0, min_tanzania=0,
                            max_per_institution=99)
        self.assertEqual(sum(1 for r in result["rows"] if r["shortlisted"]), 2)
        self.assertEqual(sum(1 for r in result["rows"] if r["waitlisted"]), 2)
        # Ranks 1-2 hold the seats, 3-4 the waitlist: no overlap, in order.
        placed = [(r["rank"], r["shortlisted"], r["waitlisted"]) for r in result["rows"][:4]]
        self.assertEqual(placed, [(1, True, False), (2, True, False),
                                  (3, False, True), (4, False, True)])

    def test_the_women_floor_is_met_before_the_open_seats(self):
        # Three higher-scoring men, then two women scoring lower (no code sample).
        for _ in range(3):
            self.applicant(gender="Male")
        for _ in range(2):
            self.applicant(gender="Female", code=False)

        without = self.build(seats=3, min_women=0, min_tanzania=0, max_per_institution=99)
        self.assertEqual(
            sum(1 for r in without["rows"]
                if r["shortlisted"] and r["application"].gender == "Female"),
            0,
        )

        result = self.build(seats=3, min_women=2, min_tanzania=0, max_per_institution=99)
        self.assertTrue(result["floors"]["women_met"])
        self.assertEqual(result["floors"]["women"], 2)
        self.assertEqual(result["floors"]["shortlisted"], 3)

    def test_an_unmeetable_floor_is_reported_rather_than_faked(self):
        for _ in range(3):
            self.applicant(gender="Male")
        floors = self.build(seats=3, min_women=2, min_tanzania=0,
                            max_per_institution=99)["floors"]
        self.assertFalse(floors["women_met"])
        self.assertEqual(floors["women"], 0)

    def test_tanzania_floor_matches_legacy_free_text_spellings(self):
        self.applicant(country="Kenya")
        self.applicant(country="United Republic of Tanzania")
        floors = self.build(seats=2, min_women=0, min_tanzania=1,
                            max_per_institution=99)["floors"]
        self.assertTrue(floors["tanzania_met"])

    def test_the_institution_cap_limits_one_employer(self):
        for _ in range(4):
            self.applicant(institution="Same Institute")
        result = self.build(seats=4, min_women=0, min_tanzania=0, max_per_institution=2)
        self.assertEqual(result["floors"]["shortlisted"], 2)
        self.assertEqual(result["floors"]["largest_institution_count"], 2)

    def test_bluffers_are_excluded_by_default_and_kept_on_request(self):
        self.applicant(claims={"read.csv": "used", "st_reproject": "used"})
        self.assertEqual(self.build(seats=1)["floors"]["shortlisted"], 0)
        kept = self.build(seats=1, drop_bluff=False)
        self.assertEqual(kept["floors"]["shortlisted"], 1)
        self.assertIn("BLUFF", kept["rows"][0]["score"]["flags"])

    def test_prefer_confirmed_travel_fills_from_confirmed_applicants_first(self):
        # The unconfirmed applicant scores higher (code sample), so merit alone
        # would seat them.
        self.applicant(funding=assessment.UNCONFIRMED_TRAVEL_ANSWER, code=True)
        self.applicant(code=False)

        prefer = self.build(seats=1, min_women=0, min_tanzania=0,
                            max_per_institution=99, travel=shortlist.TRAVEL_PREFER)
        self.assertEqual(prefer["floors"]["travel_unconfirmed"], 0)

        ignore = self.build(seats=1, min_women=0, min_tanzania=0,
                            max_per_institution=99, travel=shortlist.TRAVEL_IGNORE)
        self.assertEqual(ignore["floors"]["travel_unconfirmed"], 1)

    def test_prefer_still_uses_unconfirmed_applicants_for_empty_seats(self):
        """The softer setting must not leave a seat unfilled to avoid a flag."""
        self.applicant(funding=assessment.UNCONFIRMED_TRAVEL_ANSWER)
        result = self.build(seats=2, min_women=0, min_tanzania=0,
                            travel=shortlist.TRAVEL_PREFER)
        self.assertEqual(result["floors"]["shortlisted"], 1)

    def test_confirmed_only_excludes_them_entirely(self):
        self.applicant(funding=assessment.UNCONFIRMED_TRAVEL_ANSWER)
        result = self.build(seats=2, min_women=0, min_tanzania=0,
                            travel=shortlist.TRAVEL_ONLY)
        self.assertEqual(result["floors"]["shortlisted"], 0)

    def test_the_ranking_is_stable_between_calls(self):
        for _ in range(5):
            self.applicant()
        first = [row["application"].pk for row in self.build()["rows"]]
        self.assertEqual(first, [row["application"].pk for row in self.build()["rows"]])


class ShortlistApiTests(TestCase):
    """The panel's builder and its CSV, including who may download it."""

    def setUp(self):
        from django.contrib.auth.models import User
        from rest_framework.authtoken.models import Token

        reviewer = User.objects.create_user(
            "reviewer", password="x", is_staff=True, is_superuser=True
        )
        self.token = Token.objects.create(user=reviewer).key
        Application.objects.create(
            **APPLICANT, email="one@example.org", gender="Female", institution="IHI",
            country_of_residence=countries.TANZANIA, nationality=countries.TANZANIA,
            claims={"read.csv": "used"}, written_code="library(sf)\nst_read('x')",
            final_submitted_at=timezone.now(),
        )

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token}"}

    def test_the_builder_ranks_and_marks_the_picks(self):
        response = self.client.post(
            "/api/admin/shortlist/",
            {"seats": 1, "min_women": 0, "min_tanzania": 0},
            content_type="application/json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["rows"][0]["rank"], 1)
        self.assertTrue(data["rows"][0]["shortlisted"])
        self.assertEqual(data["floors"]["shortlisted"], 1)

    def test_unparseable_controls_fall_back_to_the_defaults(self):
        response = self.client.post(
            "/api/admin/shortlist/",
            {"seats": "", "travel": "nonsense", "pool": "nope"},
            content_type="application/json",
            **self.auth(),
        )
        used = response.json()["settings"]
        self.assertEqual(used["seats"], shortlist.DEFAULTS["seats"])
        self.assertEqual(used["travel"], shortlist.DEFAULTS["travel"])
        self.assertEqual(used["pool"], shortlist.DEFAULTS["pool"])

    def test_the_csv_carries_the_rank_and_placement_columns(self):
        response = self.client.post(
            "/api/admin/shortlist/export/",
            {"seats": 1, "min_women": 0, "min_tanzania": 0, "only_shortlist": True},
            content_type="application/json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        lines = body.splitlines()
        self.assertTrue(lines[0].startswith("Rank,Shortlisted,Waitlisted,"))
        self.assertTrue(lines[1].startswith("1,Yes,,"))

    def _staff_header(self, username, *, viewer=False):
        from django.contrib.auth.models import Group, User
        from rest_framework.authtoken.models import Token

        user = User.objects.create_user(username, password="x", is_staff=True)
        if viewer:
            group, _ = Group.objects.get_or_create(name="Applicant viewers")
            user.groups.add(group)
        return {"HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=user).key}"}

    def test_the_shortlist_and_its_csv_are_superuser_only(self):
        """
        A staff login is not a licence to run the selection.

        A reviewer reads applications and can export them; the ranking with the cut
        line drawn stays with the superuser accounts. Both other tiers get a 403
        with a reason, not a 404.
        """
        for label, header in (
            ("reviewer", self._staff_header("plain_reviewer")),
            ("viewer", self._staff_header("plain_viewer", viewer=True)),
        ):
            with self.subTest(role=label):
                for path in ("/api/admin/shortlist/", "/api/admin/shortlist/export/"):
                    response = self.client.post(
                        path, {}, content_type="application/json", **header
                    )
                    self.assertEqual(response.status_code, 403, (path, response.content))
                    self.assertIn("superuser", response.json()["detail"])
                # GET on the builder is the panel's "open the view" call, and it is
                # refused too -- otherwise the restriction is one URL wide.
                self.assertEqual(
                    self.client.get("/api/admin/shortlist/", **header).status_code, 403
                )

    def test_a_reviewer_can_export_the_applicant_csv(self):
        """
        The export is a reviewer action: it is the data they already read.

        Gating it would not keep anything in -- a reviewer can read every field in
        the panel -- it would only make them do it 500 times through a web page.
        """
        response = self.client.get(
            "/api/admin/applications/export/", **self._staff_header("csv_reviewer")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        # It streams, so the rows arrive as chunks rather than `.content`.
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        self.assertIn("one@example.org", body)

    def test_a_viewer_still_cannot_export(self):
        """
        The one tier the file is withheld from.

        A viewer exists to change nothing; handing that account the whole applicant
        table in one file is the case where the file is the entire point. They keep
        the list, which is what they are for.
        """
        header = self._staff_header("csv_viewer", viewer=True)
        response = self.client.get("/api/admin/applications/export/", **header)
        self.assertEqual(response.status_code, 403)
        self.assertIn("view-only", response.json()["detail"])
        self.assertEqual(
            self.client.get("/api/admin/applications/", **header).status_code, 200
        )

    def test_a_superuser_can_still_rank_and_export(self):
        self.assertEqual(
            self.client.post("/api/admin/shortlist/", {},
                             content_type="application/json", **self.auth()).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/admin/applications/export/", **self.auth()).status_code,
            200,
        )

    def test_the_panel_is_told_which_controls_to_hide(self):
        """The `can_*` flags drive the buttons; the endpoints enforce the same rules."""
        superuser = self.client.get("/api/admin/me/", **self.auth()).json()
        self.assertTrue(superuser["can_export"])
        self.assertTrue(superuser["can_shortlist"])
        self.assertTrue(superuser["can_delete"])

        reviewer = self.client.get(
            "/api/admin/me/", **self._staff_header("flags_reviewer")
        ).json()
        self.assertTrue(reviewer["can_review"])       # decisions, bulk decisions
        self.assertTrue(reviewer["can_export"])       # the CSV is theirs now
        self.assertFalse(reviewer["can_delete"])      # the one destructive verb
        self.assertFalse(reviewer["can_shortlist"])

        viewer = self.client.get(
            "/api/admin/me/", **self._staff_header("flags_viewer", viewer=True)
        ).json()
        self.assertEqual(viewer["role"], "viewer")
        for flag in ("can_review", "can_export", "can_delete", "can_shortlist"):
            self.assertFalse(viewer[flag], flag)


class DeleteRestrictionTests(TestCase):
    """
    Deleting an applicant is superuser-only, and the record must survive a refusal.

    A wrong decision is an edit; a wrong delete is an applicant who looks exactly
    like someone who never applied, discovered in the week offers go out. So a
    reviewer can do everything else and not this -- and the test that matters is
    not the status code but that the row is still there afterwards.
    """

    def setUp(self):
        from django.contrib.auth.models import Group, User
        from rest_framework.authtoken.models import Token

        self.application = Application.objects.create(
            **APPLICANT, email="keepme@example.org",
            country_of_residence=countries.TANZANIA, nationality=countries.TANZANIA,
        )
        self.url = f"/api/admin/applications/{self.application.pk}/"

        def header(username, **flags):
            viewer = flags.pop("viewer", False)
            user = User.objects.create_user(username, password="x", is_staff=True, **flags)
            if viewer:
                group, _ = Group.objects.get_or_create(name="Applicant viewers")
                user.groups.add(group)
            return {"HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=user).key}"}

        self.superuser = header("boss", is_superuser=True)
        self.reviewer = header("hands")
        self.viewer = header("eyes", viewer=True)

    def test_a_reviewer_cannot_delete_an_applicant(self):
        response = self.client.delete(self.url, **self.reviewer)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("superuser", response.json()["detail"])
        self.assertTrue(Application.objects.filter(pk=self.application.pk).exists())

    def test_a_viewer_cannot_delete_an_applicant(self):
        self.assertEqual(self.client.delete(self.url, **self.viewer).status_code, 403)
        self.assertTrue(Application.objects.filter(pk=self.application.pk).exists())

    def test_a_reviewer_can_still_set_a_decision(self):
        """The restriction is on deleting, not on reviewing -- PATCH is untouched."""
        response = self.client.patch(
            self.url, {"decision": "SELECTED"},
            content_type="application/json", **self.reviewer,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.application.refresh_from_db()
        self.assertEqual(self.application.decision, "SELECTED")

    def test_a_superuser_can_delete(self):
        self.assertEqual(self.client.delete(self.url, **self.superuser).status_code, 204)
        self.assertFalse(Application.objects.filter(pk=self.application.pk).exists())

    def test_bulk_delete_is_refused_for_a_reviewer_but_bulk_decisions_are_not(self):
        """
        Bulk is where a mistaken delete does the most damage, so it gets the same
        rule -- and it must not be a back door around the single-record check.
        """
        body = {"ids": [str(self.application.pk)], "action": "delete"}
        response = self.client.post(
            "/api/admin/applications/bulk/", body,
            content_type="application/json", **self.reviewer,
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertTrue(Application.objects.filter(pk=self.application.pk).exists())

        response = self.client.post(
            "/api/admin/applications/bulk/",
            {"ids": [str(self.application.pk)], "action": "reject"},
            content_type="application/json", **self.reviewer,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 1)

    def test_bulk_delete_works_for_a_superuser(self):
        response = self.client.post(
            "/api/admin/applications/bulk/",
            {"ids": [str(self.application.pk)], "action": "delete"},
            content_type="application/json", **self.superuser,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["deleted"], 1)
        self.assertFalse(Application.objects.filter(pk=self.application.pk).exists())

    def test_the_django_admin_will_not_delete_for_a_non_superuser_either(self):
        """
        The back door must not be wider than the front one.

        Django grants admin deletion from the `delete_application` model
        permission, so a reviewer handed "all application permissions" in the group
        editor would get in `/admin/` exactly what the panel refuses them -- next to
        a bulk delete action over a whole filtered page.
        """
        from django.contrib.admin.sites import site
        from django.contrib.auth.models import Permission, User
        from django.test import RequestFactory

        admin_instance = site._registry[Application]
        request = RequestFactory().get("/admin/")

        reviewer = User.objects.get(username="hands")
        reviewer.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="application")
        )
        request.user = User.objects.get(pk=reviewer.pk)     # re-read: permissions are cached
        self.assertFalse(admin_instance.has_delete_permission(request))
        self.assertNotIn("delete_selected", admin_instance.get_actions(request))

        request.user = User.objects.get(username="boss")
        self.assertTrue(admin_instance.has_delete_permission(request))
