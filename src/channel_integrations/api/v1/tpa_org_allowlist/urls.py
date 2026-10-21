"""
URL definitions for TPA Org Allowlist API.
"""
from rest_framework import routers
from .views import TpaOrgAllowlistViewSet

app_name = 'tpa_org_allowlist'
router = routers.SimpleRouter()
# Make the trailing slash optional. Otherwise Django's APPEND_SLASH answers a POST without it
# with a 301, which HTTP clients follow as a GET: the caller gets a 200 and nothing is created.
router.trailing_slash = '/?'
router.register(r'tpa-org-allowlist', TpaOrgAllowlistViewSet, basename='tpa-org-allowlist')
urlpatterns = router.urls
