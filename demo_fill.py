#!/usr/bin/env python
"""
Demo API fill for the onboarding application flow.

Drives the public API exactly like a real client would, in the order the portal now
uses -- the work step comes BEFORE the knowledge check, and is what unlocks it:
    1. POST /api/applications/                       -> create applicant (details only)
    2. POST /api/applications/<id>/eligibility/       -> the four practical questions
    3. POST /api/applications/<id>/experience/        -> experience and plans
    4. GET/POST /api/applications/<id>/claims/        -> the honesty check
    5. POST /api/applications/<id>/finalize/          -> written answers, motivation + CV
    6. POST /api/applications/<id>/quiz/start/        -> build the shuffled session
       GET  /api/quiz/<session>/current/             -> fetch the current question
       POST /api/quiz/<session>/answer/              -> submit an answer  (repeat)
       GET  /api/quiz/<session>/result/              -> final score, graded against the
                                                        pass mark but gating nothing

Usage:
    # 1. start the server in one terminal:
    #    .venv/Scripts/python.exe manage.py runserver
    # 2. run this demo in another:
    python demo_fill.py
    python demo_fill.py --base-url http://127.0.0.1:8000 --answers correct

--answers correct  (default) looks up the right answer via the Django ORM so the
                   run ends with a perfect score (nice for demos).
--answers first    picks the first option every time -- pure API, no DB access.
"""

import argparse
import io
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

# A realistic-looking applicant payload (mirrors the Application model fields).
APPLICANT = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada.lovelace@example.org",
    # Both country fields are dropdowns validated against application/countries.py,
    # and the phone must carry a country code -- a local "0..." number is rejected.
    "phone": "+44 20 7946 0958",
    "nationality": "United Kingdom",
    "country_of_residence": "United Kingdom",
    "gender": "Female",
    "institution": "Analytical Engine Institute",
    "institution_type": "University",
    "role": "Research Scientist",
    "education": "PhD",
    "r_experience": "Intermediate",
    "bayesian_knowledge": "Beginner",
}

# Step 2 — eligibility. These exact strings are validated server-side.
ELIGIBILITY = {
    "elig_attend": "Yes, all four days",
    "elig_laptop": "Yes",
    "elig_data": "Yes, I work with it now",
    "elig_funding": "My institution has agreed to cover it",
}

# Step 3 — experience and plans.
EXPERIENCE = {
    "exp_rfreq": "Most weeks",
    "exp_rself": "Intermediate — I write my own analysis scripts",
    "exp_bayes": "Beginner",
    "exp_glm": "Yes, several times",
    "exp_dtype": "Survey or sampling points with coordinates",
    "exp_when": "Within six months",
    "exp_share": "Yes, in principle",
    "exp_use": "Sometimes",
}

# Step 5 — the applicant's own work. Collected from every eligible applicant,
# before the quiz, and no longer conditional on the score.
FINAL_STEP = {
    "written_dataset": "One row per household surveyed in Kilombero district between 2019 and "
                       "2023, about 4,200 rows, with GPS coordinates for each homestead.",
    "written_code": "library(sf)\npts <- st_read('households.gpkg')\n"
                    "pts <- st_transform(pts, 32737)\n# reproject before buffering",
    "written_why_not_ols": "The outcome is a count with many zeros and nearby households are "
                           "correlated, so OLS would understate the uncertainty.",
    "written_other": "",
    "motivation": "I am passionate about spatial statistics and want to apply Bayesian "
                  "methods to improve public health outcomes in my region.",
    "expectations": "I expect to gain a deeper understanding of INLA and how to handle "
                    "spatial autocorrelation in disease mapping.",
}

CV_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
    b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000108 00000 n\n"
    b"trailer << /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"
)


