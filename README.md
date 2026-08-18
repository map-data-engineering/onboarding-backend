# Onboarding Portal

A Django + Django REST Framework application for running an **applicant intake + timed knowledge
check**. Candidates fill in their details, submit their own work — mandatory motivation, expectations
and a PDF CV (max 2 pages) — and then take a **shuffled, per-question timed quiz** whose clock is
enforced by the server. The quiz is **graded, not a gate**: the score is one component of the
composite the panel ranks on, and a low one no longer discards an application. Staff review
applicants and scores through a **custom token-authenticated admin API** (and a built-in admin panel),
and set the **application deadline** there too.

Originally built as an onboarding/recruitment tool for applicants in R programming, spatial data and
Bayesian statistics.

---

## Features

- **Eight-step application** — Before you begin → Details → Eligibility → Experience → Honesty check
  → **Your work** → **Knowledge check** → Result. Every step is persisted as it is completed, so a
  reload resumes from the record rather than from anything the browser remembers. The written answers
  and the CV come *before* the timed section: they used to come after it and be unlocked only by a
  passing score, which meant the panel had a bare number and nothing to read for everyone below the
  benchmark, and applicants met a countdown before being asked for the CV they were told to prepare.
- **Admin-set deadline** — the closing date lives in one editable row (`PortalSettings`), changed from
  the staff panel, defaulting to **30 August 2026**. The applicant page prints it and the intake
  endpoints enforce it, so the portal cannot go on accepting applications after the date it displays.
  It is inclusive: applicants can start and submit all day on the deadline itself.
- **Preparation screen** — what to have ready (a 2-page PDF CV, a dataset, 5–15 lines of their own R,
  their motivation) with a tickbox per item and a **Print this list** button. The start button stays
  disabled until every box is ticked. The tickboxes are not legal cover: ticking *"my CV is a PDF,
  no more than 2 pages and under 5 MB"* makes people go and check, which is the point. Applicants who
  start unprepared either abandon halfway or paste something thin into the written boxes, and neither
  tells the panel anything.
- **A different paper per applicant** — 14 questions drawn from a bank of 24 by per-category quota
  (`settings.PORTAL["QUOTA"]`), with the options shuffled and the draw frozen. "The answer is B" is
  worthless to pass around, because it is usually about a question the next applicant never sees.
  Every question allows **30 seconds** — far too short to search for an unfamiliar result, read it
  and evaluate it, which is the point of the clock. It is also tight for the longer scenario items,
  so watch where `TIMEOUTS` cluster (see *Editing the question bank*).
- **Shortlist builder** — ranks every application on the composite, then allocates seats under
  explicit floors (minimum women, minimum Tanzania-based, maximum per institution), with three
  travel-certainty modes and a waitlist. Floors are satisfied first, then remaining seats fill on
  merit; unmet floors are reported rather than quietly fudged.
- **Clean country data** — country of residence and nationality are dropdowns over the 195 UN member
  states with Tanzania and its neighbours pinned at the top, validated server-side. WhatsApp numbers
  must carry a `+` and a country code, with an error that says why a local `07…` number is refused.
- **Eligibility gate** — four practical questions (can you attend, laptop, spatial data, travel
  funding) answered *before* any real effort. Someone who cannot take up a place is told immediately
  rather than after fifteen minutes, and the reason is stored on the record.
- **Honesty check** — a grid of R functions, four of which are invented. Claiming one costs more than
  admitting you don't know it. Which names are fake is only ever known server-side, so it can't be
  read out of the page source.
- **Your own work, before the clock** — a **motivation statement**, **expectations**, a dataset
  description, 5–15 lines of their own R, and a **PDF CV** (strictly validated: max 2 pages, max 5 MB).
  Required of every eligible applicant, and it is this submission that unlocks the knowledge check
  (enforced server-side, not just ordered in the UI). Nothing here is gated on the score: the quiz is
  graded against `PASS_MARK`, but the grade no longer decides who may apply.
- **Composite score /100** — knowledge 45 + honesty 20 + relevance 20 + impact 15, plus review flags
  (`BLUFF`, `NO-CODE`, `RUSHED`, `INCONSISTENT`, `UNFUNDED`, …). Derived on read, so it can never
  drift from the answers.
- **Timed quiz** — one question at a time. The draw, the question order **and the answer options** are
  fixed per applicant when the session is built. The per-question deadline (30s, plus a 3s network
  grace) is **server-authoritative**: the client can't grant itself more time, restart, or reshuffle.
