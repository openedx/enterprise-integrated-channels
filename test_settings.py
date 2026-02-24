"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

import os
import sys
from os.path import abspath, dirname, join

from celery import Celery

def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)

# Add mock_apps to the Python path at the beginning to ensure it's checked first
sys.path.insert(0, root('mock_apps'))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'default.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.sites',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',

    'channel_integrations.cornerstone',
    'channel_integrations.degreed2',
    'channel_integrations.canvas',
    'channel_integrations.blackboard',
    'channel_integrations.moodle',
    'channel_integrations.sap_success_factors',
    'channel_integrations.integrated_channel',
    'channel_integrations.xapi',

    'enterprise',
    'consent',

    'oauth2_provider',
    'edx_rbac',
    'social_django',
    'waffle',
)

LOCALE_PATHS = [
    root('channel_integrations', 'conf', 'locale'),
]

ROOT_URLCONF = 'channel_integrations.urls'

SECRET_KEY = 'insecure-secret-key'

MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'APP_DIRS': True,
    'DIRS': [
        root('mock_apps/templates'),
    ],
    'OPTIONS': {
        'context_processors': [
            'django.contrib.auth.context_processors.auth',  # this is required for admin
            'django.contrib.messages.context_processors.messages',  # this is required for admin
            'django.template.context_processors.request',   # this is required for admin
        ],
    },
}]
ENTERPRISE_SERVICE_WORKER_USERNAME = 'enterprise_worker'
ENTERPRISE_CATALOG_INTERNAL_ROOT_URL = "http://localhost:18160"


LMS_ROOT_URL = "http://lms.example.com"
LMS_INTERNAL_ROOT_URL = "http://localhost:8000"
LMS_ENROLLMENT_API_PATH = "/api/enrollment/v1/"

ENTERPRISE_ENROLLMENT_API_URL = LMS_INTERNAL_ROOT_URL + LMS_ENROLLMENT_API_PATH

ENTERPRISE_COURSE_ENROLLMENT_AUDIT_MODES = ['audit', 'honor']

# Keep AutoField to match edx-platform (not BigAutoField)
# edx-platform uses: DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
OAUTH_ID_TOKEN_EXPIRATION = 60 * 60  # in seconds

SITE_ID = 1

USE_TZ = True
TIME_ZONE = 'UTC'


#################################### CELERY ####################################

app = Celery('enterprise')
app.conf.task_protocol = 1
app.config_from_object('django.conf:settings')

CELERY_ALWAYS_EAGER = True

CLEAR_REQUEST_CACHE_ON_TASK_COMPLETION = False

##### END CELERY #####

JWT_AUTH = {
    'JWT_AUDIENCE': 'test-aud',
    'JWT_DECODE_HANDLER': 'edx_rest_framework_extensions.auth.jwt.decoder.jwt_decode_handler',
    'JWT_ISSUER': 'test-iss',
    'JWT_LEEWAY': 1,
    'JWT_SECRET_KEY': 'test-key',
    'JWT_SUPPORTED_VERSION': '1.0.0',
    'JWT_VERIFY_AUDIENCE': False,
    'JWT_VERIFY_EXPIRATION': True,

    # JWT_ISSUERS enables token decoding for multiple issuers (Note: This is not a native DRF-JWT field)
    # We use it to allow different values for the 'ISSUER' field, but keep the same SECRET_KEY and
    # AUDIENCE values across all issuers.
    'JWT_ISSUERS': [
        {
            'ISSUER': 'test-issuer-1',
            'SECRET_KEY': 'test-secret-key',
            'AUDIENCE': 'test-audience',
        },
        {
            'ISSUER': 'test-issuer-2',
            'SECRET_KEY': 'test-secret-key',
            'AUDIENCE': 'test-audience',
        }
    ],
}

USER_THROTTLE_RATE = '190/minute'
SERVICE_USER_THROTTLE_RATE = '200/minute'
SERVICE_USER_HIGH_THROTTLE_RATE = '200/minute'
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'URL_FORMAT_OVERRIDE': None,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'user': USER_THROTTLE_RATE,
        'service_user': SERVICE_USER_THROTTLE_RATE,
        'high_service_user': SERVICE_USER_HIGH_THROTTLE_RATE,
    },
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%SZ',
}

INTEGRATED_CHANNELS_API_CHUNK_TRANSMISSION_LIMIT = {
    'SAP': 1,
}

# URL for the server that django client listens to by default.
TEST_SERVER = "http://testserver"
ALLOWED_HOSTS = ["testserver.enterprise"]
MEDIA_URL = "/"

#################################### CACHES ####################################

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
        'TIMEOUT': 3600,
    }
}

#################################### SNOWFLAKE ####################################

# Snowflake Configuration for Learning Time (Test Environment)
# These values are mocked in tests - real values should come from environment
SNOWFLAKE_ACCOUNT = 'test-account.us-east-1'
SNOWFLAKE_WAREHOUSE = 'TEST_WH'
SNOWFLAKE_DATABASE = 'TEST'
SNOWFLAKE_SCHEMA = 'TEST_SCHEMA'
SNOWFLAKE_ROLE = 'TEST_ROLE'
SNOWFLAKE_SERVICE_USER = 'test_service_user'
SNOWFLAKE_SERVICE_USER_PASSWORD = 'test_password'  # In production, from secrets manager

#################################### PERCIPIO ####################################

# Percipio OAuth2 credentials.
PERCIPIO_CLIENT_ID = os.environ.get('PERCIPIO_CLIENT_ID', '')
PERCIPIO_CLIENT_SECRET = os.environ.get('PERCIPIO_CLIENT_SECRET', '')

# Token endpoint URLs by region. Override in environment-specific settings to
# point at staging/sandbox endpoints when testing end-to-end.
PERCIPIO_TOKEN_URLS = {
    'US': 'https://oauth2-provider.develop.squads-dev.com/oauth2-provider/token',
    'EU': 'https://euc1-prod-oauth2-provider.percipio.com/oauth2-provider/token',
    'OTHER': 'https://oauth2-provider.develop.squads-dev.com/oauth2-provider/token',
}

#################################### FEATURES ####################################

FEATURES = {
}

#################################### CELERY QUEUES ####################################

# Celery task routing configuration
CELERY_TASK_ROUTES = {
    'channel_integrations.integrated_channel.tasks.enrich_and_send_completion_webhook': {
        'queue': 'edx.lms.core.webhook_enrichment'
    },
    'channel_integrations.integrated_channel.tasks.process_webhook_queue': {
        'queue': 'edx.lms.enterprise.webhooks'
    },
}
