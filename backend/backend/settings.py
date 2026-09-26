import os
from pathlib import Path
import dotenv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
dotenv.load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-cloudwise-default-key-2026')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    # Local app
    'api.apps.ApiConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# Database Setup (SQLite by default, PostgreSQL if DATABASE_URL is defined)
# Tests always use local SQLite regardless of DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL')
_TESTING = os.getenv('DJANGO_TESTING', '').lower() in ('1', 'true') or 'test' in os.sys.argv

if DATABASE_URL and not _TESTING:
    DATABASES = {
        'default': dj_database_url.config(default=DATABASE_URL)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'api.CustomUser'

# Password validation
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

# REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
}

# SimpleJWT Settings
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'AUTH_HEADER_TYPES': ('Bearer', 'cw_token'),
}

# ---------------------------------------------------------------------------
# GitHub OAuth configuration. Keep the client secret server-side only.
#
# Every value comes from the environment (see backend/.env.example). Nothing
# about a GitHub account, token, repository or CloudWise user id is hardcoded.
#
# GITHUB_REDIRECT_URI must EXACTLY match the "Authorization callback URL"
# configured on the GitHub OAuth App (GitHub rejects any other value with
# `redirect_uri_mismatch`). For local development the canonical value is:
#     http://localhost:8000/api/github/oauth/callback
# ---------------------------------------------------------------------------
GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET', '')
GITHUB_REDIRECT_URI = os.getenv(
    'GITHUB_REDIRECT_URI',
    'http://localhost:8000/api/github/oauth/callback'
).strip()
# Space separated OAuth scopes requested from GitHub.
#   repo         -> read/write private + public repositories
#   workflow     -> push files into .github/workflows
GITHUB_OAUTH_SCOPES = os.getenv('GITHUB_OAUTH_SCOPES', 'repo workflow').strip() or 'repo workflow'
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
# Symmetric key used to encrypt stored GitHub access tokens.
# Falls back to SECRET_KEY when unset (see api.services.token_encryption).
GITHUB_TOKEN_ENCRYPTION_KEY = os.getenv('GITHUB_TOKEN_ENCRYPTION_KEY', '')
# OAuth state (CSRF) validity window, in seconds.
GITHUB_OAUTH_STATE_MAX_AGE = int(os.getenv('GITHUB_OAUTH_STATE_MAX_AGE', '600'))

# Retired deployment targets (Vercel, Render) are no longer supported.
# CloudWise deploys to AWS EC2 only; their credentials are intentionally
# not read anywhere in the application.

# When True the AWS deployment pipeline runs synchronously inside the
# request thread instead of on a background thread. The test suite sets
# this so deployment outcomes are deterministic; production leaves it
# False so POST /api/deploy returns immediately and the client polls
# GET /api/deployments/<id>/status.
DEPLOYMENT_RUN_INLINE = os.getenv('DEPLOYMENT_RUN_INLINE', '').lower() in ('1', 'true', 'yes')

# ------------------------------------------------------------------
# AWS account connection (Part 3) — IAM role + STS temporary credentials
#
# CloudWise platform deployer credentials (server-side only). Used ONLY to
# call sts:AssumeRole into the USER's AWS account. Users never provide
# permanent AWS access keys; a connection stores only a Role ARN + External
# ID, and short-lived STS credentials are obtained per operation in memory.
# When unset, boto3's default credential chain (env vars / instance role)
# is used.
# ------------------------------------------------------------------
AWS_DEPLOYER_ACCESS_KEY_ID = os.getenv('AWS_DEPLOYER_ACCESS_KEY_ID', '')
AWS_DEPLOYER_SECRET_ACCESS_KEY = os.getenv('AWS_DEPLOYER_SECRET_ACCESS_KEY', '')
AWS_DEPLOYER_REGION = os.getenv('AWS_DEPLOYER_REGION', 'us-east-1')
AWS_ROLE_SESSION_NAME = os.getenv('AWS_ROLE_SESSION_NAME', 'cloudwise-deploy')
AWS_ROLE_DURATION_SECONDS = int(os.getenv('AWS_ROLE_DURATION_SECONDS', '3600'))
# AWS account id that appears in the user's role trust policy.
# Empty -> auto-detected from the deployer credentials via sts:GetCallerIdentity.
AWS_TRUSTED_ACCOUNT_ID = os.getenv('AWS_TRUSTED_ACCOUNT_ID', '')

