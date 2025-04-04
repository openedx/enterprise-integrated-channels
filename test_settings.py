"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from os.path import abspath, dirname, join


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


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

    'enterprise',
    'consent',

    'oauth2_provider',
)

LOCALE_PATHS = [
    root('channel_integrations', 'conf', 'locale'),
]

ROOT_URLCONF = 'channel_integrations.urls'

SECRET_KEY = 'insecure-secret-key'

MIDDLEWARE = (
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
)

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'APP_DIRS': False,
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

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
OAUTH_ID_TOKEN_EXPIRATION = 60 * 60  # in seconds

SITE_ID = 1

USE_TZ = True
TIME_ZONE = 'UTC'

INTEGRATED_CHANNELS_API_CHUNK_TRANSMISSION_LIMIT = {
    'SAP': 1,
}

# URL for the server that django client listens to by default.
TEST_SERVER = "http://testserver"
ALLOWED_HOSTS = ["testserver.enterprise"]
MEDIA_URL = "/"