def _encode_multipart(fields, file_field, filename, file_bytes):
    """Build a multipart/form-data body from plain fields + one file."""
    boundary = f"----demo{uuid.uuid4().hex}"
    crlf = b"\r\n"
    buf = io.BytesIO()

    for name, value in fields.items():
        buf.write(f"--{boundary}".encode() + crlf)
        buf.write(f'Content-Disposition: form-data; name="{name}"'.encode() + crlf)
        buf.write(crlf)
        buf.write(str(value).encode("utf-8") + crlf)

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    buf.write(f"--{boundary}".encode() + crlf)
    buf.write(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode()
        + crlf
    )
    buf.write(f"Content-Type: {content_type}".encode() + crlf)
    buf.write(crlf)
    buf.write(file_bytes + crlf)

    buf.write(f"--{boundary}--".encode() + crlf)
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def _request(method, url, *, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def _load_answer_key():
    """Map question text -> correct answer via the Django ORM (for a perfect run)."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onboarding.settings")
    import django

    django.setup()
    from application.models import Question

    return {q.text: q.correct_answer for q in Question.objects.all()}


def main():
    parser = argparse.ArgumentParser(description="Demo API fill for the onboarding app.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--answers", choices=["correct", "first"], default="correct")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    answer_key = _load_answer_key() if args.answers == "correct" else {}

    print(f"-> Creating application at {base}/api/applications/ ...")
    status, app = _request(
        "POST",
        f"{base}/api/applications/",
        data=json.dumps(APPLICANT).encode(),
        headers={"Content-Type": "application/json"},
    )
    if status != 201:
        print(f"[x] Failed to create application ({status}): {app}")
        sys.exit(1)
    application_id = app["id"]
    print(f"  [ok] Application created: {application_id} ({app['first_name']} {app['last_name']})")

    for label, path, payload in (
        ("eligibility", "eligibility", ELIGIBILITY),
        ("experience", "experience", EXPERIENCE),
    ):
        print(f"-> Submitting {label} ...")
        status, resp = _request(
            "POST",
            f"{base}/api/applications/{application_id}/{path}/",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        if status != 200:
            print(f"[x] {label} rejected ({status}): {resp}")
            sys.exit(1)
        if label == "eligibility" and not resp.get("eligible"):
            print(f"  [--] Ruled out: {resp['reason']}")
            return
        print(f"  [ok] {label} accepted")

    print("-> Honesty check ...")
    status, resp = _request("GET", f"{base}/api/applications/{application_id}/claims/")
    # Answer honestly: this demo "knows" the four common ones and nothing else,
    # which is also the only way to score the honesty component.
    known = {"read.csv", "group_by", "ggplot", "glm"}
    claims = {fn: ("used" if fn in known else "no") for fn in resp["functions"]}
    status, resp = _request(
        "POST",
        f"{base}/api/applications/{application_id}/claims/",
        data=json.dumps({"claims": claims}).encode(),
        headers={"Content-Type": "application/json"},
    )
    if status != 200:
        print(f"[x] Honesty check rejected ({status}): {resp}")
        sys.exit(1)
    print(f"  [ok] answered for {len(claims)} functions")

    print("-> Submitting the applicant's own work (written answers + CV) ...")
    body, content_type = _encode_multipart(
        FINAL_STEP, "cv", "ada_lovelace_cv.pdf", CV_BYTES
    )
    status, final = _request(
        "POST",
        f"{base}/api/applications/{application_id}/finalize/",
        data=body,
        headers={"Content-Type": content_type},
    )
    if status != 200:
        print(f"[x] Work step rejected ({status}): {final}")
        sys.exit(1)
    print(f"  [ok] Application submitted at {final['submitted_at']} (cv={final['cv']})")

    print("-> Starting quiz ...")
    status, current = _request(
        "POST", f"{base}/api/applications/{application_id}/quiz/start/"
    )
    if status != 201:
        print(f"[x] Failed to start quiz ({status}): {current}")
        sys.exit(1)
    session_id = current["session"]
    total = current["total"]
    print(f"  [ok] Session {session_id} - {total} questions\n")

    answered = 0
    while current and current.get("question"):
        q = current["question"]
        position = current["position"]
        options = q["options"]

        if args.answers == "correct":
            answer = answer_key.get(q["text"], options[0])
        else:
            answer = options[0]

        print(f"  Q{position + 1}/{total} [{q['category']}] {q['text']}")
        print(f"     -> answering: {answer!r}")

        status, resp = _request(
            "POST",
            f"{base}/api/quiz/{session_id}/answer/",
            data=json.dumps({"answer": answer}).encode(),
            headers={"Content-Type": "application/json"},
        )
        if status != 200:
            print(f"[x] Answer rejected ({status}): {resp}")
            sys.exit(1)
        answered += 1

        if resp.get("finished"):
            break
        current = resp.get("next")

    print(f"\n-> Fetching result ({answered} answered) ...")
    status, result = _request("GET", f"{base}/api/quiz/{session_id}/result/")
    print(f"  [ok] Score: {result['score']} / {result['total']}  (completed_at={result['completed_at']})")

    # A grade, not a gate: the application went in at step 5 and stands whatever the
    # quiz says. Printed because it is what the panel ranks on.
    if not result.get("passed"):
        print(
            f"  [--] Below the pass mark ({result.get('pass_mark')}) -- the application "
            f"still stands; the score is one component of the composite."
        )


if __name__ == "__main__":
    main()
