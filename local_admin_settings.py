"""Local development settings extending test_settings with admin URL routing."""

from test_settings import *  # noqa: F401,F403

ROOT_URLCONF = "local_admin_urls"
ALLOWED_HOSTS = ["*"]
