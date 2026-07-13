from dotenv import load_dotenv
from pathlib import Path
import os
import dj_database_url


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# ============================================================
# ENV HELPERS
# ============================================================

def env_bool(name, default=False):
    value = os.environ.get(name, str(default))
    return value.strip().lower() in ["1", "true", "yes", "on"]


def env_list(name, default=""):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-heartly-local-development-key-change-in-production",
)

DEBUG = env_bool("DJANGO_DEBUG", True)

DJANGO_ENV = os.environ.get("DJANGO_ENV", "local").strip().lower()

IS_PRODUCTION = DJANGO_ENV == "production"

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost",
)

CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000",
)


# ============================================================
# PRODUCTION SAFETY CHECKS
# ============================================================

if IS_PRODUCTION and DEBUG:
    raise RuntimeError(
        "DJANGO_ENV is production but DJANGO_DEBUG is True. "
        "Set DJANGO_DEBUG=False in production."
    )

if not DEBUG:
    if SECRET_KEY.startswith("django-insecure"):
        raise RuntimeError(
            "DEBUG is False but DJANGO_SECRET_KEY is still using the insecure local default."
        )

    if ALLOWED_HOSTS == ["127.0.0.1", "localhost"]:
        raise RuntimeError(
            "DEBUG is False but DJANGO_ALLOWED_HOSTS is still local-only. "
            "Set your real production domain."
        )

    if CSRF_TRUSTED_ORIGINS == ["http://127.0.0.1:8000", "http://localhost:8000"]:
        raise RuntimeError(
            "DEBUG is False but DJANGO_CSRF_TRUSTED_ORIGINS is still local-only. "
            "Set your production origin with https://."
        )


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [
    # Keep Daphne first so its ASGI-aware runserver command is used.
    "daphne",

    # Django apps must appear before cloudinary_storage so Django's
    # normal collectstatic command remains active.
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # Cloudinary is used for uploaded media, not static files.
    "cloudinary_storage",
    "cloudinary",

    # Third-party apps
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "rest_framework",
    "channels",
    "corsheaders",
    "django_ratelimit",
    "django_extensions",
    "storages",

    # Heartly apps
    "accounts.apps.AccountsConfig",
    "profiles",
    "matches",
    "chat",
    "ai_features",
    "feed",
   
    "notifications.apps.NotificationsConfig",
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    # CORS should stay before CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Required by django-allauth
    "allauth.account.middleware.AccountMiddleware",
]


# ============================================================
# URL / WSGI / ASGI
# ============================================================

ROOT_URLCONF = "heartly.urls"

WSGI_APPLICATION = "heartly.wsgi.application"

ASGI_APPLICATION = "heartly.asgi.application"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates",
        ],

        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",

                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",

                # Heartly global badges
                "notifications.context_processors.unread_notifications",
                "chat.context_processors.unread_chat_messages",
            ],
        },
    },
]


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ============================================================
# CUSTOM USER MODEL
# ============================================================

AUTH_USER_MODEL = "accounts.CustomUser"


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Africa/Kampala")

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Optional: only keep this if you actually have a project-level static folder.
STATICFILES_DIRS = [

    BASE_DIR / "static",
] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ============================================================
# CLOUDINARY SETTINGS
# ============================================================

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    "API_KEY": os.environ.get("CLOUDINARY_API_KEY", ""),
    "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", ""),
}

MEDIA_STORAGE_BACKEND = os.environ.get("MEDIA_STORAGE_BACKEND", "cloudinary").strip().lower()

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if MEDIA_STORAGE_BACKEND == "cloudinary":
    STORAGES["default"] = {
        "BACKEND": "heartly.storage_backends.AutoResourceCloudinaryStorage",
    }

elif MEDIA_STORAGE_BACKEND == "s3":
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.environ.get("AWS_ACCESS_KEY_ID"),
            "secret_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
            "bucket_name": os.environ.get("AWS_STORAGE_BUCKET_NAME"),
            "region_name": os.environ.get("AWS_S3_REGION_NAME", ""),
            "endpoint_url": os.environ.get("AWS_S3_ENDPOINT_URL", "") or None,
            "custom_domain": os.environ.get("AWS_S3_CUSTOM_DOMAIN", "") or None,
            "querystring_auth": env_bool("AWS_QUERYSTRING_AUTH", False),
            "file_overwrite": False,
        },
    }

elif MEDIA_STORAGE_BACKEND != "local":
    raise RuntimeError("Invalid MEDIA_STORAGE_BACKEND. Use one of: local, cloudinary, s3.")

DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE", 70 * 1024 * 1024))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE", 70 * 1024 * 1024))

HEARTLY_MAX_IMAGE_UPLOAD_SIZE = int(os.environ.get("HEARTLY_MAX_IMAGE_UPLOAD_SIZE", 15 * 1024 * 1024))
HEARTLY_MAX_VIDEO_UPLOAD_SIZE = int(os.environ.get("HEARTLY_MAX_VIDEO_UPLOAD_SIZE", 60 * 1024 * 1024))



# ============================================================
# DEFAULT PRIMARY KEY FIELD
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# DJANGO SITES FRAMEWORK
# ============================================================

SITE_ID = int(os.environ.get("DJANGO_SITE_ID", "1"))


# ============================================================
# AUTHENTICATION / ALLAUTH
# ============================================================

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/post-login-redirect/"
LOGOUT_REDIRECT_URL = "/"

ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_SIGNUP_REDIRECT_URL = "/post-login-redirect/"

# New allauth-style settings
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = [
    "email*",
    "password1*",
    "password2*",
]

# Heartly custom signup fields are handled here.
ACCOUNT_SIGNUP_FORM_CLASS = "accounts.forms.CustomSignupForm"

ACCOUNT_EMAIL_VERIFICATION = os.environ.get(
    "ACCOUNT_EMAIL_VERIFICATION",
    "optional",
)

ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_SESSION_REMEMBER = True

# ============================================================
# EMAIL
# ============================================================

EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)

DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL",
    "Heartly <noreply@heartly.local>",
)


# ============================================================
# CHANNELS / WEBSOCKETS
# ============================================================

REDIS_URL = os.environ.get("REDIS_URL", "").strip()

USE_REDIS_CHANNEL_LAYER = env_bool(
    "USE_REDIS_CHANNEL_LAYER",
    bool(REDIS_URL) and IS_PRODUCTION,
)

if USE_REDIS_CHANNEL_LAYER:
    if not REDIS_URL:
        raise RuntimeError(
            "USE_REDIS_CHANNEL_LAYER=True but REDIS_URL is missing."
        )

    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [
                    {
                        "address": REDIS_URL,
                        "socket_connect_timeout": 10,
                        "socket_timeout": 30,
                        "retry_on_timeout": True,
                        "health_check_interval": 30,
                    }
                ],
                "capacity": int(os.environ.get("CHANNEL_LAYER_CAPACITY", "1500")),
                "expiry": int(os.environ.get("CHANNEL_LAYER_EXPIRY", "60")),
                "group_expiry": int(os.environ.get("CHANNEL_LAYER_GROUP_EXPIRY", "86400")),
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# ============================================================
# REST FRAMEWORK
# ============================================================

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}


# ============================================================
# CORS
# ============================================================

CORS_ALLOWED_ORIGINS = env_list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000",
)

CORS_ALLOW_CREDENTIALS = True


# ============================================================
# CACHE
# ============================================================

CACHES = {
    "default": {
        "BACKEND": os.environ.get(
            "DJANGO_CACHE_BACKEND",
            "django.core.cache.backends.locmem.LocMemCache",
        ),
        "LOCATION": os.environ.get(
            "DJANGO_CACHE_LOCATION",
            "heartly-local-cache",
        ),
    }
}


# ============================================================
# DJANGO-RATELIMIT
# ============================================================

RATELIMIT_ENABLE = env_bool("RATELIMIT_ENABLE", True)

RATELIMIT_USE_CACHE = "default"

SILENCED_SYSTEM_CHECKS = [
    "django_ratelimit.E003",
    "django_ratelimit.W001",
]


# ============================================================
# GROQ AI
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")


# ============================================================
# LOCAL / PRODUCTION SECURITY
# ============================================================

if DEBUG:
    INTERNAL_IPS = [
        "127.0.0.1",
        "localhost",
    ]
else:
    SECURE_CONTENT_TYPE_NOSNIFF = True

    X_FRAME_OPTIONS = "DENY"

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = False

    SECURE_SSL_REDIRECT = env_bool(
        "DJANGO_SECURE_SSL_REDIRECT",
        True,
    )

    if env_bool("DJANGO_USE_X_FORWARDED_PROTO", False):
        SECURE_PROXY_SSL_HEADER = (
            "HTTP_X_FORWARDED_PROTO",
            "https",
        )

    SECURE_HSTS_SECONDS = int(
        os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "3600")
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
        False,
    )

    SECURE_HSTS_PRELOAD = env_bool(
        "DJANGO_SECURE_HSTS_PRELOAD",
        False,
    )