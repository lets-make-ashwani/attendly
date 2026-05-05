import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')


# SECURITY
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-wf)!z^4o#_wio@7pg$j0*=4i#i(et11+9puwmz-4km^3%g83e2')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

if not DEBUG and SECRET_KEY == 'django-insecure-wf)!z^4o#_wio@7pg$j0*=4i#i(et11+9puwmz-4km^3%g83e2':
    raise ValueError("CRITICAL: SECRET_KEY must be configured securely in production!")

# Ensure secure host checking in production
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost,attendly-app.onrender.com').split(',')


# APPLICATIONS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary_storage',
    'cloudinary',

    'accounts',
    'attendance',
]


# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'attendly.urls'


# TEMPLATES (✅ FIXED)
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],   # ✅ important
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'attendly.wsgi.application'


# DATABASE
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# If DATABASE_URL is set (like on Render), use that instead of SQLite
# Forces SSL in production to satisfy Render's PostgreSQL security requirements
db_from_env = dj_database_url.config(conn_max_age=600, ssl_require=not DEBUG)
if db_from_env:
    DATABASES['default'].update(db_from_env)


# PASSWORD VALIDATION
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# INTERNATIONALIZATION (✅ FIXED)
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True


# STATIC FILES (✅ FIXED)
STATIC_URL = '/static/'

# Safely load root static dir only if it exists, preventing collectstatic crashes
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'

# 🛡️ Dummy variable to prevent legacy third-party packages from crashing in Django 5.1+
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# 🛡️ Prevents 500 Server Errors if an HTML template references a missing static file
WHITENOISE_MANIFEST_STRICT = False

# CUSTOM USER MODEL
AUTH_USER_MODEL = 'accounts.User'


# PRODUCTION SECURITY SETTINGS
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # 🛡️ Force fresh secure cookies & trust Render's load balancer Host headers
    CSRF_COOKIE_NAME = "attendly_prod_csrftoken"
    SESSION_COOKIE_NAME = "attendly_prod_sessionid"
    USE_X_FORWARDED_HOST = True
    
    # 🛡️ Ensure strict browsers attach cookies correctly across Render's internal load balancers
    CSRF_COOKIE_DOMAIN = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'attendly-app.onrender.com')

    # CLOUDINARY CONFIG FOR MEDIA FILES (Profile Pictures)
    CLOUDINARY_STORAGE = {
        'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME', 'missing_keys'),
        'API_KEY': os.environ.get('CLOUDINARY_API_KEY', 'missing_keys'),
        'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET', 'missing_keys'),
    }
    
    # 🛡️ Modern Django (4.2+) Storage Configuration
    STORAGES = {
        "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# REQUIRED FOR HTTPS ON RENDER TO PREVENT LOGIN/FORM 403 ERRORS
CSRF_TRUSTED_ORIGINS = [
    'https://attendly-app.onrender.com',
    'https://*.onrender.com', 
    'https://*.ngrok-free.app',
    'http://localhost:8000',
    'http://127.0.0.1:8000'
]

# GEOFENCING SETTINGS
# Define your office coordinates here (Default is New Delhi as an example)
OFFICE_LATITUDE = 28.6139
OFFICE_LONGITUDE = 77.2090

# EMAIL SETTINGS (Output emails to the terminal for local testing)
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # In production (Render), use a real SMTP server like Gmail
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER