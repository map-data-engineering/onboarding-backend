"""
Django settings for the onboarding project.

Applicant intake + timed, shuffled knowledge-check quiz (DRF API).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-insecure-key-change-me-in-production"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"


def _csv_env(name, default):
    """Split a comma-separated env var, trimming blanks and stray whitespace.

    Hosts and origins are typed by hand into a WSGI file or an `export` line, and
    a value like `" host.example.com "` would otherwise be kept verbatim -- Django
    compares Host headers exactly, so the padded entry never matches and every
    request 400s with DisallowedHost.
    """
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


ALLOWED_HOSTS = _csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Required by Django for session-based POSTs (e.g. the admin login) over HTTPS.
CSRF_TRUSTED_ORIGINS = [
    # Internal spaces ("https:// host") are just as fatal as padding, and Django's
    # own check only validates the scheme -- so squash whitespace entirely.
    "".join(origin.split())
    for origin in _csv_env("DJANGO_CSRF_TRUSTED_ORIGINS", "")
]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    # Local
    "application",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves static files (incl. css/styles.css) in production so the layout
    # renders correctly even without a web-server static mapping.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "onboarding.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "onboarding.wsgi.application"
ASGI_APPLICATION = "onboarding.asgi.application"


# --- Database -----------------------------------------------------------------
# MySQL in production (PythonAnywhere), SQLite locally. Switch by setting
# DJANGO_DB_ENGINE=mysql; everything else is read from the environment so no
# credentials live in this file.
#
#   DJANGO_DB_ENGINE=mysql
#   DJANGO_DB_NAME=USER$onboarding
#   DJANGO_DB_USER=USER
#   DJANGO_DB_PASSWORD=...
#   DJANGO_DB_HOST=USER.mysql.pythonanywhere-services.com
#
# Requires the mysqlclient driver: pip install -r requirements-prod.txt
if os.environ.get("DJANGO_DB_ENGINE", "sqlite").lower() in ("mysql", "django.db.backends.mysql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DJANGO_DB_NAME", ""),
            "USER": os.environ.get("DJANGO_DB_USER", ""),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", ""),
            "PORT": os.environ.get("DJANGO_DB_PORT", "3306"),
            # Reuse connections, but for less time than PythonAnywhere's MySQL
            # idle timeout (300s) -- otherwise Django hands out dead sockets.
            "CONN_MAX_AGE": int(os.environ.get("DJANGO_DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {
                "charset": "utf8mb4",  # full Unicode, incl. emoji, in free-text answers
                # Fail loudly on truncation/bad dates instead of silently coercing.
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
# `collectstatic` gathers admin + app static files here. WhiteNoise serves them
# in production; you can optionally also map /static/ to this folder in the PA Web tab.
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- Production hardening (only active when DEBUG is off) ---------------------
# PythonAnywhere terminates HTTPS in front of the app, so trust its proxy header
# and only send cookies over HTTPS.
if not DEBUG:
    # Let WhiteNoise compress and cache-bust static files in production.
    STORAGES["staticfiles"]["BACKEND"] = (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # Token auth is used by the custom admin panel. There is NO global default
    # permission, so it stays AllowAny -- the applicant endpoints remain open and
    # only the /api/admin/ views opt in to IsAdminUser.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

CORS_ALLOWED_ORIGINS = [
    "https://spaat-onboardnig-portal-frontend.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://spaat-onboardnig-portal-frontend-.*\.vercel\.app$",
]
CORS_ALLOW_CREDENTIALS = False