- **The countdown doesn't depend on the applicant's clock** — each question payload carries
  `remaining_seconds`, computed server-side and clamped to `0…time_limit_seconds`, and the page ticks
  from a monotonic timer. A device clock a few minutes out used to mean either every question
  auto-submitted blank or every answer discarded as late, silently in both cases.
- **Running out of time moves on** — at zero the page submits whatever is selected, including nothing;
  the server records the question as unanswered and returns the next one with a fresh clock. That
  automatic submission gets a retry and then a resync, because a single dropped request at zero would
  otherwise strand an applicant in a quiz that cannot be restarted.
- **Hidden grading** — correct answers are never sent to the applicant; only the final score is
  revealed at the end.
- **Pass/fail status — a grade, not a gate** — every applicant carries a `status` derived from their
  score: **Pass** (≥ 8), **Fail** (below 8), or **Pending** (quiz unfinished). Computed on read, so it
  never drifts from the answers, and kept separate from the staff's own `decision`
  (Selected/Rejected). A **Fail** still has a complete application behind it — CV, motivation, code —
  because the work step comes first, so the panel can weigh a 6/14 against a strong record instead of
  seeing only the number.
- **Custom admin API** — staff-only, token-authenticated endpoints to list applicants (searchable and
  filterable by status), view details + CV, and see a per-question quiz breakdown.
- **CSV export** — download the applicants matching the current search/status filters, so the file
  contains exactly the rows on screen.
- **Three staff tiers** — *superusers* (everything, and the only tier that can run a CSV export or
  the shortlist builder), *reviewers* (read applications, change decisions, delete, move the
  deadline) and *viewers*, read-only accounts that can see applicant counts, details and quiz
  breakdowns and nothing else. A staff login is not a licence to walk off with the applicant
  table or to run the selection.
- **Same-origin frontend** — lightweight HTML/JS pages served by Django, so the browser calls `/api/`
  with no CORS setup.

---

## Tech stack

- **Python 3.12+** (developed on 3.14)
- **Django 6.0**
- **Django REST Framework 3.17** (+ `authtoken` for the admin panel)
- **MySQL** in production (PythonAnywhere), **SQLite** locally — selected by `DJANGO_DB_ENGINE`, no
  code change between the two
- Vanilla HTML/CSS/JS templates (no frontend build step, no CSS framework) styled in the Malaria
  Atlas Project tile: gold `#EBBC40` / black `#111010`, Lato headings, Nunito Sans body

---

## Project structure

```
onboarding/
├── manage.py
├── requirements.txt               # base deps (local dev, SQLite)
├── requirements-prod.txt          # the above + mysqlclient (production)
├── db.sqlite3                     # local dev only; created on first migrate (git-ignored)
├── media/                         # uploaded CVs (git-ignored)
├── onboarding/                    # project package
│   ├── settings.py                # env-driven config (DEBUG, SECRET_KEY, hosts, DB, static/media)
│   ├── urls.py                    # /admin/, /api/, and the frontend pages
│   ├── wsgi.py / asgi.py
├── application/                   # the app
│   ├── models.py                  # Question, Application (+ PASS_MARK, status), QuizSession, SessionQuestion, PortalSettings (the deadline)
│   ├── assessment.py              # eligibility rules, honesty check, composite score + flags
│   ├── shortlist.py               # ranking, diversity floors, travel modes, waitlist
│   ├── countries.py               # the 195 UN member states, Tanzania + neighbours pinned
│   ├── services.py                # server-authoritative quiz logic (draw, shuffle, timing, grading)
│   ├── views.py                   # applicant-facing API (function-based views)
│   ├── admin_views.py             # staff-only admin API
│   ├── permissions.py             # the three staff tiers (superuser / reviewer / viewer)
│   ├── validators.py              # CV (PDF, pages, size), phone, word limits
│   ├── exports.py / cv_links.py   # CSV rows; short-lived signed CV links
│   ├── checks.py                  # warns when STATIC_ROOT is stale (application.W001)
│   ├── serializers.py / admin_serializers.py
│   ├── urls.py                    # all /api/ routes
│   ├── admin.py                   # Django built-in admin registrations
│   ├── management/commands/seed_questions.py
│   ├── templates/                 # base.html, applicant/portal.html, panel/index.html
│   ├── tests.py                   # static-asset check, the draw, the quiz clock, the shortlist
│   ├── tests_journey.py           # the deadline, the step order, and the score as a grade
│   └── static/                    # css/styles.css, js/{api,applicant,panel}.js
└── demo_fill.py                   # scripted end-to-end API walkthrough
```

---

## Quick start (local)

