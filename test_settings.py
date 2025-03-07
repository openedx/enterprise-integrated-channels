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

    'channel_integrations.integrated_channel.apps.IntegratedChannelConfig',
    'channel_integrations.cornerstone',
    'channel_integrations.degreed2',
    'channel_integrations.canvas',
    'channel_integrations.blackboard',
    'channel_integrations.moodle',
    'channel_integrations.sap_success_factors',

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


LMS_ROOT_URL = "http://lms.example.com"
LMS_INTERNAL_ROOT_URL = "http://localhost:8000"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SITE_ID = 1

