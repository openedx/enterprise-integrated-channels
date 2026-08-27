"""
URL definitions for TPA Org Allowlist API.
"""
from rest_framework import routers
from .views import TpaOrgAllowlistViewSet

app_name = 'tpa_org_allowlist'
router = routers.DefaultRouter()
router.register(r'', TpaOrgAllowlistViewSet, basename='tpa-org-allowlist')
urlpatterns = router.urls