# EC2 provisioning configuration (configurable — never hardcoded in the provider)
AWS_DEFAULT_REGION = os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')
AWS_EC2_INSTANCE_TYPE = os.getenv('AWS_EC2_INSTANCE_TYPE', 't3.micro')
AWS_EC2_AMI_ID = os.getenv('AWS_EC2_AMI_ID', '')
AWS_EC2_AMI_SSM_PARAMETER = os.getenv(
    'AWS_EC2_AMI_SSM_PARAMETER',
    '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64',
)
AWS_EC2_KEY_NAME = os.getenv('AWS_EC2_KEY_NAME', '')
AWS_EC2_INSTANCE_PROFILE = os.getenv('AWS_EC2_INSTANCE_PROFILE', '')
AWS_EC2_ROOT_VOLUME_GB = int(os.getenv('AWS_EC2_ROOT_VOLUME_GB', '30'))
AWS_EC2_WAIT_FOR_RUNNING = os.getenv('AWS_EC2_WAIT_FOR_RUNNING', 'true').lower() in ('1', 'true', 't')
AWS_EC2_WAIT_TIMEOUT_SECONDS = int(os.getenv('AWS_EC2_WAIT_TIMEOUT_SECONDS', '300'))

# Security group — only these ports are ever opened publicly (80/443/22).
# Application ports (3000/8000/8080...) are intentionally NOT exposed.
AWS_SECURITY_GROUP_NAME = os.getenv('AWS_SECURITY_GROUP_NAME', 'cloudwise-sg')
AWS_SECURITY_GROUP_PORTS = [
    int(p.strip())
    for p in os.getenv('AWS_SECURITY_GROUP_PORTS', '80,443,22').split(',')
    if p.strip()
]
AWS_SECURITY_GROUP_HTTP_CIDR = os.getenv('AWS_SECURITY_GROUP_HTTP_CIDR', '0.0.0.0/0')
AWS_SECURITY_GROUP_SSH_CIDR = os.getenv('AWS_SECURITY_GROUP_SSH_CIDR', '0.0.0.0/0')

# Install Docker + Docker Compose on first boot via EC2 user data
AWS_INSTALL_DOCKER = os.getenv('AWS_INSTALL_DOCKER', 'true').lower() in ('1', 'true', 't')

# Container deployment via SSM RunShellScript (Part 4)
# Remote project root on each EC2 instance (per-project isolation).
AWS_DEPLOY_ROOT = os.getenv('AWS_DEPLOY_ROOT', '/opt/cloudwise/projects')
# SSM command polling / timeout (seconds)
AWS_SSM_POLL_SECONDS = int(os.getenv('AWS_SSM_POLL_SECONDS', '3'))
AWS_SSM_TIMEOUT_SECONDS = int(os.getenv('AWS_SSM_TIMEOUT_SECONDS', '600'))
# Post-deploy HTTP health check against the live URL
AWS_HEALTH_CHECK_RETRIES = int(os.getenv('AWS_HEALTH_CHECK_RETRIES', '30'))
AWS_HEALTH_CHECK_INTERVAL_SECONDS = float(os.getenv('AWS_HEALTH_CHECK_INTERVAL_SECONDS', '2'))
AWS_HEALTH_CHECK_TIMEOUT_SECONDS = float(os.getenv('AWS_HEALTH_CHECK_TIMEOUT_SECONDS', '10'))
# URL schemes accepted for DATABASE_URL / MONGO_URI style values
AWS_ALLOWED_DB_URL_SCHEMES = (
    'postgres://', 'postgresql://', 'mysql://', 'mariadb://',
    'mongodb://', 'mongodb+srv://', 'redis://', 'rediss://',
    'sqlserver://', 'mysql2://',
)

# CloudWise repository analysis limits (platform limits, configurable via env).
# Enforced by api.services.github_repository_service when scanning repositories.
MAX_REPOSITORY_SIZE_MB = int(os.getenv('MAX_REPOSITORY_SIZE_MB', '500'))
MAX_FILES = int(os.getenv('MAX_FILES', '10000'))
MAX_SINGLE_FILE_MB = int(os.getenv('MAX_SINGLE_FILE_MB', '10'))
MAX_ANALYSIS_TIME_MINUTES = int(os.getenv('MAX_ANALYSIS_TIME_MINUTES', '5'))

# ---------------------------------------------------------------------------
# CORS / CSRF
#
# In local development the Vite dev server proxies /api/* to Django, so the
# browser talks to a single origin and no CORS headers are needed. When the
# React app is served from a *different* origin (production build, second
# dev machine, ...) its origin must be listed explicitly.
#
# CORS_ALLOW_ALL_ORIGINS=True together with CORS_ALLOW_CREDENTIALS=True is
# rejected by browsers (the spec forbids `Access-Control-Allow-Origin: *` on
# credentialed responses), so the default is an explicit origin whitelist.
# ---------------------------------------------------------------------------
DEFAULT_CORS_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]
_env_cors_origins = [o.strip() for o in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if o.strip()]
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(
    _env_cors_origins or ([FRONTEND_URL] if FRONTEND_URL else []) + DEFAULT_CORS_ORIGINS
))
CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'false').lower() in ('true', '1', 't')
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-user-role',
    'x-user-id',
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