Requires Python 3.12+.

```bash
# 1. Create/activate a virtualenv, then install deps
pip install -r requirements.txt

# 2. Set up the database and load the quiz questions
python manage.py migrate
python manage.py seed_questions        # loads the 24-question bank (14 drawn per applicant)

# 3. (optional) create a staff account for the admin panel / Django admin
python manage.py createsuperuser

# 4. Run it
python manage.py runserver
```

Then open:

| URL | What it is |
|-----|-----------|
| `http://127.0.0.1:8000/` | Applicant portal (apply + take the quiz) |
| `http://127.0.0.1:8000/panel/` | Staff panel (custom admin frontend) |
| `http://127.0.0.1:8000/admin/` | Django built-in admin |
| `http://127.0.0.1:8000/api/` | REST API root |

> **Windows note:** on this machine, call Python via the venv directly, e.g.
> `.venv\Scripts\python.exe manage.py runserver`. If port 8000 is busy, use another port
> (`runserver 8077`).

---

## Configuration (environment variables)

Settings read from the environment, with dev-friendly defaults:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DJANGO_DEBUG` | `1` | `0` in production |
| `DJANGO_SECRET_KEY` | insecure dev key | **set a real key in production** |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | *(empty)* | e.g. `https://yourdomain` — needed for admin login over HTTPS |
| `DJANGO_DB_ENGINE` | `sqlite` | set to `mysql` to use MySQL |
| `DJANGO_DB_NAME` / `_USER` / `_PASSWORD` / `_HOST` | *(empty)* | MySQL connection details |
| `DJANGO_DB_PORT` | `3306` | MySQL port |
| `DJANGO_DB_CONN_MAX_AGE` | `60` | connection reuse, in seconds (keep under MySQL's idle timeout) |
| `PORTAL_CONTACT_EMAIL` | `cmyalla@ihi.or.tz` | shown on the exit screens so blocked applicants can join the mailing list |
| `PORTAL_DEADLINE` | `2026-08-30` | ISO date a **fresh database** starts with. The live deadline is the `PortalSettings` row, changed from the staff panel — editing this variable afterwards changes nothing |
| `PORTAL_DURATION` | `about 15 minutes` | how long the application takes — set it honestly |
| `PORTAL_FUNDING_GATE` | `1` | `0` lets applicants who cannot fund travel apply anyway, flagged `UNFUNDED` |

The same block (`settings.PORTAL`) holds `QUOTA`, the per-category size of the question draw. All of
it is served to the applicant page by `GET /api/config/`, so the page cannot promise a limit the API
does not enforce.

### The funding gate is a decision, not a default

There is no travel, accommodation or subsistence support, and the portal says so in three places
rather than burying it: a callout on the preparation screen, an eligibility question asking how travel
will be covered, and — with `PORTAL_FUNDING_GATE=1` — an honest exit for anyone who could not attend
without support, telling them plainly that this reflects the budget and not their application.

Telling someone "no" in ten seconds is kinder than a fifteen-minute application you cannot honour.
But a hard gate also excludes junior and lower-resourced applicants disproportionately, which pulls
against most diversity goals. Set `PORTAL_FUNDING_GATE=0` to let them through flagged `UNFUNDED` and
judge case by case. There is no neutral option here; pick one deliberately.

MySQL also needs the driver: `pip install -r requirements-prod.txt` (adds `mysqlclient` on top of
`requirements.txt`).

---

## API overview

All endpoints live under `/api/`.

**Applicant flow (open, no auth):**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/config/` | Deadline (`deadline`, `deadline_date`, `applications_open`), limits, country lists, shape of the knowledge check |
| POST | `/api/applications/` | Create applicant — contact + profile only. **403** once the deadline has passed |
| GET | `/api/applications/{id}/status/` | Where the applicant is in the journey (client resume; 404 = stale id) |
| POST | `/api/applications/{id}/eligibility/` | Step 2 — returns `{eligible, reason}`; a `false` ends the journey |
| POST | `/api/applications/{id}/experience/` | Step 3 — experience and plans |
| GET/POST | `/api/applications/{id}/claims/` | Step 4 — honesty check (GET returns the shuffled function names) |
| POST | `/api/applications/{id}/finalize/` | Step 5: written answers, motivation + CV (multipart). **403** after the deadline, or before the earlier steps are answered |
| POST | `/api/applications/{id}/quiz/start/` | Step 6 — draw this applicant's questions and start the clock. **403** until step 5 is submitted |
| GET | `/api/quiz/{session}/current/` | Current question (or result) |
| POST | `/api/quiz/{session}/answer/` | Submit an answer, get the next |
| GET | `/api/quiz/{session}/result/` | Final score (+ `passed`, `pass_mark` — reported, not enforced) |

**Admin panel (staff-only, `Authorization: Token <token>`):**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/admin/login/` | Staff login → token |
| POST | `/api/admin/logout/` | Invalidate token |
| GET | `/api/admin/me/` | Current staff user |
| GET/PATCH | `/api/admin/settings/` | The application deadline. GET for any staff account; PATCH `{"application_deadline": "2026-08-30"}` for reviewers |
| GET | `/api/admin/applications/` | List applicants (`?search=`, `?status=pass\|fail\|pending`, `?page=`) |
| GET | `/api/admin/applications/export/` | CSV of the filtered applicants (**superusers only**) |
| GET | `/api/admin/applications/{id}/` | Applicant detail + CV URL |
| GET | `/api/admin/applications/{id}/cv/` | Stream an applicant's CV (staff token, or the short-lived `?sig=` link the detail returns) |
| GET | `/api/admin/applications/{id}/quiz/` | Per-question breakdown |
| GET/POST | `/api/admin/shortlist/` | Full ranking + seat allocation under the floors (**superusers only**) |
| POST | `/api/admin/shortlist/export/` | CSV of that ranking, with Rank/Shortlisted/Waitlisted (**superusers only**) |

Full request/response shapes and frontend integration notes are in
[`README_FRONTEND.md`](./README_FRONTEND.md).

---

## Testing the API

- **Fast end-to-end check:** `python demo_fill.py` creates an applicant, takes the whole quiz, prints
  the score (`Score: 14 / 14`), and submits the work step (motivation, expectations, CV) before it.
  The motivation and expectations are capped at 300 words each, and the CV must be a valid PDF.
  Options: `--base-url`, `--answers correct|first`.
- **Manual / exploratory:** a Thunder Client collection (`thunder-collection_onboarding.json`) and a
  step-by-step guide are provided in `README_API_TESTING.md` (kept locally).

---

## Management commands

| Command | Description |
|---------|-------------|
| `python manage.py seed_questions` | Load/refresh the 24-question bank (idempotent — see below) |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py collectstatic` | Gather static files (for production) |
| `python manage.py createsuperuser` | Create a staff/admin account (full reviewer) |
| `python manage.py create_viewer <username>` | Create a **view-only** staff account |

### Staff roles

| Role | How to create | Can do |
|------|---------------|--------|
| **Superuser** | `createsuperuser` | Everything, and the **only** tier that may run a CSV export or the shortlist builder |
| **Reviewer** | any `is_staff` account that is not a superuser | Read applications and CVs, change decisions, bulk actions, delete, move the deadline. **No exports, no shortlist** |
| **Viewer** | `create_viewer <username>` | Read-only: applicant count, list, details, CV download, quiz breakdown |

A viewer is a normal staff account placed in the **"Applicant viewers"** group, so you can also
toggle the role from Django admin (add/remove the group) without touching code. `create_viewer
<username> --revoke` promotes one back to a full reviewer, and superusers are never treated as
view-only.

**Why exports and the shortlist sit above reviewer.** They are the two actions whose effects
leave the panel. A CSV is the whole filtered applicant database — names, emails, phone numbers,
free text — living on somebody's laptop where none of these checks apply; reading records one at
a time leaves the data where it is. The shortlist is the selection itself, the ranking with the
cut line drawn and the floors applied, and a provisional ordering circulated before the panel
meets reads as the outcome. Granting either should be an explicit act, not a side effect of
issuing a staff login.

The panel hides the controls an account can't use, but that's cosmetic — `PATCH`, `DELETE`,
`/bulk/`, both `/export/` endpoints and `/shortlist/` all enforce their own rule and return
**403** regardless of what the browser sends.

### Editing the question bank

`application/management/commands/seed_questions.py` holds the bank: **5 R, 7 spatial, 5 general
statistics, 4 Bayesian, 3 health application = 24**, from which each applicant is drawn **14** by the
quota in `settings.PORTAL["QUOTA"]` (`R 3, SPATIAL 5, GENERAL 3, BAYESIAN 2, APPLICATION 1`).

Each entry is `(category, text, options, correct_answer[, code[, seconds]])`:

- **`code`** renders under the question in a monospaced block — use it for snippets like
  `d %>% group_by(district)` instead of burying them in the prose.
- **`seconds`** overrides `DEFAULT_SECONDS` (**30s**, which every question in the bank currently
  uses) for a single question. Reach for it rather than raising the default: if timeouts cluster on
  the same few long scenario items — the panel raises `TIMEOUTS`, and the per-question breakdown
  shows which — give *those* items more room. 30s is tightest for applicants reading in a second
  language, who are most of the pool.

Edit that list and re-run `seed_questions`: it **updates** existing questions in place (matched on
their text) and **retires** anything no longer listed — setting `is_active=False` rather than
deleting, since the draw only serves active questions while past quizzes must stay auditable.
Questions never used in a quiz are deleted outright; pass `--keep-retired` to always deactivate
instead. The command prints the count per category against its quota and **warns when a category has
no spares**, which is the failure that otherwise hides: the draw still works, it just hands every
applicant the same items.

Two rules when adding questions:

1. **Keep at least two spares per category** beyond its quota, or the draw stops varying.
2. **Write scenarios, not recall.** Anything with a single correct answer that exists in the
   literature is found in twenty seconds, so it ranks nobody. Every item here poses a situation with
   its own numbers and asks for a consequence or a next action, and the distractors are the common
   misconceptions rather than filler, so elimination doesn't work either.

Changing the size of the draw affects the pass mark, which is an absolute count (`PASS_MARK = 8` in
`application/models.py`), not a percentage. Because `status` is derived on read, changing it re-grades
every application, including ones already submitted. It re-grades only: no applicant loses a
submission over it, because the written answers and the CV are collected before the quiz and are not
conditional on the score.

---

## Running the selection

The design assumption is 500 applicants for 25 seats. At 20:1 the job is not to pick the best 25 by
machine — it is to rank everyone automatically so that humans read 60 applications instead of 500.

1. **Open `/panel/` as a superuser** and click **Build a shortlist**. The builder and both CSV
   exports are superuser-only; reviewers read applications here but do not run the selection.
   Check the **deadline card** above the applicants table while you are there — the round closes
   at the end of the date shown, and applicants see the same one.
2. **Read the header advice.** If the median applicant is near the ceiling of the knowledge check, the
   panel says so: the questions have stopped discriminating and the ranking is really being driven by
   the other three components. That is not something anyone notices by looking at a table.
3. **Set your floors** — seats, minimum women, minimum Tanzania-based, maximum per institution,
   travel certainty, waitlist size — and rebuild. Floors are satisfied first, then remaining seats
   fill on merit. A floor that cannot be met turns red rather than being quietly fudged.
4. **Read the written answers** of everyone near the cut line. The whole ranking is listed with the
   picks marked, not just the picks, because those are the applications a human needs to read; click
   any row to open it.
5. **Export** the full ranking or the shortlist and waitlist alone. Both are CSVs of personal
   data leaving the panel, which is why they sit with the superuser tier.

**Travel certainty** has three modes:

| Mode | Behaviour |
|---|---|
| Prefer confirmed *(default)* | Fills every seat from applicants with confirmed travel first, then uses unconfirmed ones only if seats remain |
| Confirmed only | Excludes unconfirmed applicants entirely |
| Ignore | Ranks purely on merit |

On a simulated 500-applicant pool where 40% had unconfirmed travel, "prefer" cut unconfirmed
participants in the final 25 from **12 to zero** for about **3 points of median score** — a trivial
price for materially fewer no-shows, and offers go out once, shortly before the workshop. "Confirmed
only" gave an identical result there, so the softer setting is the sensible default: it costs nothing
when confirmed applicants are plentiful and degrades gracefully when they are not.

**Apply the floors when cutting to the shortlist, not at the final 25.** A shortlist of 60 that is
lopsided by gender or institution is very hard to fix afterwards, and at 20:1 you can afford to be
wrong at the margins on an individual technical score — two slightly weaker participants will not
damage the workshop, but a homogeneous room will.

Every score in the panel is **recomputed from the stored answers** (`application/shortlist.py` calls
`assessment.compute_score`), so a tampered submission is scored correctly regardless of what the
browser sent.

---

## Deployment

See [`README_DEPLOY_PYTHONANYWHERE.md`](./README_DEPLOY_PYTHONANYWHERE.md) for a full step-by-step
PythonAnywhere deployment (MySQL, Python 3.12+).

> **Not suitable for Vercel** as-is: Vercel's serverless filesystem is ephemeral, so uploaded CVs
> wouldn't persist (the database is fine once it's MySQL). Use a persistent host (PythonAnywhere,
> Render, Railway, Fly.io) — or move media to object storage first.

---

## License

See [`LICENSE`](./LICENSE).
