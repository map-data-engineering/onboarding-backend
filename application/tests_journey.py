"""
The deadline, the order of the journey, and the score as a grade rather than a gate.

A separate module from tests.py, which covers the static-asset check, the draw, the
quiz clock and the shortlist. The helpers are shared rather than copied — a second
definition of APPLICANT would drift from the first.

Each class below pins down something that previously cost the panel information:

  * The deadline was a string in settings.PORTAL, so moving it meant a redeploy and
    nothing enforced it — the portal kept accepting applications after the date it
    was displaying. It is now one row staff edit from the panel, read both by the
    applicant page and by the endpoints that accept applications.
  * "Your work" (written answers, motivation, CV) came *after* the knowledge check
    and was unlocked only by a passing score, so for everyone below the benchmark
    the panel had a bare number and nothing to read.
  * That benchmark is still computed, still flagged and still filterable. It simply
    no longer decides who may apply.
"""

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from application import assessment, countries, services, shortlist
from application.models import Application, PortalSettings, Question
from application.tests import APPLICANT, make_question, portal_settings


def one_page_pdf(name="cv.pdf"):
    """A real, parseable, single-page PDF — validators.validate_cv reads the bytes."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")


WRITTEN_PAYLOAD = {
    "written_dataset": (
        "Facility monthly malaria counts for 42 districts, 2018-2023, one row per "
        "district-month, with district names rather than coordinates."
    ),
    "written_code": "library(sf)\npts <- st_read('clinics.gpkg')\nplot(st_geometry(pts))",
    "written_why_not_ols": "The counts are overdispersed and spatially correlated.",
    "written_other": "",
    "motivation": "I want to fit spatial models to our own surveillance data.",
    "expectations": "A workflow I can rerun on next quarter's data.",
}


def applicant(**overrides):
    """One saved application, far enough through the journey to reach the work step."""
    fields = {
        "email": "order@example.org",
        "gender": "Female",
        "institution": "IHI",
        "country_of_residence": countries.TANZANIA,
        "nationality": countries.TANZANIA,
        "elig_attend": "Yes, all four days",
        "exp_rfreq": "Most weeks",
        "claims": {"read.csv": "used"},
        **overrides,
    }
    return Application.objects.create(**APPLICANT, **fields)


class DeadlineTests(TestCase):
    """The deadline staff set in the panel is the one the API enforces."""

    def payload(self, **overrides):
        return {
            **APPLICANT,
            "email": "deadline@example.org",
            "gender": "Female",
            "institution": "IHI",
            "country_of_residence": countries.TANZANIA,
            "nationality": countries.TANZANIA,
            **overrides,
        }

    def set_deadline(self, deadline):
        portal = PortalSettings.load()
        portal.application_deadline = deadline
        portal.save()
        return portal

    def test_a_fresh_install_closes_on_30_august_2026(self):
        portal = PortalSettings.load()
        self.assertEqual(portal.application_deadline, date(2026, 8, 30))
        self.assertEqual(portal.deadline_display, "Sunday 30 August 2026")

    def test_the_row_stays_a_singleton(self):
        """Two rows would mean two answers to "when does this close?"."""
        PortalSettings.load()
        PortalSettings(application_deadline=date(2030, 1, 1)).save()
        self.assertEqual(PortalSettings.objects.count(), 1)
        self.assertEqual(PortalSettings.load().application_deadline, date(2030, 1, 1))

    def test_config_publishes_the_deadline_and_whether_intake_is_open(self):
        wanted = timezone.localdate() + timedelta(days=1)
        self.set_deadline(wanted)
        data = self.client.get("/api/config/").json()
        self.assertTrue(data["applications_open"])
        self.assertEqual(data["deadline_date"], wanted.isoformat())
        # The page prints `deadline` verbatim, so it has to be the sentence, not a date.
        self.assertEqual(data["deadline"], PortalSettings.load().deadline_display)

    def test_the_deadline_day_itself_is_still_open(self):
        """Advertised as a day, so it lasts all day instead of expiring at midnight."""
        self.set_deadline(timezone.localdate())
        self.assertTrue(self.client.get("/api/config/").json()["applications_open"])
        response = self.client.post(
            "/api/applications/", self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_new_application_is_refused_the_day_after(self):
        self.set_deadline(timezone.localdate() - timedelta(days=1))
        response = self.client.post(
            "/api/applications/", self.payload(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("closed", response.json()["detail"])
        self.assertFalse(self.client.get("/api/config/").json()["applications_open"])
        self.assertEqual(Application.objects.count(), 0)

    def test_a_late_submission_of_the_work_step_is_refused_too(self):
        """Closing intake has to stop the CV upload, not only new records."""
        application = applicant(email="late@example.org")
        self.set_deadline(timezone.localdate() - timedelta(days=1))
        response = self.client.post(
            f"/api/applications/{application.id}/finalize/",
            {**WRITTEN_PAYLOAD, "cv": one_page_pdf()},
        )
        self.assertEqual(response.status_code, 403, response.content)
        application.refresh_from_db()
        self.assertIsNone(application.final_submitted_at)


class DeadlineAdminApiTests(TestCase):
    """Moving the deadline is a panel action, and a reviewers-only one."""

    def setUp(self):
        from django.contrib.auth.models import Group, User
        from rest_framework.authtoken.models import Token

        reviewer = User.objects.create_user("reviewer", password="x", is_staff=True)
        self.reviewer = {
            "HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=reviewer).key}"
        }

        viewer = User.objects.create_user("viewer", password="x", is_staff=True)
        group, _ = Group.objects.get_or_create(name="Applicant viewers")
        viewer.groups.add(group)
        self.viewer = {
            "HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=viewer).key}"
        }

    def patch(self, deadline, **headers):
        return self.client.patch(
            "/api/admin/settings/",
            {"application_deadline": deadline},
            content_type="application/json",
            **headers,
        )

    def test_a_reviewer_moves_the_deadline_and_the_portal_follows(self):
        wanted = (timezone.localdate() + timedelta(days=30)).isoformat()
        response = self.patch(wanted, **self.reviewer)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["application_deadline"], wanted)
        self.assertTrue(response.json()["applications_open"])
        # The applicant page reads the same row, so the two cannot disagree.
        self.assertEqual(self.client.get("/api/config/").json()["deadline_date"], wanted)

    def test_a_malformed_date_is_rejected_rather_than_stored(self):
        for bad in ("next Tuesday", "2026-13-40", "", "30/08/2026"):
            with self.subTest(value=bad):
                response = self.patch(bad, **self.reviewer)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("application_deadline", response.json())
        self.assertEqual(PortalSettings.load().application_deadline, date(2026, 8, 30))

    def test_a_past_date_is_accepted_so_a_round_can_be_closed_early(self):
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.patch(yesterday, **self.reviewer)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["applications_open"])

    def test_a_viewer_can_read_the_deadline_but_not_move_it(self):
        self.assertEqual(
            self.client.get("/api/admin/settings/", **self.viewer).status_code, 200
        )
        self.assertEqual(self.patch("2027-01-01", **self.viewer).status_code, 403)
        self.assertEqual(PortalSettings.load().application_deadline, date(2026, 8, 30))

    def test_the_settings_are_staff_only(self):
        self.assertEqual(self.client.get("/api/admin/settings/").status_code, 401)


class JourneyOrderTests(TestCase):
    """
    The work step comes before the knowledge check, and the score gates nothing.

    Both halves matter. If the quiz could be started first, an applicant would meet
    a countdown before being asked for the CV they were told to have ready; if the
    score still gated the work step, everyone below the benchmark would again leave
    nothing but a number behind.
    """

    QUOTA = {"R": 4}

    def setUp(self):
        for index in range(4):
            make_question("R", index, seconds=30)
        self.application = applicant()

    def submit_work(self):
        response = self.client.post(
            f"/api/applications/{self.application.id}/finalize/",
            {**WRITTEN_PAYLOAD, "cv": one_page_pdf()},
        )
        self.application.refresh_from_db()
        if self.application.cv:
            self.addCleanup(self.application.cv.delete, save=False)
        return response

    def start_quiz(self):
        with override_settings(PORTAL=portal_settings(QUOTA=self.QUOTA)):
            return self.client.post(
                f"/api/applications/{self.application.id}/quiz/start/"
            )

    def sit_quiz(self, correct):
        """Answer the whole paper, getting `correct` of the questions right."""
        with override_settings(PORTAL=portal_settings(QUOTA=self.QUOTA)):
            self.start_quiz()
            session = Application.objects.get(pk=self.application.pk).quiz
            for index, item in enumerate(session.items.all()):
                self.client.post(
                    f"/api/quiz/{session.id}/answer/",
                    {"answer": item.question.correct_answer if index < correct else "b"},
                    content_type="application/json",
                )
        session.refresh_from_db()
        return session

    def test_the_work_step_no_longer_needs_a_quiz_at_all(self):
        response = self.submit_work()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(self.application.final_submitted_at)
        self.assertTrue(self.application.cv)

    def test_the_quiz_cannot_be_started_before_the_work_is_submitted(self):
        response = self.start_quiz()
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("own work", response.json()["detail"])
        self.assertFalse(hasattr(self.application, "quiz"))

    def test_submitting_the_work_unlocks_the_quiz(self):
        self.submit_work()
        response = self.start_quiz()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["question"]["time_limit_seconds"], 30)

    def test_the_earlier_steps_are_still_required_first(self):
        self.application.claims = {}
        self.application.save(update_fields=["claims"])
        self.assertEqual(self.submit_work().status_code, 403)

    def test_an_ineligible_applicant_cannot_submit_work(self):
        self.application.ineligible_reason = "Cannot attend the full period."
        self.application.save(update_fields=["ineligible_reason"])
        self.assertEqual(self.submit_work().status_code, 403)

    def test_the_work_step_cannot_be_submitted_twice(self):
        self.submit_work()
        # Re-submitting would rewrite the answers of someone already sitting the quiz.
        self.assertEqual(self.submit_work().status_code, 400)

    def test_a_score_below_the_benchmark_keeps_the_application_and_the_grade(self):
        """
        The change this locks in: a low score no longer discards the application,
        but it is still graded, still flagged, and still filterable in the panel.
        """
        self.submit_work()
        session = self.sit_quiz(correct=1)

        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.final_submitted_at)            # kept
        self.assertEqual(self.application.status, Application.Status.FAIL)   # and graded
        self.assertFalse(services.has_passed(session))
        self.assertIn("BELOW-PASS", assessment.compute_flags(self.application))
        # Still in the panel's default (submitted) pool, to be judged on the
        # composite rather than dropped on the quiz alone.
        rows = shortlist.build_shortlist(Application.objects.all())["rows"]
        self.assertEqual(len(rows), 1)

    def test_the_result_payload_still_reports_the_grade(self):
        """
        The grade survives the gate's removal: score, total, benchmark, verdict.

        Asserted against `PASS_MARK` rather than a literal -- the benchmark is a
        panel decision that moves between rounds, and a test that pins the number
        turns changing it into a test failure instead of a policy change.
        """
        from application.models import PASS_MARK

        self.submit_work()
        session = self.sit_quiz(correct=4)
        result = self.client.get(f"/api/quiz/{session.id}/result/").json()
        self.assertEqual(result["score"], 4)
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["pass_mark"], PASS_MARK)
        # 4 correct out of the 4 drawn here, against a benchmark set over the full
        # 14-question paper, so this is a fail however the mark is set.
        self.assertGreater(PASS_MARK, 4)
        self.assertFalse(result["passed"])
        self.assertTrue(result["final_submitted"])

    def test_status_reports_the_work_step_so_a_reload_resumes_after_it(self):
        state = self.client.get(f"/api/applications/{self.application.id}/status/").json()
        self.assertFalse(state["completed"]["written"])
        self.submit_work()
        state = self.client.get(f"/api/applications/{self.application.id}/status/").json()
        self.assertTrue(state["completed"]["written"])


class QuestionClockTests(TestCase):
    """Thirty seconds a question, for every question in the bank."""

    def test_a_new_question_gets_thirty_seconds(self):
        self.assertEqual(Question().time_limit_seconds, 30)

    def test_the_shape_the_applicant_is_told_reports_thirty(self):
        for index in range(3):
            Question.objects.create(
                text=f"R scenario {index}?",
                category="R",
                options=["a", "b"],
                correct_answer="a",
            )
        with override_settings(PORTAL=portal_settings(QUOTA={"R": 3})):
            shape = services.quiz_shape()
        self.assertEqual(shape["seconds_min"], 30)
        self.assertEqual(shape["seconds_max"], 30)


class DeadlineDoesNotStrandAnApplicantTests(TestCase):
    """
    Closing the round must not cut off someone already sitting the quiz.

    The quiz cannot be restarted, so refusing an answer after the deadline would
    leave the applicant on a dead screen with no way back in. The deadline is
    therefore checked on intake (create, and the work step) and deliberately NOT
    on the quiz endpoints.
    """

    def setUp(self):
        for index in range(3):
            make_question("R", index, seconds=30)
        self.application = applicant(final_submitted_at=timezone.now())

    def test_a_quiz_in_progress_survives_the_deadline_passing(self):
        with override_settings(PORTAL=portal_settings(QUOTA={"R": 3})):
            started = self.client.post(
                f"/api/applications/{self.application.id}/quiz/start/"
            )
            self.assertEqual(started.status_code, 201, started.content)

            portal = PortalSettings.load()
            portal.application_deadline = timezone.localdate() - timedelta(days=1)
            portal.save()

            session = Application.objects.get(pk=self.application.pk).quiz
            for item in session.items.all():
                response = self.client.post(
                    f"/api/quiz/{session.id}/answer/",
                    {"answer": item.question.correct_answer},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 200, response.content)

        session.refresh_from_db()
        self.assertTrue(session.is_complete)
        self.assertEqual(session.score, 3)
