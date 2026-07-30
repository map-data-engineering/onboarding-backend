# Onboarding Portal

A Django + Django REST Framework application for running an **applicant intake + timed knowledge
check**. Candidates fill in an application form (with a CV upload), then take a **shuffled,
per-question timed quiz** whose clock is enforced by the server. Staff review applicants and scores
through a **custom token-authenticated admin API** (and a built-in admin panel).

Originally built as an onboarding/recruitment tool for applicants in R programming, spatial data,
Bayesian statistics, and health-application topics.

---

## Features

- **Applicant intake** — full contact/profile form with a required CV file upload.
- **Timed quiz** — one question at a time, shuffled once per applicant and frozen. The 40s-per-question
  deadline (plus a 3s network grace) is **server-authoritative**: the client can't grant itself more
  time, restart, or reshuffle.
- **Hidden grading** — correct answers are never sent to the applicant; only the final score is
  revealed at the end.
- **Custom admin API** — staff-only, token-authenticated endpoints to list applicants, view details +
  CV, and see a per-question quiz breakdown.
- **Same-origin frontend** — lightweight HTML/JS pages served by Django, so the browser calls `/api/`
  with no CORS setup.

---

## Tech stack

- **Python 3.12+** (developed on 3.14)
- **Django 6.0**
- **Django REST Framework 3.17** (+ `authtoken` for the admin panel)
- **SQLite** (default; swappable for MySQL/Postgres)
- Vanilla HTML/CSS/JS templates (no frontend build step)

---

## Project structure

```
onboarding/
├── manage.py
├── requirements.txt
├── db.sqlite3                     # created on first migrate (git-ignored)
├── media/                         # uploaded CVs (git-ignored)
├── onboarding/                    # project package
│   ├── settings.py                # env-driven config (DEBUG, SECRET_KEY, hosts, static/media)
│   ├── urls.py                    # /admin/, /api/, and the frontend pages
│   ├── wsgi.py / asgi.py
├── application/                   # the app
│   ├── models.py                  # Question, Application, QuizSession, SessionQuestion
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

---

## API overview

All endpoints live under `/api/`.

**Applicant flow (open, no auth):**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/applications/` | Create applicant + upload CV (multipart) |
| POST | `/api/applications/{id}/quiz/start/` | Start the shuffled quiz |
| GET | `/api/quiz/{session}/current/` | Current question (or result) |
| POST | `/api/quiz/{session}/answer/` | Submit an answer, get the next |
| GET | `/api/quiz/{session}/result/` | Final score |

**Admin panel (staff-only, `Authorization: Token <token>`):**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/admin/login/` | Staff login → token |
| POST | `/api/admin/logout/` | Invalidate token |
| GET | `/api/admin/me/` | Current staff user |
| GET | `/api/admin/applications/` | List applicants (`?search=`, `?page=`) |
| GET | `/api/admin/applications/{id}/` | Applicant detail + CV URL |
| GET | `/api/admin/applications/{id}/quiz/` | Per-question breakdown |

Full request/response shapes and frontend integration notes are in
[`README_FRONTEND.md`](./README_FRONTEND.md).

---

## Testing the API

- **Fast end-to-end check:** `python demo_fill.py` creates an applicant, takes the whole quiz, and
  prints the score (`Score: 12 / 12`). Options: `--base-url`, `--answers correct|first`.
- **Manual / exploratory:** a Thunder Client collection (`thunder-collection_onboarding.json`) and a
  step-by-step guide are provided in `README_API_TESTING.md` (kept locally).

---

## Management commands

| Command | Description |
|---------|-------------|
| `python manage.py seed_questions` | Load/refresh the 12 quiz questions (idempotent) |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py collectstatic` | Gather static files (for production) |
| `python manage.py createsuperuser` | Create a staff/admin account |

---

## Deployment

See [`README_DEPLOY_PYTHONANYWHERE.md`](./README_DEPLOY_PYTHONANYWHERE.md) for a full step-by-step
PythonAnywhere deployment (SQLite, Python 3.12+).

> **Not suitable for Vercel** as-is: Vercel's serverless filesystem is ephemeral, so SQLite writes
> and uploaded CVs wouldn't persist. Use a persistent host (PythonAnywhere, Render, Railway, Fly.io)
> — or migrate to Postgres + object storage first.

---

## License

See [`LICENSE`](./LICENSE).
