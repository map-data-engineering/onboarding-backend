# Deploying to PythonAnywhere

Step-by-step guide to deploy this Django onboarding app to **PythonAnywhere** using **SQLite** and
**Python 3.12+** (keeps Django 6.0). PythonAnywhere is a good fit: it has a persistent filesystem, so
your database and uploaded CVs survive restarts, and it runs Django natively via WSGI.

Throughout, replace **`USER`** with your PythonAnywhere username, and note your repo is
`https://github.com/samzypaul/onboarding-.git`.

---

## 1. Prerequisites
- A PythonAnywhere account (the free "Beginner" tier is enough to start).
- Your code pushed to GitHub (already done — `samzypaul/onboarding-`).
- Confirm your account offers **Python 3.12 or 3.13** (Django 6.0 requires 3.12+).

> Free-tier notes: you get one web app at `USER.pythonanywhere.com`; log in at least every 3 months
> or the app is disabled; outbound internet is limited to a whitelist (this app makes no external
> calls, so that's fine).

---

## 2. Get the code onto PythonAnywhere

Open a **Bash console** (Dashboard → *Consoles* → *Bash*):

```bash
git clone https://github.com/samzypaul/onboarding-.git
cd onboarding-

# Create a virtualenv (use the Python version your account has, e.g. 3.13)
mkvirtualenv --python=/usr/bin/python3.13 onboarding-venv
pip install -r requirements.txt
```

The virtualenv is now at `/home/USER/.virtualenvs/onboarding-venv`. Keep this console open.

---

## 3. Generate a production SECRET_KEY

Still in the Bash console (virtualenv active):

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the printed value — you'll paste it into the WSGI file next.

---

## 4. Create the web app

Go to the **Web** tab → **Add a new web app**:
1. Choose **Manual configuration** (NOT the "Django" option — we already have a project).
2. Select the **same Python version** as your virtualenv (e.g. 3.13).

Then, on the Web tab, set:
- **Source code:** `/home/USER/onboarding-`
- **Working directory:** `/home/USER/onboarding-`
- **Virtualenv:** `/home/USER/.virtualenvs/onboarding-venv`

---

## 5. Configure the WSGI file

On the Web tab, click the **WSGI configuration file** link (opens
`/var/www/USER_pythonanywhere_com_wsgi.py`). **Delete everything** and replace it with:

```python
import os
import sys

# --- Project path ---
path = "/home/USER/onboarding-"
if path not in sys.path:
    sys.path.insert(0, path)

# --- Production environment variables ---
os.environ["DJANGO_SETTINGS_MODULE"] = "onboarding.settings"
os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_SECRET_KEY"] = "PASTE_THE_GENERATED_SECRET_KEY_HERE"
os.environ["DJANGO_ALLOWED_HOSTS"] = "USER.pythonanywhere.com"
os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://USER.pythonanywhere.com"

# --- Start Django ---
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Replace `USER` (3 places) and paste your generated `DJANGO_SECRET_KEY`. **Save.**

> Why these matter: `DJANGO_DEBUG=0` turns off debug mode; `ALLOWED_HOSTS` must list your domain or
> Django returns `400`; `CSRF_TRUSTED_ORIGINS` is required for the admin login (and any session POST)
> to work over HTTPS. All are read by `onboarding/settings.py`.

---

## 6. Map static & media URLs

Django doesn't serve static/media in production — PythonAnywhere does. On the **Web** tab, under
**Static files**, add two mappings:

| URL        | Directory                              |
|------------|----------------------------------------|
| `/static/` | `/home/USER/onboarding-/staticfiles`   |
| `/media/`  | `/home/USER/onboarding-/media`         |

- `/static/` serves the Django admin CSS/JS (and any app assets).
- `/media/` serves uploaded CVs, so the `cv` URLs returned by the admin API are downloadable.

---

## 7. Initialize the database & static files

Back in the **Bash console** (`cd ~/onboarding-`, virtualenv active). These env vars let
`manage.py` run with the same production settings:

```bash
export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY="the-same-key-you-generated"
export DJANGO_ALLOWED_HOSTS="USER.pythonanywhere.com"
export DJANGO_CSRF_TRUSTED_ORIGINS="https://USER.pythonanywhere.com"

python manage.py migrate            # create the SQLite tables
python manage.py collectstatic --noinput   # gather static into staticfiles/
python manage.py seed_questions     # load the 12 quiz questions
python manage.py createsuperuser    # create your staff/admin login
```

---

## 8. Go live

On the **Web** tab, click the big green **Reload** button. Then visit:

- **Applicant portal:** `https://USER.pythonanywhere.com/`
- **Staff panel:** `https://USER.pythonanywhere.com/panel/`
- **Django admin:** `https://USER.pythonanywhere.com/admin/`
- **API root example:** `https://USER.pythonanywhere.com/api/admin/login/`

Everything is same-origin, so the frontend JS calls `/api/...` with **no CORS setup needed**.

---

## 9. Deploying updates later

When you push new code to GitHub:

```bash
cd ~/onboarding-
git pull
workon onboarding-venv
pip install -r requirements.txt          # only if requirements changed
python manage.py migrate                 # only if there are new migrations
python manage.py collectstatic --noinput # only if static/templates changed
```
Then hit **Reload** on the Web tab.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `DisallowedHost` / `400` | Domain not in `ALLOWED_HOSTS` | Fix `DJANGO_ALLOWED_HOSTS` in the WSGI file, Reload |
| Admin login fails with **CSRF** error | Missing trusted origin | Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://USER.pythonanywhere.com`, Reload |
| Admin page has **no styling** | Static not collected/mapped | Run `collectstatic`; check the `/static/` mapping path |
| Uploaded CV links `404` | `/media/` not mapped | Add the `/media/` static-files mapping |
| `500` on any page | Check the **error log** | Web tab → *Error log*; usually a missing env var or unmigrated DB |
| `ModuleNotFoundError` | Wrong virtualenv / deps | Confirm the Web-tab virtualenv path; `pip install -r requirements.txt` |
| Changes not showing | Forgot to reload | Click **Reload** on the Web tab after every change |

---

## Notes & next steps
- **SQLite** is fine for low/moderate volume. If you outgrow it, PythonAnywhere includes a MySQL DB —
  ask and I'll add the `DATABASES` config + `mysqlclient` steps.
- **Backups:** your data lives in `db.sqlite3` and `media/` on PA's disk. Periodically download them
  (or `git`-exclude them, which they already are) — don't commit them to the repo.
- **Optional extra hardening:** to force HTTPS and enable HSTS, we can add `SECURE_SSL_REDIRECT` and
  `SECURE_HSTS_SECONDS` (the `manage.py check --deploy` warnings). Left off by default to avoid
  redirect surprises — say the word and I'll wire them up behind env flags.
