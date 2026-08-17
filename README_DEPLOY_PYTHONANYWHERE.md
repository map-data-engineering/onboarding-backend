# Deploying to PythonAnywhere

A step-by-step guide to deploy this Django app (the Onboarding Portal) to
[PythonAnywhere](https://www.pythonanywhere.com) using **MySQL** and **Python 3.12+**.

PythonAnywhere is a good fit for this project: it hosts MySQL for you, provides a persistent
filesystem (so uploaded CVs survive restarts), and runs Django natively through WSGI.

> **Database:** production runs on **MySQL**; local development stays on SQLite. The switch is made
> by a single environment variable (`DJANGO_DB_ENGINE=mysql`) — see [section 4](#4-create-the-mysql-database)
> — so no code changes are needed between the two. **MySQL on the free tier** is included.

Estimated time: ~15 minutes.

---

## 0. Your values (read this first)

Every console block below starts from **two shell variables**, so your username appears in exactly
one place instead of a dozen. Set them at the top of every new Bash console:

```bash
export PA_USER=MAPDET            # <-- your PythonAnywhere username
export PA_PROJECT=onboarding-backend    # <-- the folder the repo clones into
```

After that, `$PA_USER` and `$PA_PROJECT` expand for you and nothing needs hand-editing.

> **In Web-tab form fields** (source code path, virtualenv, WSGI file) there is no shell to expand
> variables, so those are written out in full using `MAPDET` / `onboarding-backend` as the example.
> **Swap in your own username there.** Leaving a placeholder in the database name is the single most
> common way this deployment fails — it produces
> `(1044, "Access denied for user 'you'@'%' to database 'USER$onboarding'")`, because MySQL then
> looks for a database owned by a user literally called `USER`.

| Thing | Value |
|-------|-------|
| Repository | `https://github.com/map-data-engineering/onboarding-backend.git` |
| Project folder | `/home/$PA_USER/onboarding-backend` |
| Virtualenv | `/home/$PA_USER/.virtualenvs/onboarding-venv` |
| Site | `https://$PA_USER.pythonanywhere.com` |
| Database | `$PA_USER$onboarding-backend` (the `$` between the two parts is part of the name) |

---

## 1. Prerequisites

- A PythonAnywhere account. The free "Beginner" tier is enough to get started — it includes MySQL.
- The project pushed to a Git repository you can clone (GitHub is used in the examples).
- **Python 3.12 or 3.13** available on your account — Django 6.0 requires 3.12 or newer. You can
  check available versions in the **Web** tab when creating the app.
- Nothing to install for MySQL itself: PythonAnywhere hosts the server, and the `mysqlclient` driver
  comes in via `requirements-prod.txt` (step 2).

> **Free-tier notes:** you get one web app at `<username>.pythonanywhere.com`; you must log in at least
> once every 3 months or the app is disabled; and outbound internet access is limited to an
> allow-list. This app makes no outbound calls, so the allow-list does not affect it.

---

## 2. Get the code onto PythonAnywhere

Open a **Bash console** (Dashboard → *Consoles* → *Bash*) and run:

```bash
export PA_USER=MAPDET                    # your username
export PA_PROJECT=onboarding-backend

git clone https://github.com/map-data-engineering/onboarding-backend.git
cd "$PA_PROJECT"

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

The virtualenv is created at `/home/$PA_USER/.virtualenvs/onboarding-venv`. Keep this console open —
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
   the real name becomes **`MAPDET$onboarding`** — the `$` is part of the name.

> **Stick to letters, numbers and underscores.** The database name does *not* have to match the
> project folder, and a hyphen (`onboarding-backend`) is a needless risk — it may be rejected or
> altered on creation, leaving you connecting to a name that was never made.

**Copy the resulting name from the Databases tab** rather than assembling it by hand; the page lists
it verbatim. Same for the host. These are the four values the next step needs:

| Setting | Example value |
|---------|---------------|
| `DJANGO_DB_NAME` | `MAPDET$onboarding` |
| `DJANGO_DB_USER` | `MAPDET` (your PythonAnywhere username) |
| `DJANGO_DB_PASSWORD` | the MySQL password you just set |
| `DJANGO_DB_HOST` | `MAPDET.mysql.pythonanywhere-services.com` |

**Verify it exists before going further** — this is faster than reading a Django traceback later:

```bash
mysql -u MAPDET -h MAPDET.mysql.pythonanywhere-services.com -p -e "SHOW DATABASES;"
```

Whatever that prints is the only name that will work. If the list shows just `information_schema`,
the database was never created.

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

After the app is created, set these fields on the **Web** tab (substituting your username — these are
form fields, so `$PA_USER` will *not* expand here):

| Field | Value |
|-------|-------|
| Source code | `/home/MAPDET/onboarding-backend` |
| Working directory | `/home/MAPDET/onboarding-backend` |
| Virtualenv | `/home/MAPDET/.virtualenvs/onboarding-venv` |

---

## 6. Configure the WSGI file

On the **Web** tab, click the **WSGI configuration file** link (it opens
`/var/www/MAPDET_pythonanywhere_com_wsgi.py`). Delete the entire contents and replace them with the
block below.

This file is plain Python, so it derives every path and hostname from **one** `PA_USER` line —
change that and nothing else:

```python
import os
import sys

PA_USER = "MAPDET"                      # <-- your PythonAnywhere username: the only line to edit
PA_PROJECT = "onboarding-backend"       # <-- the folder the repo was cloned into

# Make the project importable
path = f"/home/{PA_USER}/{PA_PROJECT}"
if path not in sys.path:
    sys.path.insert(0, path)

# Production environment variables (read by onboarding/settings.py)
os.environ["DJANGO_SETTINGS_MODULE"] = "onboarding.settings"
os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_SECRET_KEY"] = "PASTE_THE_GENERATED_SECRET_KEY_HERE"
os.environ["DJANGO_ALLOWED_HOSTS"] = f"{PA_USER}.pythonanywhere.com"
os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = f"https://{PA_USER}.pythonanywhere.com"

# MySQL (step 4). Without DJANGO_DB_ENGINE the project falls back to SQLite.
os.environ["DJANGO_DB_ENGINE"] = "mysql"
os.environ["DJANGO_DB_NAME"] = f"{PA_USER}${PA_PROJECT}"
os.environ["DJANGO_DB_USER"] = PA_USER
os.environ["DJANGO_DB_PASSWORD"] = "PASTE_YOUR_MYSQL_PASSWORD_HERE"
os.environ["DJANGO_DB_HOST"] = f"{PA_USER}.mysql.pythonanywhere-services.com"

# Start Django
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Set `PA_USER`/`PA_PROJECT`, paste the secret key from step 3 and the MySQL password from step 4, then
**Save**.

> Check `DJANGO_DB_NAME` against the **Databases** tab after saving. The `f"{PA_USER}${PA_PROJECT}"`
> form assumes you named the database after the project folder; if you called it something else, spell
> it out literally instead.

> **These values must match your console exports (step 8) exactly.** If the two disagree, the site and
> your management commands talk to *different databases* — the classic symptom is a working site with
> no questions and no applicants.

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

Uploaded **media** (applicant CVs) needs **no mapping at all**. CVs are downloaded through
`GET /api/admin/applications/{id}/cv/`, which streams the file from `MEDIA_ROOT` after authorising
the caller.

That endpoint accepts **either** staff credentials (a token or an admin session) **or** a `?sig=`
signature. The signature exists because a browser following a plain `<a href>` sends no
`Authorization` header — so a frontend can render the `cv` field straight into a link and it just
works. Only staff can obtain one: it is minted by the applicant-detail endpoint, which is itself
staff-only. It is bound to a single applicant and **expires after 15 minutes**
(`CV_LINK_MAX_AGE` in `application/cv_links.py`), so a leaked URL goes dead — unlike the old
`/media/` path, which stayed valid forever.

> **Do not add a `/media/` static-files mapping.** Earlier versions of this guide did, because the
> panel linked straight at `MEDIA_URL`. That mapping has PythonAnywhere's webserver serve the folder
> directly, bypassing Django — so **any CV is downloadable by anyone who knows or guesses its URL**,
> with no login. If you deployed under the old instructions, remove the `/media/` row from the Web
> tab and Reload.

Pasting the URL **without** its `?sig=` into a browser returns **401 Unauthorized**. That is correct,
not a fault — the address bar sends no credentials. Copy the whole link including the signature, or
use a token:

```bash
curl -H "Authorization: Token YOUR_TOKEN" -OJ \
     https://MAPDET.pythonanywhere.com/api/admin/applications/<id>/cv/
```

> **Note:** CVs are uploaded at the *end* of the journey, and only by applicants who pass the quiz
> (see [section 13](#13-the-pass-mark-gate-and-applicant-status)). An applicant who scored below the
> pass mark has no CV at all — the panel shows no download link for them. That is expected, not a
> broken mapping.

> Optionally, you may also map `/static/` → `/home/MAPDET/onboarding-backend/staticfiles` so
> PythonAnywhere serves static files directly (slightly faster than WhiteNoise). It is not required.

---

## 8. Initialize the database and collect static files

Return to the **Bash console** from step 2 (virtualenv active). The management commands read the same
environment variables as the web app, so export them here too — otherwise `migrate` builds a local
SQLite file and the web app keeps talking to an empty MySQL.

**Step 8a — set the variables.** Only the first three lines need your input:

```bash
export PA_USER=MAPDET                       # your PythonAnywhere username
export PA_PROJECT=onboarding-backend        # the repo folder / database suffix
export DJANGO_DB_PASSWORD='your-mysql-password'

cd ~/"$PA_PROJECT"
workon onboarding-venv

export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY="the-same-key-you-generated"
export DJANGO_ALLOWED_HOSTS="$PA_USER.pythonanywhere.com"
export DJANGO_CSRF_TRUSTED_ORIGINS="https://$PA_USER.pythonanywhere.com"

export DJANGO_DB_ENGINE=mysql
export DJANGO_DB_NAME="$PA_USER\$$PA_PROJECT"   # \$ is a literal $, not a variable
export DJANGO_DB_USER="$PA_USER"
export DJANGO_DB_HOST="$PA_USER.mysql.pythonanywhere-services.com"
```

**Step 8b — check before you run.** This catches the two mistakes that account for most failed
deployments; both print `OK` when correct:

```bash
case "$DJANGO_DB_NAME" in
  "")     echo "BAD: DJANGO_DB_NAME is empty" ;;
  *USER*) echo "BAD: placeholder 'USER' left in [$DJANGO_DB_NAME]" ;;
  *'$'*)  echo "OK: database is [$DJANGO_DB_NAME]" ;;
  *)      echo "BAD: no '\$' in [$DJANGO_DB_NAME] - bash expanded it away" ;;
esac
python manage.py shell -c "from django.db import connection as c; c.ensure_connection(); print('OK:', c.vendor, c.settings_dict['NAME'])"
```

The second command opens a real connection, so it fails *here* — with a one-line error instead of a
page of traceback — if the name, password or host is wrong. Fix it before continuing.

**Step 8c — run the setup:**

```bash
python manage.py migrate                    # create the tables in MySQL
python manage.py collectstatic --noinput    # gather static files for WhiteNoise
python manage.py seed_questions             # load the 12 quiz questions
python manage.py createsuperuser            # create your staff / admin login
```

`createsuperuser` prompts for a username, email, and password — this account can sign in to both the
staff panel (`/panel/`) and the Django admin (`/admin/`), with full reviewer rights.

**Optional — a read-only account** for colleagues who should see applicants but change nothing:

```bash
python manage.py create_viewer amina --email amina@example.org
```

It prompts for a password. The account can sign in to `/panel/` and browse counts, the applicant
list, details, CV downloads and quiz breakdowns, but **cannot** set decisions, run bulk actions,
delete, or export the CSV — the panel hides those controls and the API returns 403 either way. Use
`--revoke` to promote one to a full reviewer later. (Membership of the "Applicant viewers" group is
what marks the account, so you can also flip it from Django admin.)

**If step 8b reported a problem, read this before retrying:**

- **`(1044, "Access denied … to database 'USER$…'")`** — a placeholder survived. The name must start
  with *your* username. This is the most common failure; `collectstatic` still succeeds (it never
  touches the database), which can make the run look half-successful.
- **`Unknown database 'MAPDET'`** — the `$` was expanded by bash. Use `\$` inside double quotes, or
  single-quote the whole literal value: `export DJANGO_DB_NAME='MAPDET$onboarding-backend'`.
- **Padded values** — `" MAPDET.pythonanywhere.com "` is a real hazard when pasting. `settings.py`
  trims surrounding whitespace from `DJANGO_ALLOWED_HOSTS` and strips it out of
  `DJANGO_CSRF_TRUSTED_ORIGINS` (a space after `https://` breaks the origin), so these no longer
  cause `DisallowedHost` — but keep them clean anyway.
- **Forgot the exports entirely?** You will have created a stray `db.sqlite3`. `rm db.sqlite3`,
  export, and re-run — otherwise the site looks empty because the web app reads MySQL.

---

## 9. Go live

On the **Web** tab, click the green **Reload** button, then open:

| URL | Page |
|-----|------|
| `https://MAPDET.pythonanywhere.com/` | Applicant portal |
| `https://MAPDET.pythonanywhere.com/panel/` | Staff panel (log in with the superuser) |
| `https://MAPDET.pythonanywhere.com/admin/` | Django admin |
| `https://MAPDET.pythonanywhere.com/api/` | REST API root |

The frontend and API share one origin, so the pages call `/api/...` directly with no CORS setup.

**Smoke-test the whole journey** before announcing the URL: open the portal, fill in the details form,
click Next, answer the quiz, and confirm that a score of 7+ unlocks the final CV/motivation step and
that the CV downloads from the staff panel afterwards. Note: the CV must be a PDF (max 2 pages), and 
motivation/expectations are required (max 300 words each). That exercises MySQL writes, the CV download
endpoint and the pass-mark gate in one pass.

---

## 10. Deploying updates later

Whenever new code is pushed to the repository, update the live app from the Bash console. **Re-export
the `DJANGO_DB_*` variables first** (a fresh console doesn't have them) or `migrate` will quietly
target SQLite:

```bash
export PA_USER=MAPDET PA_PROJECT=onboarding-backend
cd ~/"$PA_PROJECT"
workon onboarding-venv
git pull

export DJANGO_DB_ENGINE=mysql
export DJANGO_DB_NAME="$PA_USER\$$PA_PROJECT"
export DJANGO_DB_USER="$PA_USER"
export DJANGO_DB_PASSWORD='your-mysql-password'
export DJANGO_DB_HOST="$PA_USER.mysql.pythonanywhere-services.com"

pip install -r requirements-prod.txt      # only if dependencies changed
python manage.py migrate                  # only if there are new migrations
python manage.py seed_questions           # only if the question list changed
python manage.py collectstatic --noinput  # only if static files or templates changed
python manage.py check                    # reports application.W001 if a static file was missed
```

Then click **Reload** on the **Web** tab. A reload is required for any change to take effect.

> **If `check` reports `application.W001`, do not skip it.** It means `STATIC_ROOT` holds a different
> version of a `.js`/`.css` file (or of its `.gz`) than the source, which is the one failure that
> produces no error anywhere: templates are read fresh on every request, so the page renders the new
> markup, while WhiteNoise serves months-old JavaScript underneath it. Buttons appear and do nothing.
> Re-run `collectstatic --noinput` and Reload; if the warning persists, `collectstatic --noinput --clear`
> rebuilds the directory from scratch.

> **Tip:** put the `export` lines in `~/.bashrc` so every new console already has them
> (`source ~/.bashrc` to apply immediately). Skipping them is what silently creates a stray
> `db.sqlite3` — re-run the step-8b check if you are unsure.

> **`db.sqlite3` is git-ignored, so question and applicant data never travel with a `git pull`.**
> After a release that changes the question list, `seed_questions` must be re-run on the server or the
> live quiz keeps serving the old set.

> **Upgrading to the signed CV download:** the panel JS changed, so **`collectstatic` is required** —
> without it WhiteNoise keeps serving the old `panel.js`/`api.js` and the Download CV button still
> points at the dead `/media/` URL. No migration is needed. Also remove the `/media/` static-files
> mapping if you added it under the old instructions
> ([section 7](#7-set-up-static-and-media-files)); existing CVs stay where they are and keep working.
>
> **Standalone frontends need no change.** They render the `cv` field as a link, and that field now
> carries a signature, so the link works as it always did. Rotating `DJANGO_SECRET_KEY` invalidates
> every outstanding signature — harmless, since a page reload mints new ones.

> **Upgrading to the CSV export:** run `collectstatic --noinput --clear` once (not just `collectstatic`).
> Static compression used to be enabled only when `DEBUG` was off, so servers carry `.gz` files that
> `collectstatic` will not refresh on its own — and those are what browsers actually receive. `--clear`
> rebuilds them. Compression is now on unconditionally, so ordinary `collectstatic` keeps them in step
> from here on.

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
| `(1044, "Access denied … to database 'USER$onboarding'")` | The literal placeholder `USER` was left in the database name | Substitute your own username: `export DJANGO_DB_NAME='yourusername$onboarding'` |
| `(1049, "Unknown database 'USER'")` | `USER$onboarding` was written in double quotes, so bash ate the `$` | Re-export with **single** quotes |
| `(1044, …)` with the **right** username | The database doesn't exist, or the name differs from what you typed (a hyphen may have been rejected on creation). Note that 1044 means authentication *succeeded* — only the database is wrong | List what actually exists: `mysql -u USER -h USER.mysql.pythonanywhere-services.com -p -e "SHOW DATABASES;"` and use that name verbatim |
| `(1045, "Access denied for user …")` | Wrong MySQL password (it is *not* your PythonAnywhere login) | Reset it on the **Databases** tab, update the WSGI file and your exports |
| `(2005, "Unknown server host …")` | Typo in `DJANGO_DB_HOST` | Copy the host string from the **Databases** tab |
| `(2006, "MySQL server has gone away")` | Connection idled past MySQL's ~300s timeout | Ensure `DJANGO_DB_CONN_MAX_AGE` is below 300 (default 60), or set it to `0` |
| `(1146, "Table 'USER$onboarding.application_application' doesn't exist")` | `migrate` ran against SQLite, not MySQL | Export the `DJANGO_DB_*` variables, re-run `migrate` |
| Site works but **all applicants are missing** | The console created a stray `db.sqlite3` while the web app reads MySQL | `rm db.sqlite3`, export the variables, re-run `migrate`/`seed_questions` |
| `django.db.utils.OperationalError` only on the web app | The WSGI file is missing a `DJANGO_DB_*` line | Compare it against [section 6](#6-configure-the-wsgi-file), then Reload |

### Everything else

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `DisallowedHost` / HTTP 400 | Domain not in `ALLOWED_HOSTS` | Correct `DJANGO_ALLOWED_HOSTS` in the WSGI file, then Reload. Stray spaces around the value are stripped automatically |
| Admin login fails with a **CSRF** error | Trusted origin not set | Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://MAPDET.pythonanywhere.com` (your host), then Reload |
| Panel sign-in fails with **"CSRF token from the 'X-Csrftoken' HTTP header has incorrect length"** | The page served no `<meta name="csrf-token">`, so the panel sent an empty header. Only affects staff who are *also* signed in to `/admin/` in the same browser — that session is what makes DRF enforce CSRF at all | Fixed in the current release. Run `collectstatic --noinput` and Reload; the tag is in `base.html` and `api.js` now falls back to the `csrftoken` cookie |
| Pages load but have **no styling** | `collectstatic` not run | Run `python manage.py collectstatic --noinput`, then Reload |
| Download CV returns **404** in the panel | The row references a file that is no longer in `media/` (e.g. restored database without restoring `media/`) | Check `ls media/cvs/`; restore the media backup (section 12) |
| Download CV returns **401** | The link lost its `?sig=`, or the staff token expired | Reload the applicant page to mint a fresh link; log out and back in if the whole panel 401s |
| Download CV returns **403** "link has expired" | The page sat open longer than `CV_LINK_MAX_AGE` (15 min) | Reload the applicant detail page — that mints a new signature |
| A panel button (Download CV, **Export CSV**, …) does nothing when clicked | The browser is running an old `panel.js` — most often a stale `panel.js.gz`, which WhiteNoise serves in preference to the plain file | Run `collectstatic --noinput`, then Reload. `manage.py check` now reports this as `application.W001` before you deploy; `curl` will *not* show it, because it does not ask for gzip |
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
  mysqldump -u "$PA_USER" -h "$PA_USER.mysql.pythonanywhere-services.com" \
            -p "$PA_USER\$$PA_PROJECT" > backup-$(date +%F).sql
  tar czf media-backup-$(date +%F).tar.gz media/
  ```
  `mysqldump` prompts for the MySQL password. Download the files from the **Files** tab. Neither is
  in Git by design — do not commit them.
- **Restoring:** `mysql -u "$PA_USER" -h … -p "$PA_USER\$$PA_PROJECT" < backup.sql`.
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
| **Pass** | Quiz finished with a score **≥ 7** — the final step (PDF CV, motivation, expectations) is unlocked |
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

---

## Appendix C — A separate frontend (CORS)

The portal and staff panel are served by Django itself, same-origin, so **the deployment above needs
no CORS configuration**. If you also run a standalone frontend on another domain (a Vite/Vercel app,
say), it must be listed in `onboarding/settings.py`:

```python
CORS_ALLOWED_ORIGINS = [
    "https://your-frontend.vercel.app",
    "http://localhost:5173",
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://your-frontend-.*\.vercel\.app$",   # Vercel preview deployments
]
```

These are hard-coded rather than environment-driven, so adding a domain means editing the file,
committing, `git pull` on the server and **Reload**. `CORS_ALLOW_CREDENTIALS` is `False`: the
applicant API needs no cookies, and the staff API authenticates with an `Authorization: Token …`
header, which is unaffected.

> A browser calling the API from an unlisted origin fails with a CORS error in the console while
> `curl` and Thunder Client succeed — those ignore CORS entirely. If the API works in a REST client
> but not in the browser, this list is the first thing to check.
