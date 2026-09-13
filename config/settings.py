"""
RentFlow — Django settings.
Runs identically as a web app (dev server) and inside the desktop shell
(desktop.py + waitress + pywebview).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "RENTFLOW_SECRET_KEY",
    "rentflow-local-desktop-key-change-me-in-production",
)

DEBUG = os.environ.get("RENTFLOW_DEBUG", "1") == "1"

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "https://*.e2b.app",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # RentFlow apps
    "accounts",
    "properties",
    "payments",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

X_FRAME_OPTIONS = "ALLOWALL"  # allows the desktop webview / preview iframe

# Cookie policy:
#  * Web/preview mode runs behind an HTTPS proxy inside an iframe — browsers
#    only send cookies there with SameSite=None; Secure.
#  * Desktop mode (RENTFLOW_DESKTOP=1, plain http://127.0.0.1) cannot use
#    Secure cookies, so it falls back to the standard Lax policy.
if os.environ.get("RENTFLOW_DESKTOP") == "1":
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
else:
    SESSION_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("RENTFLOW_DB", BASE_DIR / "rentflow.sqlite3"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Email — defaults to console backend for local/desktop use.
# Set the RENTFLOW_SMTP_* environment variables to send real email via Gmail.
# ---------------------------------------------------------------------------
if os.environ.get("RENTFLOW_SMTP_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["RENTFLOW_SMTP_HOST"]
    EMAIL_PORT = int(os.environ.get("RENTFLOW_SMTP_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("RENTFLOW_SMTP_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("RENTFLOW_SMTP_PASSWORD", "")
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get("RENTFLOW_FROM_EMAIL", "billing@rentflow.local")

# Company block printed on invoices
RENTFLOW_COMPANY = {
    "name": "RentFlow Property Management",
    "address": "House 12, Road 4, Gulshan-2, Dhaka 1212",
    "phone": "+880 1700 000000",
    "email": "billing@rentflow.local",
    "bank": "City Bank Ltd. — A/C 1401-2233-4455 (RentFlow PM)",
}

# Rent for month M is payable from the 1st of M+1 and due by this day of M+1.
RENT_DUE_DAY = 20

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
    },
    "handlers": {
        "file": {
            "class": "logging.FileHandler",
            "filename": LOGS_DIR / "rentflow.log",
            "formatter": "simple",
        },
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "rentflow": {"handlers": ["file", "console"], "level": "INFO"},
    },
}
