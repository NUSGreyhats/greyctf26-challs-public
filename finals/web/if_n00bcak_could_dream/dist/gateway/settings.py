import os


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "different-value-on-remote")
DEBUG = os.environ.get("DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]
ROOT_URLCONF = "gateway.urls"

INSTALLED_APPS = []

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
]

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:5000")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
