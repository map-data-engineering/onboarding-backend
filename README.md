# Onboarding Portal

A Django + Django REST Framework application for running an **applicant intake + timed knowledge
check**. Candidates fill in their details, take a **shuffled, per-question timed quiz** whose clock
is enforced by the server, and — only if they score at least the pass mark — complete their
application with their motivation, expectations and CV. Staff review applicants and scores through a
**custom token-authenticated admin API** (and a built-in admin panel).

Originally built as an onboarding/recruitment tool for applicants in R programming, spatial data and
Bayesian statistics.

---

## Features

- **Two-stage intake** — the first form collects contact/profile details only. The motivation,
  expectations and CV upload are gated behind the quiz and are collected in a final step, unlocked
  only for applicants scoring **7 or more** (`services.PASS_MARK`). The gate is enforced
  server-side, not just hidden in the UI.
- **Timed quiz** — one question at a time, shuffled once per applicant and frozen. The 40s-per-question
  deadline (plus a 3s network grace) is **server-authoritative**: the client can't grant itself more
  time, restart, or reshuffle.
- **Hidden grading** — correct answers are never sent to the applicant; only the final score is
  revealed at the end.
- **Pass/fail status** — every applicant carries a `status` derived from their score: **Pass**
  (≥ 7), **Fail** (below 7), or **Pending** (quiz unfinished). Computed on read, so it never drifts
  from the answers, and kept separate from the staff's own `decision` (Selected/Rejected).
- **Custom admin API** — staff-only, token-authenticated endpoints to list applicants (searchable and
  filterable by status), view details + CV, and see a per-question quiz breakdown.
- **CSV export** — download the applicants matching the current search/status filters, so the file
  contains exactly the rows on screen.
- **Two staff tiers** — *reviewers* (full access) and *viewers*, a read-only account that can see
  applicant counts, details and quiz breakdowns but cannot change decisions, delete or export.
- **Same-origin frontend** — lightweight HTML/JS pages served by Django, so the browser calls `/api/`
  with no CORS setup.

---

## Tech stack

- **Python 3.12+** (developed on 3.14)
- **Django 6.0**
- **Django REST Framework 3.17** (+ `authtoken` for the admin panel)
- **MySQL** in production (PythonAnywhere), **SQLite** locally — selected by `DJANGO_DB_ENGINE`, no
  code change between the two
- Vanilla HTML/CSS/JS templates (no frontend build step)

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
│   ├── models.py                  # Question, Application (+ PASS_MARK, status), QuizSession, SessionQuestion
│   ├── services.py                # server-authoritative quiz logic (shuffle, timing, grading)
│   ├── views.py                   # applicant-facing API (function-based views)
│   ├── admin_views.py             # staff-only admin API
│   ├── serializers.py / admin_serializers.py
│   ├── urls.py                    # all /api/ routes
│   ├── admin.py                   # Django built-in admin registrations
│   ├── management/commands/seed_questions.py
│   ├── templates/                 # base.html, applicant/portal.html, panel/index.html
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
python manage.py seed_questions        # loads the 12 knowledge-check questions

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

MySQL also needs the driver: `pip install -r requirements-prod.txt` (adds `mysqlclient` on top of
`requirements.txt`).

---

## API overview

All endpoints live under `/api/`.

**Applicant flow (open, no auth):**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/applications/` | Create applicant — contact + profile only |
| GET | `/api/applications/{id}/status/` | Where the applicant is in the journey (client resume; 404 = stale id) |
| POST | `/api/applications/{id}/quiz/start/` | Start the shuffled quiz |
| GET | `/api/quiz/{session}/current/` | Current question (or result) |
| POST | `/api/quiz/{session}/answer/` | Submit an answer, get the next |
| GET | `/api/quiz/{session}/result/` | Final score (+ `passed`, `pass_mark`) |
| POST | `/api/applications/{id}/finalize/` | Final submission: motivation, expectations + CV (multipart). **403** unless the quiz is complete with a score ≥ `pass_mark` |

**Admin panel (staff-only, `Authorization: Token <token>`):**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/admin/login/` | Staff login → token |
| POST | `/api/admin/logout/` | Invalidate token |
| GET | `/api/admin/me/` | Current staff user |
| GET | `/api/admin/applications/` | List applicants (`?search=`, `?status=pass\|fail\|pending`, `?page=`) |
| GET | `/api/admin/applications/export/` | CSV of the filtered applicants (reviewers only) |
| GET | `/api/admin/applications/{id}/` | Applicant detail + CV URL |
| GET | `/api/admin/applications/{id}/quiz/` | Per-question breakdown |

Full request/response shapes and frontend integration notes are in
[`README_FRONTEND.md`](./README_FRONTEND.md).

---

## Testing the API

- **Fast end-to-end check:** `python demo_fill.py` creates an applicant, takes the whole quiz, prints
  the score (`Score: 12 / 12`), then submits the final step (motivation, expectations, CV). Options: `--base-url`, `--answers correct|first`.
- **Manual / exploratory:** a Thunder Client collection (`thunder-collection_onboarding.json`) and a
  step-by-step guide are provided in `README_API_TESTING.md` (kept locally).

---

## Management commands

| Command | Description |
|---------|-------------|
| `python manage.py seed_questions` | Load/refresh the 12 quiz questions (idempotent — see below) |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py collectstatic` | Gather static files (for production) |
| `python manage.py createsuperuser` | Create a staff/admin account (full reviewer) |
| `python manage.py create_viewer <username>` | Create a **view-only** staff account |

### Staff roles

| Role | How to create | Can do |
|------|---------------|--------|
| **Reviewer** | `createsuperuser`, or any `is_staff` account | Everything: decisions, bulk actions, delete, CSV export |
| **Viewer** | `create_viewer <username>` | Read-only: applicant count, list, details, CV download, quiz breakdown |

A viewer is a normal staff account placed in the **"Applicant viewers"** group, so you can also
toggle the role from Django admin (add/remove the group) without touching code. `create_viewer
<username> --revoke` promotes one back to a full reviewer, and superusers are never treated as
view-only.

The panel hides the controls a viewer can't use, but that's cosmetic — `PATCH`, `DELETE`,
`/bulk/` and `/export/` all return **403** for them regardless of what the browser sends.

### Editing the question set

`application/management/commands/seed_questions.py` holds the canonical list, transcribed from
*Onboarding Portal — Knowledge Check Questions* (2 R, 4 spatial, 6 Bayesian). Edit that list and
re-run `seed_questions`: it **updates** existing questions in place (matched on their text) and
**retires** anything no longer listed — setting `is_active=False` rather than deleting, since
`build_session` only serves active questions while past quizzes must stay auditable. Questions never
used in a quiz are deleted outright; pass `--keep-retired` to always deactivate instead.

Changing the number of questions affects the pass mark, which is an absolute count (`PASS_MARK = 7`
in `application/models.py`), not a percentage.

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
