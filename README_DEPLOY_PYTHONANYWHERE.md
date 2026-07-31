# Deploying to PythonAnywhere

A step-by-step guide to deploy this Django app (the Onboarding Portal) to
[PythonAnywhere](https://www.pythonanywhere.com) using **SQLite** and **Python 3.12+**.

PythonAnywhere is a good fit for this project: it provides a persistent filesystem (so the SQLite
database and uploaded CVs survive restarts) and runs Django natively through WSGI.

**Before you start**, note two conventions used throughout this document:

- Replace **`USER`** with your own PythonAnywhere username wherever it appears.
- The repository is `https://github.com/samzypaul/onboarding-.git`.

Estimated time: ~15 minutes.

---

## 1. Prerequisites

- A PythonAnywhere account. The free "Beginner" tier is enough to get started.
- The project pushed to a Git repository you can clone (GitHub is used in the examples).
- **Python 3.12 or 3.13** available on your account — Django 6.0 requires 3.12 or newer. You can
  check available versions in the **Web** tab when creating the app.

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

# Install dependencies (Django, DRF, WhiteNoise)
pip install -r requirements.txt
```

The virtualenv is created at `/home/USER/.virtualenvs/onboarding-venv`. Keep this console open —
you will use it again in step 6.

---

## 3. Generate a production secret key

Django needs a unique, secret `SECRET_KEY` in production. Generate one in the same console:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the printed value. You will paste it into the WSGI file in the next step.

---

## 4. Create the web app

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

## 5. Configure the WSGI file

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

# Start Django
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Replace `USER` (three places), paste the secret key from step 3, then **Save**.

**What each variable does:**

| Variable | Purpose |
|----------|---------|
| `DJANGO_DEBUG=0` | Runs in production mode (debug pages off) |
| `DJANGO_SECRET_KEY` | Cryptographic key — keep it secret and unique |
| `DJANGO_ALLOWED_HOSTS` | The domain(s) Django will serve; a mismatch returns HTTP 400 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Required for the admin login (and any form POST) to work over HTTPS |

---

## 6. Set up static and media files

Static files (CSS/JS, including the app's own stylesheet and the Django admin assets) are served by
**WhiteNoise**, which is already configured in the project — no web-server mapping is required for
them.

Uploaded **media** (applicant CVs) are *not* served by WhiteNoise, so add one static-files mapping
on the **Web** tab → **Static files** section:

| URL | Directory |
|-----|-----------|
| `/media/` | `/home/USER/onboarding-/media` |

This makes the `cv` download links (returned by the admin API and shown in the staff panel) work.

> Optionally, you may also map `/static/` → `/home/USER/onboarding-/staticfiles` so PythonAnywhere
> serves static files directly (slightly faster than WhiteNoise). It is not required.

---

## 7. Initialize the database and collect static files

Return to the **Bash console** from step 2 (`cd ~/onboarding-`, virtualenv active). Export the same
production variables so the management commands use production settings, then run the setup:

```bash
export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY="the-same-key-you-generated"
export DJANGO_ALLOWED_HOSTS="USER.pythonanywhere.com"
export DJANGO_CSRF_TRUSTED_ORIGINS="https://USER.pythonanywhere.com"

python manage.py migrate                    # create the database tables
python manage.py collectstatic --noinput    # gather static files for WhiteNoise
python manage.py seed_questions             # load the 12 quiz questions
python manage.py createsuperuser            # create your staff / admin login
```

`createsuperuser` prompts for a username, email, and password — this account can sign in to both the
staff panel (`/panel/`) and the Django admin (`/admin/`).

---

## 8. Go live

On the **Web** tab, click the green **Reload** button, then open:

| URL | Page |
|-----|------|
| `https://USER.pythonanywhere.com/` | Applicant portal |
| `https://USER.pythonanywhere.com/panel/` | Staff panel (log in with the superuser) |
| `https://USER.pythonanywhere.com/admin/` | Django admin |
| `https://USER.pythonanywhere.com/api/` | REST API root |

The frontend and API share one origin, so the pages call `/api/...` directly with no CORS setup.

---

## 9. Deploying updates later

Whenever new code is pushed to the repository, update the live app from the Bash console:

```bash
cd ~/onboarding-
workon onboarding-venv
git pull
pip install -r requirements.txt          # only if dependencies changed
python manage.py migrate                  # only if there are new migrations
python manage.py collectstatic --noinput  # only if static files or templates changed
```

Then click **Reload** on the **Web** tab. A reload is required for any change to take effect.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `DisallowedHost` / HTTP 400 | Domain not in `ALLOWED_HOSTS` | Correct `DJANGO_ALLOWED_HOSTS` in the WSGI file, then Reload |
| Admin login fails with a **CSRF** error | Trusted origin not set | Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://USER.pythonanywhere.com`, then Reload |
| Pages load but have **no styling** | `collectstatic` not run | Run `python manage.py collectstatic --noinput`, then Reload |
| Uploaded CV links return **404** | `/media/` mapping missing | Add the `/media/` static-files mapping (step 6) |
| Any page returns **HTTP 500** | See the error log | **Web** tab → *Error log*; usually a missing env var or an unmigrated database |
| `ModuleNotFoundError` | Wrong virtualenv or missing deps | Confirm the virtualenv path on the Web tab; run `pip install -r requirements.txt` |
| Changes don't appear | App not reloaded | Click **Reload** on the Web tab after every change |

---

## 11. Maintenance

- **Backups:** application data lives in `db.sqlite3` and the `media/` folder on the PythonAnywhere
  disk. Both are excluded from Git by design. Download them periodically (Files tab or `tar` in a
  console) to keep backups. Do not commit them to the repository.
- **Rotating the secret key:** generate a new key (step 3), update `DJANGO_SECRET_KEY` in the WSGI
  file, and Reload. Note this invalidates existing sessions.

---

## Appendix A — Using MySQL instead of SQLite (optional)

SQLite is fine for low-to-moderate applicant volume. To use PythonAnywhere's MySQL instead:

1. **Databases** tab → set a MySQL password and create a database, e.g. `USER$onboarding`.
2. Install the driver in the virtualenv:
   ```bash
   pip install mysqlclient
   ```
3. In `onboarding/settings.py`, replace the `DATABASES` block with:
   ```python
   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.mysql",
           "NAME": "USER$onboarding",
           "USER": "USER",
           "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
           "HOST": "USER.mysql.pythonanywhere-services.com",
           "OPTIONS": {"charset": "utf8mb4"},
       }
   }
   ```
4. Add `os.environ["DJANGO_DB_PASSWORD"] = "..."` to the WSGI file (and `export` it in the console).
5. Re-run `python manage.py migrate` and `python manage.py seed_questions`, then Reload.

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
