# Deploying to PythonAnywhere

A step-by-step guide to deploy this Django app (the Onboarding Portal) to
[PythonAnywhere](https://www.pythonanywhere.com) using **MySQL** and **Python 3.12+**.

PythonAnywhere is a good fit for this project: it hosts MySQL for you, provides a persistent
filesystem (so uploaded CVs survive restarts), and runs Django natively through WSGI.

> **Database:** production runs on **MySQL**; local development stays on SQLite. The switch is made
> by a single environment variable (`DJANGO_DB_ENGINE=mysql`) — see [section 4](#4-create-the-mysql-database)
> — so no code changes are needed between the two. **MySQL on the free tier** is included.

**Before you start**, note two conventions used throughout this document:

- Replace **`USER`** with your own PythonAnywhere username wherever it appears.
- The repository is `https://github.com/samzypaul/onboarding-.git`.

Estimated time: ~15 minutes.

---

## 1. Prerequisites

- A PythonAnywhere account. The free "Beginner" tier is enough to get started — it includes MySQL.
- The project pushed to a Git repository you can clone (GitHub is used in the examples).
- **Python 3.12 or 3.13** available on your account — Django 6.0 requires 3.12 or newer. You can
  check available versions in the **Web** tab when creating the app.
- Nothing to install for MySQL itself: PythonAnywhere hosts the server, and the `mysqlclient` driver
  comes in via `requirements-prod.txt` (step 2).

> **Free-tier notes:** you get one web app at `USER.pythonanywhere.com`; you must log in at least
> once every 3 months or the app is disabled; and outbound internet access is limited to an
> allow-list. This app makes no outbound calls, so the allow-list does not affect it.

---

## 2. Get the code onto PythonAnywhere

Open a **Bash console** (Dashboard → *Consoles* → *Bash*) and run:

```bash
git clone https://github.com/samzypaul/onboarding-.git
cd onboarding-

# Create a virtualenv using the Python version your account offers (e.g. 3.13)
mkvirtualenv --python=/usr/bin/python3.13 onboarding-venv

# Install dependencies (Django, DRF, WhiteNoise) + the MySQL driver
pip install -r requirements-prod.txt
```

> **Use `requirements-prod.txt`, not `requirements.txt`,** on the server. It pulls in everything from
> `requirements.txt` *plus* `mysqlclient`, the MySQL driver. (`mysqlclient` is kept out of the base
> file because it is a C extension that doesn't build everywhere — local development runs on SQLite
> and doesn't need it.)
>
> If `pip install mysqlclient` fails with `Command 'x86_64-linux-gnu-gcc' failed`, the MySQL headers
> are missing from the image — PythonAnywhere ships them, so this normally just works. Failing that,
> `pip install mysqlclient --only-binary=:all:` forces a wheel.

The virtualenv is created at `/home/USER/.virtualenvs/onboarding-venv`. Keep this console open —
you will use it again in step 8.

---

## 3. Generate a production secret key

Django needs a unique, secret `SECRET_KEY` in production. Generate one in the same console:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the printed value. You will paste it into the WSGI file in the next step.

---

## 4. Create the MySQL database

Go to the **Databases** tab:

1. If this is your first database, set a **MySQL password** (this is separate from your
   PythonAnywhere login password) and wait for the server to initialise.
2. Under *Create a database*, enter `onboarding`. PythonAnywhere prefixes it with your username, so
   the real database name becomes **`USER$onboarding`** — the `$` is part of the name.

Note the four values you will need in the next step:

| Setting | Value |
|---------|-------|
| `DJANGO_DB_NAME` | `USER$onboarding` |
| `DJANGO_DB_USER` | `USER` (your PythonAnywhere username) |
| `DJANGO_DB_PASSWORD` | the MySQL password you just set |
| `DJANGO_DB_HOST` | `USER.mysql.pythonanywhere-services.com` |

The host is shown at the top of the **Databases** tab — copy it from there rather than typing it.

> **No code change is needed to use MySQL.** `onboarding/settings.py` reads these variables and
> switches engine when `DJANGO_DB_ENGINE=mysql`; without it, the project falls back to SQLite for
> local development. The connection is opened with `charset=utf8mb4` (so accents and emoji in the
> free-text answers round-trip correctly) and `sql_mode=STRICT_TRANS_TABLES` (so over-long values
> raise an error instead of being silently truncated).

---

## 5. Create the web app

Go to the **Web** tab → **Add a new web app**:

1. Choose **Manual configuration** (do **not** pick the "Django" option — this project already
   contains a full Django project).
2. Select the **same Python version** as the virtualenv you created (e.g. 3.13).

After the app is created, set these fields on the **Web** tab:

| Field | Value |
|-------|-------|
| Source code | `/home/USER/onboarding-` |
| Working directory | `/home/USER/onboarding-` |
| Virtualenv | `/home/USER/.virtualenvs/onboarding-venv` |

---

## 6. Configure the WSGI file

On the **Web** tab, click the **WSGI configuration file** link (it opens
`/var/www/USER_pythonanywhere_com_wsgi.py`). Delete the entire contents and replace them with:

```python
import os
import sys

# Make the project importable
path = "/home/USER/onboarding-"
if path not in sys.path:
    sys.path.insert(0, path)

# Production environment variables (read by onboarding/settings.py)
os.environ["DJANGO_SETTINGS_MODULE"] = "onboarding.settings"
os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_SECRET_KEY"] = "PASTE_THE_GENERATED_SECRET_KEY_HERE"
os.environ["DJANGO_ALLOWED_HOSTS"] = "USER.pythonanywhere.com"
os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://USER.pythonanywhere.com"

# MySQL (step 4). Without DJANGO_DB_ENGINE the project falls back to SQLite.
os.environ["DJANGO_DB_ENGINE"] = "mysql"
os.environ["DJANGO_DB_NAME"] = "USER$onboarding"
os.environ["DJANGO_DB_USER"] = "USER"
os.environ["DJANGO_DB_PASSWORD"] = "PASTE_YOUR_MYSQL_PASSWORD_HERE"
os.environ["DJANGO_DB_HOST"] = "USER.mysql.pythonanywhere-services.com"

# Start Django
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Replace `USER` everywhere, paste the secret key from step 3 and the MySQL password from step 4, then
**Save**.

**What each variable does:**

| Variable | Purpose |
|----------|---------|
| `DJANGO_DEBUG=0` | Runs in production mode (debug pages off) |
| `DJANGO_SECRET_KEY` | Cryptographic key — keep it secret and unique |
| `DJANGO_ALLOWED_HOSTS` | The domain(s) Django will serve; a mismatch returns HTTP 400 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Required for the admin login (and any form POST) to work over HTTPS |
| `DJANGO_DB_ENGINE` | `mysql` switches the project to MySQL; omit it for SQLite |
| `DJANGO_DB_NAME` / `_USER` / `_PASSWORD` / `_HOST` | MySQL connection details from step 4 |
| `DJANGO_DB_PORT` | Optional, defaults to `3306` |
| `DJANGO_DB_CONN_MAX_AGE` | Optional, defaults to `60` seconds — see below |

> **Why `CONN_MAX_AGE=60`?** Reusing connections avoids a TCP + auth handshake on every request, but
> PythonAnywhere's MySQL closes idle connections after ~300s. Holding them longer than that hands
> Django dead sockets and produces intermittent
> `(2006, 'MySQL server has gone away')` errors. 60s is comfortably under the timeout. Set
> `DJANGO_DB_CONN_MAX_AGE=0` to disable pooling entirely if you ever see that error.

> **The WSGI file holds your database password in plaintext.** It lives outside the repo
> (`/var/www/…`) and is readable only by your account — never copy these lines into `settings.py` or
> commit them.

---

## 7. Set up static and media files

Static files (CSS/JS, including the app's own stylesheet and the Django admin assets) are served by
**WhiteNoise**, which is already configured in the project — no web-server mapping is required for
them.

Uploaded **media** (applicant CVs) are *not* served by WhiteNoise, so add one static-files mapping
on the **Web** tab → **Static files** section:

| URL | Directory |
|-----|-----------|
| `/media/` | `/home/USER/onboarding-/media` |

This makes the `cv` download links (returned by the admin API and shown in the staff panel) work.

> **Note:** CVs are uploaded at the *end* of the journey, and only by applicants who pass the quiz
> (see [section 13](#13-the-pass-mark-gate-and-applicant-status)). An applicant who scored below the
> pass mark has no CV at all — the panel shows no download link for them. That is expected, not a
> broken mapping.

> Optionally, you may also map `/static/` → `/home/USER/onboarding-/staticfiles` so PythonAnywhere
> serves static files directly (slightly faster than WhiteNoise). It is not required.

---

## 8. Initialize the database and collect static files

Return to the **Bash console** from step 2 (`cd ~/onboarding-`, virtualenv active). Export the same
production variables so the management commands hit **MySQL**, not a local SQLite file, then run the
setup:

```bash
export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY="the-same-key-you-generated"
export DJANGO_ALLOWED_HOSTS="USER.pythonanywhere.com"
export DJANGO_CSRF_TRUSTED_ORIGINS="https://USER.pythonanywhere.com"

export DJANGO_DB_ENGINE=mysql
export DJANGO_DB_NAME='USER$onboarding'     # single quotes: $ must not be expanded by bash
export DJANGO_DB_USER=USER
export DJANGO_DB_PASSWORD='your-mysql-password'
export DJANGO_DB_HOST=USER.mysql.pythonanywhere-services.com

python manage.py migrate                    # create the tables in MySQL
python manage.py collectstatic --noinput    # gather static files for WhiteNoise
python manage.py seed_questions             # load the 12 quiz questions
python manage.py createsuperuser            # create your staff / admin login
```

> **Quote `USER$onboarding` with single quotes.** In double quotes bash expands `$onboarding` to an
> empty string, and `migrate` then fails with `Unknown database 'USER'`.

Confirm you are really on MySQL before going further:

```bash
python manage.py shell -c "from django.db import connection; print(connection.vendor, connection.settings_dict['NAME'])"
# -> mysql USER$onboarding
```

`createsuperuser` prompts for a username, email, and password — this account can sign in to both the
staff panel (`/panel/`) and the Django admin (`/admin/`).

**Forget the exports and you will silently create a `db.sqlite3` file instead** — the app will look
empty when it starts, because the web app (which *does* have the variables) is reading MySQL. If that
happens, `rm db.sqlite3`, re-export, and re-run the commands.

---

## 9. Go live

On the **Web** tab, click the green **Reload** button, then open:

| URL | Page |
|-----|------|
| `https://USER.pythonanywhere.com/` | Applicant portal |
| `https://USER.pythonanywhere.com/panel/` | Staff panel (log in with the superuser) |
| `https://USER.pythonanywhere.com/admin/` | Django admin |
| `https://USER.pythonanywhere.com/api/` | REST API root |

The frontend and API share one origin, so the pages call `/api/...` directly with no CORS setup.

---

## 10. Deploying updates later

Whenever new code is pushed to the repository, update the live app from the Bash console. **Re-export
the `DJANGO_DB_*` variables first** (a fresh console doesn't have them) or `migrate` will quietly
target SQLite:

```bash
cd ~/onboarding-
workon onboarding-venv
git pull
export DJANGO_DB_ENGINE=mysql DJANGO_DB_NAME='USER$onboarding' DJANGO_DB_USER=USER \
       DJANGO_DB_PASSWORD='your-mysql-password' \
       DJANGO_DB_HOST=USER.mysql.pythonanywhere-services.com
pip install -r requirements-prod.txt      # only if dependencies changed
python manage.py migrate                  # only if there are new migrations
python manage.py collectstatic --noinput  # only if static files or templates changed
```

Then click **Reload** on the **Web** tab. A reload is required for any change to take effect.

> **Tip:** put those exports in `~/.bashrc` so every new console has them, then `source ~/.bashrc`.

> **Upgrading to the two-stage intake:** this release ships migration
> `0004_application_final_submitted_at_alter_application_cv`, so `migrate` is **required**, and the
> applicant JS changed, so `collectstatic` is too. The migration makes `cv` optional at the database
> level and adds `final_submitted_at` — it is additive and does not touch existing rows, so
> applications submitted under the old single-form flow keep their CV and simply show a blank
> `final_submitted_at`.
>
> Applicants whose browsers hold a half-finished journey in `localStorage` are handled
> automatically: the portal validates the stored id against `/api/applications/{id}/status/` on load
> and restarts them at the details form if it is stale.

---

## 11. Troubleshooting

### Database (MySQL)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ImproperlyConfigured: Error loading MySQLdb module` | `mysqlclient` not installed in the virtualenv | `workon onboarding-venv && pip install -r requirements-prod.txt` |
| `(1049, "Unknown database 'USER'")` | `USER$onboarding` was written in double quotes, so bash ate the `$` | Re-export with **single** quotes |
| `(1045, "Access denied for user …")` | Wrong MySQL password (it is *not* your PythonAnywhere login) | Reset it on the **Databases** tab, update the WSGI file and your exports |
| `(2005, "Unknown server host …")` | Typo in `DJANGO_DB_HOST` | Copy the host string from the **Databases** tab |
| `(2006, "MySQL server has gone away")` | Connection idled past MySQL's ~300s timeout | Ensure `DJANGO_DB_CONN_MAX_AGE` is below 300 (default 60), or set it to `0` |
| `(1146, "Table 'USER$onboarding.application_application' doesn't exist")` | `migrate` ran against SQLite, not MySQL | Export the `DJANGO_DB_*` variables, re-run `migrate` |
| Site works but **all applicants are missing** | The console created a stray `db.sqlite3` while the web app reads MySQL | `rm db.sqlite3`, export the variables, re-run `migrate`/`seed_questions` |
| `django.db.utils.OperationalError` only on the web app | The WSGI file is missing a `DJANGO_DB_*` line | Compare it against [section 6](#6-configure-the-wsgi-file), then Reload |

### Everything else

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `DisallowedHost` / HTTP 400 | Domain not in `ALLOWED_HOSTS` | Correct `DJANGO_ALLOWED_HOSTS` in the WSGI file, then Reload |
| Admin login fails with a **CSRF** error | Trusted origin not set | Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://USER.pythonanywhere.com`, then Reload |
| Pages load but have **no styling** | `collectstatic` not run | Run `python manage.py collectstatic --noinput`, then Reload |
| Uploaded CV links return **404** | `/media/` mapping missing | Add the `/media/` static-files mapping (step 7) |
| An applicant has **no CV / empty motivation** | Status is **Fail**, so the final step never unlocked | Expected — check their status/score on the detail page |
| Final step returns **403** | Quiz unfinished, or score below the pass mark | Expected — the gate is server-side (section 13) |
| Portal **skips the details form** and 404s on quiz start | Stale `application_id` in the browser's `localStorage` (e.g. the applicant was deleted) | Fixed in the current release — the portal validates via `/api/applications/{id}/status/`. Make sure `collectstatic` ran and the browser reloaded the new `applicant.js` |
| Any page returns **HTTP 500** | See the error log | **Web** tab → *Error log*; usually a missing env var or an unmigrated database |
| `ModuleNotFoundError` | Wrong virtualenv or missing deps | Confirm the virtualenv path on the Web tab; run `pip install -r requirements-prod.txt` |
| Changes don't appear | App not reloaded | Click **Reload** on the Web tab after every change |

---

## 12. Maintenance

- **Backups:** applicant data lives in **MySQL**, uploaded CVs in the `media/` folder on disk. Back
  up both:
  ```bash
  mysqldump -u USER -h USER.mysql.pythonanywhere-services.com -p 'USER$onboarding' > backup.sql
  tar czf media-backup.tar.gz media/
  ```
  `mysqldump` prompts for the MySQL password. Download the files from the **Files** tab. Neither is
  in Git by design — do not commit them.
- **Restoring:** `mysql -u USER -h … -p 'USER$onboarding' < backup.sql`.
- **Browsing the data:** `python manage.py dbshell` opens a MySQL prompt with the app's credentials,
  or use the **Databases** tab → *MySQL console*.
- **Rotating the secret key:** generate a new key (step 3), update `DJANGO_SECRET_KEY` in the WSGI
  file, and Reload. Note this invalidates existing sessions.
- **Free-tier MySQL** has a disk quota (512 MB on Beginner). CVs live on the filesystem, not in the
  database, so the applicant tables stay small.

---

## 13. The pass-mark gate and applicant status

The applicant journey is **two-stage**: the first form collects contact/profile details only, then
the quiz runs, and the **motivation, expectations and CV upload are only offered to applicants who
score at least the pass mark**.

The pass mark is a constant in the code, not an environment variable:

```python
# application/models.py
PASS_MARK = 7        # out of 12 seeded questions
```

To change it, edit that line, `git pull` on the server, and **Reload**. No migration is needed.

**Every applicant carries a status derived from that number:**

| Status | Meaning |
|--------|---------|
| **Pass** | Quiz finished with a score **≥ 7** — the final step (CV, motivation, expectations) is unlocked |
| **Fail** | Quiz finished **below 7** — the journey ends at the results screen; no CV is ever collected |
| **Pending** | Quiz not started, or still in progress |

The status is **computed from the score on every read**, not stored in a column. Two consequences
worth knowing:

- It can never drift out of sync with the actual answers, and there is no migration or backfill when
  you change `PASS_MARK` — **every applicant is re-graded immediately** on the next page load. Raising
  the mark to 8 will flip existing 7-scorers from Pass to Fail (applicants who already submitted keep
  their CV; only the label changes).
- It is separate from **`decision`** (Pending/Selected/Rejected), which is the staff's own review
  outcome and *is* stored. Status is about the quiz; decision is about your judgement.

Staff can see the status as a badge in the applicants table and on the detail page, filter the list
by it (**All statuses / Pass / Fail / Pending**), and it is exposed via the API as `status` on
`GET /api/admin/applications/` and `…/{id}/`, plus `?status=pass|fail|pending` for filtering.

The gate itself is enforced in `POST /api/applications/{id}/finalize/`, which returns **403** unless
the quiz is complete with `score >= PASS_MARK`. Hiding the form in the browser is a convenience only,
so a tampered client still cannot upload a CV without passing.

> If you change the number of seeded questions in `seed_questions.py`, revisit `PASS_MARK` — it is an
> absolute count, not a percentage. Re-running `seed_questions` after editing that list updates
> changed questions and retires removed ones (`is_active=False`, so past quizzes stay auditable);
> **already-completed quizzes keep their original questions and scores**, so a status can change only
> if you move `PASS_MARK` itself.

---

## Appendix A — Staying on SQLite (optional)

MySQL is the documented production setup, but nothing forces it: **omit `DJANGO_DB_ENGINE`** (or set
it to `sqlite`) and the project uses `db.sqlite3` in the project folder, which persists on
PythonAnywhere's disk. You can then install `requirements.txt` instead of `requirements-prod.txt`.

SQLite is fine for low applicant volume and is what local development uses. Prefer MySQL in
production for concurrent writes (SQLite locks the whole file on write, so simultaneous quiz
submissions can hit `database is locked`) and for the easier `mysqldump` backup story.

To migrate existing SQLite data into MySQL:

```bash
# with the SQLite settings active (no DJANGO_DB_* exports)
python manage.py dumpdata --natural-foreign --natural-primary \
    -e contenttypes -e auth.Permission -e sessions > data.json

# then with the MySQL variables exported
python manage.py migrate
python manage.py loaddata data.json
```

Copy the `media/` folder across as well — the database only stores CV *paths*, not the files.

---

## Appendix B — Stricter HTTPS (optional)

The project sends secure cookies and trusts the PythonAnywhere HTTPS proxy in production. To also
force HTTPS and enable HSTS, add the following inside the `if not DEBUG:` block in
`onboarding/settings.py`:

```python
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000            # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
```

Enable HSTS only once you are certain the site will always be served over HTTPS — the browser will
refuse plain HTTP for the duration of `SECURE_HSTS_SECONDS`.
